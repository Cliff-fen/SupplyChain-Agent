import asyncio
from io import BytesIO

from fastapi import UploadFile
from sqlalchemy import select

from app.core.config import get_settings
from app.db import SessionLocal
from app.models import Document, IngestionTask, KnowledgeBase
from app.schemas import Principal


def test_identical_uploads_are_idempotent_within_each_knowledge_base(monkeypatch, tmp_path):
    monkeypatch.setenv("SUPPLYMIND_DOCUMENT_DIRECTORY", str(tmp_path))
    monkeypatch.setenv("SUPPLYMIND_INGESTION_MODE", "broker")
    get_settings.cache_clear()
    from app.api import upload_document

    async def exercise():
        async with SessionLocal() as session:
            bases = [KnowledgeBase(tenant_id="tenant", name=name, created_by="admin")
                     for name in ("生产", "制度")]
            session.add_all(bases)
            await session.commit()

            async def upload(base):
                return await upload_document(
                    base.id, file=UploadFile(file=BytesIO(b"same content"), filename="policy.txt"),
                    metric_name=None, metric_definition=None, metric_formula=None,
                    metric_unit=None, applicable_factories="", applicable_product_lines="",
                    effective_from=None, replace_document_id=None,
                    principal=Principal(tenant_id="tenant", user_id="admin", role="org_admin"),
                    session=session,
                )

            first = await upload(bases[0])
            duplicate = await upload(bases[0])
            second = await upload(bases[1])
            assert duplicate.id == first.id and duplicate.duplicate
            assert second.id != first.id and second.knowledge_base_id == bases[1].id
            assert len(list(await session.scalars(select(Document)))) == 2
            assert len(list(await session.scalars(select(IngestionTask)))) == 2

    try:
        asyncio.run(exercise())
    finally:
        get_settings.cache_clear()
