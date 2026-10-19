from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Role = Literal["platform_admin", "org_admin", "analyst", "viewer"]


class LoginRequest(BaseModel):
    email: str
    password: str
    organization_slug: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"


class OrganizationAccessView(BaseModel):
    id: str
    slug: str
    name: str
    role: Role


class OrganizationSwitchRequest(BaseModel):
    organization_id: str


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=20)


class MemberView(BaseModel):
    user_id: str
    email: str
    display_name: str
    role: Role
    is_active: bool


class MemberRoleUpdate(BaseModel):
    role: Role


class MemberStatusUpdate(BaseModel):
    is_active: bool


class MemberInvitationCreate(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    role: Role = "viewer"
    expires_in_days: int = Field(default=7, ge=1, le=30)


class MemberInvitationView(BaseModel):
    id: str
    email: str
    role: Role
    status: Literal["pending", "accepted", "expired", "revoked"]
    expires_at: datetime
    created_at: datetime
    token: str | None = None


class MemberInvitationAccept(BaseModel):
    token: str = Field(min_length=20)
    display_name: str = Field(min_length=1, max_length=160)
    password: str = Field(min_length=8, max_length=128)


class Principal(BaseModel):
    user_id: str
    tenant_id: str
    role: Role


class OrganizationSummary(BaseModel):
    id: str
    slug: str
    name: str
    owner_user_id: str | None = None
    owner_name: str | None = None
    role: Role
    member_count: int
    active_member_count: int
    data_source_count: int
    knowledge_base_count: int
    report_count: int
    dashboard_count: int
    quota: dict[str, int]
    quota_usage: dict[str, int]


class QuotaUpdate(BaseModel):
    max_concurrent_analyses: int = Field(ge=1, le=100)
    daily_analysis_runs: int = Field(ge=1, le=100_000)
    max_document_size_mb: int = Field(ge=1, le=1024)
    retention_days: int = Field(ge=1, le=3650)


class PlatformOrganizationView(BaseModel):
    id: str
    slug: str
    name: str
    owner_user_id: str | None = None
    owner_name: str | None = None
    member_count: int
    active_member_count: int
    data_source_count: int
    knowledge_base_count: int
    report_count: int
    created_at: datetime
    is_active: bool
    quota: dict[str, int]


class PlatformOrganizationCreate(BaseModel):
    slug: str = Field(min_length=2, max_length=64, pattern=r"^[a-z0-9][a-z0-9-]*$")
    name: str = Field(min_length=2, max_length=160)
    owner_user_id: str | None = None
    quota: QuotaUpdate | None = None


class PlatformOrganizationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    owner_user_id: str | None = None
    quota: QuotaUpdate | None = None


class PlatformOrganizationStatusUpdate(BaseModel):
    is_active: bool


class OrganizationSettingsUpdate(BaseModel):
    owner_user_id: str = Field(min_length=1)


class PermissionMatrixView(BaseModel):
    roles: dict[str, dict[str, bool]]


class DataSourceCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    engine: Literal["mysql", "postgresql"]
    host: str
    port: int = Field(ge=1, le=65535)
    database_name: str
    username: str
    password: str = Field(min_length=1)
    # The allowlist is selected from a synced schema after the connection exists.
    allowed_tables: list[str] = Field(default_factory=list)
    tls_required: bool = False


class DataSourceAllowlistUpdate(BaseModel):
    allowed_tables: list[str] = Field(min_length=1)


class DataSourceTlsUpdate(BaseModel):
    tls_required: bool


class DataSourceView(BaseModel):
    id: str
    name: str
    engine: str
    host: str
    port: int
    database_name: str
    allowed_tables: list[str]
    tls_required: bool
    status: str = "active"
    last_tested_at: datetime | None = None
    last_synced_at: datetime | None = None
    created_at: datetime


class SchemaSnapshotView(BaseModel):
    id: str
    data_source_id: str
    tables: list
    table_count: int
    created_at: datetime


class DataSourceSyncTaskView(BaseModel):
    id: str
    data_source_id: str
    status: str
    attempts: int = 0
    max_attempts: int = 3
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None
    snapshot_id: str | None = None
    celery_task_id: str | None = None
    created_at: datetime


class QueryRequest(BaseModel):
    sql: str = Field(min_length=8, max_length=20_000)


class AnalysisRequest(BaseModel):
    data_source_id: str
    knowledge_base_id: str | None = None
    question: str = Field(min_length=5, max_length=4000)
    conversation_id: str | None = None
    context: list[str] = Field(default_factory=list, max_length=12)


class AnalysisAccepted(BaseModel):
    run_id: str
    conversation_id: str
    status: Literal["queued"] = "queued"
    stream_url: str


class ConversationMessageView(BaseModel):
    id: str
    conversation_id: str
    role: Literal["user", "assistant", "system"]
    content: str
    metadata: dict = Field(default_factory=dict)
    created_at: datetime


class MemorySettingView(BaseModel):
    enabled: bool


class MemorySettingUpdate(BaseModel):
    enabled: bool


class UserMemoryCreate(BaseModel):
    category: Literal[
        "communication",
        "kpi_interest",
        "factory_scope",
        "product_line",
        "time_range",
        "role_context",
    ]
    memory_key: str = Field(min_length=1, max_length=120, pattern=r"^[a-zA-Z0-9_.:-]+$")
    content: str = Field(min_length=1, max_length=2000)
    confidence: float = Field(default=1.0, ge=0.8, le=1.0)
    expires_at: datetime | None = None


class UserMemoryUpdate(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
    confidence: float = Field(default=1.0, ge=0.8, le=1.0)
    expires_at: datetime | None = None


class UserMemoryView(BaseModel):
    id: str
    category: str
    memory_key: str
    content: str
    confidence: float
    source_run_id: str | None
    version: int
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime


class MCPServerCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    transport: Literal["streamable_http", "stdio"] = "streamable_http"
    endpoint: str | None = Field(default=None, max_length=2000)
    stdio_catalog_key: str | None = Field(default=None, max_length=120)
    auth_token: str | None = Field(default=None, max_length=4000)


class MCPServerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    enabled: bool | None = None
    endpoint: str | None = Field(default=None, max_length=2000)
    stdio_catalog_key: str | None = Field(default=None, max_length=120)
    auth_token: str | None = Field(default=None, max_length=4000)


class MCPServerView(BaseModel):
    id: str
    name: str
    transport: str
    endpoint: str | None
    stdio_catalog_key: str | None
    enabled: bool
    status: str
    discovered_tools: list
    last_checked_at: datetime | None
    error_message: str | None
    created_at: datetime


class AgentApprovalView(BaseModel):
    id: str
    analysis_run_id: str
    tool_name: str
    side_effect: str
    status: str
    request_payload: dict
    requested_by: str
    decided_by: str | None
    decision_reason: str | None
    expires_at: datetime | None
    decided_at: datetime | None
    created_at: datetime


class ApprovalDecision(BaseModel):
    reason: str = Field(default="", max_length=1000)


class TrainingDatasetCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    description: str = Field(default="", max_length=4000)
    source: str = Field(default="curated", max_length=80)
    consent_scope: str = Field(default="tenant", max_length=80)


class TrainingDatasetView(BaseModel):
    id: str
    name: str
    description: str
    status: str
    version: int
    source: str
    consent_scope: str
    redaction_status: str
    created_by: str
    created_at: datetime


class TrainingExampleCreate(BaseModel):
    kind: Literal["intent", "plan", "sql", "answer", "correction", "risk"]
    input_payload: dict
    target_payload: dict


class TrainingExampleView(BaseModel):
    id: str
    dataset_id: str
    kind: str
    input_payload: dict
    target_payload: dict
    status: str
    created_by: str
    created_at: datetime


class DatasetVersionView(BaseModel):
    id: str
    dataset_id: str
    version: int
    checksum_sha256: str
    example_count: int
    status: str
    created_by: str
    created_at: datetime


class ModelVersionCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    provider: str = Field(min_length=2, max_length=80)
    model_name: str = Field(min_length=2, max_length=160)
    version: str = Field(min_length=1, max_length=80)
    model_type: Literal["base", "sft", "preference", "adapter"] = "base"
    dataset_version_id: str | None = None
    prompt_version: str | None = None


class ModelVersionView(BaseModel):
    id: str
    name: str
    provider: str
    model_name: str
    version: str
    model_type: str
    status: str
    dataset_version_id: str | None
    prompt_version: str | None
    evaluation_report: dict
    created_by: str
    created_at: datetime


class EvaluationRunCreate(BaseModel):
    dataset_version_id: str
    model_version_id: str | None = None


class EvaluationRunView(BaseModel):
    id: str
    dataset_version_id: str
    model_version_id: str | None
    status: str
    metrics: dict
    failure_reason: str | None
    created_by: str
    created_at: datetime


class FineTuneJobCreate(BaseModel):
    dataset_version_id: str
    base_model_version_id: str
    method: Literal["sft", "preference"] = "sft"
    hyperparameters: dict = Field(default_factory=dict)


class FineTuneJobView(BaseModel):
    id: str
    dataset_version_id: str
    base_model_version_id: str
    status: str
    method: str
    hyperparameters: dict
    provider_job_id: str | None
    failure_reason: str | None
    created_by: str
    created_at: datetime


class HermesEvolutionSignal(BaseModel):
    id: str
    label: str
    value: float
    unit: str = ""
    status: Literal["healthy", "watch", "blocked"]


class HermesEvolutionCandidate(BaseModel):
    id: str
    title: str
    target: Literal["prompt", "retrieval", "tool", "policy", "memory"]
    reason: str
    gate: str
    status: Literal["candidate", "evaluating", "needs_approval", "adoptable"]


class HermesRuntimeView(BaseModel):
    framework: Literal["Hermes"] = "Hermes"
    mode: Literal["guarded_self_evolution"] = "guarded_self_evolution"
    version: str = "2026.08"
    status: Literal["learning", "watching", "blocked"]
    signals: list[HermesEvolutionSignal]
    candidates: list[HermesEvolutionCandidate]
    safeguards: list[str]
    updated_at: datetime


class AnalysisView(BaseModel):
    id: str
    status: str
    question: str
    data_source_id: str | None = None
    knowledge_base_id: str | None = None
    sql: str | None
    sql_draft: str | None = None
    guard_error: str | None = None
    rewrite_count: int = 0
    idempotency_key: str | None = None
    retry_of_id: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    attempts: int = 1
    max_attempts: int = 3
    error_message: str | None = None
    result: dict | None
    graph_version: str = "enterprise-v2"
    checkpoint_thread_id: str | None = None
    route: str | None = None
    last_event_sequence: int = 0
    token_usage: dict = Field(default_factory=dict)
    estimated_cost_usd: float = 0.0
    created_at: datetime


class AgentStepView(BaseModel):
    id: str
    analysis_run_id: str
    name: str
    status: str
    input_summary: str
    output: dict
    model_version: str
    prompt_version: str
    error_message: str | None
    elapsed_ms: int | None
    created_at: datetime


class KnowledgeBaseCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    description: str = Field(default="", max_length=2000)


class KnowledgeBaseUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    description: str = Field(default="", max_length=2000)


class KnowledgeBaseView(BaseModel):
    id: str
    name: str
    description: str
    created_by: str
    is_archived: bool = False
    archived_at: datetime | None = None
    created_at: datetime


class DocumentView(BaseModel):
    id: str
    knowledge_base_id: str
    filename: str
    content_type: str
    status: str
    file_size_bytes: int = 0
    version: int = 1
    language: str = "unknown"
    category: str = "other"
    embedding_model: str | None = None
    embedding_dimension: int | None = None
    is_archived: bool = False
    error_message: str | None = None
    duplicate: bool = False
    metric_name: str | None = None
    metric_definition: str | None = None
    metric_formula: str | None = None
    metric_unit: str | None = None
    applicable_factories: list[str] = []
    applicable_product_lines: list[str] = []
    effective_from: datetime | None = None
    chunk_count: int
    ingestion_task_id: str | None = None
    created_at: datetime


class DocumentVersionView(BaseModel):
    id: str
    document_id: str
    version: int
    content_sha256: str
    source_path: str | None = None
    file_size_bytes: int
    status: str
    created_by: str
    created_at: datetime


class DocumentMetadataUpdate(BaseModel):
    metric_name: str | None = Field(default=None, max_length=160)
    metric_definition: str | None = Field(default=None, max_length=10000)
    metric_formula: str | None = Field(default=None, max_length=2000)
    metric_unit: str | None = Field(default=None, max_length=40)
    applicable_factories: list[str] = Field(default_factory=list, max_length=100)
    applicable_product_lines: list[str] = Field(default_factory=list, max_length=100)
    effective_from: datetime | None = None


class IngestionTaskView(BaseModel):
    id: str
    document_id: str
    status: str
    attempts: int
    max_attempts: int = 3
    next_retry_at: datetime | None = None
    dead_letter: bool = False
    elapsed_ms: int | None = None
    celery_task_id: str | None
    error_message: str | None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=2000)
    limit: int = Field(default=5, ge=1, le=20)


class ReportCreate(BaseModel):
    analysis_run_id: str
    title: str | None = Field(default=None, max_length=240)


class ReportView(BaseModel):
    id: str
    analysis_run_id: str
    title: str
    markdown: str
    citations: list
    status: str
    created_by: str
    created_at: datetime
    analysis_status: str | None = None
    analysis_sql: str | None = None
    analysis_sql_draft: str | None = None
    analysis_result: dict | None = None
    data_source_id: str | None = None
    knowledge_base_id: str | None = None


class ReportExportView(BaseModel):
    id: str
    report_id: str
    format: str
    status: str
    attempts: int = 0
    max_attempts: int = 3
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None
    checksum_sha256: str | None
    object_key: str | None = None
    storage_backend: str = "local"
    celery_task_id: str | None
    created_at: datetime
    updated_at: datetime
