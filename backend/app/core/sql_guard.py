from dataclasses import dataclass

from sqlglot import exp, parse
from sqlglot.errors import ParseError


class SQLGuardError(ValueError):
    pass


@dataclass(frozen=True)
class GuardedSQL:
    sql: str
    tables: tuple[str, ...]


FORBIDDEN_FUNCTIONS = {
    "pg_sleep", "load_file", "sleep", "benchmark", "lo_import", "lo_export",
    "pg_read_file", "pg_read_binary_file", "pg_ls_dir", "pg_terminate_backend",
    "pg_cancel_backend", "set_config", "dblink", "dblink_exec", "dblink_connect",
    "pg_advisory_lock", "pg_advisory_xact_lock", "pg_try_advisory_lock",
}


def validate_read_only_sql(sql: str, allowed_tables: set[str], max_rows: int = 500) -> GuardedSQL:
    if not sql or len(sql) > 20_000:
        raise SQLGuardError("SQL is empty or exceeds the maximum length")
    if ";" in sql.rstrip("; ").strip():
        raise SQLGuardError("Only one SQL statement is allowed")
    try:
        statements = parse(sql)
    except ParseError as exc:
        raise SQLGuardError("SQL cannot be parsed") from exc
    if len(statements) != 1 or not isinstance(statements[0], exp.Query):
        raise SQLGuardError("Only SELECT or WITH queries are allowed")
    statement = statements[0]
    if statement.find(exp.Insert) or statement.find(exp.Update) or statement.find(exp.Delete):
        raise SQLGuardError("Write operations are forbidden")
    if statement.find(exp.Into) or statement.find(exp.Lock):
        raise SQLGuardError("SELECT INTO and locking reads are forbidden")
    for table in statement.find_all(exp.Table):
        if table.catalog or (table.db and table.db != "public"):
            raise SQLGuardError("Cross-schema and cross-database reads are forbidden")
    cte_names = {cte.alias_or_name for cte in statement.find_all(exp.CTE) if cte.alias_or_name}
    tables = tuple(
        sorted(
            {table.name for table in statement.find_all(exp.Table) if table.name not in cte_names}
        )
    )
    if not tables:
        raise SQLGuardError("Query must reference an approved table")
    unknown = set(tables) - allowed_tables
    if unknown:
        raise SQLGuardError(f"Table is not approved: {', '.join(sorted(unknown))}")
    functions = {function.name.lower() for function in statement.find_all(exp.Anonymous)}
    if functions & FORBIDDEN_FUNCTIONS:
        raise SQLGuardError("Query uses a forbidden function")
    limit = statement.args.get("limit")
    if limit is None:
        sql = f"{sql.rstrip(';')} LIMIT {max_rows}"
    else:
        value = limit.expression
        if not isinstance(value, exp.Literal) or not value.is_int or int(value.this) < 0:
            raise SQLGuardError("LIMIT must be a non-negative integer literal")
        if int(value.this) > max_rows:
            sql = statement.limit(max_rows).sql()
    return GuardedSQL(sql=sql, tables=tables)
