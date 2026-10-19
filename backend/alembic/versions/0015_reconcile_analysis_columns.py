"""Reconcile analysis columns for databases stamped before resource migrations."""

from alembic import op

revision = "0015_reconcile_analysis_columns"
down_revision = "0014_organization_owner"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE analysis_runs ADD COLUMN IF NOT EXISTS knowledge_base_id VARCHAR(36)")
    op.execute("ALTER TABLE analysis_runs ADD COLUMN IF NOT EXISTS sql_draft TEXT")
    op.execute("ALTER TABLE analysis_runs ADD COLUMN IF NOT EXISTS guard_error TEXT")
    op.execute("ALTER TABLE analysis_runs ADD COLUMN IF NOT EXISTS rewrite_count INTEGER NOT NULL DEFAULT 0")


def downgrade() -> None:
    op.execute("ALTER TABLE analysis_runs DROP COLUMN IF EXISTS knowledge_base_id")
    op.execute("ALTER TABLE analysis_runs DROP COLUMN IF EXISTS sql_draft")
    op.execute("ALTER TABLE analysis_runs DROP COLUMN IF EXISTS guard_error")
    op.execute("ALTER TABLE analysis_runs DROP COLUMN IF EXISTS rewrite_count")
