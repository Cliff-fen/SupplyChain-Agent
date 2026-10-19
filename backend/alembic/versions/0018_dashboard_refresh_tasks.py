"""Persist dashboard refresh task status."""
from alembic import op
import sqlalchemy as sa

revision = "0018_dashboard_refresh_tasks"
down_revision = "0017_sync_task_celery_id"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "dashboard_refresh_tasks",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("celery_task_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("filters", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_dashboard_refresh_tasks_tenant_id", "dashboard_refresh_tasks", ["tenant_id"])
    op.create_index("ix_dashboard_refresh_tasks_celery_task_id", "dashboard_refresh_tasks", ["celery_task_id"])

def downgrade() -> None:
    op.drop_index("ix_dashboard_refresh_tasks_celery_task_id", table_name="dashboard_refresh_tasks")
    op.drop_index("ix_dashboard_refresh_tasks_tenant_id", table_name="dashboard_refresh_tasks")
    op.drop_table("dashboard_refresh_tasks")
