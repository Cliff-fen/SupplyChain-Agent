"""Bounded LangGraph workflow for evidence-grounded answer generation."""

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.services.llm import AnswerPlan, ModelConfigurationError, OpenAICompatibleClient


class AnswerState(TypedDict, total=False):
    question: str
    rows: list[dict]
    citations: list[dict]
    context: list[str]
    planner_insight: str
    answer: dict
    verified: bool
    verification_error: str | None
    trace: list[dict]


async def _evidence_node(state: AnswerState) -> AnswerState:
    rows = state.get("rows", [])
    citations = state.get("citations", [])
    return {
        "trace": [
            {
                "node": "evidence_agent",
                "row_count": len(rows),
                "citation_count": len(citations),
            }
        ]
    }


def _answer_node_factory(client: OpenAICompatibleClient):
    async def answer_node(state: AnswerState) -> AnswerState:
        rows = state.get("rows", [])
        if not rows:
            answer = AnswerPlan(
                direct_answer="查询没有返回数据，当前无法形成确定性结论。",
                limitations=["请检查时间范围、筛选条件或数据源是否包含相关记录。"],
            )
        else:
            answer = await client.answer_question(
                state["question"],
                rows,
                state.get("citations", []),
                state.get("context"),
                state.get("planner_insight", ""),
            )
        return {
            "answer": answer.model_dump(),
            "trace": state.get("trace", []) + [{"node": "answer_agent", "row_count": len(rows)}],
        }

    return answer_node


async def _verify_node(state: AnswerState) -> AnswerState:
    answer = state.get("answer") or {}
    rows = state.get("rows", [])
    if not answer.get("direct_answer"):
        return {
            "verified": False,
            "verification_error": "答案缺少直接回答",
            "trace": state.get("trace", []) + [{"node": "answer_verifier", "verified": False}],
        }
    if not rows and (answer.get("facts") or answer.get("risks") or answer.get("recommendations")):
        return {
            "verified": False,
            "verification_error": "无查询数据时不得生成事实、风险或建议",
            "trace": state.get("trace", []) + [{"node": "answer_verifier", "verified": False}],
        }
    return {
        "verified": True,
        "verification_error": None,
        "trace": state.get("trace", []) + [{"node": "answer_verifier", "verified": True}],
    }


def build_answer_graph(client: OpenAICompatibleClient | None = None):
    client = client or OpenAICompatibleClient()
    graph = StateGraph(AnswerState)
    graph.add_node("evidence_agent", _evidence_node)
    graph.add_node("answer_agent", _answer_node_factory(client))
    graph.add_node("answer_verifier", _verify_node)
    graph.add_edge(START, "evidence_agent")
    graph.add_edge("evidence_agent", "answer_agent")
    graph.add_edge("answer_agent", "answer_verifier")
    graph.add_edge("answer_verifier", END)
    return graph.compile()


async def run_answer_graph(
    state: AnswerState, client: OpenAICompatibleClient | None = None
) -> AnswerState:
    try:
        return await build_answer_graph(client).ainvoke(state)
    except ModelConfigurationError:
        raise
