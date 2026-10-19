"""Lifecycle-managed factories for Checkpointer, Store and Agent clients."""

from contextlib import AsyncExitStack
from dataclasses import dataclass, field

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from app.core.config import get_settings


def checkpoint_dsn(database_url: str) -> str:
    return database_url.replace("postgresql+psycopg://", "postgresql://", 1).replace(
        "postgresql+asyncpg://", "postgresql://", 1
    )


@dataclass
class RuntimeContainer:
    checkpointer: object | None = None
    store: object | None = None
    _stack: AsyncExitStack = field(default_factory=AsyncExitStack)

    async def start(self) -> None:
        settings = get_settings()
        if settings.database_url.startswith("postgresql"):
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
            from langgraph.store.postgres.aio import AsyncPostgresStore

            dsn = checkpoint_dsn(settings.database_url)
            self.checkpointer = await self._stack.enter_async_context(
                AsyncPostgresSaver.from_conn_string(dsn)
            )
            self.store = await self._stack.enter_async_context(
                AsyncPostgresStore.from_conn_string(dsn)
            )
            await self.checkpointer.setup()
            await self.store.setup()
        else:
            self.checkpointer = InMemorySaver()
            self.store = InMemoryStore()

    async def stop(self) -> None:
        await self._stack.aclose()
        self.checkpointer = None
        self.store = None


runtime = RuntimeContainer()
