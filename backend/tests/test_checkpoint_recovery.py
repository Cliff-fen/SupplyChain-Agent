"""Regression tests for actual graph checkpoints, not a replacement workflow."""

import asyncio
from collections import Counter

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from app.agents.graph import AgentServices, build_enterprise_graph


@pytest.mark.asyncio
async def test_checkpoint_resume_does_not_repeat_completed_parallel_branch():
    calls = Counter()
    data_finished = asyncio.Event()

    async def route(question):
        calls["router"] += 1
        return "hybrid", 1.0

    async def subagent(name, state):
        calls[name] += 1
        if name == "data_analysis":
            data_finished.set()
            return {"rows": [{"count": 3}]}
        await data_finished.wait()
        if calls[name] == 1:
            raise ConnectionError("Controlled knowledge backend outage")
        return {"citations": [{"chunk_id": "verified-source"}]}

    async def synthesize(state):
        calls["synthesis"] += 1
        return {"direct_answer": "已查询到 3 条数据", "rows": [{"count": 3}]}

    saver = InMemorySaver()
    services = AgentServices(route=route, run_subagent=subagent, synthesize=synthesize)
    config = {"configurable": {"thread_id": "tenant:user:conversation"}}
    graph = build_enterprise_graph(services, checkpointer=saver)
    with pytest.raises(ConnectionError):
        await graph.ainvoke({"run_id": "run", "question": "统计并说明口径"}, config=config)
    # Recreate the compiled graph, as a new Worker process does.
    resumed = build_enterprise_graph(services, checkpointer=saver)
    result = await resumed.ainvoke(None, config=config)
    assert result["completed"] is True
    assert calls == {"router": 1, "data_analysis": 1, "knowledge_research": 2, "synthesis": 1}


@pytest.mark.parametrize("approved", [True, False])
@pytest.mark.asyncio
async def test_approval_interrupt_survives_graph_recreation(approved):
    calls = Counter()

    async def subagent(name, state):
        calls[name] += 1
        return {"rows": [{"count": 3}]}

    async def synthesize(state):
        calls["synthesis"] += 1
        return {"direct_answer": "等待审批", "requires_approval": True}

    saver = InMemorySaver()
    services = AgentServices(run_subagent=subagent, synthesize=synthesize)
    config = {"configurable": {"thread_id": "tenant:user:approval"}}
    graph = build_enterprise_graph(services, checkpointer=saver)
    result = await graph.ainvoke({"run_id": "approval-run", "question": "统计订单数量"}, config=config)
    assert result["__interrupt__"]
    resumed = build_enterprise_graph(services, checkpointer=saver)
    result = await resumed.ainvoke(Command(resume={"approved": approved}), config=config)
    assert result["completed"] is approved
    assert result["approval"]["approved"] is approved
    assert calls == {"data_analysis": 1, "synthesis": 1}
