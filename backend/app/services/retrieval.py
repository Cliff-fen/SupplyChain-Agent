import math

from pgvector.sqlalchemy import Vector
from sqlalchemy import cast, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Chunk, Document
from app.services.llm import OpenAICompatibleClient


class RetrievalError(RuntimeError):
    pass


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left or not right:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    return dot / (left_norm * right_norm) if left_norm and right_norm else 0.0


async def search_knowledge(
    session: AsyncSession, tenant_id: str, knowledge_base_id: str, query: str, limit: int = 5
) -> list[dict]:
    from app.rag.retrieval import AdvancedRetriever

    advanced = await AdvancedRetriever().search(
        session, tenant_id, knowledge_base_id, query, limit
    )
    return advanced.results


async def search_knowledge_dense_legacy(
    session: AsyncSession, tenant_id: str, knowledge_base_id: str, query: str, limit: int = 5
) -> list[dict]:
    vector = (await OpenAICompatibleClient().embed([query]))[0]
    query = (
        select(Chunk, Document)
        .join(Document, Chunk.document_id == Document.id)
        .where(
            Chunk.tenant_id == tenant_id,
            Document.tenant_id == tenant_id,
            Document.knowledge_base_id == knowledge_base_id,
            Document.status == "completed",
            Document.is_archived.is_(False),
        )
    )
    bind = session.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        dimensions = get_settings().embedding_dimension
        distance = cast(Chunk.embedding, Vector(dimensions)).cosine_distance(vector)
        rows = await session.execute(
            query.add_columns((1 - distance).label("score"))
            .where(Chunk.embedding.is_not(None))
            .order_by(distance)
            .limit(limit)
        )
        return [
            {
                "text": chunk.text,
                "score": round(float(score), 6),
                "document_id": document.id,
                "document_name": document.filename,
                "location": chunk.location,
                "chunk_id": chunk.id,
            }
            for chunk, document, score in rows.all()
        ]
    rows = await session.execute(query)
    ranked = [
        (cosine_similarity(vector, chunk.embedding), chunk, document)
        for chunk, document in rows.all()
        if chunk.embedding
    ]
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [
        {
            "text": chunk.text,
            "score": round(score, 6),
            "document_id": document.id,
            "document_name": document.filename,
            "location": chunk.location,
            "chunk_id": chunk.id,
        }
        for score, chunk, document in ranked[:limit]
    ]
