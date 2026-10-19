import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import AgentApproval, Base, OutboxEvent, Report, ReportExport
from app.schemas import ApprovalDecision, Principal


def test_approved_export_commits_durable_outbox_before_worker_dispatch(monkeypatch, tmp_path):
    monkeypatch.setenv("SUPPLYMIND_INGESTION_MODE", "broker")
    from app.core.config import get_settings

    get_settings.cache_clear()
    from app.api import _decide_approval
    from scripts.worker import celery_app

    def premature_dispatch(*args, **kwargs):
        raise AssertionError("Approval must commit an outbox entry before dispatch")

    monkeypatch.setattr(celery_app, "send_task", premature_dispatch)

    async def exercise():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'approval.db'}")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            session.add(Report(
                id="report", tenant_id="tenant", analysis_run_id="run",
                title="报告", markdown="# 报告", created_by="admin",
            ))
            session.add(AgentApproval(
                id="approval", tenant_id="tenant", analysis_run_id="run",
                tool_name="report.export", requested_by="admin",
                request_payload={"report_id": "report"},
            ))
            await session.commit()
            decision = await _decide_approval(
                "approval", True, ApprovalDecision(reason="验收"), session,
                Principal(user_id="admin", tenant_id="tenant", role="org_admin"),
            )
            assert decision.status == "approved"
        async with sessions() as session:
            export = await session.scalar(select(ReportExport))
            event = await session.scalar(select(OutboxEvent))
            assert export.status == "queued" and export.celery_task_id is None
            assert event.aggregate_id == export.id
            assert event.event_type == "report.pdf_export_requested"
            assert event.payload == {"export_id": export.id}
            assert event.status == "pending"
        await engine.dispose()

    try:
        asyncio.run(exercise())
    finally:
        get_settings.cache_clear()
