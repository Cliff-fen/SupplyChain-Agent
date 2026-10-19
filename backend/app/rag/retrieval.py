from dataclasses import dataclass, field
from time import perf_counter

import httpx
from pgvector.sqlalchemy import Vector
from sqlalchemy import cast, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Chunk, ChunkTerm, Document, KnowledgeCorpusStat
from app.observability import RAG_STAGE_DURATION, genai_span
from app.rag.ranking import bm25_score, reciprocal_rank_fusion, tokenize
from app.services.llm import ModelConfigurationError, ModelResponseError, OpenAICompatibleClient


@dataclass
class AdvancedRetrievalResult:
    results: list[dict]
    trace: list[dict] = field(default_factory=list)
    degraded: bool = False
    warnings: list[str] = field(default_factory=list)


class AdvancedRetriever:
    def __init__(self, client: OpenAICompatibleClient | None = None) -> None:
        self.client = client or OpenAICompatibleClient()

    async def search(
        self,
        session: AsyncSession,
        tenant_id: str,
        knowledge_base_id: str,
        query: str,
        limit: int | None = None,
    ) -> AdvancedRetrievalResult:
        settings = get_settings()
        trace: list[dict] = []
        warnings: list[str] = []
        started = perf_counter()
        try:
            with genai_span(
                "rag.query_optimization",
                {"rag.multi_query_count": settings.rag_multi_query_count},
            ):
                optimized = await self.client.optimize_retrieval_query(
                    query, settings.rag_multi_query_count
                )
            query_variants = [query, *optimized.get("queries", [])]
            bm25_queries = list(query_variants)
            hypothetical = optimized.get("hypothetical_answer")
            if hypothetical:
                query_variants.append(hypothetical)
        except (ModelResponseError, RuntimeError, ValueError, httpx.HTTPError) as exc:
            query_variants = [query]
            bm25_queries = [query]
            warnings.append(f"query_optimization_failed:{type(exc).__name__}")
        query_variants = list(
            dict.fromkeys(item.strip() for item in query_variants if item.strip())
        )
        trace.append(
            {
                "stage": "query_optimization",
                "query_count": len(query_variants),
                "elapsed_ms": int((perf_counter() - started) * 1000),
            }
        )
        RAG_STAGE_DURATION.labels("query_optimization").observe(perf_counter() - started)

        dense_rankings: list[list[str]] = []
        bm25_rankings: list[list[str]] = []
        candidates: dict[str, dict] = {}
        dense_started = perf_counter()
        for variant in query_variants:
            try:
                # Savepoints allow lexical retrieval to continue after an
                # optional vector/index error without an aborted SQL transaction.
                async with session.begin_nested():
                    with genai_span(
                        "rag.dense_retrieval", {"rag.top_k": settings.rag_dense_top_k}
                    ):
                        ranking, details = await self._dense_rank(
                            session, tenant_id, knowledge_base_id, variant, settings.rag_dense_top_k
                        )
                dense_rankings.append(ranking)
                candidates.update(details)
            except ModelConfigurationError:
                raise
            except (ModelResponseError, httpx.HTTPError, SQLAlchemyError) as exc:
                warnings.append(f"dense_retrieval_failed:{type(exc).__name__}")
                break
        trace.append(
            {
                "stage": "dense_retrieval",
                "candidate_count": len({item for ranking in dense_rankings for item in ranking}),
                "elapsed_ms": int((perf_counter() - dense_started) * 1000),
            }
        )
        RAG_STAGE_DURATION.labels("dense_retrieval").observe(perf_counter() - dense_started)

        bm25_started = perf_counter()
        for variant in dict.fromkeys(bm25_queries):
            try:
                async with session.begin_nested():
                    with genai_span(
                        "rag.bm25_retrieval", {"rag.top_k": settings.rag_bm25_top_k}
                    ):
                        ranking, scores = await self._bm25_rank(
                            session, tenant_id, knowledge_base_id, variant, settings.rag_bm25_top_k
                        )
                bm25_rankings.append(ranking)
                for identifier, score in scores.items():
                    candidates.setdefault(identifier, {})["bm25_score"] = round(score, 6)
            except SQLAlchemyError as exc:
                warnings.append(f"bm25_retrieval_failed:{type(exc).__name__}")
                break
        if not dense_rankings and not bm25_rankings:
            raise ModelResponseError("All knowledge retrieval backends failed")
        trace.append(
            {
                "stage": "bm25_retrieval",
                "candidate_count": len({item for ranking in bm25_rankings for item in ranking}),
                "elapsed_ms": int((perf_counter() - bm25_started) * 1000),
            }
        )
        RAG_STAGE_DURATION.labels("bm25_retrieval").observe(perf_counter() - bm25_started)

        fusion_started = perf_counter()
        fused = reciprocal_rank_fusion([*dense_rankings, *bm25_rankings], k=settings.rag_rrf_k)[
            : settings.rag_fusion_top_k
        ]
        fused_ids = [identifier for identifier, _ in fused]
        for identifier, score in fused:
            candidates.setdefault(identifier, {})["rrf_score"] = round(score, 6)
        trace.append(
            {
                "stage": "rrf_fusion",
                "candidate_count": len(fused_ids),
                "elapsed_ms": int((perf_counter() - fusion_started) * 1000),
            }
        )
        RAG_STAGE_DURATION.labels("rrf_fusion").observe(perf_counter() - fusion_started)

        rows = await self._load_candidates(
            session, tenant_id, knowledge_base_id, fused_ids, candidates
        )
        rerank_started = perf_counter()
        try:
            with genai_span("rag.rerank", {"rag.candidate_count": len(rows)}):
                ordered_ids = await self.client.rerank(
                    query, rows, settings.rag_rerank_top_k
                )
            order = {identifier: index for index, identifier in enumerate(ordered_ids)}
            rows.sort(key=lambda item: order.get(item["chunk_id"], len(order)))
        except (ModelResponseError, RuntimeError, ValueError, httpx.HTTPError) as exc:
            warnings.append(f"rerank_failed:{type(exc).__name__}")
        rows = rows[: (limit or settings.rag_rerank_top_k)]
        trace.append(
            {
                "stage": "llm_rerank",
                "result_count": len(rows),
                "elapsed_ms": int((perf_counter() - rerank_started) * 1000),
            }
        )
        RAG_STAGE_DURATION.labels("rerank").observe(perf_counter() - rerank_started)

        parent_started = perf_counter()
        await self._map_parent_context(session, tenant_id, rows)
        trace.append(
            {
                "stage": "parent_context_mapping",
                "result_count": len(rows),
                "elapsed_ms": int((perf_counter() - parent_started) * 1000),
            }
        )
        RAG_STAGE_DURATION.labels("parent_context_mapping").observe(
            perf_counter() - parent_started
        )
        return AdvancedRetrievalResult(
            results=rows,
            trace=trace,
            degraded=bool(warnings),
            warnings=warnings,
        )

    async def _dense_rank(
        self,
        session: AsyncSession,
        tenant_id: str,
        knowledge_base_id: str,
        query_text: str,
        limit: int,
    ) -> tuple[list[str], dict[str, dict]]:
        vector = (await self.client.embed([query_text]))[0]
        base = (
            select(Chunk, Document)
            .join(Document, Chunk.document_id == Document.id)
            .where(
                Chunk.tenant_id == tenant_id,
                Chunk.level == "child",
                Document.tenant_id == tenant_id,
                Document.knowledge_base_id == knowledge_base_id,
                Document.status == "completed",
                Document.is_archived.is_(False),
                Chunk.embedding.is_not(None),
            )
        )
        bind = session.get_bind()
        if bind is not None and bind.dialect.name == "postgresql":
            distance = cast(
                Chunk.embedding, Vector(get_settings().embedding_dimension)
            ).cosine_distance(vector)
            result = await session.execute(
                base.add_columns((1 - distance).label("score")).order_by(distance).limit(limit)
            )
            records = result.all()
            return (
                [chunk.id for chunk, _, _ in records],
                {chunk.id: {"dense_score": round(float(score), 6)} for chunk, _, score in records},
            )
        from app.services.retrieval import cosine_similarity

        result = await session.execute(base)
        records = sorted(
            (
                (cosine_similarity(vector, chunk.embedding or []), chunk)
                for chunk, _ in result.all()
            ),
            key=lambda item: item[0],
            reverse=True,
        )[:limit]
        return (
            [chunk.id for _, chunk in records],
            {chunk.id: {"dense_score": round(score, 6)} for score, chunk in records},
        )

    async def _bm25_rank(
        self,
        session: AsyncSession,
        tenant_id: str,
        knowledge_base_id: str,
        query_text: str,
        limit: int,
    ) -> tuple[list[str], dict[str, float]]:
        terms = list(dict.fromkeys(tokenize(query_text)))
        if not terms:
            return [], {}
        stat = await session.scalar(
            select(KnowledgeCorpusStat).where(
                KnowledgeCorpusStat.tenant_id == tenant_id,
                KnowledgeCorpusStat.knowledge_base_id == knowledge_base_id,
            )
        )
        if not stat or not stat.child_chunk_count:
            return [], {}
        rows = list(
            (
                await session.execute(
                    select(ChunkTerm).where(
                        ChunkTerm.tenant_id == tenant_id,
                        ChunkTerm.knowledge_base_id == knowledge_base_id,
                        ChunkTerm.term.in_(terms),
                    )
                )
            ).scalars()
        )
        document_frequency: dict[str, int] = {}
        for term in terms:
            document_frequency[term] = len({row.chunk_id for row in rows if row.term == term})
        scores: dict[str, float] = {}
        for row in rows:
            scores[row.chunk_id] = scores.get(row.chunk_id, 0.0) + bm25_score(
                row.term_frequency,
                document_frequency[row.term],
                row.document_length,
                stat.average_document_length,
                stat.child_chunk_count,
            )
        ranked = sorted(scores, key=lambda identifier: (-scores[identifier], identifier))[:limit]
        return ranked, scores

    async def _load_candidates(
        self,
        session: AsyncSession,
        tenant_id: str,
        knowledge_base_id: str,
        identifiers: list[str],
        scores: dict[str, dict],
    ) -> list[dict]:
        if not identifiers:
            return []
        result = await session.execute(
            select(Chunk, Document)
            .join(Document, Chunk.document_id == Document.id)
            .where(
                Chunk.id.in_(identifiers),
                Chunk.tenant_id == tenant_id,
                Document.tenant_id == tenant_id,
                Document.knowledge_base_id == knowledge_base_id,
            )
        )
        lookup = {
            chunk.id: {
                "text": chunk.text,
                # Preserve the public search API while exposing stage-specific scores.
                "score": scores.get(chunk.id, {}).get("dense_score", 0.0),
                "document_id": document.id,
                "document_name": document.filename,
                "location": chunk.location,
                "chunk_id": chunk.id,
                "parent_chunk_id": chunk.parent_chunk_id,
                **scores.get(chunk.id, {}),
            }
            for chunk, document in result.all()
        }
        return [lookup[identifier] for identifier in identifiers if identifier in lookup]

    async def _map_parent_context(
        self, session: AsyncSession, tenant_id: str, rows: list[dict]
    ) -> None:
        parent_ids = {item["parent_chunk_id"] for item in rows if item.get("parent_chunk_id")}
        if not parent_ids:
            for item in rows:
                item["parent_text"] = item["text"]
            return
        parents = {
            chunk.id: chunk.text
            for chunk in (
                await session.scalars(
                    select(Chunk).where(Chunk.id.in_(parent_ids), Chunk.tenant_id == tenant_id)
                )
            )
        }
        for item in rows:
            item["parent_text"] = parents.get(item.get("parent_chunk_id"), item["text"])
