import math
import re
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import UserMemory, UserMemorySetting

ALLOWED_CATEGORIES = frozenset(
    {"communication", "kpi_interest", "factory_scope", "product_line", "time_range", "role_context"}
)
SENSITIVE_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"(?i)(api[_ -]?key|password|secret|token)\s*[:=]"),
    re.compile(r"\b\d{17}[0-9Xx]\b"),
    re.compile(r"\b1[3-9]\d{9}\b"),
)


class MemoryPolicyError(ValueError):
    pass


class MemoryService:
    @staticmethod
    def validate(category: str, content: str, confidence: float) -> None:
        if category not in ALLOWED_CATEGORIES:
            raise MemoryPolicyError("Memory category is not allowed")
        if not content.strip() or len(content) > 2000:
            raise MemoryPolicyError("Memory content length is invalid")
        if not math.isfinite(confidence) or confidence < get_settings().memory_confidence_threshold or confidence > 1:
            raise MemoryPolicyError("Memory confidence is below policy threshold")
        if any(pattern.search(content) for pattern in SENSITIVE_PATTERNS):
            raise MemoryPolicyError("Sensitive content cannot be stored in long-term memory")

    async def enabled(self, session: AsyncSession, tenant_id: str, user_id: str) -> bool:
        setting = await session.scalar(
            select(UserMemorySetting).where(
                UserMemorySetting.tenant_id == tenant_id,
                UserMemorySetting.user_id == user_id,
            )
        )
        return setting.enabled if setting else get_settings().memory_enabled_default

    async def set_enabled(
        self, session: AsyncSession, tenant_id: str, user_id: str, enabled: bool
    ) -> UserMemorySetting:
        setting = await session.scalar(
            select(UserMemorySetting).where(
                UserMemorySetting.tenant_id == tenant_id,
                UserMemorySetting.user_id == user_id,
            )
        )
        if setting is None:
            setting = UserMemorySetting(tenant_id=tenant_id, user_id=user_id, enabled=enabled)
            session.add(setting)
        else:
            setting.enabled = enabled
        await session.flush()
        return setting

    async def list(
        self, session: AsyncSession, tenant_id: str, user_id: str, category: str | None = None
    ) -> list[UserMemory]:
        query = select(UserMemory).where(
            UserMemory.tenant_id == tenant_id,
            UserMemory.user_id == user_id,
        )
        if category:
            query = query.where(UserMemory.category == category)
        query = query.where(
            (UserMemory.expires_at.is_(None)) | (UserMemory.expires_at > datetime.now(UTC))
        )
        return list(await session.scalars(query.order_by(UserMemory.updated_at.desc())))

    async def upsert(
        self,
        session: AsyncSession,
        tenant_id: str,
        user_id: str,
        *,
        category: str,
        memory_key: str,
        content: str,
        confidence: float = 1.0,
        source_run_id: str | None = None,
        expires_at: datetime | None = None,
    ) -> UserMemory:
        self.validate(category, content, confidence)
        if not re.fullmatch(r"[a-zA-Z0-9_.:-]{1,120}", memory_key):
            raise MemoryPolicyError("Memory key is invalid")
        if expires_at is not None:
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if expires_at <= datetime.now(UTC):
                raise MemoryPolicyError("Memory expiration must be in the future")
        item = await session.scalar(
            select(UserMemory).where(
                UserMemory.tenant_id == tenant_id,
                UserMemory.user_id == user_id,
                UserMemory.category == category,
                UserMemory.memory_key == memory_key,
            )
        )
        if item is None:
            item = UserMemory(
                tenant_id=tenant_id,
                user_id=user_id,
                category=category,
                memory_key=memory_key,
                content=content.strip(),
                confidence=confidence,
                source_run_id=source_run_id,
                expires_at=expires_at,
            )
            session.add(item)
        else:
            item.content = content.strip()
            item.confidence = confidence
            item.source_run_id = source_run_id
            item.expires_at = expires_at
            item.version += 1
        await session.flush()
        return item

    async def delete(
        self, session: AsyncSession, tenant_id: str, user_id: str, memory_id: str | None = None
    ) -> int:
        statement = delete(UserMemory).where(
            UserMemory.tenant_id == tenant_id,
            UserMemory.user_id == user_id,
        )
        if memory_id:
            statement = statement.where(UserMemory.id == memory_id)
        result = await session.execute(statement)
        return int(result.rowcount or 0)
