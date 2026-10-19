from typing import Protocol

from app.core.sql_guard import GuardedSQL
from app.models import DataSource
from app.services.datasource import SourceSchema


class DataSourceGateway(Protocol):
    async def test_connection(self, source: DataSource) -> dict: ...
    async def synchronize_schema(self, source: DataSource) -> SourceSchema: ...
    async def execute_guarded_query(
        self, source: DataSource, sql: str
    ) -> tuple[GuardedSQL, list[dict]]: ...
