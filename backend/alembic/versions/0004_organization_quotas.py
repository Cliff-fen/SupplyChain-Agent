"""Add persisted organization quota configuration."""

from alembic import op
import sqlalchemy as sa

revision = "0004_organization_quotas"
down_revision = "0003_dashboards"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column(
            "quota_config",
            sa.JSON(),
            nullable=False,
            server_default=sa.text(
                "'{\"max_concurrent_analyses\": 4, \"daily_analysis_runs\": 100, "
                "\"max_document_size_mb\": 10, \"retention_days\": 90}'"
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("organizations", "quota_config")
