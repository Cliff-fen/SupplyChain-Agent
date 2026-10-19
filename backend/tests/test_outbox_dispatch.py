import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Base, OutboxEvent


def test_outbox_dispatches_ingestion_and_recovers_expired_lease(monkeypatch, tmp_path) -> None:
    async def setup():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'outbox.db'}")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            session.add_all(
                [
                    OutboxEvent(
                        tenant_id="tenant-1",
                        aggregate_type="ingestion_task",
                        aggregate_id="task-queued",
                        event_type="document.ingestion_requested",
                        payload={"task_id": "task-queued"},
                    ),
                    OutboxEvent(
                        tenant_id="tenant-1",
                        aggregate_type="ingestion_task",
                        aggregate_id="task-expired",
                        event_type="document.ingestion_requested",
                        payload={"task_id": "task-expired"},
                        status="processing",
                        available_at=datetime.now(UTC) - timedelta(seconds=1),
                    ),
                ]
            )
            await session.commit()
        return engine, sessions

    engine, sessions = asyncio.run(setup())
    from scripts import worker

    sent: list[tuple[str, list[str], str]] = []
    monkeypatch.setattr(worker, "SessionLocal", sessions)
    monkeypatch.setattr(
        worker.celery_app,
        "send_task",
        lambda name, args, queue: sent.append((name, args, queue))
        or SimpleNamespace(id=f"celery-{len(sent)}"),
    )

    assert worker.dispatch_outbox.run() == 2
    assert sent == [
        ("supplymind.documents.ingest", ["task-queued"], "analysis"),
        ("supplymind.documents.ingest", ["task-expired"], "analysis"),
    ]

    async def verify() -> None:
        async with sessions() as session:
            rows = list(await session.scalars(select(OutboxEvent).order_by(OutboxEvent.aggregate_id)))
            assert [row.status for row in rows] == ["completed", "completed"]
            assert [row.attempts for row in rows] == [1, 1]
        await engine.dispose()

    asyncio.run(verify())
