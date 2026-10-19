from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db import get_session
from app.dependencies import get_principal, require_role
from app.models import Dashboard, DashboardRefreshTask, DashboardWidget, DataSource
from app.modules.dashboards.schemas import DashboardConfigUpdate, DashboardConfigView, DashboardView
from app.modules.dashboards.service import get_supply_chain_dashboard
from app.schemas import Principal
from app.services.audit import audit
from app.services.datasource import DataSourceError, execute_guarded_query

router = APIRouter(prefix="/api/v1", tags=["dashboards"])


@router.get("/dashboards/supply-chain/config", response_model=DashboardConfigView)
async def supply_chain_dashboard_config(
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> DashboardConfigView:
    dashboard = await session.scalar(
        select(Dashboard).where(
            Dashboard.tenant_id == principal.tenant_id,
            Dashboard.slug == "supply-chain",
        )
    )
    if not dashboard:
        dashboard = Dashboard(
            tenant_id=principal.tenant_id, name="供应链运营大屏", slug="supply-chain"
        )
        session.add(dashboard)
        await session.flush()
    widget = await session.scalar(
        select(DashboardWidget).where(
            DashboardWidget.tenant_id == principal.tenant_id,
            DashboardWidget.dashboard_id == dashboard.id,
            DashboardWidget.key == "layout",
        )
    )
    visible = list((widget.config if widget else {}).get("visible_widgets", []))
    return DashboardConfigView(
        dashboard_id=dashboard.id,
        refresh_interval_seconds=dashboard.refresh_interval_seconds,
        visible_widgets=visible,
        updated_at=dashboard.cached_at,
    )


@router.patch("/dashboards/supply-chain/config", response_model=DashboardConfigView)
async def update_supply_chain_dashboard_config(
    payload: DashboardConfigUpdate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_role("org_admin", "platform_admin")),
) -> DashboardConfigView:
    if not 60 <= payload.refresh_interval_seconds <= 86400:
        raise HTTPException(
            status_code=422, detail="refresh_interval_seconds must be between 60 and 86400"
        )
    allowed = {
        "delivery",
        "production",
        "inventory",
        "quality",
        "fulfillment",
        "trend",
        "factories",
        "product_lines",
        "suppliers",
        "anomalies",
        "retail",
    }
    visible = list(dict.fromkeys(payload.visible_widgets))
    unknown = [key for key in visible if key not in allowed]
    if unknown:
        raise HTTPException(
            status_code=422, detail=f"Unknown dashboard widgets: {', '.join(unknown)}"
        )
    dashboard = await session.scalar(
        select(Dashboard).where(
            Dashboard.tenant_id == principal.tenant_id,
            Dashboard.slug == "supply-chain",
        )
    )
    if not dashboard:
        dashboard = Dashboard(
            tenant_id=principal.tenant_id, name="供应链运营大屏", slug="supply-chain"
        )
        session.add(dashboard)
        await session.flush()
    dashboard.refresh_interval_seconds = payload.refresh_interval_seconds
    widget = await session.scalar(
        select(DashboardWidget).where(
            DashboardWidget.tenant_id == principal.tenant_id,
            DashboardWidget.dashboard_id == dashboard.id,
            DashboardWidget.key == "layout",
        )
    )
    if not widget:
        widget = DashboardWidget(
            tenant_id=principal.tenant_id,
            dashboard_id=dashboard.id,
            key="layout",
            widget_type="config",
        )
        session.add(widget)
    widget.config = {"visible_widgets": visible}
    await audit(
        session,
        principal.tenant_id,
        principal.user_id,
        "dashboard.config_updated",
        "dashboard",
        dashboard.id,
        payload.model_dump(),
    )
    await session.commit()
    return DashboardConfigView(
        dashboard_id=dashboard.id,
        refresh_interval_seconds=dashboard.refresh_interval_seconds,
        visible_widgets=visible,
        updated_at=dashboard.cached_at,
    )


@router.get("/dashboards/supply-chain", response_model=DashboardView)
async def supply_chain_dashboard(
    factory: str | None = Query(default=None, max_length=80),
    product_line: str | None = Query(default=None, max_length=80),
    period: str | None = Query(default=None, pattern="^(7d|30d|90d)$"),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> dict:
    try:
        return await get_supply_chain_dashboard(
            session,
            principal.tenant_id,
            {"factory": factory, "product_line": product_line, "period": period},
        )
    except DataSourceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/dashboards/supply-chain/refresh", status_code=202)
async def refresh_supply_chain_dashboard(
    factory: str | None = Query(default=None, max_length=80),
    product_line: str | None = Query(default=None, max_length=80),
    period: str | None = Query(default=None, pattern="^(7d|30d|90d)$"),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_role("org_admin", "platform_admin")),
) -> dict[str, str]:
    if get_settings().ingestion_mode == "broker":
        from scripts.worker import celery_app

        filters = {"factory": factory, "product_line": product_line, "period": period}
        refresh_task = DashboardRefreshTask(
            tenant_id=principal.tenant_id, filters=filters, status="queued"
        )
        session.add(refresh_task)
        await session.flush()
        task = celery_app.send_task(
            "supplymind.dashboards.refresh", args=[principal.tenant_id, filters, refresh_task.id]
        )
        refresh_task.celery_task_id = task.id
        await audit(
            session,
            principal.tenant_id,
            principal.user_id,
            "dashboard.refresh_queued",
            "dashboard",
            None,
            {"task_id": task.id},
        )
        await session.commit()
        return {"status": "queued", "task_id": refresh_task.id, "celery_task_id": task.id}
    from app.modules.dashboards.service import refresh_supply_chain_dashboard as refresh

    try:
        await refresh(
            session,
            principal.tenant_id,
            {"factory": factory, "product_line": product_line, "period": period},
        )
    except DataSourceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    await audit(session, principal.tenant_id, principal.user_id, "dashboard.refreshed", "dashboard")
    await session.commit()
    return {"status": "completed", "task_id": "eager"}


@router.get("/dashboards/supply-chain/dimensions")
async def supply_chain_dimensions(
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> dict[str, list[str]]:
    source = await session.scalar(
        select(DataSource)
        .where(DataSource.tenant_id == principal.tenant_id, DataSource.status == "active")
        .order_by(DataSource.created_at)
    )
    if not source:
        raise HTTPException(status_code=503, detail="没有可用的真实数据源")
    try:
        _, factories = await execute_guarded_query(
            source, "SELECT DISTINCT factory FROM production_work_orders ORDER BY factory"
        )
        _, product_lines = await execute_guarded_query(
            source, "SELECT DISTINCT product_line FROM production_work_orders ORDER BY product_line"
        )
        _, suppliers = await execute_guarded_query(
            source, "SELECT supplier_name FROM suppliers ORDER BY supplier_name"
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail="读取大屏筛选维度失败") from exc
    return {
        "factories": [str(item.get("factory")) for item in factories if item.get("factory")],
        "product_lines": [
            str(item.get("product_line")) for item in product_lines if item.get("product_line")
        ],
        "suppliers": [
            str(item.get("supplier_name")) for item in suppliers if item.get("supplier_name")
        ],
    }


@router.get("/dashboards/supply-chain/refresh/{task_id}")
async def refresh_status(
    task_id: str,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> dict:
    task = await session.scalar(
        select(DashboardRefreshTask).where(
            DashboardRefreshTask.id == task_id,
            DashboardRefreshTask.tenant_id == principal.tenant_id,
        )
    )
    if not task:
        raise HTTPException(status_code=404, detail="Dashboard refresh task not found")
    if task.status in {"queued", "running"} and task.celery_task_id:
        try:
            from scripts.worker import celery_app

            state = celery_app.AsyncResult(task.celery_task_id).state
            if state == "SUCCESS":
                task.status = "completed"
            elif state in {"FAILURE", "REVOKED"}:
                task.status = "failed"
                task.error_message = "Dashboard refresh task failed"
            if task.status in {"completed", "failed"}:
                from datetime import UTC, datetime

                task.finished_at = task.finished_at or datetime.now(UTC)
                await session.commit()
        except Exception:
            # The persisted state remains authoritative when the broker is unavailable.
            pass
    recent_success_at = await session.scalar(
        select(func.max(DashboardRefreshTask.finished_at)).where(
            DashboardRefreshTask.tenant_id == principal.tenant_id,
            DashboardRefreshTask.status == "completed",
        )
    )
    return {
        "id": task.id,
        "status": task.status,
        "celery_task_id": task.celery_task_id,
        "filters": task.filters,
        "error_message": task.error_message,
        "attempts": task.attempts,
        "max_attempts": task.max_attempts,
        "started_at": task.started_at,
        "finished_at": task.finished_at,
        "recent_success_at": recent_success_at,
    }
