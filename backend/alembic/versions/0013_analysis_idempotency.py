"""Persist analysis idempotency and retry lineage."""
from alembic import op
import sqlalchemy as sa

revision = "0013_analysis_idempotency"
down_revision = "0012_analysis_resources"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("analysis_runs", sa.Column("idempotency_key", sa.String(128), nullable=True))
    op.add_column("analysis_runs", sa.Column("retry_of_id", sa.String(36), nullable=True))
    op.create_index("ix_analysis_runs_idempotency_key", "analysis_runs", ["idempotency_key"])
    op.create_index("ix_analysis_runs_retry_of_id", "analysis_runs", ["retry_of_id"])


def downgrade() -> None:
    op.drop_index("ix_analysis_runs_retry_of_id", table_name="analysis_runs")
    op.drop_index("ix_analysis_runs_idempotency_key", table_name="analysis_runs")
    op.drop_column("analysis_runs", "retry_of_id")
    op.drop_column("analysis_runs", "idempotency_key")
