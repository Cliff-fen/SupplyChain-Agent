from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DataSource


async def get_for_tenant(
    session: AsyncSession, source_id: str, tenant_id: str
) -> DataSource | None:
    return await session.scalar(
        select(DataSource).where(DataSource.id == source_id, DataSource.tenant_id == tenant_id)
    )
