import json
from datetime import UTC, date, datetime
from decimal import Decimal
from time import perf_counter

import httpx
from langgraph.types import Command, Overwrite
from sqlalchemy import select, text

from app.agents.graph import AgentServices, build_enterprise_graph
from app.agents.runtime import RuntimeContainer
from app.agents.state import SupplyMindState
from app.core.config import get_settings
from app.core.sql_guard import SQLGuardError, validate_read_only_sql
from app.db import SessionLocal, set_tenant_context
from app.mcp_runtime.client import MCPClientManager, MCPToolError
from app.mcp_runtime.security import issue_tool_context
from app.memory.service import MemoryPolicyError, MemoryService
from app.models import (
    AgentApproval,
    AgentStep,
    AnalysisRun,
    ConversationMessage,
    DataSource,
    KnowledgeBase,
    Membership,
    Report,
)
from app.observability import (
    AGENT_FALLBACKS,
    AGENT_RUNS,
    AGENT_SUBAGENT_DURATION,
    MODEL_TOKENS,
    configure_telemetry,
    genai_span,
)
from app.schemas import Principal
from app.services.events import append_event
from app.services.llm import ModelResponseError, OpenAICompatibleClient
from app.services.reports import render_markdown


class AnalysisCancelled(RuntimeError):
    """Cooperative stop: a durable cancellation must never become a retry."""


def normalize_value(value):
    if isinstance(value, str):
        # Some legacy MySQL connections returned UTF-8 bytes decoded as Latin-1.
        # Repair only strings that round-trip safely, leaving ordinary Unicode intact.
        try:
            repaired = value.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            return value
        return repaired if any(marker in value for marker in ("Ã", "Â", "ä¸", "å·", "æ")) else value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _root_error_message(exc: BaseException) -> str:
    if isinstance(exc, BaseExceptionGroup):
        for nested in exc.exceptions:
            message = _root_error_message(nested)
            if message:
                return message
    return str(exc)


class EnterpriseAnalysisExecutor:
    def __init__(self, client: OpenAICompatibleClient | None = None) -> None:
        self.client = client or OpenAICompatibleClient()
        self.mcp = MCPClientManager()

    async def _emit(self, run_id: str, tenant_id: str, event_type: str, payload: dict) -> None:
        async with SessionLocal() as session:
            await set_tenant_context(session, tenant_id)
            run = await session.scalar(
                select(AnalysisRun).where(
                    AnalysisRun.id == run_id, AnalysisRun.tenant_id == tenant_id
                )
            )
            if run:
                if run.status == "cancelled":
                    raise AnalysisCancelled("Analysis was cancelled")
                await append_event(session, run, event_type, payload)

    async def execute(self, run_id: str, *, retry_pending: bool = False) -> None:
        # Outbox is at-least-once. Hold a per-run, transaction-scoped advisory
        # lock for the entire attempt; PostgreSQL releases it on worker death.
        async with SessionLocal() as lease:
            if lease.bind and lease.bind.dialect.name == "postgresql":
                claimed = await lease.scalar(
                    text("SELECT pg_try_advisory_xact_lock(hashtextextended(:run_id, 0))"),
                    {"run_id": run_id},
                )
                if not claimed:
                    return
                conversation_id = await lease.scalar(select(AnalysisRun.conversation_id).where(
                    AnalysisRun.id == run_id,
                ))
                if conversation_id:
                    # Different runs share a conversation checkpoint namespace.
                    # Serialize them before either can read or update its state.
                    await lease.execute(
                        text("SELECT pg_advisory_xact_lock(hashtextextended(:thread, 1))"),
                        {"thread": conversation_id},
                    )
            await self._execute(run_id, retry_pending=retry_pending)

    async def _execute(self, run_id: str, *, retry_pending: bool = False) -> None:
        configure_telemetry("supplymind-worker")
        async with SessionLocal() as session:
            run = await session.scalar(select(AnalysisRun).where(AnalysisRun.id == run_id))
            if not run or run.status not in {"queued", "running"}:
                return
            await set_tenant_context(session, run.tenant_id)
            run.status = "running"
            run.started_at = run.started_at or datetime.now(UTC)
            run.attempts += 1
            from app.models import Conversation

            conversation = await session.scalar(
                select(Conversation).where(Conversation.id == run.conversation_id)
            )
            if not conversation:
                run.status = "failed"
                run.error_message = "Conversation not found"
                await session.commit()
                return
            membership = await session.scalar(
                select(Membership).where(
                    Membership.organization_id == run.tenant_id,
                    Membership.user_id == conversation.created_by,
                    Membership.is_active.is_(True),
                )
            )
            if not membership:
                run.status = "failed"
                run.error_message = "Analysis owner has no active organization membership"
                await session.commit()
                return
            if membership.role not in {"analyst", "org_admin", "platform_admin"}:
                run.status = "failed"
                run.error_message = "Analysis owner no longer has analysis permission"
                await append_event(session, run, "failed", {"reason": run.error_message})
                return
            principal = Principal(
                user_id=conversation.created_by,
                tenant_id=run.tenant_id,
                role=membership.role,
            )
            source = await session.scalar(select(DataSource).where(
                DataSource.id == run.data_source_id,
                DataSource.tenant_id == run.tenant_id,
                DataSource.status == "active",
            ))
            knowledge_base = await session.scalar(select(KnowledgeBase).where(
                KnowledgeBase.id == run.knowledge_base_id,
                KnowledgeBase.tenant_id == run.tenant_id,
                KnowledgeBase.is_archived.is_(False),
            ))
            if source is None or knowledge_base is None:
                run.status = "failed"
                run.error_message = "Analysis resources are no longer available or authorized"
                await append_event(session, run, "failed", {"reason": run.error_message})
                return
            allowed_tables = set(source.allowed_tables)
            run.checkpoint_thread_id = f"{run.tenant_id}:{principal.user_id}:{run.conversation_id}"
            await session.commit()

        await self._emit(
            run_id,
            principal.tenant_id,
            "step_started",
            {"step": "context_loader", "message": "正在恢复会话与长期记忆"},
        )
        memories: list[dict] = []
        async with SessionLocal() as session:
            await set_tenant_context(session, principal.tenant_id)
            memory_service = MemoryService()
            if await memory_service.enabled(session, principal.tenant_id, principal.user_id):
                memories = [
                    {
                        "id": item.id,
                        "category": item.category,
                        "key": item.memory_key,
                        "content": item.content,
                    }
                    for item in await memory_service.list(
                        session, principal.tenant_id, principal.user_id
                    )
                ]
        await self._emit(
            run_id,
            principal.tenant_id,
            "memory_loaded",
            {"count": len(memories), "namespace": "tenant/user"},
        )

        async def route(question: str):
            try:
                selected, confidence = await self.client.route_question(question)
            except (ModelResponseError, RuntimeError, httpx.HTTPError):
                selected, confidence = "hybrid", 0.5
                AGENT_FALLBACKS.labels("router", "hybrid").inc()
                await self._emit(
                    run_id,
                    principal.tenant_id,
                    "degraded",
                    {"stage": "router", "fallback": "hybrid"},
                )
            await self._emit(
                run_id,
                principal.tenant_id,
                "route_selected",
                {"route": selected, "confidence": confidence},
            )
            return selected, confidence

        async def run_subagent(name: str, state: SupplyMindState) -> dict:
            started = perf_counter()
            await self._emit(
                run_id,
                principal.tenant_id,
                "subagent_started",
                {"agent": name},
            )
            with genai_span("agent.subagent", {"gen_ai.agent.name": name}):
                if name == "data_analysis":
                    result = await self._run_data_subagent(run_id, principal, state)
                elif name == "knowledge_research":
                    result = await self._run_knowledge_subagent(run_id, principal, state)
                else:
                    result = {"error": "unsupported_subagent"}
            subagent_status = "completed" if "error" not in result else "failed"
            AGENT_SUBAGENT_DURATION.labels(name, subagent_status).observe(
                perf_counter() - started
            )
            await self._emit(
                run_id,
                principal.tenant_id,
                "subagent_completed",
                {"agent": name, "status": subagent_status},
            )
            return result

        async def synthesize(state: SupplyMindState) -> dict:
            data = next(
                (
                    item
                    for item in state.get("subagent_results", [])
                    if item["agent"] == "data_analysis"
                ),
                {},
            )
            knowledge = next(
                (
                    item
                    for item in state.get("subagent_results", [])
                    if item["agent"] == "knowledge_research"
                ),
                {},
            )
            rows = data.get("rows", [])
            citations = knowledge.get("citations", [])
            answer_plan = await self.client.answer_question(
                state["question"],
                rows,
                citations,
                [item["content"] for item in memories],
                data.get("planner_insight", ""),
            )
            prompt = (
                "请基于以下已验证证据，用中文直接回答供应链问题。不得补充证据之外的事实。\n"
                f"问题：{state['question']}\n"
                f"数据：{json.dumps(rows[:50], ensure_ascii=False, default=str)}\n"
                f"知识依据：{json.dumps(citations[:8], ensure_ascii=False, default=str)}"
            )
            streamed = ""
            buffer = ""
            try:
                async for token in self.client.stream_text(prompt):
                    streamed += token
                    buffer += token
                    if len(buffer) >= 40:
                        await self._emit(
                            run_id,
                            principal.tenant_id,
                            "token",
                            {"text": buffer},
                        )
                        buffer = ""
                if buffer:
                    await self._emit(run_id, principal.tenant_id, "token", {"text": buffer})
            except (ModelResponseError, RuntimeError, httpx.HTTPError):
                streamed = answer_plan.direct_answer
                AGENT_FALLBACKS.labels("token_stream", "structured_answer").inc()
                await self._emit(
                    run_id,
                    principal.tenant_id,
                    "degraded",
                    {"stage": "token_stream", "fallback": "structured_answer"},
                )
            payload = answer_plan.model_dump()
            payload["direct_answer"] = streamed.strip() or answer_plan.direct_answer
            model_name = (
                get_settings().ai_answer_model or get_settings().chat_model or "unknown"
            )
            MODEL_TOKENS.labels(model_name, "output").inc(
                max(1, len(payload["direct_answer"]) // 4)
            )
            payload["rows"] = rows
            payload["citations"] = citations
            payload["sql"] = data.get("sql")
            payload["chart"] = data.get("chart", {"type": "table"})
            return payload

        async def verify(state: SupplyMindState):
            answer = state.get("answer") or {}
            if not answer.get("direct_answer"):
                return False, "答案缺少直接回答", "synthesize"
            if not answer.get("rows") and not answer.get("citations"):
                return False, "没有可验证证据", "synthesize"
            return True, None, None

        local_runtime = RuntimeContainer()
        try:
            await local_runtime.start()
            graph = build_enterprise_graph(
                AgentServices(
                    route=route,
                    run_subagent=run_subagent,
                    synthesize=synthesize,
                    verify=verify,
                ),
                checkpointer=local_runtime.checkpointer,
                store=local_runtime.store,
            )
            with genai_span(
                "agent.graph",
                {
                    "gen_ai.operation.name": "invoke_agent",
                    "gen_ai.agent.name": "supplymind-root",
                    "supplymind.graph.version": run.graph_version,
                    "supplymind.run.id": run_id,
                    "supplymind.checkpoint_thread_id": run.checkpoint_thread_id,
                },
            ) as graph_span:
                span_context = graph_span.get_span_context()
                if span_context.is_valid:
                    await self._emit(
                        run_id,
                        principal.tenant_id,
                        "trace_started",
                        {
                            "trace_id": f"{span_context.trace_id:032x}",
                            "checkpoint_thread_id": run.checkpoint_thread_id,
                        },
                    )
                invocation = {
                        "tenant_id": principal.tenant_id,
                        "user_id": principal.user_id,
                        "role": principal.role,
                        "run_id": run_id,
                        "conversation_id": run.conversation_id,
                        "question": run.question,
                        "data_source_id": run.data_source_id,
                        "knowledge_base_id": run.knowledge_base_id or "",
                        "memories": memories,
                    }
                graph_config = {"configurable": {"thread_id": run.checkpoint_thread_id}}
                snapshot = await graph.aget_state(graph_config)
                same_run = snapshot.values.get("run_id") == run.id
                if same_run:
                    for result in snapshot.values.get("subagent_results", []):
                        if result.get("sql"):
                            validate_read_only_sql(result["sql"], allowed_tables, get_settings().sql_max_rows)
                if not same_run:
                    # Keep the conversation transcript, but never merge a prior
                    # run's evidence/approval into a new analysis on that thread.
                    for field in ("memories", "subagent_results", "citations", "trace", "errors"):
                        invocation[field] = Overwrite(memories if field == "memories" else [])
                    invocation.update({
                        "answer": {}, "verified": False, "completed": False,
                        "approval": None, "requires_approval": False,
                        "attempts": Overwrite({}), "token_usage": Overwrite({}),
                    })
                if same_run:
                    await self._emit(run_id, principal.tenant_id, "checkpoint_resumed", {
                        "checkpoint_thread_id": run.checkpoint_thread_id,
                        "next_nodes": list(snapshot.next),
                    })
                    if any(task.interrupts for task in snapshot.tasks):
                        async with SessionLocal() as approval_session:
                            approval = await approval_session.scalar(
                                select(AgentApproval).where(
                                    AgentApproval.analysis_run_id == run.id,
                                    AgentApproval.tenant_id == principal.tenant_id,
                                    AgentApproval.tool_name == "analysis.continue",
                                    AgentApproval.status.in_(["approved", "rejected"]),
                                ).order_by(AgentApproval.decided_at.desc())
                            )
                        if approval is None:
                            await self._persist_waiting_approval(run_id, principal.tenant_id)
                            return
                        invocation = Command(resume={
                            "approved": approval.status == "approved", "approval_id": approval.id,
                        })
                    elif snapshot.next:
                        invocation = None
                    else:
                        # Graph finished before a process died while persisting
                        # the report/memory. Reuse that answer, not its tools.
                        state = snapshot.values
                        invocation = None
                if not same_run or snapshot.next:
                    state = await graph.ainvoke(invocation, config=graph_config)
            if state.get("__interrupt__"):
                await self._persist_waiting_approval(run_id, principal.tenant_id)
                return
            if state.get("approval") and not state["approval"].get("approved"):
                await self._persist_rejected_approval(run_id, principal.tenant_id)
                return
            if not state.get("verified") or not state.get("completed"):
                raise RuntimeError(
                    state.get("verification_error") or "Agent answer failed verification"
                )
            await self._persist_success(run_id, principal, state)
        except AnalysisCancelled:
            # Cancellation is already durable; it must not schedule a retry.
            return
        except Exception as exc:
            await self._persist_failure(run_id, principal.tenant_id, exc, retry_pending=retry_pending)
            raise
        finally:
            await local_runtime.stop()

    async def _persist_waiting_approval(self, run_id: str, tenant_id: str) -> None:
        async with SessionLocal() as session:
            await set_tenant_context(session, tenant_id)
            run = await session.scalar(
                select(AnalysisRun).where(
                    AnalysisRun.id == run_id, AnalysisRun.tenant_id == tenant_id
                )
            )
            if not run:
                return
            run.status = "waiting_approval"
            approval = await session.scalar(select(AgentApproval).where(
                AgentApproval.analysis_run_id == run_id,
                AgentApproval.tenant_id == tenant_id,
                AgentApproval.tool_name == "analysis.continue",
                AgentApproval.status == "pending",
            ))
            if approval is None:
                from app.models import Conversation

                conversation = await session.get(Conversation, run.conversation_id)
                approval = AgentApproval(
                    tenant_id=tenant_id, analysis_run_id=run_id,
                    tool_name="analysis.continue", side_effect="external_write",
                    request_payload={"checkpoint_thread_id": run.checkpoint_thread_id},
                    requested_by=conversation.created_by,
                )
                session.add(approval)
                await session.flush()
            await append_event(
                session,
                run,
                "approval_required",
                {"run_id": run.id, "checkpoint_thread_id": run.checkpoint_thread_id,
                 "approval_id": approval.id},
            )

    async def _persist_rejected_approval(self, run_id: str, tenant_id: str) -> None:
        async with SessionLocal() as session:
            await set_tenant_context(session, tenant_id)
            run = await session.get(AnalysisRun, run_id)
            if run is None or run.status == "cancelled":
                return
            run.status = "cancelled"
            run.finished_at = datetime.now(UTC)
            run.error_message = "Analysis approval was rejected"
            await append_event(session, run, "cancelled", {
                "run_id": run_id, "reason": "approval_rejected",
            })

    async def _run_data_subagent(
        self, run_id: str, principal: Principal, state: SupplyMindState
    ) -> dict:
        context_token = issue_tool_context(principal, run_id=run_id)
        connection = {
            "transport": "streamable_http",
            "endpoint": get_settings().mcp_internal_url,
        }
        schema_result = await self.mcp.call(
            "schema.lookup",
            {"context_token": context_token, "data_source_id": state["data_source_id"]},
            **connection,
        )
        await self._emit(
            run_id,
            principal.tenant_id,
            "handoff",
            {"from": "data_analysis", "to": "sql_planner"},
        )
        schema = schema_result.get("tables", [])
        allowed_tables = {
            item.get("name", "") if isinstance(item, dict) else str(item) for item in schema
        }
        failures: list[str] = []
        plan: dict = {}
        query_result: dict | None = None
        for attempt in range(1, 3):
            plan = await self.client.plan_sql(
                state["question"], schema, previous_error=failures[-1] if failures else None
            )
            try:
                validate_read_only_sql(plan["sql"], allowed_tables, get_settings().sql_max_rows)
                query_result = await self.mcp.call(
                    "sql.query",
                    {
                        "context_token": issue_tool_context(principal, run_id=run_id),
                        "data_source_id": state["data_source_id"],
                        "sql": plan["sql"],
                    },
                    **connection,
                )
                break
            except (MCPToolError, SQLGuardError, RuntimeError, ValueError) as exc:
                reason = str(exc)[:600]
                failures.append(reason)
                await self._emit(
                    run_id,
                    principal.tenant_id,
                    "fallback",
                    {
                        "stage": "sql_planner",
                        "attempt": attempt,
                        "max_attempts": 2,
                        "reason": reason,
                    },
                )
        if query_result is None:
            raise RuntimeError(
                "SQL planning was rejected after 2 attempts: "
                + (failures[-1] if failures else "unknown")
            )
        rows = [
            {key: normalize_value(value) for key, value in row.items()}
            for row in query_result.get("rows", [])
        ]
        chart_result = await self.mcp.call(
            "chart.render",
            {"context_token": issue_tool_context(principal, run_id=run_id), "rows": rows},
            **connection,
        )
        await self._emit(
            run_id,
            principal.tenant_id,
            "tool_result",
            {
                "tool": "sql.query",
                "row_count": len(rows),
                "tables": query_result.get("tables", []),
            },
        )
        return {
            "sql": query_result.get("sql"),
            "rows": rows,
            "tables": query_result.get("tables", []),
            "planner_insight": plan["insight"],
            "chart": chart_result.get("spec", {"type": "table"}),
        }

    async def _run_knowledge_subagent(
        self, run_id: str, principal: Principal, state: SupplyMindState
    ) -> dict:
        result = await self.mcp.call(
            "knowledge.search",
            {
                "context_token": issue_tool_context(principal, run_id=run_id),
                "knowledge_base_id": state["knowledge_base_id"],
                "query": state["question"],
                "limit": get_settings().rag_rerank_top_k,
            },
            transport="streamable_http",
            endpoint=get_settings().mcp_internal_url,
        )
        for stage in result.get("trace", []):
            await self._emit(run_id, principal.tenant_id, "retrieval_stage", stage)
        if result.get("degraded"):
            await self._emit(
                run_id,
                principal.tenant_id,
                "degraded",
                {"stage": "advanced_rag", "warnings": result.get("warnings", [])},
            )
        citations = result.get("results", [])
        await self._emit(
            run_id,
            principal.tenant_id,
            "tool_result",
            {"tool": "knowledge.search", "result_count": len(citations)},
        )
        return {"citations": citations, "retrieval_trace": result.get("trace", [])}

    async def _persist_success(
        self, run_id: str, principal: Principal, state: SupplyMindState
    ) -> None:
        async with SessionLocal() as session:
            await set_tenant_context(session, principal.tenant_id)
            run = await session.scalar(
                select(AnalysisRun).where(
                    AnalysisRun.id == run_id, AnalysisRun.tenant_id == principal.tenant_id
                )
            )
            if not run or run.status in {"completed", "cancelled"}:
                return
            answer = state.get("answer") or {}
            run.route = state.get("route")
            run.sql = answer.get("sql")
            run.result = {
                "rows": answer.get("rows", []),
                "insight": answer.get("direct_answer"),
                "direct_answer": answer.get("direct_answer"),
                "insights": {
                    key: answer.get(key, [])
                    for key in ("facts", "risks", "recommendations", "assumptions", "limitations")
                },
                "chart": answer.get("chart", {"type": "table"}),
                "citations": answer.get("citations", []),
                "route": state.get("route"),
            }
            run.error_message = None
            report = await session.scalar(select(Report).where(
                Report.analysis_run_id == run.id, Report.tenant_id == principal.tenant_id,
            ))
            if report is None:
                for item in state.get("trace", []):
                    session.add(
                        AgentStep(
                            tenant_id=principal.tenant_id,
                            analysis_run_id=run.id,
                            name=item.get("node", "agent"),
                            status="completed" if item.get("verified", True) else "failed",
                            output=item,
                            model_version=get_settings().chat_model or "",
                            prompt_version=item.get("prompt_version", "enterprise-agent-v2"),
                        )
                    )
                markdown, citations = render_markdown(run)
                report = Report(
                    tenant_id=principal.tenant_id,
                    analysis_run_id=run.id,
                    title=f"供应链分析报告 · {run.question[:80]}",
                    markdown=markdown,
                    citations=citations,
                    created_by=principal.user_id,
                )
                session.add(report)
                await session.flush()
                session.add(
                    ConversationMessage(
                        tenant_id=principal.tenant_id,
                        conversation_id=run.conversation_id,
                        role="assistant",
                        content=answer.get("direct_answer") or "分析已完成",
                        metadata_json={"analysis_run_id": run.id, "citations": citations},
                    )
                )
            # JSON columns do not track nested dictionary mutation after flush.
            run.result = {**(run.result or {}), "report_id": report.id}
            await session.commit()
            await set_tenant_context(session, principal.tenant_id)
            saved_memories = 0
            try:
                if await MemoryService().enabled(session, principal.tenant_id, principal.user_id):
                    candidates = await self.client.extract_memories(
                        run.question, answer.get("direct_answer") or ""
                    )
                    for candidate in candidates:
                        try:
                            await MemoryService().upsert(
                                session,
                                principal.tenant_id,
                                principal.user_id,
                                category=str(candidate.get("category", "")),
                                memory_key=str(candidate.get("memory_key", "")),
                                content=str(candidate.get("content", "")),
                                confidence=float(candidate.get("confidence", 0)),
                                source_run_id=run.id,
                            )
                            saved_memories += 1
                        except (MemoryPolicyError, TypeError, ValueError):
                            continue
                    await session.commit()
            except (ModelResponseError, RuntimeError, httpx.HTTPError):
                await session.rollback()
                # Rollback expires ORM attributes even when commits do not.
                # Optional memory failure must not break the final result event.
                await session.refresh(run)
                await session.refresh(report)
            await append_event(
                session,
                run,
                "memory_saved",
                {"count": saved_memories, "policy": "allowlist"},
            )
            # Commit terminal status together with its event. Otherwise the
            # stream can close while optional memory extraction is still running.
            run.status = "completed"
            run.finished_at = datetime.now(UTC)
            await append_event(
                session,
                run,
                "completed",
                {
                    "run_id": run.id,
                    "sql": run.sql,
                    "result": run.result,
                    "report_id": report.id,
                    "route": run.route,
                },
            )
            AGENT_RUNS.labels(state.get("route") or "unknown", "completed").inc()

    async def _persist_failure(
        self, run_id: str, tenant_id: str, exc: Exception, *, retry_pending: bool = False
    ) -> None:
        async with SessionLocal() as session:
            await set_tenant_context(session, tenant_id)
            run = await session.scalar(
                select(AnalysisRun).where(
                    AnalysisRun.id == run_id, AnalysisRun.tenant_id == tenant_id
                )
            )
            if not run or run.status in {"completed", "cancelled"}:
                return
            # Celery owns automatic retries. A transient attempt failure must
            # not close SSE as terminal while the same task will run again.
            run.status = "queued" if retry_pending else "failed"
            if not retry_pending:
                AGENT_RUNS.labels(run.route or "unknown", "failed").inc()
            run.finished_at = None if retry_pending else datetime.now(UTC)
            error_message = _root_error_message(exc) or type(exc).__name__
            run.error_message = error_message[:1000]
            await append_event(
                session,
                run,
                "retry_scheduled" if retry_pending else "failed",
                {
                    "run_id": run.id,
                    "message": "本次执行失败，正在等待自动重试" if retry_pending else "分析执行失败",
                    "error_type": type(exc).__name__,
                    "reason": error_message[:600],
                },
            )
