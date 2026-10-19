import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


class Base(DeclarativeBase):
    pass


class UUIDPrimaryKey:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))


class TenantModel(UUIDPrimaryKey):
    __abstract__ = True
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)


class EmbeddingVector(TypeDecorator):
    """Use pgvector in PostgreSQL and JSON only for isolated SQLite tests."""

    impl = JSON
    cache_ok = True

    def __init__(self, dimensions: int = 1024, **kwargs) -> None:
        self.dimensions = dimensions
        super().__init__(**kwargs)

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(Vector(self.dimensions))
        return dialect.type_descriptor(JSON())


class Organization(UUIDPrimaryKey, Base):
    __tablename__ = "organizations"
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    owner_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    quota_config: Mapped[dict] = mapped_column(
        JSON,
        default=lambda: {
            "max_concurrent_analyses": 4,
            "daily_analysis_runs": 100,
            "max_document_size_mb": 10,
            "retention_days": 90,
        },
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class User(UUIDPrimaryKey, Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(160))
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, default=False)


class Membership(UUIDPrimaryKey, Base):
    __tablename__ = "memberships"
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(32), default="viewer")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class MemberInvitation(UUIDPrimaryKey, Base):
    __tablename__ = "member_invitations"
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    email: Mapped[str] = mapped_column(String(320), index=True)
    role: Mapped[str] = mapped_column(String(32), default="viewer")
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RefreshToken(UUIDPrimaryKey, Base):
    __tablename__ = "refresh_tokens"
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    replaced_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OIDCLoginState(UUIDPrimaryKey, Base):
    __tablename__ = "oidc_login_states"
    state_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    nonce: Mapped[str] = mapped_column(String(128))
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DataSource(TenantModel, Base):
    __tablename__ = "data_sources"
    name: Mapped[str] = mapped_column(String(160))
    engine: Mapped[str] = mapped_column(String(16))
    host: Mapped[str] = mapped_column(String(255))
    port: Mapped[int] = mapped_column(Integer)
    database_name: Mapped[str] = mapped_column(String(160))
    username: Mapped[str] = mapped_column(String(160))
    encrypted_password: Mapped[str] = mapped_column(Text)
    allowed_tables: Mapped[list[str]] = mapped_column(JSON, default=list)
    tls_required: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(24), default="active")
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SchemaSnapshot(TenantModel, Base):
    __tablename__ = "schema_snapshots"
    data_source_id: Mapped[str] = mapped_column(ForeignKey("data_sources.id"), index=True)
    tables: Mapped[list] = mapped_column(JSON, default=list)
    table_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DataSourceSyncTask(TenantModel, Base):
    __tablename__ = "data_source_sync_tasks"
    data_source_id: Mapped[str] = mapped_column(ForeignKey("data_sources.id"), index=True)
    status: Mapped[str] = mapped_column(String(24), default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    snapshot_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    celery_task_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Conversation(TenantModel, Base):
    __tablename__ = "conversations"
    title: Mapped[str] = mapped_column(String(240))
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ConversationMessage(TenantModel, Base):
    __tablename__ = "conversation_messages"
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    role: Mapped[str] = mapped_column(String(24))
    content: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AnalysisRun(TenantModel, Base):
    __tablename__ = "analysis_runs"
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    data_source_id: Mapped[str] = mapped_column(ForeignKey("data_sources.id"))
    knowledge_base_id: Mapped[str | None] = mapped_column(
        ForeignKey("knowledge_bases.id"), nullable=True
    )
    question: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="queued")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    sql: Mapped[str | None] = mapped_column(Text, nullable=True)
    sql_draft: Mapped[str | None] = mapped_column(Text, nullable=True)
    guard_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    rewrite_count: Mapped[int] = mapped_column(Integer, default=0)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    retry_of_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    agent_version: Mapped[str] = mapped_column(String(32), default="v1")
    graph_version: Mapped[str] = mapped_column(String(32), default="enterprise-v2")
    route: Mapped[str | None] = mapped_column(String(24), nullable=True)
    checkpoint_thread_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    last_event_sequence: Mapped[int] = mapped_column(Integer, default=0)
    token_usage: Mapped[dict] = mapped_column(JSON, default=dict)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AnalysisEvent(TenantModel, Base):
    __tablename__ = "analysis_events"
    __table_args__ = (
        UniqueConstraint("analysis_run_id", "sequence", name="uq_analysis_event_sequence"),
    )
    analysis_run_id: Mapped[str] = mapped_column(ForeignKey("analysis_runs.id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AgentApproval(TenantModel, Base):
    __tablename__ = "agent_approvals"
    analysis_run_id: Mapped[str] = mapped_column(ForeignKey("analysis_runs.id"), index=True)
    tool_name: Mapped[str] = mapped_column(String(160))
    side_effect: Mapped[str] = mapped_column(String(24), default="external_write")
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    request_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    requested_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    decided_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OutboxEvent(TenantModel, Base):
    __tablename__ = "outbox_events"
    aggregate_type: Mapped[str] = mapped_column(String(64), index=True)
    aggregate_id: Mapped[str] = mapped_column(String(36), index=True)
    event_type: Mapped[str] = mapped_column(String(100), index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditEvent(TenantModel, Base):
    __tablename__ = "audit_events"
    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    action: Mapped[str] = mapped_column(String(100), index=True)
    resource_type: Mapped[str] = mapped_column(String(100))
    resource_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AgentStep(TenantModel, Base):
    __tablename__ = "agent_steps"
    analysis_run_id: Mapped[str] = mapped_column(ForeignKey("analysis_runs.id"), index=True)
    name: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32))
    input_summary: Mapped[str] = mapped_column(Text, default="")
    output: Mapped[dict] = mapped_column(JSON, default=dict)
    model_version: Mapped[str] = mapped_column(String(64), default="")
    prompt_version: Mapped[str] = mapped_column(String(64), default="")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    elapsed_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Dashboard(TenantModel, Base):
    __tablename__ = "dashboards"
    name: Mapped[str] = mapped_column(String(160))
    slug: Mapped[str] = mapped_column(String(80))
    refresh_interval_seconds: Mapped[int] = mapped_column(Integer, default=300)
    cached_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    cached_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DashboardRefreshTask(TenantModel, Base):
    __tablename__ = "dashboard_refresh_tasks"
    celery_task_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    filters: Mapped[dict] = mapped_column(JSON, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DashboardWidget(TenantModel, Base):
    __tablename__ = "dashboard_widgets"
    dashboard_id: Mapped[str] = mapped_column(ForeignKey("dashboards.id"), index=True)
    key: Mapped[str] = mapped_column(String(80))
    widget_type: Mapped[str] = mapped_column(String(40))
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    position: Mapped[int] = mapped_column(Integer, default=0)


class KnowledgeBase(TenantModel, Base):
    __tablename__ = "knowledge_bases"
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Document(TenantModel, Base):
    __tablename__ = "documents"
    knowledge_base_id: Mapped[str] = mapped_column(ForeignKey("knowledge_bases.id"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(120))
    content_sha256: Mapped[str] = mapped_column(String(64), index=True)
    file_size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)
    language: Mapped[str] = mapped_column(String(16), default="unknown")
    category: Mapped[str] = mapped_column(String(40), default="other")
    embedding_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    embedding_dimension: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="processed")
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    metric_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    metric_definition: Mapped[str | None] = mapped_column(Text, nullable=True)
    metric_formula: Mapped[str | None] = mapped_column(Text, nullable=True)
    metric_unit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    applicable_factories: Mapped[list] = mapped_column(JSON, default=list)
    applicable_product_lines: Mapped[list] = mapped_column(JSON, default=list)
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Chunk(TenantModel, Base):
    __tablename__ = "document_chunks"
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    parent_chunk_id: Mapped[str | None] = mapped_column(
        ForeignKey("document_chunks.id"), nullable=True, index=True
    )
    level: Mapped[str] = mapped_column(String(16), default="child", index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    location: Mapped[dict] = mapped_column(JSON, default=dict)
    embedding: Mapped[list[float] | None] = mapped_column(EmbeddingVector(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChunkTerm(TenantModel, Base):
    __tablename__ = "chunk_terms"
    __table_args__ = (UniqueConstraint("chunk_id", "term", name="uq_chunk_term"),)
    knowledge_base_id: Mapped[str] = mapped_column(ForeignKey("knowledge_bases.id"), index=True)
    chunk_id: Mapped[str] = mapped_column(ForeignKey("document_chunks.id"), index=True)
    term: Mapped[str] = mapped_column(String(160), index=True)
    term_frequency: Mapped[int] = mapped_column(Integer)
    document_length: Mapped[int] = mapped_column(Integer)


class KnowledgeCorpusStat(TenantModel, Base):
    __tablename__ = "knowledge_corpus_stats"
    __table_args__ = (UniqueConstraint("knowledge_base_id", name="uq_knowledge_corpus_stat"),)
    knowledge_base_id: Mapped[str] = mapped_column(ForeignKey("knowledge_bases.id"), index=True)
    child_chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    average_document_length: Mapped[float] = mapped_column(Float, default=0.0)
    index_version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DocumentVersion(TenantModel, Base):
    __tablename__ = "document_versions"
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    content_sha256: Mapped[str] = mapped_column(String(64))
    source_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(24), default="active")
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IngestionTask(TenantModel, Base):
    __tablename__ = "ingestion_tasks"
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    task_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dead_letter: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    elapsed_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    celery_task_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Report(TenantModel, Base):
    __tablename__ = "reports"
    analysis_run_id: Mapped[str] = mapped_column(ForeignKey("analysis_runs.id"), index=True)
    title: Mapped[str] = mapped_column(String(240))
    markdown: Mapped[str] = mapped_column(Text)
    citations: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(32), default="ready")
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReportExport(TenantModel, Base):
    __tablename__ = "report_exports"
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id"), index=True)
    format: Mapped[str] = mapped_column(String(16), default="pdf")
    status: Mapped[str] = mapped_column(String(32), default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    object_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    storage_backend: Mapped[str] = mapped_column(String(16), default="local")
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    celery_task_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TrainingDataset(TenantModel, Base):
    __tablename__ = "training_datasets"
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(24), default="draft")
    version: Mapped[int] = mapped_column(Integer, default=1)
    source: Mapped[str] = mapped_column(String(80), default="curated")
    consent_scope: Mapped[str] = mapped_column(String(80), default="tenant")
    redaction_status: Mapped[str] = mapped_column(String(24), default="pending")
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TrainingExample(TenantModel, Base):
    __tablename__ = "training_examples"
    dataset_id: Mapped[str] = mapped_column(ForeignKey("training_datasets.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    input_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    target_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(24), default="pending_review")
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DatasetVersion(TenantModel, Base):
    __tablename__ = "dataset_versions"
    dataset_id: Mapped[str] = mapped_column(ForeignKey("training_datasets.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    checksum_sha256: Mapped[str] = mapped_column(String(64))
    example_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(24), default="draft")
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LabelReview(TenantModel, Base):
    __tablename__ = "label_reviews"
    example_id: Mapped[str] = mapped_column(ForeignKey("training_examples.id"), index=True)
    reviewer_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    decision: Mapped[str] = mapped_column(String(24))
    comments: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EvaluationRun(TenantModel, Base):
    __tablename__ = "evaluation_runs"
    dataset_version_id: Mapped[str] = mapped_column(ForeignKey("dataset_versions.id"), index=True)
    model_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("model_versions.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(24), default="queued")
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ModelVersion(TenantModel, Base):
    __tablename__ = "model_versions"
    name: Mapped[str] = mapped_column(String(160))
    provider: Mapped[str] = mapped_column(String(80))
    model_name: Mapped[str] = mapped_column(String(160))
    version: Mapped[str] = mapped_column(String(80))
    model_type: Mapped[str] = mapped_column(String(32), default="base")
    status: Mapped[str] = mapped_column(String(24), default="candidate")
    dataset_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("dataset_versions.id"), nullable=True
    )
    prompt_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    evaluation_report: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FineTuneJob(TenantModel, Base):
    __tablename__ = "fine_tune_jobs"
    dataset_version_id: Mapped[str] = mapped_column(ForeignKey("dataset_versions.id"), index=True)
    base_model_version_id: Mapped[str] = mapped_column(ForeignKey("model_versions.id"))
    status: Mapped[str] = mapped_column(String(24), default="queued")
    method: Mapped[str] = mapped_column(String(32), default="sft")
    hyperparameters: Mapped[dict] = mapped_column(JSON, default=dict)
    provider_job_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserMemorySetting(TenantModel, Base):
    __tablename__ = "user_memory_settings"
    __table_args__ = (UniqueConstraint("tenant_id", "user_id", name="uq_user_memory_setting"),)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class UserMemory(TenantModel, Base):
    __tablename__ = "user_memories"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", "category", "memory_key", name="uq_user_memory"),
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    category: Mapped[str] = mapped_column(String(40), index=True)
    memory_key: Mapped[str] = mapped_column(String(120))
    content: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    source_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("analysis_runs.id"), nullable=True, index=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class MCPServer(TenantModel, Base):
    __tablename__ = "mcp_servers"
    name: Mapped[str] = mapped_column(String(160))
    transport: Mapped[str] = mapped_column(String(32), default="streamable_http")
    endpoint: Mapped[str | None] = mapped_column(Text, nullable=True)
    stdio_catalog_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    encrypted_auth_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="unknown")
    discovered_tools: Mapped[list] = mapped_column(JSON, default=list)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class A2ATask(TenantModel, Base):
    __tablename__ = "a2a_tasks"
    analysis_run_id: Mapped[str] = mapped_column(ForeignKey("analysis_runs.id"), index=True)
    context_id: Mapped[str] = mapped_column(String(128), index=True)
    status: Mapped[str] = mapped_column(String(32), default="submitted", index=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
