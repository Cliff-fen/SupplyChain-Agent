from __future__ import annotations

import asyncio
import ipaddress
from dataclasses import dataclass

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.config import get_settings
from app.core.security import decrypt_secret
from app.core.sql_guard import GuardedSQL, validate_read_only_sql
from app.models import DataSource


class DataSourceError(ValueError):
    pass


@dataclass(frozen=True)
class SourceSchema:
    tables: list[dict]


def validate_source_host(host: str) -> None:
    settings = get_settings()
    normalized = host.strip().lower()
    if normalized in settings.datasource_host_list:
        return
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError as exc:
        raise DataSourceError("Host is not in the deployment allowlist") from exc
    networks = [
        ipaddress.ip_network(item.strip())
        for item in settings.datasource_allowed_cidrs.split(",")
        if item.strip()
    ]
    if not any(address in network for network in networks):
        raise DataSourceError("IP address is not in an allowed CIDR")


def source_url(source: DataSource) -> str:
    password = decrypt_secret(source.encrypted_password)
    if source.engine == "postgresql":
        return f"postgresql+asyncpg://{source.username}:{password}@{source.host}:{source.port}/{source.database_name}"
    if source.engine == "mysql":
        return f"mysql+aiomysql://{source.username}:{password}@{source.host}:{source.port}/{source.database_name}?charset=utf8mb4"
    raise DataSourceError("Unsupported database engine")


def source_engine(source: DataSource) -> AsyncEngine:
    validate_source_host(source.host)
    return create_async_engine(source_url(source), pool_pre_ping=True, pool_recycle=1800)


async def test_connection(source: DataSource) -> dict:
    engine = source_engine(source)
    try:
        async with engine.connect() as connection:
            value = (await connection.execute(text("SELECT 1"))).scalar_one()
            return {"connected": value == 1, "engine": source.engine}
    finally:
        await engine.dispose()


async def synchronize_schema(source: DataSource) -> SourceSchema:
    engine = source_engine(source)
    try:
        async with engine.connect() as connection:

            def collect(sync_connection) -> list[dict]:
                inspector = inspect(sync_connection)
                tables: list[dict] = []
                for table_name in inspector.get_table_names():
                    if table_name not in source.allowed_tables:
                        continue
                    columns = []
                    for column in inspector.get_columns(table_name):
                        columns.append(
                            {
                                "name": column["name"],
                                "type": str(column["type"]),
                                "nullable": column["nullable"],
                                "comment": column.get("comment"),
                            }
                        )
                    try:
                        table_comment = inspector.get_table_comment(table_name).get("text")
                    except (NotImplementedError, AttributeError):
                        table_comment = None
                    tables.append(
                        {
                            "name": table_name,
                            "columns": columns,
                            "primary_key": inspector.get_pk_constraint(table_name).get(
                                "constrained_columns", []
                            ),
                            "foreign_keys": inspector.get_foreign_keys(table_name),
                            "indexes": inspector.get_indexes(table_name),
                            "comment": table_comment,
                            "sample_limit": 100,
                        }
                    )
                return tables

            return SourceSchema(tables=await connection.run_sync(collect))
    finally:
        await engine.dispose()


async def execute_guarded_query(
    source: DataSource, sql: str, params: dict[str, object] | None = None
) -> tuple[GuardedSQL, list[dict]]:
    guarded = validate_read_only_sql(sql, set(source.allowed_tables), get_settings().sql_max_rows)
    engine = source_engine(source)
    try:
        async with engine.connect() as connection:
            async with connection.begin():
                timeout_ms = max(1, get_settings().sql_timeout_seconds * 1000)
                if source.engine == "postgresql":
                    await connection.execute(text("SET TRANSACTION READ ONLY"))
                    await connection.execute(
                        text("SELECT set_config('statement_timeout', :timeout, true)"),
                        {"timeout": str(timeout_ms)},
                    )
                elif source.engine == "mysql":
                    await connection.execute(text(f"SET SESSION MAX_EXECUTION_TIME = {timeout_ms}"))
                    await connection.execute(text("SET TRANSACTION READ ONLY"))
                async with asyncio.timeout(get_settings().sql_timeout_seconds):
                    result = await connection.execute(text(guarded.sql), params or {})
                    rows = [dict(row) for row in result.mappings().fetchmany(get_settings().sql_max_rows)]
                return guarded, rows
    finally:
        await engine.dispose()
