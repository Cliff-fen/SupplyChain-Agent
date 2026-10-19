"""Persist analysis knowledge-base selection."""
from alembic import op
import sqlalchemy as sa

revision = "0012_analysis_resources"
down_revision = "0011_report_object_storage"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("analysis_runs", sa.Column("knowledge_base_id", sa.String(36), sa.ForeignKey("knowledge_bases.id"), nullable=True))

def downgrade() -> None:
    op.drop_column("analysis_runs", "knowledge_base_id")
