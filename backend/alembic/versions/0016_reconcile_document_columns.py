"""Reconcile document classification and embedding columns."""

from alembic import op

revision = "0016_reconcile_document_columns"
down_revision = "0015_reconcile_analysis_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS category VARCHAR(40) NOT NULL DEFAULT 'other'")
    op.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS embedding_model VARCHAR(120)")
    op.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS embedding_dimension INTEGER")


def downgrade() -> None:
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS embedding_dimension")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS embedding_model")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS category")
