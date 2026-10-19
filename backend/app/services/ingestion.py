from datetime import UTC, datetime
from pathlib import Path
from time import monotonic

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Chunk, ChunkTerm, Document, IngestionTask, KnowledgeCorpusStat
from app.rag.ranking import term_frequencies
from app.services.knowledge import chunk_text, classify_document, extract_text
from app.services.llm import OpenAICompatibleClient


async def process_ingestion(session: AsyncSession, task: IngestionTask, document: Document) -> None:
    """Idempotently process a persisted document. Safe to call from API or Celery."""
    started = monotonic()
    task.status = "processing"
    task.attempts += 1
    task.started_at = datetime.now(UTC)
    task.finished_at = None
    document.status = "processing"
    await session.flush()
    try:
        if not document.source_path:
            raise ValueError("Document source is unavailable")
        payload = Path(document.source_path).read_bytes()
        text, metadata = extract_text(document.filename, document.content_type, payload)
        document.category = classify_document(document.filename, text)
        old_chunk_ids = list(
            await session.scalars(select(Chunk.id).where(Chunk.document_id == document.id))
        )
        if old_chunk_ids:
            await session.execute(delete(ChunkTerm).where(ChunkTerm.chunk_id.in_(old_chunk_ids)))
        await session.execute(delete(Chunk).where(Chunk.document_id == document.id))
        parent_pieces = list(chunk_text(text, size=2400, overlap=240))
        pieces: list[tuple[Chunk, int, str, dict]] = []
        for parent_ordinal, parent_text, parent_location in parent_pieces:
            parent_location.update(metadata)
            parent = Chunk(
                tenant_id=document.tenant_id,
                document_id=document.id,
                level="parent",
                ordinal=parent_ordinal,
                text=parent_text,
                token_count=term_frequencies(parent_text)[1],
                location=parent_location,
                embedding=None,
            )
            session.add(parent)
            await session.flush()
            for child_ordinal, value, child_location in chunk_text(
                parent_text, size=600, overlap=80
            ):
                child_location = {
                    **metadata,
                    "parent_ordinal": parent_ordinal,
                    "child_ordinal": child_ordinal,
                    "start": parent_location["start"] + child_location["start"],
                    "end": parent_location["start"] + child_location["end"],
                }
                pieces.append((parent, child_ordinal, value, child_location))
        vectors = []
        settings = get_settings()
        if pieces:
            if (
                not settings.embedding_base_url
                or not settings.embedding_model
                or not settings.embedding_api_key
            ):
                raise ValueError(
                    "Embedding model configuration is required before a document can be searchable"
                )
            vectors = await OpenAICompatibleClient().embed([piece[2] for piece in pieces])
            if (
                vectors
                and session.get_bind() is not None
                and session.get_bind().dialect.name == "postgresql"
                and len(vectors[0]) != settings.embedding_dimension
            ):
                raise ValueError(
                    f"Embedding dimension {len(vectors[0])} does not match configured dimension {settings.embedding_dimension}"
                )
            document.embedding_model = settings.embedding_model
            document.embedding_dimension = len(vectors[0]) if vectors else None
        for index, (parent, ordinal, value, location) in enumerate(pieces):
            frequencies, token_count = term_frequencies(value)
            chunk = Chunk(
                tenant_id=document.tenant_id,
                document_id=document.id,
                parent_chunk_id=parent.id,
                level="child",
                ordinal=parent.ordinal * 10_000 + ordinal,
                text=value,
                token_count=token_count,
                location=location,
                embedding=vectors[index] if vectors else None,
            )
            session.add(chunk)
            await session.flush()
            session.add_all(
                ChunkTerm(
                    tenant_id=document.tenant_id,
                    knowledge_base_id=document.knowledge_base_id,
                    chunk_id=chunk.id,
                    term=term,
                    term_frequency=count,
                    document_length=token_count,
                )
                for term, count in frequencies.items()
            )
        await session.flush()
        child_count, average_length = (
            await session.execute(
                select(func.count(Chunk.id), func.avg(Chunk.token_count))
                .join(Document, Chunk.document_id == Document.id)
                .where(
                    Chunk.tenant_id == document.tenant_id,
                    Chunk.level == "child",
                    Document.knowledge_base_id == document.knowledge_base_id,
                    Document.is_archived.is_(False),
                )
            )
        ).one()
        corpus = await session.scalar(
            select(KnowledgeCorpusStat).where(
                KnowledgeCorpusStat.tenant_id == document.tenant_id,
                KnowledgeCorpusStat.knowledge_base_id == document.knowledge_base_id,
            )
        )
        if corpus is None:
            corpus = KnowledgeCorpusStat(
                tenant_id=document.tenant_id,
                knowledge_base_id=document.knowledge_base_id,
                index_version=1,
            )
            session.add(corpus)
        else:
            corpus.index_version += 1
        corpus.child_chunk_count = int(child_count or 0)
        corpus.average_document_length = float(average_length or 0)
        document.status = "completed"
        task.status = "completed"
        task.error_message = None
        task.dead_letter = False
    except Exception as exc:
        document.status = "failed"
        document.error_message = str(exc)
        task.status = "failed"
        task.error_message = str(exc)
        task.dead_letter = task.attempts >= task.max_attempts
        raise
    finally:
        task.elapsed_ms = int((monotonic() - started) * 1000)
        task.finished_at = datetime.now(UTC)
