from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditEvent


async def audit(
    session: AsyncSession,
    tenant_id: str,
    actor_id: str | None,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    details: dict | None = None,
) -> None:
    safe_details = dict(details or {})
    safe_details.setdefault("trace_id", uuid4().hex)
    session.add(
        AuditEvent(
            tenant_id=tenant_id,
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=safe_details,
        )
    )
