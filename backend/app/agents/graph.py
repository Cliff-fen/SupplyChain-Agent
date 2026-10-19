"""State-driven Handoffs, Router and tool-like Subagent execution."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send, interrupt
from pydantic import BaseModel, Field

from app.agents.middleware import DynamicAgentMiddleware
from app.agents.state import AgentRoute, SupplyMindState

RouterHandler = Callable[[str], Awaitable[tuple[AgentRoute, float]]]
SubagentHandler = Callable[[str, SupplyMindState], Awaitable[dict[str, Any]]]
SynthesisHandler = Callable[[SupplyMindState], Awaitable[dict[str, Any]]]
VerificationHandler = Callable[[SupplyMindState], Awaitable[tuple[bool, str | None, str | None]]]


@dataclass
class AgentServices:
    run_subagent: SubagentHandler
    synthesize: SynthesisHandler
    route: RouterHandler | None = None
    verify: VerificationHandler | None = None
    middleware: DynamicAgentMiddleware | None = None


class SubagentToolInput(BaseModel):
    question: str = Field(min_length=2, max_length=4000)
    data_source_id: str | None = None
    knowledge_base_id: str | None = None


def _heuristic_route(question: str) -> tuple[AgentRoute, float]:
    lowered = question.lower()
    data_terms = ("统计", "趋势", "同比", "环比", "多少", "sql", "订单", "工厂", "数量", "金额")
    knowledge_terms = ("口径", "定义", "制度", "规范", "为什么", "知识库", "依据")
    data = any(term in lowered for term in data_terms)
    knowledge = any(term in lowered for term in knowledge_terms)
    if data and knowledge:
        return "hybrid", 0.9
    if data:
        return "data", 0.82
    if knowledge:
        return "knowledge", 0.82
    return "hybrid", 0.55


def build_enterprise_graph(services: AgentServices, *, checkpointer=None, store=None):
    middleware = services.middleware or DynamicAgentMiddleware()

    async def load_context(state: SupplyMindState) -> dict:
        context = middleware.resolve(
            "router", state.get("role", "viewer"), state.get("memories", [])
        )
        return {
            "trace": [{"node": "context_loader", "prompt_version": context.prompt_version}],
            "messages": [{"role": "user", "content": state["question"]}],
            "attempts": {"verification": 0},
        }

    async def router(state: SupplyMindState) -> dict:
        route, confidence = (
            await services.route(state["question"])
            if services.route
            else _heuristic_route(state["question"])
        )
        selected = {
            "data": ["data_analysis"],
            "knowledge": ["knowledge_research"],
            "hybrid": ["data_analysis", "knowledge_research"],
            "unsupported": [],
        }[route]
        return {
            "route": route,
            "route_confidence": confidence,
            "selected_subagents": selected,
            "trace": [
                {
                    "node": "router",
                    "route": route,
                    "confidence": confidence,
                    "handoff": selected,
                }
            ],
        }

    def dispatch(state: SupplyMindState):
        if state.get("route") == "unsupported":
            return "synthesize"
        return [
            Send("subagent", {**state, "selected_subagents": [name]})
            for name in state["selected_subagents"]
        ]

    async def subagent(state: SupplyMindState) -> dict:
        name = state["selected_subagents"][0]
        context = middleware.resolve(
            "data" if name == "data_analysis" else "knowledge",
            state.get("role", "viewer"),
            state.get("memories", []),
        )
        result = await services.run_subagent(name, state)
        return {
            "subagent_results": [{"agent": name, **result}],
            "citations": result.get("citations", []),
            "trace": [
                {
                    "node": name,
                    "status": "completed",
                    "prompt_version": context.prompt_version,
                    "handoff": "synthesize",
                }
            ],
        }

    async def synthesize(state: SupplyMindState) -> dict:
        answer = await services.synthesize(state)
        return {
            "answer": answer,
            "requires_approval": bool(answer.get("requires_approval", False)),
            "trace": [{"node": "synthesis_agent", "handoff": "verifier"}],
        }

    async def verify(state: SupplyMindState) -> dict:
        if services.verify:
            verified, error, retry_target = await services.verify(state)
        else:
            answer = state.get("answer") or {}
            verified = bool(answer.get("direct_answer"))
            error = None if verified else "answer_missing"
            retry_target = "synthesize" if not verified else None
        attempts = dict(state.get("attempts", {}))
        attempts["verification"] = attempts.get("verification", 0) + (0 if verified else 1)
        return {
            "verified": verified,
            "verification_error": error,
            "retry_target": retry_target,
            "attempts": attempts,
            "trace": [{"node": "answer_verifier", "verified": verified, "error": error}],
        }

    def after_verify(state: SupplyMindState) -> str:
        if not state.get("verified") and state.get("attempts", {}).get("verification", 0) < 2:
            return state.get("retry_target") or "synthesize"
        if state.get("requires_approval"):
            return "approval_gate"
        return "complete"

    async def approval_gate(state: SupplyMindState) -> dict:
        decision = interrupt(
            {
                "run_id": state.get("run_id"),
                "reason": "side_effect_tool",
                "answer": state.get("answer", {}),
            }
        )
        approved = bool(isinstance(decision, dict) and decision.get("approved"))
        return {
            "approval": decision if isinstance(decision, dict) else {"approved": approved},
            "completed": approved,
            "trace": [{"node": "approval_gate", "approved": approved}],
        }

    async def complete(state: SupplyMindState) -> dict:
        return {
            "completed": bool(state.get("verified")) and (
                not state.get("requires_approval") or bool((state.get("approval") or {}).get("approved"))
            ),
            "trace": [{"node": "complete", "verified": state.get("verified", False)}],
        }

    graph = StateGraph(SupplyMindState)
    graph.add_node("load_context", load_context)
    graph.add_node("router", router)
    graph.add_node("subagent", subagent)
    graph.add_node("synthesize", synthesize)
    graph.add_node("verify", verify)
    graph.add_node("approval_gate", approval_gate)
    graph.add_node("complete", complete)
    graph.add_edge(START, "load_context")
    graph.add_edge("load_context", "router")
    graph.add_conditional_edges("router", dispatch, ["subagent", "synthesize"])
    graph.add_edge("subagent", "synthesize")
    graph.add_edge("synthesize", "verify")
    graph.add_conditional_edges("verify", after_verify, ["synthesize", "approval_gate", "complete"])
    graph.add_edge("approval_gate", "complete")
    graph.add_edge("complete", END)
    return graph.compile(checkpointer=checkpointer, store=store)
