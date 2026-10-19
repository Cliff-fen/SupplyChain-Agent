from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def set_tenant_context(session: AsyncSession, tenant_id: str) -> None:
    if session.bind and session.bind.dialect.name == "postgresql":
        await session.execute(
            text("select set_config('app.tenant_id', :tenant_id, true)"), {"tenant_id": tenant_id}
        )


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
