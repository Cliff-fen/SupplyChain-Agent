import json
from collections.abc import AsyncGenerator
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.sql_guard import SQLGuardError, validate_read_only_sql
from app.mcp.registry import ToolRegistry
from app.mcp.tools import register_default_tools
from app.models import (
    AgentStep,
    AnalysisRun,
    Conversation,
    ConversationMessage,
    DataSource,
    KnowledgeBase,
    Report,
)
from app.schemas import AnalysisRequest, Principal
from app.services.agent_graph import run_answer_graph
from app.services.audit import audit
from app.services.datasource import DataSourceError
from app.services.llm import ModelConfigurationError, ModelResponseError, OpenAICompatibleClient
from app.services.reports import render_markdown


class AnalysisService:
    def __init__(self, client: OpenAICompatibleClient | None = None) -> None:
        self.client = client or OpenAICompatibleClient()

    async def stream(
        self,
        session: AsyncSession,
        principal: Principal,
        request: AnalysisRequest,
        *,
        idempotency_key: str | None = None,
        retry_of_id: str | None = None,
    ) -> AsyncGenerator[str, None]:
        source = await session.scalar(
            select(DataSource).where(
                DataSource.id == request.data_source_id, DataSource.tenant_id == principal.tenant_id
            )
        )
        if not source:
            yield self.event("failed", {"message": "Data source not found"})
            return
        if request.knowledge_base_id:
            knowledge_base = await session.scalar(
                select(KnowledgeBase).where(
                    KnowledgeBase.id == request.knowledge_base_id,
                    KnowledgeBase.tenant_id == principal.tenant_id,
                )
            )
            if not knowledge_base or knowledge_base.is_archived:
                yield self.event(
                    "failed", {"message": "Knowledge base is unavailable for new analysis"}
                )
                return
        conversation = None
        if request.conversation_id:
            conversation = await session.scalar(
                select(Conversation).where(
                    Conversation.id == request.conversation_id,
                    Conversation.tenant_id == principal.tenant_id,
                    Conversation.created_by == principal.user_id,
                )
            )
        if conversation is None:
            conversation = Conversation(
                tenant_id=principal.tenant_id,
                title=request.question[:80],
                created_by=principal.user_id,
            )
            session.add(conversation)
            await session.flush()
        session.add(
            ConversationMessage(
                tenant_id=principal.tenant_id,
                conversation_id=conversation.id,
                role="user",
                content=request.question,
                metadata_json={
                    "data_source_id": source.id,
                    "knowledge_base_id": request.knowledge_base_id,
                },
            )
        )
        run = AnalysisRun(
            tenant_id=principal.tenant_id,
            conversation_id=conversation.id,
            data_source_id=source.id,
            knowledge_base_id=request.knowledge_base_id,
            question=request.question,
            status="running",
            started_at=datetime.now(UTC),
            idempotency_key=idempotency_key,
            retry_of_id=retry_of_id,
        )
        session.add(run)
        await session.flush()
        await session.commit()

        async def fail(message: str) -> None:
            """Persist a terminal failure before the SSE generator returns.

            A streaming connection can be interrupted by the browser or proxy at
            any point.  Keeping the terminal state on the run makes refresh and
            reconnect deterministic instead of leaving an eternal "running"
            record behind.
            """
            run.status = "failed"
            run.error_message = message[:1000]
            run.finished_at = datetime.now(UTC)

        async def was_cancelled() -> bool:
            await session.refresh(run, attribute_names=["status"])
            if run.status == "cancelled":
                yield_event = self.event("cancelled", {"run_id": run.id, "message": "分析已取消"})
                return True, yield_event
            return False, ""

        yield self.event("queued", {"run_id": run.id, "conversation_id": conversation.id})
        tools = ToolRegistry()
        register_default_tools(tools, session, principal)
        try:
            schema_tool = await tools.call(
                "schema.lookup", principal.role, {"data_source_id": source.id}
            )
            allowed_tables = [item["name"] for item in schema_tool.tables]
            schema_context = schema_tool.tables
            await audit(
                session,
                principal.tenant_id,
                principal.user_id,
                "mcp.schema.lookup",
                "data_source",
                source.id,
                {"table_count": len(allowed_tables)},
            )
        except (RuntimeError, OSError) as exc:
            allowed_tables = source.allowed_tables
            schema_context = allowed_tables
            await audit(
                session,
                principal.tenant_id,
                principal.user_id,
                "mcp.schema.lookup_failed",
                "data_source",
                source.id,
                {"reason": str(exc)},
            )
        yield self.event("step_started", {"step": "schema", "tables": allowed_tables})
        cancelled, cancel_event = await was_cancelled()
        if cancelled:
            yield cancel_event
            return
        citations: list[dict] = []
        if request.knowledge_base_id:
            try:
                knowledge_tool = await tools.call(
                    "knowledge.search",
                    principal.role,
                    {
                        "knowledge_base_id": request.knowledge_base_id,
                        "query": request.question,
                        "limit": 5,
                    },
                )
                citations = knowledge_tool.results
                await audit(
                    session,
                    principal.tenant_id,
                    principal.user_id,
                    "mcp.knowledge.search",
                    "knowledge_base",
                    request.knowledge_base_id,
                    {"result_count": len(citations)},
                )
                yield self.event(
                    "tool_result",
                    {
                        "tool": "knowledge.search",
                        "result_count": len(citations),
                        "citations": citations,
                    },
                )
            except (RuntimeError, OSError) as exc:
                await audit(
                    session,
                    principal.tenant_id,
                    principal.user_id,
                    "mcp.knowledge.search_failed",
                    "knowledge_base",
                    request.knowledge_base_id,
                    {"reason": str(exc)},
                )
                await fail(f"Knowledge retrieval failed: {exc}")
                await session.commit()
                yield self.event("failed", {"message": f"Knowledge retrieval failed: {exc}"})
                return
        for step, message in (
            ("router", "Identifying analysis intent"),
            ("rag", "Retrieving manufacturing metric definitions"),
        ):
            session.add(
                AgentStep(
                    tenant_id=principal.tenant_id,
                    analysis_run_id=run.id,
                    name=step,
                    status="completed",
                    output={"message": message},
                    model_version=get_settings().chat_model or "",
                    prompt_version="analysis-v1",
                )
            )
            yield self.event("step_started", {"step": step, "message": message})
        cancelled, cancel_event = await was_cancelled()
        if cancelled:
            yield cancel_event
            return
        try:
            plan = await self.client.plan_sql(request.question, schema_context, request.context)
        except (ModelConfigurationError, ModelResponseError) as exc:
            await fail(str(exc))
            await audit(
                session,
                principal.tenant_id,
                principal.user_id,
                "analysis.model_failed",
                "analysis_run",
                run.id,
                {"reason": str(exc)},
            )
            await session.commit()
            yield self.event("failed", {"message": str(exc)})
            return
        candidate = plan["sql"]
        run.sql_draft = candidate
        session.add(
            AgentStep(
                tenant_id=principal.tenant_id,
                analysis_run_id=run.id,
                name="sql_planner",
                status="completed",
                output=plan,
                model_version=get_settings().chat_model or "",
                prompt_version="sql-planner-v1",
            )
        )
        yield self.event("sql_draft", {"sql": candidate})
        cancelled, cancel_event = await was_cancelled()
        if cancelled:
            yield cancel_event
            return
        try:
            guarded = validate_read_only_sql(
                candidate, set(source.allowed_tables), get_settings().sql_max_rows
            )
        except SQLGuardError as exc:
            await fail(str(exc))
            run.guard_error = str(exc)
            await audit(
                session,
                principal.tenant_id,
                principal.user_id,
                "analysis.blocked",
                "analysis_run",
                run.id,
                {"reason": str(exc)},
            )
            await session.commit()
            yield self.event("failed", {"message": str(exc)})
            return
        session.add(
            AgentStep(
                tenant_id=principal.tenant_id,
                analysis_run_id=run.id,
                name="sql_guard",
                status="completed",
                output={"tables": guarded.tables},
                prompt_version="sql-guard-v1",
            )
        )
        query_tool = None
        rows: list[dict] = []
        query_error: Exception | None = None
        for attempt in range(2):
            try:
                query_tool = await tools.call(
                    "sql.query", principal.role, {"data_source_id": source.id, "sql": guarded.sql}
                )
                rows = [self.normalize_row(row) for row in query_tool.rows]
                await audit(
                    session,
                    principal.tenant_id,
                    principal.user_id,
                    "mcp.sql.query",
                    "data_source",
                    source.id,
                    {"tables": query_tool.tables, "row_count": len(rows), "attempt": attempt + 1},
                )
                query_error = None
                break
            except (DataSourceError, SQLAlchemyError, RuntimeError, OSError) as exc:
                query_error = exc
                if attempt == 0:
                    try:
                        repair_prompt = (
                            f"修复上一次只读 SQL。原问题：{request.question}\n"
                            f"失败 SQL：{guarded.sql}\n数据库错误：{str(exc)[:800]}\n"
                            "请严格依据提供的表和字段生成一个修复后的单条 SELECT/WITH SQL，并返回 JSON。"
                        )
                        repaired = await self.client.plan_sql(
                            repair_prompt, schema_context, request.context
                        )
                        candidate = repaired["sql"]
                        run.sql_draft = candidate
                        guarded = validate_read_only_sql(
                            candidate, set(source.allowed_tables), get_settings().sql_max_rows
                        )
                        yield self.event("sql_repair", {"sql": candidate})
                        continue
                    except (
                        ModelConfigurationError,
                        ModelResponseError,
                        SQLGuardError,
                    ) as repair_exc:
                        query_error = repair_exc
                break
        if query_error is not None or query_tool is None:
            await fail("Read-only query execution failed")
            await audit(
                session,
                principal.tenant_id,
                principal.user_id,
                "analysis.query_failed",
                "analysis_run",
                run.id,
                {"reason": str(query_error)[:500]},
            )
            await session.commit()
            yield self.event("failed", {"message": "Read-only query execution failed"})
            return
        cancelled, cancel_event = await was_cancelled()
        if cancelled:
            yield cancel_event
            return
        try:
            chart = await tools.call("chart.render", principal.role, {"rows": rows})
        except (RuntimeError, OSError) as exc:
            await fail(f"图表生成失败：{exc}")
            await audit(
                session,
                principal.tenant_id,
                principal.user_id,
                "analysis.chart_failed",
                "analysis_run",
                run.id,
                {"reason": str(exc)[:500]},
            )
            await session.commit()
            yield self.event("failed", {"message": "图表生成失败，请稍后重试"})
            return
        # Keep model text intact while exposing a stable, auditable result contract.
        # Facts are only populated from the model response and observed query rows;
        # no conclusion is manufactured when the query is empty.
        factual_rows = self.result_facts(rows)
        try:
            graph_state = await run_answer_graph(
                {
                    "question": request.question,
                    "rows": rows,
                    "citations": citations,
                    "context": request.context,
                    "planner_insight": plan["insight"],
                },
                self.client,
            )
        except (ModelConfigurationError, ModelResponseError) as exc:
            await fail("答案生成失败，请稍后重试")
            await audit(
                session,
                principal.tenant_id,
                principal.user_id,
                "analysis.answer_failed",
                "analysis_run",
                run.id,
                {"reason": str(exc)},
            )
            await session.commit()
            yield self.event("failed", {"message": "答案生成失败，请稍后重试"})
            return
        if not graph_state.get("verified"):
            verification_error = graph_state.get("verification_error") or "答案校验失败"
            await fail(verification_error)
            run.guard_error = verification_error
            await session.commit()
            yield self.event(
                "failed", {"message": graph_state.get("verification_error") or "答案校验失败"}
            )
            return
        for trace_item in graph_state.get("trace", []):
            session.add(
                AgentStep(
                    tenant_id=principal.tenant_id,
                    analysis_run_id=run.id,
                    name=trace_item.get("node", "agent"),
                    status="completed" if trace_item.get("verified", True) else "failed",
                    output=trace_item,
                    model_version=get_settings().chat_model or "",
                    prompt_version="answer-graph-v1",
                )
            )
        answer = graph_state.get("answer") or {}
        structured_insights = {
            "facts": answer.get("facts", factual_rows),
            "risks": answer.get("risks", []),
            "recommendations": answer.get("recommendations", []),
            "assumptions": answer.get("assumptions", []),
            "limitations": answer.get("limitations", []),
            "evidence": citations,
        }
        result = {
            "rows": rows,
            "insight": answer.get("direct_answer")
            or (
                f"{plan['insight']} {' '.join(factual_rows)}"
                if rows and factual_rows
                else "查询没有返回数据，无法形成确定性结论。"
            ),
            "direct_answer": answer.get("direct_answer"),
            "insights": structured_insights,
            "chart": chart.spec if rows else {"type": "table"},
            "citations": citations,
        }
        session.add(
            AgentStep(
                tenant_id=principal.tenant_id,
                analysis_run_id=run.id,
                name="query",
                status="completed",
                output={"row_count": len(rows)},
            )
        )
        session.add(
            AgentStep(
                tenant_id=principal.tenant_id,
                analysis_run_id=run.id,
                name="insight",
                status="completed",
                output={"insight": plan["insight"], "chart": result["chart"]},
                model_version=get_settings().chat_model or "",
                prompt_version="insight-v1",
            )
        )
        run.status = "completed"
        run.finished_at = datetime.now(UTC)
        run.error_message = None
        run.sql = guarded.sql
        run.result = result
        markdown, citations = render_markdown(run)
        report = Report(
            tenant_id=principal.tenant_id,
            analysis_run_id=run.id,
            title=f"供应链分析报告 · {request.question[:80]}",
            markdown=markdown,
            citations=citations,
            created_by=principal.user_id,
        )
        session.add(report)
        await session.flush()
        result["report_id"] = report.id
        session.add(
            ConversationMessage(
                tenant_id=principal.tenant_id,
                conversation_id=conversation.id,
                role="assistant",
                content=str(result.get("direct_answer") or result.get("insight") or "分析已完成"),
                metadata_json={"analysis_run_id": run.id, "citations": citations},
            )
        )
        session.add(
            AgentStep(
                tenant_id=principal.tenant_id,
                analysis_run_id=run.id,
                name="report",
                status="completed",
                output={"report_id": report.id},
                prompt_version="report-v1",
            )
        )
        export_tool = await tools.call(
            "report.export", principal.role, {"report_id": report.id, "format": "pdf"}
        )
        await audit(
            session,
            principal.tenant_id,
            principal.user_id,
            "mcp.report.export",
            "report",
            report.id,
            {"status": export_tool.status},
        )
        await audit(
            session,
            principal.tenant_id,
            principal.user_id,
            "analysis.executed",
            "analysis_run",
            run.id,
            {"tables": guarded.tables},
        )
        await session.commit()
        yield self.event(
            "tool_result",
            {"tool": "sql.query", "tables": guarded.tables, "row_count": len(result["rows"])},
        )
        yield self.event("chart_ready", {"chart": result["chart"]})
        yield self.event(
            "completed",
            {"run_id": run.id, "sql": guarded.sql, "result": result, "report_id": report.id},
        )

    @staticmethod
    def normalize_row(row: dict) -> dict:
        return {
            key: (
                float(value)
                if isinstance(value, Decimal)
                else value.isoformat()
                if isinstance(value, (datetime, date))
                else value
            )
            for key, value in row.items()
        }

    @staticmethod
    def result_facts(rows: list[dict]) -> list[str]:
        """Render only values observed in the read-only query result."""
        facts: list[str] = []
        for row in rows[:10]:
            if "total_orders" in row and "fulfillment_rate" in row:
                facts.append(
                    f"订单总数 {row['total_orders']}，订货总量 {row.get('total_ordered', '—')}，"
                    f"已交付总量 {row.get('total_delivered', '—')}，履约率 {row['fulfillment_rate']}%。"
                )
                continue
            label = (
                row.get("factory")
                or row.get("supplier")
                or row.get("supplier_name")
                or row.get("total_orders")
            )
            rate_key = next(
                (key for key in ("achievement_rate", "fulfillment_rate", "rate") if key in row),
                None,
            )
            if label is not None and rate_key:
                facts.append(f"{label} 的 {rate_key} 为 {row[rate_key]}%。")
            elif len(rows) == 1:
                facts.append(
                    "查询返回：" + "，".join(f"{key}={value}" for key, value in row.items()) + "。"
                )
        return facts

    @staticmethod
    def event(name: str, payload: dict) -> str:
        return f"event: {name}\ndata: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"

    @staticmethod
    def chart_spec(rows: list[dict]) -> dict:
        if not rows:
            return {"type": "table"}
        fields = list(rows[0])
        numeric = next(
            (field for field, value in rows[0].items() if isinstance(value, (int, float))), None
        )
        return {"type": "bar", "x": fields[0], "y": numeric or fields[-1]}
