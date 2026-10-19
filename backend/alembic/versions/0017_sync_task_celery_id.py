"""Persist Celery id for datasource schema sync tasks."""

from alembic import op
import sqlalchemy as sa

revision = "0017_sync_task_celery_id"
down_revision = "0016_reconcile_document_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("data_source_sync_tasks", sa.Column("celery_task_id", sa.String(length=128), nullable=True))


def downgrade() -> None:
    op.drop_column("data_source_sync_tasks", "celery_task_id")
