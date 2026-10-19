import pytest

from app.core.sql_guard import SQLGuardError, validate_read_only_sql


def test_adds_limit_and_accepts_allowed_table() -> None:
    guarded = validate_read_only_sql("SELECT * FROM production_orders", {"production_orders"})
    assert guarded.sql.endswith("LIMIT 500")
    assert guarded.tables == ("production_orders",)


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM production_orders",
        "SELECT * FROM hidden_table",
        "SELECT * FROM production_orders; DROP TABLE production_orders",
        "SELECT * INTO copied_orders FROM production_orders",
        "SELECT * FROM production_orders FOR UPDATE",
        "SELECT * FROM secret.production_orders",
        "SELECT pg_sleep(10) FROM production_orders",
    ],
)
def test_rejects_unsafe_sql(sql: str) -> None:
    with pytest.raises(SQLGuardError):
        validate_read_only_sql(sql, {"production_orders"})


def test_nested_limit_does_not_bypass_top_level_budget():
    result = validate_read_only_sql(
        "SELECT * FROM production_orders WHERE id IN (SELECT id FROM production_orders LIMIT 1)",
        {"production_orders"}, 3,
    )
    assert result.sql.endswith("LIMIT 3")
    result = validate_read_only_sql("SELECT * FROM production_orders LIMIT 999999", {"production_orders"}, 3)
    assert result.sql.endswith("LIMIT 3")
