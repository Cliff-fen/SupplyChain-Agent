"""Add datasource lifecycle and schema snapshots."""

from alembic import op
import sqlalchemy as sa

revision = "0006_datasource_lifecycle"
down_revision = "0005_knowledge_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns("data_sources")}
    for column in (
        sa.Column("status", sa.String(24), nullable=False, server_default="active"),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
    ):
        if column.name not in existing_columns:
            op.add_column("data_sources", column)
    if "schema_snapshots" not in inspector.get_table_names():
        op.create_table(
            "schema_snapshots",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("tenant_id", sa.String(36), nullable=False, index=True),
            sa.Column("data_source_id", sa.String(36), nullable=False),
            sa.Column("tables", sa.JSON(), nullable=False),
            sa.Column("table_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
    if bind.dialect.name == "postgresql":
        bind.execute(sa.text("ALTER TABLE schema_snapshots ENABLE ROW LEVEL SECURITY"))
        bind.execute(sa.text("DROP POLICY IF EXISTS schema_snapshots_tenant_isolation ON schema_snapshots"))
        bind.execute(sa.text("CREATE POLICY schema_snapshots_tenant_isolation ON schema_snapshots USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true))"))


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        bind.execute(sa.text("DROP POLICY IF EXISTS schema_snapshots_tenant_isolation ON schema_snapshots"))
    if "schema_snapshots" in sa.inspect(bind).get_table_names():
        op.drop_table("schema_snapshots")
    for column in ("disabled_at", "last_synced_at", "last_tested_at", "status"):
        op.drop_column("data_sources", column)
