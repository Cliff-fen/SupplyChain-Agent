"""add organization owner"""

from alembic import op
import sqlalchemy as sa

revision = "0014_organization_owner"
down_revision = "0013_analysis_idempotency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("owner_user_id", sa.String(length=36), nullable=True))
    op.create_index("ix_organizations_owner_user_id", "organizations", ["owner_user_id"], unique=False)
    op.create_foreign_key("fk_organizations_owner_user_id_users", "organizations", "users", ["owner_user_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_organizations_owner_user_id_users", "organizations", type_="foreignkey")
    op.drop_index("ix_organizations_owner_user_id", table_name="organizations")
    op.drop_column("organizations", "owner_user_id")
