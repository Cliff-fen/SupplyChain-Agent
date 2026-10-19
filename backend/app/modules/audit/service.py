from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditEvent
from app.modules.audit.repository import count_events, get_event, list_events

_SENSITIVE_KEYS = ("password", "secret", "token", "api_key", "connection", "credential")


def _redact_value(key: str, value):
    if any(word in key.lower() for word in _SENSITIVE_KEYS):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {
            child_key: _redact_value(child_key, child_value)
            for child_key, child_value in value.items()
        }
    if isinstance(value, list):
        return [_redact_value(key, item) if isinstance(item, dict) else item for item in value]
    return value


def _redact(event: AuditEvent) -> AuditEvent:
    event.details = {key: _redact_value(key, value) for key, value in (event.details or {}).items()}
    return event


async def get_tenant_events(
    session: AsyncSession,
    tenant_id: str,
    limit: int = 100,
    offset: int = 0,
    action: str | None = None,
    resource_type: str | None = None,
    actor_id: str | None = None,
    occurred_from: datetime | None = None,
    occurred_to: datetime | None = None,
    run_id: str | None = None,
) -> list[AuditEvent]:
    events = await list_events(
        session,
        tenant_id,
        limit,
        offset,
        action,
        resource_type,
        actor_id,
        occurred_from,
        occurred_to,
        run_id,
    )
    return [_redact(event) for event in events]


async def get_tenant_event(
    session: AsyncSession, tenant_id: str, event_id: str
) -> AuditEvent | None:
    event = await get_event(session, tenant_id, event_id)
    return _redact(event) if event else None


async def count_tenant_events(
    session: AsyncSession,
    tenant_id: str,
    action: str | None = None,
    resource_type: str | None = None,
    actor_id: str | None = None,
    occurred_from: datetime | None = None,
    occurred_to: datetime | None = None,
    run_id: str | None = None,
) -> int:
    return await count_events(
        session, tenant_id, action, resource_type, actor_id, occurred_from, occurred_to, run_id
    )
