from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import KnowledgeBase
from app.modules.knowledge.repository import get_for_tenant
from app.services.retrieval import search_knowledge


async def get_tenant_knowledge_base(
    session: AsyncSession, knowledge_base_id: str, tenant_id: str
) -> KnowledgeBase:
    knowledge_base = await get_for_tenant(session, knowledge_base_id, tenant_id)
    if not knowledge_base:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found"
        )
    return knowledge_base


async def search_tenant_knowledge(
    session: AsyncSession, tenant_id: str, knowledge_base_id: str, query: str, limit: int
) -> list[dict]:
    return await search_knowledge(session, tenant_id, knowledge_base_id, query, limit)
