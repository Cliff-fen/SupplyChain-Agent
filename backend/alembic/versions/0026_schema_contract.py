"""Reconcile historical migrations with the upstream ORM's integrity contract.

No business columns are removed or renamed. Existing inconsistent data causes
the transaction to fail rather than being silently deleted or fabricated.
"""

from alembic import op
import sqlalchemy as sa

revision = "0026_schema_contract"
down_revision = "0025_enterprise_agent_runtime"
branch_labels = None
depends_on = None

REQUIRED_TIMESTAMPS = {
    "a2a_tasks": ("created_at",),
    "agent_approvals": ("created_at",),
    "analysis_events": ("created_at",),
    "conversation_messages": ("created_at",),
    "dashboards": ("created_at",),
    "dataset_versions": ("created_at",),
    "document_versions": ("created_at",),
    "evaluation_runs": ("created_at",),
    "fine_tune_jobs": ("created_at",),
    "knowledge_corpus_stats": ("updated_at",),
    "label_reviews": ("created_at",),
    "mcp_servers": ("created_at",),
    "model_versions": ("created_at",),
    "outbox_events": ("available_at", "created_at"),
    "schema_snapshots": ("created_at",),
    "training_datasets": ("created_at",),
    "training_examples": ("created_at",),
    "user_memories": ("created_at", "updated_at"),
    "user_memory_settings": ("updated_at",),
}
INDEXES = {
    "dashboard_widgets": ("dashboard_id",),
    "data_source_sync_tasks": ("tenant_id",),
    "dataset_versions": ("dataset_id",),
    "evaluation_runs": ("dataset_version_id",),
    "fine_tune_jobs": ("dataset_version_id",),
    "label_reviews": ("example_id",),
    "outbox_events": ("aggregate_type",),
    "schema_snapshots": ("data_source_id",),
    "training_examples": ("dataset_id",),
}
FOREIGN_KEYS = (
    ("dashboard_widgets", "dashboard_id", "dashboards"),
    ("dataset_versions", "created_by", "users"),
    ("dataset_versions", "dataset_id", "training_datasets"),
    ("evaluation_runs", "model_version_id", "model_versions"),
    ("evaluation_runs", "dataset_version_id", "dataset_versions"),
    ("evaluation_runs", "created_by", "users"),
    ("fine_tune_jobs", "dataset_version_id", "dataset_versions"),
    ("fine_tune_jobs", "base_model_version_id", "model_versions"),
    ("fine_tune_jobs", "created_by", "users"),
    ("label_reviews", "example_id", "training_examples"),
    ("label_reviews", "reviewer_id", "users"),
    ("model_versions", "dataset_version_id", "dataset_versions"),
    ("model_versions", "created_by", "users"),
    ("schema_snapshots", "data_source_id", "data_sources"),
    ("training_datasets", "created_by", "users"),
    ("training_examples", "dataset_id", "training_datasets"),
    ("training_examples", "created_by", "users"),
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    inspector = sa.inspect(bind)
    for table, columns in REQUIRED_TIMESTAMPS.items():
        for column in columns:
            op.alter_column(table, column, nullable=False)
    for table, columns in INDEXES.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column], if_not_exists=True)
    for table, column, target in FOREIGN_KEYS:
        # A few old installations already received these constraints from
        # metadata-based initialization. Check the actual constraint, not stamp.
        if column not in {item["name"] for item in inspector.get_columns(table)}:
            continue
        existing = inspector.get_foreign_keys(table)
        if not any(fk["constrained_columns"] == [column] and fk["referred_table"] == target
                   for fk in existing):
            op.create_foreign_key(f"fk_{table}_{column}", table, target, [column], ["id"])
    # The dashboard refresh table was the only tenant table introduced without
    # the tenant policy used throughout the original migration chain.
    op.execute("ALTER TABLE dashboard_refresh_tasks ENABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS dashboard_refresh_tasks_tenant_isolation ON dashboard_refresh_tasks")
    op.execute(
        "CREATE POLICY dashboard_refresh_tasks_tenant_isolation ON dashboard_refresh_tasks "
        "USING (tenant_id = current_setting('app.tenant_id', true)) "
        "WITH CHECK (tenant_id = current_setting('app.tenant_id', true))"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    inspector = sa.inspect(bind)
    op.execute("DROP POLICY IF EXISTS dashboard_refresh_tasks_tenant_isolation ON dashboard_refresh_tasks")
    op.execute("ALTER TABLE dashboard_refresh_tasks DISABLE ROW LEVEL SECURITY")
    for table, column, _ in reversed(FOREIGN_KEYS):
        name = f"fk_{table}_{column}"
        if any(fk["name"] == name for fk in inspector.get_foreign_keys(table)):
            op.drop_constraint(name, table, type_="foreignkey")
    for table, columns in INDEXES.items():
        for column in columns:
            op.drop_index(f"ix_{table}_{column}", table_name=table, if_exists=True)
    for table, columns in REQUIRED_TIMESTAMPS.items():
        for column in columns:
            op.alter_column(table, column, nullable=True)
