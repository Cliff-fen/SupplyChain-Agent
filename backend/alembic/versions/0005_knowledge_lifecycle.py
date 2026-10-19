"""Add knowledge base and ingestion lifecycle fields."""

from alembic import op
import sqlalchemy as sa

revision = "0005_knowledge_lifecycle"
down_revision = "0004_organization_quotas"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("knowledge_bases", sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("knowledge_bases", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("documents", sa.Column("file_size_bytes", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("documents", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("documents", sa.Column("language", sa.String(16), nullable=False, server_default="unknown"))
    op.add_column("documents", sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("documents", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("ingestion_tasks", sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"))
    op.add_column("ingestion_tasks", sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("ingestion_tasks", sa.Column("dead_letter", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("ingestion_tasks", sa.Column("elapsed_ms", sa.Integer(), nullable=True))


def downgrade() -> None:
    for table, columns in {
        "ingestion_tasks": ("elapsed_ms", "dead_letter", "next_retry_at", "max_attempts"),
        "documents": ("archived_at", "is_archived", "language", "version", "file_size_bytes"),
        "knowledge_bases": ("archived_at", "is_archived"),
    }.items():
        for column in columns:
            op.drop_column(table, column)
