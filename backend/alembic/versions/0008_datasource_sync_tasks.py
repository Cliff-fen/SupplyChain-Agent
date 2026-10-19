"""Persist data source schema synchronization tasks."""
from alembic import op
import sqlalchemy as sa

revision = "0008_datasource_sync_tasks"
down_revision = "0007_member_invitations"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "data_source_sync_tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("data_source_id", sa.String(36), sa.ForeignKey("data_sources.id"), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="queued"),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("error_message", sa.Text()),
        sa.Column("snapshot_id", sa.String(36)),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_data_source_sync_tasks_data_source_id", "data_source_sync_tasks", ["data_source_id"])
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        bind.execute(sa.text("ALTER TABLE data_source_sync_tasks ENABLE ROW LEVEL SECURITY"))
        bind.execute(sa.text(
            "CREATE POLICY data_source_sync_tasks_tenant_isolation ON data_source_sync_tasks "
            "USING (tenant_id = current_setting('app.tenant_id', true)) "
            "WITH CHECK (tenant_id = current_setting('app.tenant_id', true))"
        ))

def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        bind.execute(sa.text("DROP POLICY IF EXISTS data_source_sync_tasks_tenant_isolation ON data_source_sync_tasks"))
    op.drop_table("data_source_sync_tasks")
