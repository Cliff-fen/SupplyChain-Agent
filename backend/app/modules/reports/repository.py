from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Report


async def get_for_tenant(session: AsyncSession, report_id: str, tenant_id: str) -> Report | None:
    return await session.scalar(
        select(Report).where(Report.id == report_id, Report.tenant_id == tenant_id)
    )
