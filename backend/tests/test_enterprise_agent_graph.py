import pytest

from app.agents.graph import AgentServices, build_enterprise_graph


@pytest.mark.asyncio
async def test_hybrid_router_dispatches_parallel_subagents_and_handoffs() -> None:
    calls: list[str] = []

    async def route(_: str):
        return "hybrid", 0.98

    async def subagent(name: str, state: dict):
        calls.append(name)
        if name == "data_analysis":
            return {"rows": [{"factory": "A", "rate": 91.2}]}
        return {"citations": [{"chunk_id": "c1", "text": "达成率口径"}]}

    async def synthesize(state: dict):
        return {
            "direct_answer": "A 工厂达成率为 91.2%。",
            "rows": state["subagent_results"][0].get("rows", []),
            "citations": state.get("citations", []),
        }

    graph = build_enterprise_graph(
        AgentServices(route=route, run_subagent=subagent, synthesize=synthesize)
    )
    result = await graph.ainvoke(
        {
            "question": "结合口径分析工厂达成率",
            "role": "analyst",
            "memories": [],
        }
    )
    assert set(calls) == {"data_analysis", "knowledge_research"}
    assert result["route"] == "hybrid"
    assert result["verified"] is True
    assert any(item.get("handoff") == "synthesize" for item in result["trace"])


@pytest.mark.asyncio
async def test_verifier_rolls_back_once_before_completion() -> None:
    syntheses = 0

    async def subagent(name: str, state: dict):
        return {"rows": [{"value": 1}], "agent": name}

    async def synthesize(state: dict):
        nonlocal syntheses
        syntheses += 1
        return {"direct_answer": "" if syntheses == 1 else "已验证", "rows": [{"value": 1}]}

    graph = build_enterprise_graph(AgentServices(run_subagent=subagent, synthesize=synthesize))
    result = await graph.ainvoke({"question": "统计订单", "role": "analyst", "memories": []})
    assert syntheses == 2
    assert result["verified"] is True
    assert result["attempts"]["verification"] == 1
