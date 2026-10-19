"""Persist analysis SQL draft and guard diagnostics."""
from alembic import op
import sqlalchemy as sa

revision = "0010_analysis_trace_fields"
down_revision = "0009_document_classification_embedding"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("analysis_runs", sa.Column("sql_draft", sa.Text(), nullable=True))
    op.add_column("analysis_runs", sa.Column("guard_error", sa.Text(), nullable=True))
    op.add_column("analysis_runs", sa.Column("rewrite_count", sa.Integer(), nullable=False, server_default="0"))

def downgrade() -> None:
    op.drop_column("analysis_runs", "rewrite_count")
    op.drop_column("analysis_runs", "guard_error")
    op.drop_column("analysis_runs", "sql_draft")
