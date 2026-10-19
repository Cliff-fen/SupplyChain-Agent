from datetime import datetime

from pydantic import BaseModel


class AuditEventView(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    actor_id: str | None
    action: str
    resource_type: str
    resource_id: str | None
    details: dict
    occurred_at: datetime
    actor_role: str | None = None
    trace_id: str | None = None
    input_summary: str | None = None
    result_summary: str | None = None
    failure_reason: str | None = None
