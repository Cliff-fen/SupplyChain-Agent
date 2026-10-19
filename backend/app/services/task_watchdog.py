"""Recover persisted tasks that would otherwise remain permanently in progress."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.models import (
    AnalysisRun,
    AuditEvent,
    DashboardRefreshTask,
    DataSourceSyncTask,
    Document,
    IngestionTask,
    ReportExport,
)


@dataclass(frozen=True)
class RetryRequest:
    task_name: str
    args: tuple[object, ...]


def _expired(value: datetime | None, cutoff: datetime) -> bool:
    if value is None:
        return False
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value <= cutoff


async def reconcile_stalled_tasks(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    settings: Settings | None = None,
) -> list[RetryRequest]:
    """Make stale work visible and only requeue idempotent document ingestion.

    Schema sync, dashboard refresh and PDF export remain explicitly retryable by
    the user. This avoids silently repeating external I/O after a worker crash.
    """
    settings = settings or get_settings()
    now = now or datetime.now(UTC)
    queued_cutoff = now - timedelta(seconds=settings.task_queued_timeout_seconds)
    running_cutoff = now - timedelta(seconds=settings.task_running_timeout_seconds)
    retries: list[RetryRequest] = []

    ingestion_tasks = list(
        await session.scalars(
            select(IngestionTask).where(IngestionTask.status.in_(["queued", "processing"]))
        )
    )
    for task in ingestion_tasks:
        previous_status = task.status
        reference = task.updated_at or task.created_at
        cutoff = queued_cutoff if task.status == "queued" else running_cutoff
        if not _expired(reference, cutoff):
            continue
        if task.attempts < task.max_attempts:
            task.status = "queued"
            task.next_retry_at = now
            task.error_message = "摄取任务超时，已由看门狗重新排队"
            retries.append(RetryRequest("supplymind.documents.ingest", (task.id,)))
            action = "task.watchdog_requeued"
        else:
            task.status = "failed"
            task.dead_letter = True
            task.error_message = "摄取任务超时且已达到最大尝试次数，已转入死信队列"
            document = await session.scalar(select(Document).where(Document.id == task.document_id))
            if document:
                document.status = "failed"
                document.error_message = task.error_message
            action = "task.watchdog_dead_lettered"
        session.add(
            AuditEvent(
                tenant_id=task.tenant_id,
                actor_id=None,
                action=action,
                resource_type="ingestion_task",
                resource_id=task.id,
                details={"previous_status": previous_status},
            )
        )

    for model, resource_type in (
        (DataSourceSyncTask, "data_source_sync_task"),
        (DashboardRefreshTask, "dashboard_refresh_task"),
        (ReportExport, "report_export"),
    ):
        rows = list(await session.scalars(select(model).where(model.status.in_(["queued", "running"]))))
        for task in rows:
            reference = getattr(task, "started_at", None) if task.status == "running" else None
            reference = reference or task.created_at
            cutoff = running_cutoff if task.status == "running" else queued_cutoff
            if not _expired(reference, cutoff):
                continue
            task.status = "failed"
            task.error_message = "任务超时，未自动重复外部操作；请检查原因后重试"
            if hasattr(task, "finished_at"):
                task.finished_at = now
            session.add(
                AuditEvent(
                    tenant_id=task.tenant_id,
                    actor_id=None,
                    action="task.watchdog_failed",
                    resource_type=resource_type,
                    resource_id=task.id,
                    details={"reason": "timeout"},
                )
            )

    analysis_runs = list(
        await session.scalars(select(AnalysisRun).where(AnalysisRun.status.in_(["queued", "running"])))
    )
    for run in analysis_runs:
        reference = run.started_at if run.status == "running" else None
        reference = reference or run.created_at
        cutoff = running_cutoff if run.status == "running" else queued_cutoff
        if not _expired(reference, cutoff):
            continue
        run.status = "failed"
        run.finished_at = now
        run.error_message = "分析运行超时或连接中断，请重试。"
        result = dict(run.result or {})
        result["error"] = "分析运行超时或连接中断，请重试。"
        result["failure_reason"] = "watchdog_timeout"
        run.result = result
        session.add(
            AuditEvent(
                tenant_id=run.tenant_id,
                actor_id=None,
                action="analysis.watchdog_failed",
                resource_type="analysis_run",
                resource_id=run.id,
                details={"reason": "timeout"},
            )
        )

    await session.commit()
    return retries
