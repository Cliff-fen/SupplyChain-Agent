import asyncio
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agents import executor
from app.agents.executor import EnterpriseAnalysisExecutor
from app.models import AnalysisRun, Base
from app.schemas import Principal
from app.services import events


def test_retry_keeps_event_stream_open_until_final_completion(monkeypatch, tmp_path):
    async def exercise():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'retry.db'}")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(executor, "SessionLocal", sessions)
        monkeypatch.setattr(events, "SessionLocal", sessions)
        async with sessions() as session:
            session.add(AnalysisRun(
                id="run", tenant_id="tenant", conversation_id="conversation",
                data_source_id="source", question="统计订单", status="running", attempts=1,
            ))
            await session.commit()
        stream = events.stream_events("run", "tenant")
        try:
            await EnterpriseAnalysisExecutor()._persist_failure(
                "run", "tenant", TimeoutError(), retry_pending=True,
            )
            retry = await anext(stream)
            assert "event: retry_scheduled" in retry
            next_event = asyncio.create_task(anext(stream))
            await asyncio.wait({next_event}, timeout=0.05)
            assert not next_event.done(), "An automatic retry must not terminate SSE"
            async with sessions() as session:
                run = await session.scalar(select(AnalysisRun).where(AnalysisRun.id == "run"))
                assert run.status == "queued" and run.finished_at is None
                assert run.error_message == "TimeoutError"
                run.status = "completed"
                await events.append_event(session, run, "completed", {"run_id": run.id})
            assert "event: completed" in await asyncio.wait_for(next_event, timeout=2)
            assert [event async for event in stream] == []
        finally:
            await stream.aclose()
            await engine.dispose()

    monkeypatch.setenv("SUPPLYMIND_REDIS_URL", "redis://127.0.0.1:1/0")
    from app.core.config import get_settings

    get_settings.cache_clear()
    try:
        asyncio.run(exercise())
    finally:
        get_settings.cache_clear()


@pytest.mark.parametrize("memory_failure", [False, True])
def test_completion_status_is_not_visible_before_its_stream_event(monkeypatch, tmp_path, memory_failure):
    async def exercise():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'completion.db'}")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(executor, "SessionLocal", sessions)
        monkeypatch.setattr(events, "SessionLocal", sessions)
        extracting, release = asyncio.Event(), asyncio.Event()

        async def enabled(*_):
            return True

        async def extract_memories(*_):
            extracting.set()
            await release.wait()
            if memory_failure:
                raise RuntimeError("Optional memory model is unavailable")
            return []

        monkeypatch.setattr(executor.MemoryService, "enabled", enabled)
        async with sessions() as session:
            session.add(AnalysisRun(
                id="run", tenant_id="tenant", conversation_id="conversation",
                data_source_id="source", question="统计订单", status="running", attempts=1,
            ))
            await session.commit()
        service = EnterpriseAnalysisExecutor(client=SimpleNamespace(extract_memories=extract_memories))
        stream = events.stream_events("run", "tenant")
        persistence = asyncio.create_task(service._persist_success(
            "run", Principal(user_id="user", tenant_id="tenant", role="org_admin"),
            {"route": "data", "answer": {"direct_answer": "已核对来源", "rows": [{"count": 3}]}},
        ))
        next_event = None
        try:
            await asyncio.wait_for(extracting.wait(), timeout=2)
            async with sessions() as session:
                run = await session.get(AnalysisRun, "run")
                assert run.status == "running", "Terminal status must not precede its result event"
            next_event = asyncio.create_task(anext(stream))
            await asyncio.wait({next_event}, timeout=0.05)
            assert not next_event.done(), "Memory extraction must not cause SSE to terminate early"
            release.set()
            await asyncio.wait_for(persistence, timeout=2)
            received = [await asyncio.wait_for(next_event, timeout=2)]
            received.extend([event async for event in stream])
            assert any("event: completed" in event and "已核对来源" in event for event in received)
            async with sessions() as session:
                saved_run = await session.get(AnalysisRun, "run")
                assert saved_run.status == "completed"
                assert saved_run.result["report_id"]
        finally:
            release.set()
            await persistence
            if next_event and not next_event.done():
                next_event.cancel()
                await asyncio.gather(next_event, return_exceptions=True)
            await stream.aclose()
            await engine.dispose()

    monkeypatch.setenv("SUPPLYMIND_REDIS_URL", "redis://127.0.0.1:1/0")
    from app.core.config import get_settings

    get_settings.cache_clear()
    try:
        asyncio.run(exercise())
    finally:
        get_settings.cache_clear()
