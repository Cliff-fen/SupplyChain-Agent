import asyncio
import json
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

from redis.exceptions import RedisError
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db import SessionLocal
from app.models import AnalysisEvent, AnalysisRun, OutboxEvent

TERMINAL_RUN_STATUSES = frozenset({"completed", "failed", "cancelled", "rejected"})


def encode_sse(event: AnalysisEvent) -> str:
    return (
        f"id: {event.sequence}\n"
        f"event: {event.event_type}\n"
        f"data: {json.dumps(event.payload, ensure_ascii=False, default=str)}\n\n"
    )


async def append_event(
    session: AsyncSession,
    run: AnalysisRun,
    event_type: str,
    payload: dict,
    *,
    commit: bool = True,
) -> AnalysisEvent:
    if session.get_bind() is not None and session.get_bind().dialect.name == "postgresql":
        await session.execute(
            text("select set_config('app.tenant_id', :tenant_id, true)"),
            {"tenant_id": run.tenant_id},
        )
    # Send branches emit concurrently. Let the database allocate the sequence
    # so independently scoped sessions cannot reuse a stale ORM value.
    sequence = await session.scalar(
        update(AnalysisRun)
        .where(AnalysisRun.id == run.id, AnalysisRun.tenant_id == run.tenant_id)
        .values(last_event_sequence=AnalysisRun.last_event_sequence + 1)
        .returning(AnalysisRun.last_event_sequence)
    )
    if sequence is None:
        raise LookupError("Analysis run not found while appending event")
    run.last_event_sequence = sequence
    event = AnalysisEvent(
        tenant_id=run.tenant_id,
        analysis_run_id=run.id,
        sequence=sequence,
        event_type=event_type,
        payload=payload,
    )
    session.add(event)
    if commit:
        await session.commit()
    else:
        await session.flush()
    try:
        import redis.asyncio as redis

        client = redis.from_url(get_settings().redis_url, decode_responses=True)
        await client.publish(
            f"supplymind:analysis:{run.id}",
            json.dumps({"sequence": event.sequence, "event": event_type}),
        )
        await client.aclose()
    except (ImportError, OSError, RuntimeError, RedisError):
        pass
    return event


async def stream_events(
    run_id: str, tenant_id: str, after_sequence: int = 0
) -> AsyncGenerator[str, None]:
    settings = get_settings()
    cursor = after_sequence
    last_heartbeat = asyncio.get_running_loop().time()
    while True:
        async with SessionLocal() as session:
            if session.get_bind() is not None and session.get_bind().dialect.name == "postgresql":
                await session.execute(
                    text("select set_config('app.tenant_id', :tenant_id, true)"),
                    {"tenant_id": tenant_id},
                )
            run = await session.scalar(
                select(AnalysisRun).where(
                    AnalysisRun.id == run_id, AnalysisRun.tenant_id == tenant_id
                )
            )
            if not run:
                return
            events = list(
                await session.scalars(
                    select(AnalysisEvent)
                    .where(
                        AnalysisEvent.analysis_run_id == run_id,
                        AnalysisEvent.tenant_id == tenant_id,
                        AnalysisEvent.sequence > cursor,
                    )
                    .order_by(AnalysisEvent.sequence)
                )
            )
            for event in events:
                cursor = event.sequence
                yield encode_sse(event)
            if run.status in TERMINAL_RUN_STATUSES and cursor >= run.last_event_sequence:
                return
        now = asyncio.get_running_loop().time()
        if now - last_heartbeat >= settings.analysis_sse_heartbeat_seconds:
            last_heartbeat = now
            yield ": heartbeat\n\n"
        await asyncio.sleep(settings.analysis_event_poll_seconds)


def create_outbox_event(run: AnalysisRun, event_type: str, payload: dict) -> OutboxEvent:
    return create_background_task_event(
        tenant_id=run.tenant_id,
        aggregate_type="analysis_run",
        aggregate_id=run.id,
        event_type=event_type,
        payload=payload,
    )


def create_background_task_event(
    *,
    tenant_id: str,
    aggregate_type: str,
    aggregate_id: str,
    event_type: str,
    payload: dict,
) -> OutboxEvent:
    """Create work that is committed with its domain record before dispatch."""
    return OutboxEvent(
        tenant_id=tenant_id,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        event_type=event_type,
        payload=payload,
        available_at=datetime.now(UTC),
    )
