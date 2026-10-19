from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Dashboard, DataSource
from app.modules.dashboards.repository import get_dashboard, save_dashboard
from app.services.datasource import DataSourceError, execute_guarded_query


async def _live_payload(
    session: AsyncSession, tenant_id: str, filters: dict[str, str | None]
) -> dict[str, Any]:
    source = await session.scalar(
        select(DataSource)
        .where(
            DataSource.tenant_id == tenant_id,
            DataSource.status == "active",
        )
        .order_by(DataSource.created_at)
    )
    if not source:
        raise DataSourceError("没有可用的真实数据源，无法生成大屏")
    allowed = set(source.allowed_tables or [])
    required = {
        "production_work_orders",
        "inventory_balances",
        "materials",
        "quality_inspections",
        "sales_orders",
        "purchase_orders",
    }
    if not required.issubset(allowed):
        raise DataSourceError("数据源白名单缺少大屏所需业务表")
    factory = filters.get("factory")
    product_line = filters.get("product_line")
    period_days = {"7d": 7, "30d": 30, "90d": 90}.get(filters.get("period") or "30d", 30)
    date_filter = (
        "CURRENT_DATE - INTERVAL '%s days'" % period_days
        if source.engine == "postgresql"
        else "DATE_SUB(CURDATE(), INTERVAL %s DAY)" % period_days
    )

    def clause(alias: str, fields: list[str]) -> tuple[str, dict[str, str]]:
        parts, params = [], {}
        if factory:
            parts.append(f"{alias}.factory = :factory")
            params["factory"] = factory
        if product_line and "product_line" in fields:
            parts.append(f"{alias}.product_line = :product_line")
            params["product_line"] = product_line
        return (" WHERE " + " AND ".join(parts)) if parts else "", params

    prod_where, prod_params = clause("p", ["product_line"])
    date_predicate = f"p.planned_date >= {date_filter}"
    prod_where = f" WHERE {date_predicate}" + (
        " AND " + prod_where.removeprefix(" WHERE ") if prod_where else ""
    )
    queries = {
        "production": f"SELECT COALESCE(SUM(p.completed_quantity), 0) * 100.0 / NULLIF(SUM(p.planned_quantity), 0) AS rate FROM production_work_orders p{prod_where}",
        "inventory": "SELECT COUNT(*) AS risk_count FROM inventory_balances i JOIN materials m ON m.material_id = i.material_id WHERE i.quantity < m.safety_stock",
        "quality": "SELECT COALESCE(SUM(q.passed_quantity), 0) * 100.0 / NULLIF(SUM(q.inspected_quantity), 0) AS rate FROM quality_inspections q",
        "delivery": "SELECT COALESCE(SUM(CASE WHEN delivered_date IS NOT NULL AND delivered_date <= planned_date THEN 1 ELSE 0 END), 0) * 100.0 / NULLIF(COUNT(*), 0) AS rate FROM purchase_orders",
        "fulfillment": "SELECT COALESCE(SUM(delivered_quantity), 0) * 100.0 / NULLIF(SUM(ordered_quantity), 0) AS rate FROM sales_orders",
    }
    values: dict[str, list[dict[str, Any]]] = {}
    for key, sql in queries.items():
        try:
            _, rows = await execute_guarded_query(
                source, sql, prod_params if key == "production" else None
            )
        except Exception as exc:
            raise DataSourceError(f"大屏真实聚合失败：{key}") from exc
        values[key] = rows

    def number(key: str, field: str, default: float = 0.0) -> float:
        value = values[key][0].get(field) if values[key] else default
        return float(value or default)

    production = number("production", "rate")
    quality = number("quality", "rate")
    delivery = number("delivery", "rate")
    fulfillment = number("fulfillment", "rate")
    risk_count = int(number("inventory", "risk_count"))
    date_label = (
        "TO_CHAR(p.planned_date, 'YYYY-MM-DD')"
        if source.engine == "postgresql"
        else "DATE_FORMAT(p.planned_date, '%Y-%m-%d')"
    )
    trend_sql = f"SELECT {date_label} AS day, COALESCE(SUM(p.completed_quantity), 0) * 100.0 / NULLIF(SUM(p.planned_quantity), 0) AS rate FROM production_work_orders p{prod_where} GROUP BY p.planned_date ORDER BY p.planned_date"
    factory_sql = f"SELECT p.factory, COALESCE(SUM(p.completed_quantity), 0) * 100.0 / NULLIF(SUM(p.planned_quantity), 0) AS rate FROM production_work_orders p{prod_where} GROUP BY p.factory ORDER BY rate DESC"
    product_sql = f"SELECT p.product_line, COALESCE(SUM(p.completed_quantity), 0) * 100.0 / NULLIF(SUM(p.planned_quantity), 0) AS rate FROM production_work_orders p{prod_where} GROUP BY p.product_line ORDER BY rate DESC"
    supplier_sql = "SELECT s.supplier_name, COUNT(*) AS order_count, COALESCE(SUM(CASE WHEN po.delivered_date IS NOT NULL AND po.delivered_date <= po.planned_date THEN 1 ELSE 0 END), 0) * 100.0 / NULLIF(COUNT(*), 0) AS rate FROM purchase_orders po JOIN suppliers s ON s.supplier_id = po.supplier_id GROUP BY s.supplier_name ORDER BY rate DESC"
    try:
        _, trend_rows = await execute_guarded_query(source, trend_sql, prod_params)
        _, factory_rows = await execute_guarded_query(source, factory_sql, prod_params)
        _, product_rows = await execute_guarded_query(source, product_sql, prod_params)
        _, supplier_rows = await execute_guarded_query(source, supplier_sql)
    except Exception as exc:
        raise DataSourceError("大屏趋势或排行聚合失败") from exc
    anomalies = [
        {
            "type": "production",
            "factory": row.get("factory"),
            "rate": float(row.get("rate") or 0),
            "analysis_question": f"分析{row.get('factory') or '各工厂'}生产达成率偏低原因",
            "analysis_template": "生产达成率",
        }
        for row in factory_rows
        if float(row.get("rate") or 0) < 90
    ]

    def clean_row(row: dict[str, Any]) -> dict[str, Any]:
        return {
            key: (
                float(value)
                if isinstance(value, Decimal)
                else value.isoformat()
                if isinstance(value, datetime)
                else value
            )
            for key, value in row.items()
        }

    factory_rows = [clean_row(row) for row in factory_rows]
    product_rows = [clean_row(row) for row in product_rows]
    supplier_rows = [clean_row(row) for row in supplier_rows]
    retail: dict[str, Any] | None = None
    retail_source = await session.scalar(
        select(DataSource).where(
            DataSource.tenant_id == tenant_id,
            DataSource.host == "retail-postgres",
            DataSource.status == "active",
        )
    )
    if retail_source and "retail_transactions" in set(retail_source.allowed_tables or []):
        retail_summary_sql = """
            SELECT COUNT(*) AS transaction_rows, COUNT(DISTINCT invoice_no) AS order_count,
              COUNT(DISTINCT stock_code) AS sku_count, COUNT(DISTINCT country) AS country_count,
              MIN(invoice_at) AS first_transaction_at, MAX(invoice_at) AS last_transaction_at,
              COALESCE(SUM(quantity * unit_price), 0) AS net_transaction_value
            FROM retail_transactions
        """
        retail_recent_sql = """
            WITH latest AS (SELECT MAX(invoice_at) AS end_at FROM retail_transactions)
            SELECT COUNT(*) AS transaction_rows,
              COALESCE(SUM(quantity * unit_price), 0) AS net_transaction_value,
              MIN(invoice_at) AS start_at, MAX(invoice_at) AS end_at
            FROM retail_transactions, latest
            WHERE invoice_at >= latest.end_at - INTERVAL '30 days'
        """
        retail_markets_sql = """
            WITH latest AS (SELECT MAX(invoice_at) AS end_at FROM retail_transactions)
            SELECT country, COUNT(*) AS transaction_rows,
              COALESCE(SUM(quantity * unit_price), 0) AS net_transaction_value
            FROM retail_transactions, latest
            WHERE invoice_at >= latest.end_at - INTERVAL '30 days'
            GROUP BY country
            ORDER BY net_transaction_value DESC
            LIMIT 3
        """
        try:
            _, retail_rows = await execute_guarded_query(retail_source, retail_summary_sql)
            _, recent_rows = await execute_guarded_query(retail_source, retail_recent_sql)
            _, market_rows = await execute_guarded_query(retail_source, retail_markets_sql)
        except Exception:
            retail_rows, recent_rows, market_rows = [], [], []
        if not retail_rows:
            return_payload = None
        else:
            return_payload = retail_rows[0]
        summary = return_payload or {}
        recent = recent_rows[0] if recent_rows else {}
        retail = {
            "source": "UCI Online Retail II",
            "transaction_rows": int(summary.get("transaction_rows") or 0),
            "order_count": int(summary.get("order_count") or 0),
            "sku_count": int(summary.get("sku_count") or 0),
            "country_count": int(summary.get("country_count") or 0),
            "net_transaction_value": float(summary.get("net_transaction_value") or 0),
            "first_transaction_at": (
                summary["first_transaction_at"].isoformat()
                if summary.get("first_transaction_at")
                else None
            ),
            "last_transaction_at": (
                summary["last_transaction_at"].isoformat()
                if summary.get("last_transaction_at")
                else None
            ),
            "latest_30_days": clean_row(recent),
            "top_markets": [clean_row(row) for row in market_rows],
        }
    return {
        "cards": [
            {"label": "采购交付", "value": f"{delivery:.1f}%", "change": "实时"},
            {"label": "生产达成率", "value": f"{production:.1f}%", "change": "实时"},
            {"label": "库存风险物料", "value": str(risk_count), "change": "实时"},
            {"label": "质量合格率", "value": f"{quality:.1f}%", "change": "实时"},
            {"label": "订单履约", "value": f"{fulfillment:.1f}%", "change": "实时"},
        ],
        "trend": [
            {"month": row.get("day"), "rate": float(row.get("rate") or 0)} for row in trend_rows
        ],
        "rankings": {
            "factories": factory_rows,
            "product_lines": product_rows,
            "suppliers": supplier_rows,
        },
        "anomalies": anomalies,
        "retail": retail,
    }


async def _redis_payload(key: str) -> dict[str, Any] | None:
    client = Redis.from_url(
        get_settings().redis_url, socket_connect_timeout=0.2, socket_timeout=0.2
    )
    try:
        value = await client.get(key)
        if value:
            import json

            return json.loads(value)
    except Exception:
        return None
    finally:
        await client.aclose()
    return None


async def _cache_payload(key: str, payload: dict[str, Any], ttl: int) -> None:
    client = Redis.from_url(
        get_settings().redis_url, socket_connect_timeout=0.2, socket_timeout=0.2
    )
    try:
        import json

        await client.set(key, json.dumps(payload), ex=ttl)
    except Exception:
        return
    finally:
        await client.aclose()


async def get_supply_chain_dashboard(
    session: AsyncSession,
    tenant_id: str,
    filters: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    filters = {key: value for key, value in (filters or {}).items() if value}
    dashboard = await get_dashboard(session, tenant_id, "supply-chain")
    now = datetime.now(UTC)
    if not dashboard:
        dashboard = await save_dashboard(
            session,
            Dashboard(
                tenant_id=tenant_id,
                name="供应链运营大屏",
                slug="supply-chain",
                refresh_interval_seconds=300,
                cached_payload={},
                cached_at=now,
            ),
        )
        await session.commit()
    cached_at = dashboard.cached_at
    if cached_at and cached_at.tzinfo is None:
        # SQLite returns naive datetimes; persisted timestamps are UTC.
        cached_at = cached_at.replace(tzinfo=UTC)
    age = now - cached_at if cached_at else timedelta.max
    filter_suffix = ":".join(f"{key}={filters[key]}" for key in sorted(filters)) or "all"
    cache_key = f"supplymind:dashboard:{tenant_id}:{dashboard.slug}:{filter_suffix}"
    cached = await _redis_payload(cache_key)
    if cached:
        payload = cached
        cache_status = "redis"
    elif (
        dashboard.cached_payload
        and len(dashboard.cached_payload.get("cards", [])) == 5
        and age.total_seconds() <= dashboard.refresh_interval_seconds
    ):
        payload = dashboard.cached_payload
        cache_status = "database"
    else:
        payload = await _live_payload(session, tenant_id, filters)
        dashboard.cached_payload = payload
        dashboard.cached_at = now
        await session.commit()
        await _cache_payload(cache_key, payload, dashboard.refresh_interval_seconds)
        cache_status = "refreshed"
    return {
        "tenant_id": tenant_id,
        "dashboard_id": dashboard.id,
        "name": dashboard.name,
        "refreshed_at": dashboard.cached_at,
        "cache_status": cache_status,
        "refresh_interval_seconds": dashboard.refresh_interval_seconds,
        "filters": {
            "factory": filters.get("factory"),
            "product_line": filters.get("product_line"),
            "period": filters.get("period"),
        },
        **payload,
    }


async def refresh_supply_chain_dashboard(
    session: AsyncSession,
    tenant_id: str,
    filters: dict[str, str | None] | None = None,
) -> Dashboard:
    dashboard = await get_dashboard(session, tenant_id, "supply-chain")
    now = datetime.now(UTC)
    if not dashboard:
        dashboard = await save_dashboard(
            session,
            Dashboard(
                tenant_id=tenant_id,
                name="供应链运营大屏",
                slug="supply-chain",
                refresh_interval_seconds=300,
                cached_payload={},
            ),
        )
    dashboard.cached_payload = await _live_payload(session, tenant_id, filters or {})
    dashboard.cached_at = now
    await session.commit()
    filter_suffix = (
        ":".join(f"{key}={value}" for key, value in sorted((filters or {}).items()) if value)
        or "all"
    )
    await _cache_payload(
        f"supplymind:dashboard:{tenant_id}:{dashboard.slug}:{filter_suffix}",
        dashboard.cached_payload,
        dashboard.refresh_interval_seconds,
    )
    return dashboard
