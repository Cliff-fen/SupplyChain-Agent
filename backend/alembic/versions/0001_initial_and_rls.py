"""Initial SupplyMind schema and tenant isolation policies."""

from pathlib import Path
from runpy import run_path

from alembic import op
from sqlalchemy import String, text

# Freeze the schema that existed when 0001 was introduced. Importing app.models
# here creates future columns before their own migrations can add them.
Base = run_path(str(Path(__file__).resolve().parents[1] / "initial_schema.py"))["Base"]

revision = "0001_initial_and_rls"
down_revision = None
branch_labels = None
depends_on = None

TENANT_TABLES = (
    "data_sources", "conversations", "analysis_runs", "audit_events", "agent_steps",
    "knowledge_bases", "documents", "document_chunks", "ingestion_tasks", "reports", "report_exports",
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # Several upstream revision identifiers exceed Alembic's 32-char default.
        op.alter_column("alembic_version", "version_num", type_=String(128))
    Base.metadata.create_all(bind=bind)
    if bind.dialect.name != "postgresql":
        return
    for table in TENANT_TABLES:
        bind.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        bind.execute(text(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}"))
        bind.execute(text(
            f"CREATE POLICY {table}_tenant_isolation ON {table} "
            "USING (tenant_id = current_setting('app.tenant_id', true)) "
            "WITH CHECK (tenant_id = current_setting('app.tenant_id', true))"
        ))


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table in TENANT_TABLES:
            bind.execute(text(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}"))
            bind.execute(text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))
