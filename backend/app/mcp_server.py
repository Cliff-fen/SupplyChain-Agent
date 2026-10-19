"""SupplyMind's standards-compliant MCP Server."""

import inspect
from functools import wraps
from hashlib import sha256
from typing import Annotated

import jwt
from fastapi.encoders import jsonable_encoder
from mcp.server.fastmcp import FastMCP
from opentelemetry import trace
from opentelemetry.propagate import extract
from pydantic import Field
from sqlalchemy import select

from app.agents.middleware import ROLE_TOOLS
from app.core.config import get_settings
from app.core.sql_guard import validate_read_only_sql
from app.db import SessionLocal, set_tenant_context
from app.mcp_runtime.security import issue_tool_context, verify_tool_context
from app.models import AgentApproval, DataSource, Membership, Report
from app.observability import genai_span
from app.rag.retrieval import AdvancedRetriever
from app.services.audit import audit
from app.services.datasource import execute_guarded_query, synchronize_schema

mcp = FastMCP("SupplyMind Enterprise Tools", host="0.0.0.0", port=8001)


def enterprise_tool(*, name: str, description: str):
    """Apply the same role policy and durable audit to every protocol tool."""
    def register(function):
        signature = inspect.signature(function)

        @wraps(function)
        async def invoke(*args, **kwargs):
            arguments = signature.bind(*args, **kwargs).arguments
            token = arguments["context_token"]
            principal = verify_tool_context(token)
            claims = jwt.decode(token, get_settings().mcp_service_secret,
                                algorithms=["HS256"], audience="supplymind-mcp")
            failure = None
            try:
                async with SessionLocal() as session:
                    await set_tenant_context(session, principal.tenant_id)
                    membership = await session.scalar(select(Membership).where(
                        Membership.organization_id == principal.tenant_id,
                        Membership.user_id == principal.user_id,
                        Membership.is_active.is_(True),
                    ))
                if (membership is None
                    or name not in ROLE_TOOLS.get(membership.role, frozenset())
                    or name not in ROLE_TOOLS.get(principal.role, frozenset())):
                    raise PermissionError("Role cannot invoke this tool")
                # Membership changes take effect even while an older signed
                # context remains within its 90-second validity window.
                principal.role = membership.role
                bound = signature.bind(*args, **kwargs)
                bound.arguments["context_token"] = issue_tool_context(
                    principal, run_id=claims.get("run_id")
                )
                return await function(*bound.args, **bound.kwargs)
            except Exception as exc:
                failure = exc
                raise
            finally:
                context = trace.get_current_span().get_span_context()
                details = {
                    "tool": name, "run_id": claims.get("run_id"),
                    "status": "error" if failure else "success",
                    "error_type": type(failure).__name__ if failure else None,
                    "resource_ids": {key: value for key, value in arguments.items()
                                     if key in {"data_source_id", "knowledge_base_id", "report_id"}},
                }
                if context.is_valid:
                    details["trace_id"] = f"{context.trace_id:032x}"
                if isinstance(arguments.get("sql"), str):
                    details["sql_sha256"] = sha256(arguments["sql"].encode()).hexdigest()
                async with SessionLocal() as session:
                    await set_tenant_context(session, principal.tenant_id)
                    await audit(session, principal.tenant_id, principal.user_id,
                                "mcp.tool.call", "mcp_tool", name, details)
                    await session.commit()

        @wraps(function)
        async def guarded(*args, **kwargs):
            arguments = signature.bind(*args, **kwargs).arguments
            token = arguments["context_token"]
            verify_tool_context(token)
            claims = jwt.decode(token, get_settings().mcp_service_secret,
                                algorithms=["HS256"], audience="supplymind-mcp")
            carrier = {"traceparent": claims["traceparent"]} if claims.get("traceparent") else {}
            with genai_span("mcp.tool.server", {
                "rpc.system": "mcp", "rpc.method": name,
                "supplymind.run.id": claims.get("run_id"),
            }, context=extract(carrier)):
                return await invoke(*args, **kwargs)

        mcp.tool(name=name, description=description)(guarded)
        return guarded
    return register


@enterprise_tool(name="schema.lookup", description="Read an approved tenant datasource schema")
async def schema_lookup(context_token: str, data_source_id: str) -> dict:
    principal = verify_tool_context(context_token)
    async with SessionLocal() as session:
        await set_tenant_context(session, principal.tenant_id)
        source = await session.scalar(
            select(DataSource).where(
                DataSource.id == data_source_id,
                DataSource.tenant_id == principal.tenant_id,
            )
        )
        if not source:
            raise ValueError("Data source not found")
        schema = await synchronize_schema(source)
        return {"tables": schema.tables}


@enterprise_tool(name="sql.query", description="Execute SQL after SupplyMind's mandatory read-only guard")
async def sql_query(context_token: str, data_source_id: str, sql: str) -> dict:
    principal = verify_tool_context(context_token)
    if principal.role not in {"analyst", "org_admin", "platform_admin"}:
        raise PermissionError("Role cannot query data")
    async with SessionLocal() as session:
        await set_tenant_context(session, principal.tenant_id)
        source = await session.scalar(
            select(DataSource).where(
                DataSource.id == data_source_id,
                DataSource.tenant_id == principal.tenant_id,
            )
        )
        if not source:
            raise ValueError("Data source not found")
        guarded = validate_read_only_sql(
            sql, set(source.allowed_tables), get_settings().sql_max_rows
        )
        _, rows = await execute_guarded_query(source, guarded.sql)
        # Convert database Decimal/date values before MCP serializes them.
        # Otherwise Decimal becomes a string and chart tools lose numeric columns.
        return {"sql": guarded.sql, "tables": guarded.tables, "rows": jsonable_encoder(rows)}


@enterprise_tool(name="knowledge.search", description="Run SupplyMind's Advanced RAG retrieval pipeline")
async def knowledge_search(
    context_token: str, knowledge_base_id: str,
    query: Annotated[str, Field(min_length=2, max_length=4000)],
    limit: Annotated[int, Field(ge=1, le=20)] = 8,
) -> dict:
    principal = verify_tool_context(context_token)
    async with SessionLocal() as session:
        await set_tenant_context(session, principal.tenant_id)
        result = await AdvancedRetriever().search(
            session, principal.tenant_id, knowledge_base_id, query, limit
        )
        return {
            "results": result.results,
            "trace": result.trace,
            "degraded": result.degraded,
            "warnings": result.warnings,
        }


@enterprise_tool(name="chart.render", description="Build a safe chart specification from query rows")
async def chart_render(context_token: str, rows: list[dict]) -> dict:
    verify_tool_context(context_token)
    if not rows:
        return {"spec": {"type": "table"}}
    fields = list(rows[0])
    numeric = next(
        (field for field, value in rows[0].items() if isinstance(value, (int, float))),
        fields[-1],
    )
    return {"spec": {"type": "bar", "x": fields[0], "y": numeric}}


@enterprise_tool(
    name="report.export", description="Request a report export; execution requires human approval"
)
async def report_export(context_token: str, report_id: str, format: str = "pdf") -> dict:
    principal = verify_tool_context(context_token)
    if format != "pdf":
        raise ValueError("Only PDF export is supported")
    async with SessionLocal() as session:
        await set_tenant_context(session, principal.tenant_id)
        report = await session.scalar(
            select(Report).where(
                Report.id == report_id,
                Report.tenant_id == principal.tenant_id,
            )
        )
        if not report:
            raise ValueError("Report not found")
        approval = AgentApproval(
            tenant_id=principal.tenant_id,
            analysis_run_id=report.analysis_run_id,
            tool_name="report.export",
            side_effect="export",
            request_payload={"report_id": report_id, "format": format},
            requested_by=principal.user_id,
        )
        session.add(approval)
        await session.commit()
        await session.refresh(approval)
    return {
        "approval_id": approval.id,
        "report_id": report_id,
        "format": format,
        "status": "approval_required",
        "side_effect": "export",
        "requested_by": principal.user_id,
    }
