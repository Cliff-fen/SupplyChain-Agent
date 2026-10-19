"""Frozen revision 0001 schema from upstream commit de28e92.

Historical migrations must never import the evolving application metadata.
"""

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class UUIDPrimaryKey:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))


class TenantModel(UUIDPrimaryKey):
    __abstract__ = True
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)


class Organization(UUIDPrimaryKey, Base):
    __tablename__ = "organizations"
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Conversation(TenantModel, Base):
    __tablename__ = "conversations"
    title: Mapped[str] = mapped_column(String(240))
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AnalysisRun(TenantModel, Base):
    __tablename__ = "analysis_runs"
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    data_source_id: Mapped[str] = mapped_column(ForeignKey("data_sources.id"))
    question: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="queued")
    sql: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    agent_version: Mapped[str] = mapped_column(String(32), default="v1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditEvent(TenantModel, Base):
    __tablename__ = "audit_events"
    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    action: Mapped[str] = mapped_column(String(100), index=True)
    resource_type: Mapped[str] = mapped_column(String(100))
    resource_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AgentStep(TenantModel, Base):
    __tablename__ = "agent_steps"
    analysis_run_id: Mapped[str] = mapped_column(ForeignKey("analysis_runs.id"), index=True)
    name: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32))
    input_summary: Mapped[str] = mapped_column(Text, default="")
    output: Mapped[dict] = mapped_column(JSON, default=dict)
    elapsed_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class KnowledgeBase(TenantModel, Base):
    __tablename__ = "knowledge_bases"
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Document(TenantModel, Base):
    __tablename__ = "documents"
    knowledge_base_id: Mapped[str] = mapped_column(ForeignKey("knowledge_bases.id"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(120))
    content_sha256: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="processed")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Chunk(TenantModel, Base):
    __tablename__ = "document_chunks"
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    location: Mapped[dict] = mapped_column(JSON, default=dict)
    embedding: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IngestionTask(TenantModel, Base):
    __tablename__ = "ingestion_tasks"
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    task_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    celery_task_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


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
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    celery_task_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
