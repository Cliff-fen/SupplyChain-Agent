"""Repair report storage columns for databases stamped past 0011."""
from alembic import op
import sqlalchemy as sa

revision = "0019_repair_report_storage"
down_revision = "0018_dashboard_refresh_tasks"
branch_labels = None
depends_on = None

def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("report_exports")}
    if "object_key" not in columns:
        op.add_column("report_exports", sa.Column("object_key", sa.Text(), nullable=True))
    if "storage_backend" not in columns:
        op.add_column("report_exports", sa.Column("storage_backend", sa.String(16), nullable=False, server_default="local"))

def downgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("report_exports")}
    if "storage_backend" in columns:
        op.drop_column("report_exports", "storage_backend")
    if "object_key" in columns:
        op.drop_column("report_exports", "object_key")
