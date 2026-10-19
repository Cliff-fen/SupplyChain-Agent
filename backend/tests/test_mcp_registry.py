import pytest
from pydantic import BaseModel

from app.mcp.registry import SideEffect, ToolDefinition, ToolRegistry
from app.mcp.tools import register_default_tools
from app.schemas import Principal


class ToolInput(BaseModel):
    query: str


class ToolOutput(BaseModel):
    result: str


async def handler(value: ToolInput) -> ToolOutput:
    return ToolOutput(result=value.query.upper())


@pytest.mark.asyncio
async def test_registry_enforces_role_and_schema() -> None:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            "knowledge.search",
            "Search knowledge",
            frozenset({"analyst"}),
            SideEffect.read,
            ToolInput,
            ToolOutput,
            10,
        ),
        handler,
    )
    assert (
        await registry.call("knowledge.search", "analyst", {"query": "stock"})
    ).result == "STOCK"
    with pytest.raises(PermissionError):
        await registry.call("knowledge.search", "viewer", {"query": "stock"})


@pytest.mark.asyncio
async def test_default_tools_are_typed_and_chartable() -> None:
    registry = ToolRegistry()
    register_default_tools(registry, None, Principal(user_id="u", tenant_id="t", role="analyst"))  # type: ignore[arg-type]
    names = {item["name"] for item in registry.describe()}
    assert names == {
        "schema.lookup",
        "sql.query",
        "knowledge.search",
        "chart.render",
        "report.export",
    }
    chart = await registry.call(
        "chart.render", "analyst", {"rows": [{"factory": "A", "rate": 91.2}]}
    )
    assert chart.spec == {"type": "bar", "x": "factory", "y": "rate"}
