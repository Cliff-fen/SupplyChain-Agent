from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditEvent


async def list_events(
    session: AsyncSession,
    tenant_id: str,
    limit: int,
    offset: int = 0,
    action: str | None = None,
    resource_type: str | None = None,
    actor_id: str | None = None,
    occurred_from: datetime | None = None,
    occurred_to: datetime | None = None,
    run_id: str | None = None,
) -> list[AuditEvent]:
    query = _filtered_query(
        tenant_id, action, resource_type, actor_id, occurred_from, occurred_to, run_id
    )
    result = await session.scalars(
        query.order_by(AuditEvent.occurred_at.desc()).offset(offset).limit(limit)
    )
    return list(result)


def _filtered_query(
    tenant_id: str,
    action: str | None = None,
    resource_type: str | None = None,
    actor_id: str | None = None,
    occurred_from: datetime | None = None,
    occurred_to: datetime | None = None,
    run_id: str | None = None,
):
    query = select(AuditEvent).where(AuditEvent.tenant_id == tenant_id)
    if action:
        query = query.where(AuditEvent.action.ilike(f"%{action}%"))
    if resource_type:
        query = query.where(AuditEvent.resource_type == resource_type)
    if actor_id:
        query = query.where(AuditEvent.actor_id == actor_id)
    if occurred_from:
        query = query.where(AuditEvent.occurred_at >= occurred_from)
    if occurred_to:
        query = query.where(AuditEvent.occurred_at <= occurred_to)
    if run_id:
        query = query.where(AuditEvent.details["run_id"].as_string() == run_id)
    return query


async def count_events(
    session: AsyncSession,
    tenant_id: str,
    action: str | None = None,
    resource_type: str | None = None,
    actor_id: str | None = None,
    occurred_from: datetime | None = None,
    occurred_to: datetime | None = None,
    run_id: str | None = None,
) -> int:
    query = _filtered_query(
        tenant_id, action, resource_type, actor_id, occurred_from, occurred_to, run_id
    ).with_only_columns(func.count(AuditEvent.id))
    return int(await session.scalar(query) or 0)


async def get_event(session: AsyncSession, tenant_id: str, event_id: str) -> AuditEvent | None:
    return await session.scalar(
        select(AuditEvent).where(AuditEvent.tenant_id == tenant_id, AuditEvent.id == event_id)
    )
