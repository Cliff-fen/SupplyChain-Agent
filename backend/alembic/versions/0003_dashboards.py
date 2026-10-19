"""Add tenant-scoped dashboard definitions and widget configuration."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0003_dashboards"
down_revision = "0002_agent_step_trace"
branch_labels = None
depends_on = None


def _create_if_missing(table: sa.Table) -> None:
    bind = op.get_bind()
    if table.name not in inspect(bind).get_table_names():
        table.create(bind=bind)


def upgrade() -> None:
    dashboards = sa.Table(
        "dashboards",
        sa.MetaData(),
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False, index=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.Column("refresh_interval_seconds", sa.Integer(), nullable=False, server_default="300"),
        sa.Column("cached_payload", sa.JSON(), nullable=False),
        sa.Column("cached_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    widgets = sa.Table(
        "dashboard_widgets",
        sa.MetaData(),
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False, index=True),
        sa.Column("dashboard_id", sa.String(36), nullable=False),
        sa.Column("key", sa.String(80), nullable=False),
        sa.Column("widget_type", sa.String(40), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
    )
    _create_if_missing(dashboards)
    _create_if_missing(widgets)
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table in ("dashboards", "dashboard_widgets"):
            bind.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
            bind.execute(sa.text(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}"))
            bind.execute(sa.text(
                f"CREATE POLICY {table}_tenant_isolation ON {table} "
                "USING (tenant_id = current_setting('app.tenant_id', true)) "
                "WITH CHECK (tenant_id = current_setting('app.tenant_id', true))"
            ))


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table in ("dashboard_widgets", "dashboards"):
            bind.execute(sa.text(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}"))
    op.drop_table("dashboard_widgets")
    op.drop_table("dashboards")
