"""Seed the demo organizations with auditable knowledge documents.

The documents are example summaries with links to public references.  The source
database fixtures are synthetic and live in database/seeds/*/002_*.sql.
Run inside the API container after migrations; rerunning is idempotent.
"""

import asyncio
from pathlib import Path

from sqlalchemy import func, select

from app.core.config import get_settings
from app.db import SessionLocal
from app.models import Chunk, Document, IngestionTask, KnowledgeBase, Organization, User
from app.services.ingestion import process_ingestion
from app.services.knowledge import classify_document, extract_text, sha256

ROOT = Path(__file__).resolve().parents[2]
DOCS_ROOT = ROOT / "docs" / "knowledge-base"
if not DOCS_ROOT.exists():
    DOCS_ROOT = Path("/app/docs/knowledge-base")
DOCS = sorted(DOCS_ROOT.glob("*.md"))


async def seed() -> tuple[int, int, bool]:
    settings = get_settings()
    created_documents = 0
    created_chunks = 0
    attempted_ingestion = bool(
        settings.embedding_base_url and settings.embedding_model and settings.embedding_api_key
    )
    async with SessionLocal() as session:
        organizations = list(
            await session.scalars(select(Organization).order_by(Organization.slug))
        )
        for organization in organizations:
            owner = await session.scalar(select(User).where(User.id == organization.owner_user_id))
            if not owner:
                owner = await session.scalar(select(User).where(User.email == "admin@demo.local"))
            if not owner:
                continue
            kb = await session.scalar(
                select(KnowledgeBase).where(
                    KnowledgeBase.tenant_id == organization.id,
                    KnowledgeBase.name == "供应链运营知识库",
                    KnowledgeBase.is_archived.is_(False),
                )
            )
            if not kb:
                kb = KnowledgeBase(
                    tenant_id=organization.id,
                    name="供应链运营知识库",
                    description="指标口径、流程、质量规范和演示源库数据字典。包含示例摘要与合成测试数据说明。",
                    created_by=owner.id,
                )
                session.add(kb)
                await session.flush()
            for path in DOCS:
                payload = path.read_bytes()
                digest = sha256(payload)
                document = await session.scalar(
                    select(Document).where(
                        Document.tenant_id == organization.id, Document.content_sha256 == digest
                    )
                )
                if document:
                    continue
                text, _ = extract_text(path.name, "text/markdown", payload)
                storage_dir = Path(settings.document_directory)
                storage_dir.mkdir(parents=True, exist_ok=True)
                stored_path = storage_dir / digest
                stored_path.write_bytes(payload)
                document = Document(
                    tenant_id=organization.id,
                    knowledge_base_id=kb.id,
                    filename=path.name,
                    content_type="text/markdown",
                    content_sha256=digest,
                    file_size_bytes=len(payload),
                    language="zh",
                    category=classify_document(path.name, text),
                    status="queued",
                    source_path=str(stored_path),
                    created_by=owner.id,
                )
                session.add(document)
                await session.flush()
                task = IngestionTask(
                    tenant_id=organization.id,
                    document_id=document.id,
                    task_key=f"{organization.id}:{digest}",
                )
                session.add(task)
                await session.flush()
                created_documents += 1
                if attempted_ingestion:
                    try:
                        await process_ingestion(session, task, document)
                        created_chunks += (
                            await session.scalar(
                                select(func.count(Chunk.id)).where(Chunk.document_id == document.id)
                            )
                            or 0
                        )
                    except Exception:
                        # Keep the failed task visible for retry; do not hide missing provider config.
                        pass
        await session.commit()
    return created_documents, created_chunks, attempted_ingestion


if __name__ == "__main__":
    docs, chunks, ingested = asyncio.run(seed())
    mode = "摄取并生成向量" if ingested else "排队等待 Embedding 配置"
    print(f"知识库导入完成：新增文档 {docs} 个，新增分块 {chunks} 个；{mode}。")
