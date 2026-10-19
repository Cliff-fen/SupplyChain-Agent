"""Track document classification and embedding metadata."""
from alembic import op
import sqlalchemy as sa

revision = "0009_document_classification_embedding"
down_revision = "0008_datasource_sync_tasks"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("documents", sa.Column("category", sa.String(40), nullable=False, server_default="other"))
    op.add_column("documents", sa.Column("embedding_model", sa.String(120), nullable=True))
    op.add_column("documents", sa.Column("embedding_dimension", sa.Integer(), nullable=True))

def downgrade() -> None:
    op.drop_column("documents", "embedding_dimension")
    op.drop_column("documents", "embedding_model")
    op.drop_column("documents", "category")
