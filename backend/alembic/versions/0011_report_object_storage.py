"""Persist report object storage metadata."""
from alembic import op
import sqlalchemy as sa

revision = "0011_report_object_storage"
down_revision = "0010_analysis_trace_fields"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("report_exports", sa.Column("object_key", sa.Text(), nullable=True))
    op.add_column("report_exports", sa.Column("storage_backend", sa.String(16), nullable=False, server_default="local"))

def downgrade() -> None:
    op.drop_column("report_exports", "storage_backend")
    op.drop_column("report_exports", "object_key")
