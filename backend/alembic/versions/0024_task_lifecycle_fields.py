"""Persist lifecycle metadata for recoverable asynchronous work."""

from alembic import op
import sqlalchemy as sa

revision = "0024_task_lifecycle_fields"
down_revision = "0023_document_versions"
branch_labels = None
depends_on = None


def _add(table: str, column: sa.Column) -> None:
    op.add_column(table, column, if_not_exists=True)


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in ("data_source_sync_tasks", "dashboard_refresh_tasks", "report_exports"):
        _add(table, sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"))
        _add(table, sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"))
    for table in ("analysis_runs", "ingestion_tasks", "report_exports"):
        _add(table, sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
        _add(table, sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True))
    _add("analysis_runs", sa.Column("attempts", sa.Integer(), nullable=False, server_default="1"))
    _add("analysis_runs", sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"))
    _add("analysis_runs", sa.Column("error_message", sa.Text(), nullable=True))


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table, columns in {
        "data_source_sync_tasks": ("attempts", "max_attempts"),
        "dashboard_refresh_tasks": ("attempts", "max_attempts"),
        "report_exports": ("attempts", "max_attempts", "started_at", "finished_at"),
        "analysis_runs": ("attempts", "max_attempts", "error_message", "started_at", "finished_at"),
        "ingestion_tasks": ("started_at", "finished_at"),
    }.items():
        for column in columns:
            op.drop_column(table, column, if_exists=True)
