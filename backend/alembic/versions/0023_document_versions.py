"""Add document version history for controlled rollback."""

from alembic import op
import sqlalchemy as sa

revision = "0023_document_versions"
down_revision = "0022_ai_governance_pgvector"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.create_table(
        "document_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False, index=True),
        sa.Column("document_id", sa.String(36), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("source_path", sa.Text(), nullable=True),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(24), nullable=False, server_default="active"),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        if_not_exists=True,
    )
    op.create_index("ix_document_versions_document_id", "document_versions", ["document_id"], if_not_exists=True)
    op.execute("ALTER TABLE document_versions ENABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS document_versions_tenant_isolation ON document_versions")
    op.execute("CREATE POLICY document_versions_tenant_isolation ON document_versions USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true))")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.drop_table("document_versions", if_exists=True)
