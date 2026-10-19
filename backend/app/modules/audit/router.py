from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.dependencies import require_role
from app.models import Membership
from app.modules.audit.schemas import AuditEventView
from app.modules.audit.service import count_tenant_events, get_tenant_event, get_tenant_events
from app.schemas import Principal

router = APIRouter(prefix="/api/v1", tags=["audit"])


def _view(event, actor_role: str | None = None) -> AuditEventView:
    details = event.details or {}
    return AuditEventView(
        id=event.id,
        actor_id=event.actor_id,
        action=event.action,
        resource_type=event.resource_type,
        resource_id=event.resource_id,
        details=details,
        occurred_at=event.occurred_at,
        actor_role=actor_role,
        trace_id=details.get("trace_id"),
        input_summary=details.get("input_summary") or details.get("input"),
        result_summary=details.get("result_summary") or details.get("result"),
        failure_reason=details.get("failure_reason")
        or details.get("reason")
        or (details.get("error") if "failed" in event.action else None),
    )


@router.get("/audit", response_model=list[AuditEventView])
async def list_audit_events(
    response: Response,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    action: str | None = Query(default=None, max_length=100),
    resource_type: str | None = Query(default=None, max_length=100),
    actor_id: str | None = Query(default=None),
    occurred_from: datetime | None = Query(default=None),
    occurred_to: datetime | None = Query(default=None),
    run_id: str | None = Query(default=None, max_length=36),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_role("platform_admin", "org_admin")),
) -> list[AuditEventView]:
    events = await get_tenant_events(
        session,
        principal.tenant_id,
        limit,
        offset,
        action,
        resource_type,
        actor_id,
        occurred_from,
        occurred_to,
        run_id,
    )
    total = await count_tenant_events(
        session,
        principal.tenant_id,
        action,
        resource_type,
        actor_id,
        occurred_from,
        occurred_to,
        run_id,
    )
    if response is not None:
        response.headers["X-Total-Count"] = str(total)
        response.headers["X-Page-Offset"] = str(offset)
        response.headers["X-Page-Limit"] = str(limit)
    actor_ids = {event.actor_id for event in events if event.actor_id}
    memberships = list(
        await session.scalars(
            select(Membership).where(
                Membership.organization_id == principal.tenant_id,
                Membership.user_id.in_(actor_ids or {"-"}),
            )
        )
    )
    roles = {membership.user_id: membership.role for membership in memberships}
    return [_view(event, roles.get(event.actor_id)) for event in events]


@router.get("/audit/{event_id}", response_model=AuditEventView)
async def get_audit_event(
    event_id: str,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_role("platform_admin", "org_admin")),
) -> AuditEventView:
    event = await get_tenant_event(session, principal.tenant_id, event_id)
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audit event not found")
    role = (
        await session.scalar(
            select(Membership.role).where(
                Membership.organization_id == principal.tenant_id,
                Membership.user_id == event.actor_id,
            )
        )
        if event.actor_id
        else None
    )
    return _view(event, role)
