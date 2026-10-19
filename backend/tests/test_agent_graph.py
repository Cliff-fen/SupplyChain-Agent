import pytest

from app.services.agent_graph import run_answer_graph


@pytest.mark.asyncio
async def test_answer_graph_blocks_conclusions_without_rows() -> None:
    result = await run_answer_graph({"question": "统计生产达成率", "rows": [], "citations": []})
    assert result["verified"] is True
    assert result["answer"]["direct_answer"].startswith("查询没有返回数据")
    assert result["answer"]["facts"] == []
    assert [item["node"] for item in result["trace"]] == [
        "evidence_agent",
        "answer_agent",
        "answer_verifier",
    ]
