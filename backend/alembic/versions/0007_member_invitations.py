"""Add organization member invitations."""

from alembic import op
import sqlalchemy as sa

revision = "0007_member_invitations"
down_revision = "0006_datasource_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "member_invitations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False, server_default="viewer"),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_member_invitations_organization_id", "member_invitations", ["organization_id"])
    op.create_index("ix_member_invitations_email", "member_invitations", ["email"])
    op.create_index("ix_member_invitations_token_hash", "member_invitations", ["token_hash"], unique=True)
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        bind.execute(sa.text("ALTER TABLE member_invitations ENABLE ROW LEVEL SECURITY"))
        bind.execute(sa.text(
            "CREATE POLICY member_invitations_tenant_isolation ON member_invitations "
            "USING (organization_id = current_setting('app.tenant_id', true)) "
            "WITH CHECK (organization_id = current_setting('app.tenant_id', true))"
        ))


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        bind.execute(sa.text("DROP POLICY IF EXISTS member_invitations_tenant_isolation ON member_invitations"))
    op.drop_table("member_invitations")
