"""Add organization lifecycle status."""

from alembic import op
import sqlalchemy as sa

revision = "0021_organization_status"
down_revision = "0020_document_metric_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.alter_column("organizations", "is_active", server_default=None)


def downgrade() -> None:
    op.drop_column("organizations", "is_active")
