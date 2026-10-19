from datetime import datetime
from typing import Any

from pydantic import BaseModel


class DashboardView(BaseModel):
    tenant_id: str
    dashboard_id: str
    name: str
    refreshed_at: datetime | None
    cache_status: str
    refresh_interval_seconds: int
    filters: dict[str, str | None]
    cards: list[dict[str, Any]]
    trend: list[dict[str, Any]]
    rankings: dict[str, list[dict[str, Any]]] = {}
    anomalies: list[dict[str, Any]] = []
    retail: dict[str, Any] | None = None


class DashboardConfigView(BaseModel):
    dashboard_id: str
    refresh_interval_seconds: int
    visible_widgets: list[str]
    updated_at: datetime | None = None


class DashboardConfigUpdate(BaseModel):
    refresh_interval_seconds: int = 300
    visible_widgets: list[str] = []
