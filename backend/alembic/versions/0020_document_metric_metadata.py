"""Add explainable metric definition metadata to documents."""
from alembic import op
import sqlalchemy as sa

revision = "0020_document_metric_metadata"
down_revision = "0019_repair_report_storage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("metric_name", sa.String(length=160), nullable=True))
    op.add_column("documents", sa.Column("metric_definition", sa.Text(), nullable=True))
    op.add_column("documents", sa.Column("metric_formula", sa.Text(), nullable=True))
    op.add_column("documents", sa.Column("metric_unit", sa.String(length=40), nullable=True))
    op.add_column("documents", sa.Column("applicable_factories", sa.JSON(), nullable=False, server_default=sa.text("'[]'")))
    op.add_column("documents", sa.Column("applicable_product_lines", sa.JSON(), nullable=False, server_default=sa.text("'[]'")))
    op.add_column("documents", sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    for column in ("effective_from", "applicable_product_lines", "applicable_factories", "metric_unit", "metric_formula", "metric_definition", "metric_name"):
        op.drop_column("documents", column)
