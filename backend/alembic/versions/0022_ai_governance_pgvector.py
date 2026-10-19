"""Add server-side conversation turns, AI governance entities and pgvector."""

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = "0022_ai_governance_pgvector"
down_revision = "0021_organization_status"
branch_labels = None
depends_on = None


def _tenant_columns():
    return [
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False, index=True),
    ]


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Existing deployments used JSON embeddings. Convert only vectors with the
    # configured dimension; malformed or incompatible rows remain unavailable
    # and are re-ingested explicitly instead of blocking the migration.
    op.execute("""
    DO $$
    BEGIN
      IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'document_chunks' AND column_name = 'embedding'
          AND data_type IN ('json', 'jsonb')
      ) THEN
        ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS embedding_vector vector(1024);
        UPDATE document_chunks
        SET embedding_vector = (embedding::text)::vector
        WHERE embedding IS NOT NULL
          AND jsonb_typeof(embedding::jsonb) = 'array'
          AND jsonb_array_length(embedding::jsonb) = 1024;
        ALTER TABLE document_chunks DROP COLUMN embedding;
        ALTER TABLE document_chunks RENAME COLUMN embedding_vector TO embedding;
      END IF;
    END $$;
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_document_chunks_embedding_hnsw ON document_chunks USING hnsw (embedding vector_cosine_ops)")

    op.create_table(
        "conversation_messages",
        *_tenant_columns(),
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("conversations.id"), nullable=False),
        sa.Column("role", sa.String(24), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        if_not_exists=True,
    )
    op.create_index("ix_conversation_messages_conversation_id", "conversation_messages", ["conversation_id"], if_not_exists=True)

    for table, columns in {
        "training_datasets": [
            sa.Column("name", sa.String(160), nullable=False), sa.Column("description", sa.Text(), nullable=False),
            sa.Column("status", sa.String(24), nullable=False), sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("source", sa.String(80), nullable=False), sa.Column("consent_scope", sa.String(80), nullable=False),
            sa.Column("redaction_status", sa.String(24), nullable=False), sa.Column("created_by", sa.String(36), nullable=False),
        ],
        "training_examples": [
            sa.Column("dataset_id", sa.String(36), nullable=False), sa.Column("kind", sa.String(40), nullable=False),
            sa.Column("input_payload", sa.JSON(), nullable=False), sa.Column("target_payload", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(24), nullable=False), sa.Column("created_by", sa.String(36), nullable=False),
        ],
        "dataset_versions": [
            sa.Column("dataset_id", sa.String(36), nullable=False), sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("checksum_sha256", sa.String(64), nullable=False), sa.Column("example_count", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(24), nullable=False), sa.Column("created_by", sa.String(36), nullable=False),
        ],
        "label_reviews": [
            sa.Column("example_id", sa.String(36), nullable=False), sa.Column("reviewer_id", sa.String(36), nullable=False),
            sa.Column("decision", sa.String(24), nullable=False), sa.Column("comments", sa.Text(), nullable=False),
        ],
        "model_versions": [
            sa.Column("name", sa.String(160), nullable=False), sa.Column("provider", sa.String(80), nullable=False),
            sa.Column("model_name", sa.String(160), nullable=False), sa.Column("version", sa.String(80), nullable=False),
            sa.Column("model_type", sa.String(32), nullable=False), sa.Column("status", sa.String(24), nullable=False),
            sa.Column("dataset_version_id", sa.String(36), nullable=True), sa.Column("prompt_version", sa.String(80), nullable=True),
            sa.Column("evaluation_report", sa.JSON(), nullable=False), sa.Column("created_by", sa.String(36), nullable=False),
        ],
        "evaluation_runs": [
            sa.Column("dataset_version_id", sa.String(36), nullable=False), sa.Column("model_version_id", sa.String(36), nullable=True),
            sa.Column("status", sa.String(24), nullable=False), sa.Column("metrics", sa.JSON(), nullable=False),
            sa.Column("failure_reason", sa.Text(), nullable=True), sa.Column("created_by", sa.String(36), nullable=False),
        ],
        "fine_tune_jobs": [
            sa.Column("dataset_version_id", sa.String(36), nullable=False), sa.Column("base_model_version_id", sa.String(36), nullable=False),
            sa.Column("status", sa.String(24), nullable=False), sa.Column("method", sa.String(32), nullable=False),
            sa.Column("hyperparameters", sa.JSON(), nullable=False), sa.Column("provider_job_id", sa.String(160), nullable=True),
            sa.Column("failure_reason", sa.Text(), nullable=True), sa.Column("created_by", sa.String(36), nullable=False),
        ],
    }.items():
        op.create_table(table, *_tenant_columns(), *columns, sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()), if_not_exists=True)
    for table in ("conversation_messages", "training_datasets", "training_examples", "dataset_versions", "label_reviews", "model_versions", "evaluation_runs", "fine_tune_jobs"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
        op.execute(f"CREATE POLICY {table}_tenant_isolation ON {table} USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true))")
def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table in ("fine_tune_jobs", "evaluation_runs", "label_reviews", "dataset_versions", "training_examples", "model_versions", "training_datasets", "conversation_messages"):
            op.drop_table(table, if_exists=True)
