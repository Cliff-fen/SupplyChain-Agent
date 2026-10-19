import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.models import AnalysisRun, Base, DashboardRefreshTask, IngestionTask, ReportExport
from app.services.task_watchdog import reconcile_stalled_tasks


def test_watchdog_requeues_stale_ingestion_once(tmp_path) -> None:
    async def run() -> None:
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'watchdog.db'}")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        created_at = datetime.now(UTC) - timedelta(minutes=30)
        async with sessions() as session:
            task = IngestionTask(
                tenant_id="tenant-watchdog",
                document_id="document-watchdog",
                task_key="watchdog-test-task",
                status="processing",
                attempts=1,
                max_attempts=3,
                created_at=created_at,
                updated_at=created_at,
            )
            session.add(task)
            await session.commit()
            retries = await reconcile_stalled_tasks(
                session,
                now=datetime.now(UTC),
                settings=Settings(
                    task_queued_timeout_seconds=60,
                    task_running_timeout_seconds=60,
                ),
            )
            restored = await session.scalar(select(IngestionTask).where(IngestionTask.id == task.id))
            assert restored is not None
            assert restored.status == "queued"
            assert "重新排队" in (restored.error_message or "")
            assert [retry.task_name for retry in retries] == ["supplymind.documents.ingest"]
        await engine.dispose()

    asyncio.run(run())


def test_watchdog_finishes_stale_non_idempotent_tasks(tmp_path) -> None:
    async def run() -> None:
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'lifecycle.db'}")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        stale = datetime.now(UTC) - timedelta(minutes=30)
        async with sessions() as session:
            dashboard = DashboardRefreshTask(tenant_id="tenant", status="running", started_at=stale)
            export = ReportExport(tenant_id="tenant", report_id="report", created_by="user", status="queued", created_at=stale)
            analysis = AnalysisRun(tenant_id="tenant", conversation_id="conversation", data_source_id="source", question="stale analysis", status="running", started_at=stale)
            session.add_all([dashboard, export, analysis])
            await session.commit()
            await reconcile_stalled_tasks(session, now=datetime.now(UTC), settings=Settings(task_queued_timeout_seconds=60, task_running_timeout_seconds=60))
            assert dashboard.status == "failed" and dashboard.finished_at is not None
            assert export.status == "failed" and export.finished_at is not None
            assert analysis.status == "failed" and analysis.finished_at is not None
            assert "连接中断" in (analysis.error_message or "")
        await engine.dispose()

    asyncio.run(run())
