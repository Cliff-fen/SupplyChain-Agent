"""Typed, tenant-scoped MCP tool handlers used by the analysis workflow."""

from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.sql_guard import validate_read_only_sql
from app.mcp.registry import SideEffect, ToolDefinition, ToolRegistry
from app.models import DataSource
from app.schemas import Principal
from app.services.datasource import execute_guarded_query, synchronize_schema
from app.services.retrieval import search_knowledge


class SchemaLookupInput(BaseModel):
    data_source_id: str


class SchemaLookupOutput(BaseModel):
    tables: list[dict[str, Any]]


class SQLQueryInput(BaseModel):
    data_source_id: str
    sql: str = Field(min_length=8, max_length=20_000)


class SQLQueryOutput(BaseModel):
    sql: str
    tables: list[str]
    rows: list[dict[str, Any]]


class KnowledgeSearchInput(BaseModel):
    knowledge_base_id: str
    query: str = Field(min_length=2, max_length=2_000)
    limit: int = Field(default=5, ge=1, le=20)


class KnowledgeSearchOutput(BaseModel):
    results: list[dict[str, Any]]


class ChartRenderInput(BaseModel):
    rows: list[dict[str, Any]]


class ChartRenderOutput(BaseModel):
    spec: dict[str, Any]


class ReportExportInput(BaseModel):
    report_id: str
    format: str = "pdf"


class ReportExportOutput(BaseModel):
    report_id: str
    format: str
    status: str


def _source_query(session: AsyncSession, source_id: str, tenant_id: str):
    return session.scalar(
        select(DataSource).where(DataSource.id == source_id, DataSource.tenant_id == tenant_id)
    )


def _chart(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"type": "table"}
    fields = list(rows[0])
    numeric = next(
        (field for field, value in rows[0].items() if isinstance(value, (int, float))), fields[-1]
    )
    return {"type": "bar", "x": fields[0], "y": numeric}


def register_default_tools(
    registry: ToolRegistry, session: AsyncSession, principal: Principal
) -> None:
    async def schema_lookup(value: SchemaLookupInput) -> SchemaLookupOutput:
        source = await _source_query(session, value.data_source_id, principal.tenant_id)
        if not source:
            raise RuntimeError("Data source not found")
        schema = await synchronize_schema(source)
        return SchemaLookupOutput(tables=schema.tables)

    async def sql_query(value: SQLQueryInput) -> SQLQueryOutput:
        source = await _source_query(session, value.data_source_id, principal.tenant_id)
        if not source:
            raise RuntimeError("Data source not found")
        guarded = validate_read_only_sql(
            value.sql, set(source.allowed_tables), get_settings().sql_max_rows
        )
        _, rows = await execute_guarded_query(source, guarded.sql)
        return SQLQueryOutput(sql=guarded.sql, tables=guarded.tables, rows=rows)

    async def knowledge_search(value: KnowledgeSearchInput) -> KnowledgeSearchOutput:
        results = await search_knowledge(
            session, principal.tenant_id, value.knowledge_base_id, value.query, value.limit
        )
        return KnowledgeSearchOutput(results=results)

    async def chart_render(value: ChartRenderInput) -> ChartRenderOutput:
        return ChartRenderOutput(spec=_chart(value.rows))

    async def report_export(value: ReportExportInput) -> ReportExportOutput:
        if value.format != "pdf":
            raise RuntimeError("Only PDF export is supported")
        return ReportExportOutput(report_id=value.report_id, format=value.format, status="queued")

    registry.register(
        ToolDefinition(
            "schema.lookup",
            "Read approved datasource schema",
            frozenset({"analyst", "org_admin", "platform_admin"}),
            SideEffect.read,
            SchemaLookupInput,
            SchemaLookupOutput,
            15,
        ),
        schema_lookup,
    )
    registry.register(
        ToolDefinition(
            "sql.query",
            "Execute guarded read-only SQL",
            frozenset({"analyst", "org_admin", "platform_admin"}),
            SideEffect.read,
            SQLQueryInput,
            SQLQueryOutput,
            get_settings().sql_timeout_seconds,
        ),
        sql_query,
    )
    registry.register(
        ToolDefinition(
            "knowledge.search",
            "Search tenant knowledge citations",
            frozenset({"analyst", "org_admin", "platform_admin"}),
            SideEffect.read,
            KnowledgeSearchInput,
            KnowledgeSearchOutput,
            30,
        ),
        knowledge_search,
    )
    registry.register(
        ToolDefinition(
            "chart.render",
            "Build chart specification",
            frozenset({"analyst", "org_admin", "platform_admin"}),
            SideEffect.read,
            ChartRenderInput,
            ChartRenderOutput,
            10,
        ),
        chart_render,
    )
    registry.register(
        ToolDefinition(
            "report.export",
            "Queue a report export",
            frozenset({"analyst", "org_admin", "platform_admin"}),
            SideEffect.export,
            ReportExportInput,
            ReportExportOutput,
            15,
        ),
        report_export,
    )
