import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.mcp_runtime.security import issue_tool_context
from app.models import AuditEvent, Base, Membership
from app.schemas import Principal


@pytest.mark.asyncio
async def test_every_mcp_tool_checks_current_membership_and_audits_denial(monkeypatch, tmp_path):
    from app import mcp_server

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'mcp-policy.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(mcp_server, "SessionLocal", sessions)
    token = issue_tool_context(Principal(user_id="u", tenant_id="t", role="org_admin"), run_id="r")
    async with sessions() as session:
        session.add(Membership(organization_id="t", user_id="u", role="analyst", is_active=True))
        await session.commit()
    assert (await mcp_server.chart_render(token, [{"factory": "A", "count": 3}]))["spec"]["y"] == "count"
    async with sessions() as session:
        member = await session.scalar(select(Membership))
        member.role = "viewer"
        await session.commit()
    with pytest.raises(PermissionError):
        await mcp_server.chart_render(token, [])
    async with sessions() as session:
        rows = list(await session.scalars(select(AuditEvent).order_by(AuditEvent.occurred_at, AuditEvent.id)))
        # SQLite's server timestamp has second precision; UUID order is not
        # call order when both audit rows were written within the same second.
        assert sorted(row.details["status"] for row in rows) == ["error", "success"]
        assert all(row.details["run_id"] == "r" for row in rows)
        assert all(token not in str(row.details) for row in rows)
    await engine.dispose()
