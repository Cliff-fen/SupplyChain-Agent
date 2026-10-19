from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEVELOPMENT_JWT_SECRET = "development-only-change-me-please-change-me"
# Valid Fernet material, deliberately all-zero so it is unmistakably a local-only
# placeholder and cannot be mistaken for a deployable credential.
DEVELOPMENT_CREDENTIAL_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
DEVELOPMENT_MCP_SERVICE_SECRET = "development-mcp-service-secret-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="SUPPLYMIND_", extra="ignore")

    env: str = "development"
    auto_create_schema: bool = False
    database_url: str = "sqlite+aiosqlite:///./supplymind.db"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = DEVELOPMENT_JWT_SECRET
    credential_key: str = DEVELOPMENT_CREDENTIAL_KEY
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    sql_timeout_seconds: int = 15
    sql_max_rows: int = 500
    refresh_token_days: int = 14
    datasource_allowed_hosts: str = "localhost,127.0.0.1,demo-data,demo-postgres,demo-mysql,retail-postgres"
    datasource_allowed_cidrs: str = "127.0.0.0/8,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"
    chat_base_url: str | None = None
    chat_model: str | None = None
    chat_api_key: str | None = None
    chat_timeout_seconds: float = Field(default=45, gt=0, le=600)
    chat_stream_timeout_seconds: float = Field(default=60, gt=0, le=600)
    planner_timeout_seconds: float = Field(default=30, gt=0, le=600)
    embedding_base_url: str | None = None
    embedding_model: str | None = None
    embedding_api_key: str | None = None
    embedding_dimension: int = 1024
    ai_max_graph_steps: int = 12
    ai_max_tool_calls: int = 8
    ai_answer_model: str | None = None
    ai_router_model: str | None = None
    ai_rerank_model: str | None = None
    rerank_base_url: str | None = None
    rerank_model: str | None = None
    rerank_api_key: str | None = None
    rag_multi_query_count: int = 3
    rag_dense_top_k: int = 30
    rag_bm25_top_k: int = 30
    rag_fusion_top_k: int = 20
    rag_rerank_top_k: int = 8
    rag_rrf_k: int = 60
    memory_enabled_default: bool = True
    memory_confidence_threshold: float = 0.8
    analysis_event_poll_seconds: float = 0.5
    analysis_sse_heartbeat_seconds: int = 15
    mcp_internal_url: str = "http://mcp-server:8001/mcp"
    mcp_service_secret: str = DEVELOPMENT_MCP_SERVICE_SECRET
    mcp_allowed_hosts: str = "mcp-server,localhost,127.0.0.1"
    mcp_stdio_catalog_json: str = "{}"
    a2a_public_base_url: str = "http://localhost:8000"
    llm_gateway_url: str | None = None
    otel_exporter_otlp_endpoint: str | None = None
    eval_router_accuracy_min: float = 0.8
    eval_sql_guard_accuracy_min: float = 1.0
    eval_citation_precision_min: float = 0.8
    eval_citation_recall_min: float = 0.8
    eval_faithfulness_min: float = 0.75
    eval_answer_relevance_min: float = 0.6
    oidc_issuer: str | None = None
    oidc_client_id: str | None = None
    oidc_client_secret: str | None = None
    oidc_redirect_uri: str = "http://localhost:5173/auth/callback"
    oidc_state_ttl_seconds: int = 300
    oidc_auto_provision: bool = False
    report_directory: str = "./data/reports"
    document_directory: str = "./data/documents"
    ingestion_mode: str = "eager"
    s3_endpoint: str | None = None
    s3_bucket: str = "supplymind"
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    task_queued_timeout_seconds: int = 600
    task_running_timeout_seconds: int = 1800

    @property
    def cors_origin_list(self) -> list[str]:
        return [value.strip() for value in self.cors_origins.split(",") if value.strip()]

    @property
    def datasource_host_list(self) -> set[str]:
        return {
            value.strip().lower()
            for value in self.datasource_allowed_hosts.split(",")
            if value.strip()
        }

    @property
    def is_development(self) -> bool:
        return self.env.lower() in {"development", "dev", "test"}

    @property
    def mcp_allowed_host_list(self) -> set[str]:
        return {
            value.strip().lower()
            for value in self.mcp_allowed_hosts.split(",")
            if value.strip()
        }

    def validate_trial_runtime(self) -> None:
        """Reject a trial deployment that accidentally uses development secrets."""
        if self.env.lower() != "trial":
            return
        invalid = []
        if len(self.jwt_secret) < 32 or self.jwt_secret == DEVELOPMENT_JWT_SECRET:
            invalid.append("SUPPLYMIND_JWT_SECRET")
        if self.credential_key == DEVELOPMENT_CREDENTIAL_KEY:
            invalid.append("SUPPLYMIND_CREDENTIAL_KEY")
        if not self.s3_endpoint or not self.s3_access_key or not self.s3_secret_key:
            invalid.append("SUPPLYMIND_S3_ENDPOINT/S3_ACCESS_KEY/S3_SECRET_KEY")
        if self.mcp_service_secret == DEVELOPMENT_MCP_SERVICE_SECRET:
            invalid.append("SUPPLYMIND_MCP_SERVICE_SECRET")
        if invalid:
            raise ValueError("trial runtime configuration is unsafe: " + ", ".join(invalid))


@lru_cache
def get_settings() -> Settings:
    return Settings()
