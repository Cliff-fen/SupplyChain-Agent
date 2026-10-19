from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import KnowledgeBase


async def get_for_tenant(
    session: AsyncSession, knowledge_base_id: str, tenant_id: str
) -> KnowledgeBase | None:
    return await session.scalar(
        select(KnowledgeBase).where(
            KnowledgeBase.id == knowledge_base_id,
            KnowledgeBase.tenant_id == tenant_id,
        )
    )
