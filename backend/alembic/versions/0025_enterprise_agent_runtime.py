"""Add durable enterprise Agent runtime storage."""

from alembic import op
import sqlalchemy as sa

revision = "0025_enterprise_agent_runtime"
down_revision = "0024_task_lifecycle_fields"
branch_labels = None
depends_on = None


def _tenant_table(name: str, *columns: sa.Column, constraints=()) -> None:
    op.create_table(
        name,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        *columns,
        *constraints,
        if_not_exists=True,
    )
    op.create_index(f"ix_{name}_tenant_id", name, ["tenant_id"], if_not_exists=True)
    op.execute(f"ALTER TABLE {name} ENABLE ROW LEVEL SECURITY")
    op.execute(f"DROP POLICY IF EXISTS {name}_tenant_isolation ON {name}")
    op.execute(
        f"CREATE POLICY {name}_tenant_isolation ON {name} "
        "USING (tenant_id = current_setting('app.tenant_id', true)) "
        "WITH CHECK (tenant_id = current_setting('app.tenant_id', true))"
    )


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    for column in (
        sa.Column("graph_version", sa.String(32), nullable=False, server_default="enterprise-v2"),
        sa.Column("route", sa.String(24), nullable=True),
        sa.Column("checkpoint_thread_id", sa.String(255), nullable=True),
        sa.Column("last_event_sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("token_usage", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("estimated_cost_usd", sa.Float(), nullable=False, server_default="0"),
    ):
        op.add_column("analysis_runs", column, if_not_exists=True)
    op.create_index(
        "ix_analysis_runs_checkpoint_thread_id",
        "analysis_runs",
        ["checkpoint_thread_id"],
        if_not_exists=True,
    )
    op.add_column(
        "document_chunks",
        sa.Column("parent_chunk_id", sa.String(36), nullable=True),
        if_not_exists=True,
    )
    op.add_column(
        "document_chunks",
        sa.Column("level", sa.String(16), nullable=False, server_default="child"),
        if_not_exists=True,
    )
    op.add_column(
        "document_chunks",
        sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"),
        if_not_exists=True,
    )
    op.create_foreign_key(
        "fk_document_chunks_parent",
        "document_chunks",
        "document_chunks",
        ["parent_chunk_id"],
        ["id"],
    )
    op.create_index(
        "ix_document_chunks_parent_chunk_id",
        "document_chunks",
        ["parent_chunk_id"],
        if_not_exists=True,
    )
    op.create_index("ix_document_chunks_level", "document_chunks", ["level"], if_not_exists=True)

    _tenant_table(
        "analysis_events",
        sa.Column(
            "analysis_run_id", sa.String(36), sa.ForeignKey("analysis_runs.id"), nullable=False
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        constraints=(
            sa.UniqueConstraint("analysis_run_id", "sequence", name="uq_analysis_event_sequence"),
        ),
    )
    _tenant_table(
        "agent_approvals",
        sa.Column(
            "analysis_run_id", sa.String(36), sa.ForeignKey("analysis_runs.id"), nullable=False
        ),
        sa.Column("tool_name", sa.String(160), nullable=False),
        sa.Column("side_effect", sa.String(24), nullable=False, server_default="external_write"),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column(
            "request_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")
        ),
        sa.Column("requested_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("decided_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    _tenant_table(
        "outbox_events",
        sa.Column("aggregate_type", sa.String(64), nullable=False),
        sa.Column("aggregate_id", sa.String(36), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("available_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    _tenant_table(
        "chunk_terms",
        sa.Column(
            "knowledge_base_id", sa.String(36), sa.ForeignKey("knowledge_bases.id"), nullable=False
        ),
        sa.Column("chunk_id", sa.String(36), sa.ForeignKey("document_chunks.id"), nullable=False),
        sa.Column("term", sa.String(160), nullable=False),
        sa.Column("term_frequency", sa.Integer(), nullable=False),
        sa.Column("document_length", sa.Integer(), nullable=False),
        constraints=(sa.UniqueConstraint("chunk_id", "term", name="uq_chunk_term"),),
    )
    _tenant_table(
        "knowledge_corpus_stats",
        sa.Column(
            "knowledge_base_id", sa.String(36), sa.ForeignKey("knowledge_bases.id"), nullable=False
        ),
        sa.Column("child_chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("average_document_length", sa.Float(), nullable=False, server_default="0"),
        sa.Column("index_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        constraints=(sa.UniqueConstraint("knowledge_base_id", name="uq_knowledge_corpus_stat"),),
    )
    _tenant_table(
        "user_memory_settings",
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        constraints=(sa.UniqueConstraint("tenant_id", "user_id", name="uq_user_memory_setting"),),
    )
    _tenant_table(
        "user_memories",
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("memory_key", sa.String(120), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1"),
        sa.Column("source_run_id", sa.String(36), sa.ForeignKey("analysis_runs.id"), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        constraints=(
            sa.UniqueConstraint(
                "tenant_id", "user_id", "category", "memory_key", name="uq_user_memory"
            ),
        ),
    )
    _tenant_table(
        "mcp_servers",
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("transport", sa.String(32), nullable=False, server_default="streamable_http"),
        sa.Column("endpoint", sa.Text(), nullable=True),
        sa.Column("stdio_catalog_key", sa.String(120), nullable=True),
        sa.Column("encrypted_auth_token", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("status", sa.String(24), nullable=False, server_default="unknown"),
        sa.Column(
            "discovered_tools", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")
        ),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    _tenant_table(
        "a2a_tasks",
        sa.Column(
            "analysis_run_id", sa.String(36), sa.ForeignKey("analysis_runs.id"), nullable=False
        ),
        sa.Column("context_id", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="submitted"),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    for table, columns in {
        "analysis_events": ("analysis_run_id", "event_type"),
        "agent_approvals": ("analysis_run_id", "status"),
        "outbox_events": ("aggregate_id", "event_type", "status"),
        "chunk_terms": ("knowledge_base_id", "chunk_id", "term"),
        "knowledge_corpus_stats": ("knowledge_base_id",),
        "user_memory_settings": ("user_id",),
        "user_memories": ("user_id", "category", "source_run_id"),
        "a2a_tasks": ("analysis_run_id", "context_id", "status"),
    }.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column], if_not_exists=True)


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in (
        "a2a_tasks",
        "mcp_servers",
        "user_memories",
        "user_memory_settings",
        "knowledge_corpus_stats",
        "chunk_terms",
        "outbox_events",
        "agent_approvals",
        "analysis_events",
    ):
        op.drop_table(table, if_exists=True)
    op.drop_constraint("fk_document_chunks_parent", "document_chunks", type_="foreignkey")
    for column in ("token_count", "level", "parent_chunk_id"):
        op.drop_column("document_chunks", column, if_exists=True)
    for column in (
        "estimated_cost_usd",
        "token_usage",
        "last_event_sequence",
        "checkpoint_thread_id",
        "route",
        "graph_version",
    ):
        op.drop_column("analysis_runs", column, if_exists=True)
