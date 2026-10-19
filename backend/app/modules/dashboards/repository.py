from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Dashboard


async def get_dashboard(session: AsyncSession, tenant_id: str, slug: str) -> Dashboard | None:
    return await session.scalar(
        select(Dashboard).where(Dashboard.tenant_id == tenant_id, Dashboard.slug == slug)
    )


async def save_dashboard(session: AsyncSession, dashboard: Dashboard) -> Dashboard:
    session.add(dashboard)
    await session.flush()
    return dashboard
