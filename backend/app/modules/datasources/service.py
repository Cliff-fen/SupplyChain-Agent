from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DataSource
from app.modules.datasources.repository import get_for_tenant
from app.services.datasource import (
    DataSourceError,
    execute_guarded_query,
    synchronize_schema,
    test_connection,
)


async def get_tenant_source(session: AsyncSession, source_id: str, tenant_id: str) -> DataSource:
    source = await get_for_tenant(session, source_id, tenant_id)
    if not source:
        raise DataSourceError("Data source not found")
    return source


def ensure_source_enabled(source: DataSource) -> DataSource:
    if source.status == "disabled":
        raise DataSourceError("Data source is disabled")
    return source


__all__ = [
    "DataSourceError",
    "execute_guarded_query",
    "ensure_source_enabled",
    "get_tenant_source",
    "synchronize_schema",
    "test_connection",
]
