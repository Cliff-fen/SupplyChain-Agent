import json
import secrets
from datetime import UTC, datetime, timedelta
from hashlib import sha256 as sha256_digest
from pathlib import Path
from time import perf_counter
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import (
    APIRouter,
    Body,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, StreamingResponse
from kombu.exceptions import OperationalError as BrokerOperationalError
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decrypt_secret,
    encrypt_secret,
    hash_oidc_state,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.core.sql_guard import SQLGuardError
from app.db import get_session, set_tenant_context
from app.dependencies import get_principal, require_role
from app.mcp_runtime.client import MCPClientManager, stdio_catalog, validate_mcp_endpoint
from app.memory.service import MemoryPolicyError, MemoryService
from app.models import (
    A2ATask,
    AgentApproval,
    AgentStep,
    AnalysisRun,
    AuditEvent,
    Chunk,
    Conversation,
    ConversationMessage,
    Dashboard,
    DashboardRefreshTask,
    DatasetVersion,
    DataSource,
    DataSourceSyncTask,
    Document,
    DocumentVersion,
    EvaluationRun,
    FineTuneJob,
    IngestionTask,
    KnowledgeBase,
    MCPServer,
    MemberInvitation,
    Membership,
    ModelVersion,
    OIDCLoginState,
    Organization,
    RefreshToken,
    Report,
    ReportExport,
    SchemaSnapshot,
    TrainingDataset,
    TrainingExample,
    User,
    UserMemory,
)
from app.modules.datasources.service import (
    DataSourceError,
    ensure_source_enabled,
    execute_guarded_query,
    get_tenant_source,
    synchronize_schema,
    test_connection,
)
from app.modules.knowledge.service import get_tenant_knowledge_base, search_tenant_knowledge
from app.modules.reports.service import get_tenant_report, render_markdown, render_pdf
from app.schemas import (
    AgentApprovalView,
    AgentStepView,
    AnalysisAccepted,
    AnalysisRequest,
    AnalysisView,
    ApprovalDecision,
    ConversationMessageView,
    DatasetVersionView,
    DataSourceAllowlistUpdate,
    DataSourceCreate,
    DataSourceSyncTaskView,
    DataSourceTlsUpdate,
    DataSourceView,
    DocumentMetadataUpdate,
    DocumentVersionView,
    DocumentView,
    EvaluationRunCreate,
    EvaluationRunView,
    FineTuneJobCreate,
    FineTuneJobView,
    HermesEvolutionCandidate,
    HermesEvolutionSignal,
    HermesRuntimeView,
    IngestionTaskView,
    KnowledgeBaseCreate,
    KnowledgeBaseUpdate,
    KnowledgeBaseView,
    KnowledgeSearchRequest,
    LoginRequest,
    MCPServerCreate,
    MCPServerUpdate,
    MCPServerView,
    MemberInvitationAccept,
    MemberInvitationCreate,
    MemberInvitationView,
    MemberRoleUpdate,
    MemberStatusUpdate,
    MemberView,
    MemorySettingUpdate,
    MemorySettingView,
    ModelVersionCreate,
    ModelVersionView,
    OrganizationAccessView,
    OrganizationSettingsUpdate,
    OrganizationSummary,
    OrganizationSwitchRequest,
    PermissionMatrixView,
    PlatformOrganizationCreate,
    PlatformOrganizationStatusUpdate,
    PlatformOrganizationUpdate,
    PlatformOrganizationView,
    Principal,
    QueryRequest,
    QuotaUpdate,
    RefreshRequest,
    ReportCreate,
    ReportExportView,
    ReportView,
    SchemaSnapshotView,
    TokenResponse,
    TrainingDatasetCreate,
    TrainingDatasetView,
    TrainingExampleCreate,
    TrainingExampleView,
    UserMemoryCreate,
    UserMemoryUpdate,
    UserMemoryView,
)
from app.services.audit import audit
from app.services.events import (
    append_event,
    create_background_task_event,
    create_outbox_event,
    stream_events,
)
from app.services.ingestion import process_ingestion
from app.services.knowledge import KnowledgeError, extract_text, sha256
from app.services.llm import ModelConfigurationError, ModelResponseError
from app.services.storage import check_ready as check_storage_ready
from app.services.storage import configured as storage_configured
from app.services.storage import export_asset_available, get_file, put_file

router = APIRouter(prefix="/api/v1")
a2a_router = APIRouter()


@router.get("/conversations")
async def list_conversations(
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> list[dict]:
    rows = list(
        await session.scalars(
            select(Conversation)
            .where(
                Conversation.tenant_id == principal.tenant_id,
                Conversation.created_by == principal.user_id,
            )
            .order_by(Conversation.created_at.desc())
            .limit(100)
        )
    )
    return [{"id": item.id, "title": item.title, "created_at": item.created_at} for item in rows]


@router.post("/conversations", status_code=status.HTTP_201_CREATED)
async def create_conversation(
    title: str = Query(default="新分析会话", min_length=1, max_length=240),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_role("analyst", "org_admin", "platform_admin")),
) -> dict:
    conversation = Conversation(
        tenant_id=principal.tenant_id,
        title=title,
        created_by=principal.user_id,
    )
    session.add(conversation)
    await session.commit()
    await session.refresh(conversation)
    return {
        "id": conversation.id,
        "title": conversation.title,
        "created_at": conversation.created_at,
    }


@router.get("/me/memory/settings", response_model=MemorySettingView)
async def get_memory_settings(
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> MemorySettingView:
    enabled = await MemoryService().enabled(session, principal.tenant_id, principal.user_id)
    return MemorySettingView(enabled=enabled)


@router.patch("/me/memory/settings", response_model=MemorySettingView)
async def update_memory_settings(
    payload: MemorySettingUpdate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> MemorySettingView:
    setting = await MemoryService().set_enabled(
        session, principal.tenant_id, principal.user_id, payload.enabled
    )
    await session.commit()
    return MemorySettingView(enabled=setting.enabled)


@router.get("/me/memories", response_model=list[UserMemoryView])
async def list_user_memories(
    category: str | None = Query(default=None, max_length=40),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> list[UserMemoryView]:
    rows = await MemoryService().list(session, principal.tenant_id, principal.user_id, category)
    return [UserMemoryView.model_validate(item, from_attributes=True) for item in rows]


@router.post("/me/memories", response_model=UserMemoryView, status_code=status.HTTP_201_CREATED)
async def create_user_memory(
    payload: UserMemoryCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> UserMemoryView:
    try:
        item = await MemoryService().upsert(
            session,
            principal.tenant_id,
            principal.user_id,
            **payload.model_dump(),
        )
    except MemoryPolicyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await session.commit()
    await session.refresh(item)
    return UserMemoryView.model_validate(item, from_attributes=True)


@router.patch("/me/memories/{memory_id}", response_model=UserMemoryView)
async def update_user_memory(
    memory_id: str,
    payload: UserMemoryUpdate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> UserMemoryView:
    existing = await session.scalar(
        select(UserMemory).where(
            UserMemory.id == memory_id,
            UserMemory.tenant_id == principal.tenant_id,
            UserMemory.user_id == principal.user_id,
        )
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Memory not found")
    try:
        item = await MemoryService().upsert(
            session,
            principal.tenant_id,
            principal.user_id,
            category=existing.category,
            memory_key=existing.memory_key,
            **payload.model_dump(),
            source_run_id=existing.source_run_id,
        )
    except MemoryPolicyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await session.commit()
    await session.refresh(item)
    return UserMemoryView.model_validate(item, from_attributes=True)


@router.delete("/me/memories/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_memory(
    memory_id: str,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> Response:
    removed = await MemoryService().delete(
        session, principal.tenant_id, principal.user_id, memory_id
    )
    if not removed:
        raise HTTPException(status_code=404, detail="Memory not found")
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/me/memories", status_code=status.HTTP_204_NO_CONTENT)
async def clear_user_memories(
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> Response:
    await MemoryService().delete(session, principal.tenant_id, principal.user_id)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _validate_mcp_connection(
    transport: str, endpoint: str | None, stdio_catalog_key: str | None
) -> None:
    if transport == "streamable_http":
        if not endpoint:
            raise HTTPException(status_code=422, detail="HTTP MCP server requires an endpoint")
        try:
            validate_mcp_endpoint(endpoint)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    elif stdio_catalog_key not in stdio_catalog():
        raise HTTPException(status_code=422, detail="Unknown MCP stdio catalog entry")


@router.get("/mcp/servers", response_model=list[MCPServerView])
async def list_mcp_servers(
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_role("org_admin", "platform_admin")),
) -> list[MCPServerView]:
    rows = list(
        await session.scalars(
            select(MCPServer)
            .where(MCPServer.tenant_id == principal.tenant_id)
            .order_by(MCPServer.created_at.desc())
        )
    )
    return [MCPServerView.model_validate(item, from_attributes=True) for item in rows]


@router.post("/mcp/servers", response_model=MCPServerView, status_code=status.HTTP_201_CREATED)
async def create_mcp_server(
    payload: MCPServerCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_role("org_admin", "platform_admin")),
) -> MCPServerView:
    _validate_mcp_connection(payload.transport, payload.endpoint, payload.stdio_catalog_key)
    item = MCPServer(
        tenant_id=principal.tenant_id,
        name=payload.name,
        transport=payload.transport,
        endpoint=payload.endpoint,
        stdio_catalog_key=payload.stdio_catalog_key,
        encrypted_auth_token=encrypt_secret(payload.auth_token) if payload.auth_token else None,
        created_by=principal.user_id,
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return MCPServerView.model_validate(item, from_attributes=True)


@router.patch("/mcp/servers/{server_id}", response_model=MCPServerView)
async def update_mcp_server(
    server_id: str,
    payload: MCPServerUpdate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_role("org_admin", "platform_admin")),
) -> MCPServerView:
    item = await session.scalar(
        select(MCPServer).where(
            MCPServer.id == server_id,
            MCPServer.tenant_id == principal.tenant_id,
        )
    )
    if not item:
        raise HTTPException(status_code=404, detail="MCP server not found")
    values = payload.model_dump(exclude_unset=True)
    token = values.pop("auth_token", None)
    for key, value in values.items():
        setattr(item, key, value)
    if token is not None:
        item.encrypted_auth_token = encrypt_secret(token) if token else None
    _validate_mcp_connection(item.transport, item.endpoint, item.stdio_catalog_key)
    await session.commit()
    await session.refresh(item)
    return MCPServerView.model_validate(item, from_attributes=True)


@router.post("/mcp/servers/{server_id}/test", response_model=MCPServerView)
async def test_mcp_server(
    server_id: str,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_role("org_admin", "platform_admin")),
) -> MCPServerView:
    item = await session.scalar(
        select(MCPServer).where(
            MCPServer.id == server_id,
            MCPServer.tenant_id == principal.tenant_id,
        )
    )
    if not item:
        raise HTTPException(status_code=404, detail="MCP server not found")
    try:
        tools = await MCPClientManager().discover(
            transport=item.transport,
            endpoint=item.endpoint,
            stdio_catalog_key=item.stdio_catalog_key,
            auth_token=(
                decrypt_secret(item.encrypted_auth_token) if item.encrypted_auth_token else None
            ),
        )
        item.discovered_tools = tools
        item.status = "healthy"
        item.error_message = None
    except (OSError, RuntimeError, ValueError) as exc:
        item.status = "failed"
        item.error_message = str(exc)[:500]
    item.last_checked_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(item)
    return MCPServerView.model_validate(item, from_attributes=True)


@router.delete("/mcp/servers/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mcp_server(
    server_id: str,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_role("org_admin", "platform_admin")),
) -> Response:
    item = await session.scalar(
        select(MCPServer).where(
            MCPServer.id == server_id,
            MCPServer.tenant_id == principal.tenant_id,
        )
    )
    if not item:
        raise HTTPException(status_code=404, detail="MCP server not found")
    await session.delete(item)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/agent-approvals", response_model=list[AgentApprovalView])
async def list_agent_approvals(
    approval_status: str = Query(default="pending", alias="status", max_length=24),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_role("analyst", "org_admin", "platform_admin")),
) -> list[AgentApprovalView]:
    query = select(AgentApproval).where(
        AgentApproval.tenant_id == principal.tenant_id,
        AgentApproval.status == approval_status,
    )
    if principal.role == "analyst":
        query = query.where(AgentApproval.requested_by == principal.user_id)
    rows = list(await session.scalars(query.order_by(AgentApproval.created_at.desc())))
    return [AgentApprovalView.model_validate(item, from_attributes=True) for item in rows]


async def _decide_approval(
    approval_id: str,
    approved: bool,
    payload: ApprovalDecision,
    session: AsyncSession,
    principal: Principal,
) -> AgentApproval:
    approval = await session.scalar(
        select(AgentApproval).where(
            AgentApproval.id == approval_id,
            AgentApproval.tenant_id == principal.tenant_id,
        ).with_for_update()
    )
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found")
    if principal.role == "analyst" and approval.requested_by != principal.user_id:
        raise HTTPException(status_code=404, detail="Approval not found")
    if approval.status != "pending":
        raise HTTPException(status_code=409, detail="Approval has already been decided")
    if approval.expires_at and approval.expires_at <= datetime.now(UTC):
        approval.status = "expired"
        await session.commit()
        raise HTTPException(status_code=409, detail="Approval has expired")
    approval.status = "approved" if approved else "rejected"
    approval.decided_by = principal.user_id
    approval.decision_reason = payload.reason
    approval.decided_at = datetime.now(UTC)
    deferred_export = None
    if approved and approval.tool_name == "report.export":
        report_id = approval.request_payload.get("report_id")
        report = await session.scalar(
            select(Report).where(
                Report.id == report_id,
                Report.tenant_id == principal.tenant_id,
            )
        )
        if not report:
            raise HTTPException(status_code=422, detail="Approved report no longer exists")
        export = ReportExport(
            tenant_id=principal.tenant_id,
            report_id=report.id,
            format="pdf",
            status="queued",
            created_by=principal.user_id,
        )
        session.add(export)
        await session.flush()
        if get_settings().ingestion_mode == "broker":
            # Commit the approved action and its outbox entry together. Sending
            # to Celery before commit lets a fast Worker miss the export row.
            session.add(
                create_background_task_event(
                    tenant_id=principal.tenant_id,
                    aggregate_type="report_export",
                    aggregate_id=export.id,
                    event_type="report.pdf_export_requested",
                    payload={"export_id": export.id},
                )
            )
        else:
            deferred_export = export
    run = await session.scalar(
        select(AnalysisRun).where(
            AnalysisRun.id == approval.analysis_run_id,
            AnalysisRun.tenant_id == principal.tenant_id,
        )
    )
    if approval.tool_name == "analysis.continue" and run and run.status == "waiting_approval":
        # Approval and resume request are one transaction, including rejection:
        # the graph consumes that decision and ends without executing the action.
        run.status = "queued"
        session.add(create_background_task_event(
            tenant_id=principal.tenant_id, aggregate_type="analysis_run", aggregate_id=run.id,
            event_type="analysis.requested", payload={"run_id": run.id, "approval_id": approval.id},
        ))
    await session.commit()
    if deferred_export is not None:
        from scripts.worker import celery_app

        task = celery_app.send_task(
            "supplymind.reports.export_pdf", args=[deferred_export.id], queue="analysis"
        )
        deferred_export.celery_task_id = task.id
        await session.commit()
    if run:
        await append_event(
            session,
            run,
            "approval_decided",
            {
                "approval_id": approval.id,
                "approved": approved,
                "tool": approval.tool_name,
            },
        )
    return approval


@router.post("/agent-approvals/{approval_id}/approve", response_model=AgentApprovalView)
async def approve_agent_action(
    approval_id: str,
    payload: ApprovalDecision,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_role("analyst", "org_admin", "platform_admin")),
) -> AgentApprovalView:
    approval = await _decide_approval(approval_id, True, payload, session, principal)
    return AgentApprovalView.model_validate(approval, from_attributes=True)


@router.post("/agent-approvals/{approval_id}/reject", response_model=AgentApprovalView)
async def reject_agent_action(
    approval_id: str,
    payload: ApprovalDecision,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_role("analyst", "org_admin", "platform_admin")),
) -> AgentApprovalView:
    approval = await _decide_approval(approval_id, False, payload, session, principal)
    return AgentApprovalView.model_validate(approval, from_attributes=True)


@router.get(
    "/conversations/{conversation_id}/messages", response_model=list[ConversationMessageView]
)
async def list_conversation_messages(
    conversation_id: str,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> list[ConversationMessageView]:
    conversation = await session.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.tenant_id == principal.tenant_id,
            Conversation.created_by == principal.user_id,
        )
    )
    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    messages = list(
        await session.scalars(
            select(ConversationMessage)
            .where(
                ConversationMessage.conversation_id == conversation_id,
                ConversationMessage.tenant_id == principal.tenant_id,
            )
            .order_by(ConversationMessage.created_at.asc())
        )
    )
    return [
        ConversationMessageView(
            id=item.id,
            conversation_id=item.conversation_id,
            role=item.role,
            content=item.content,
            metadata=item.metadata_json or {},
            created_at=item.created_at,
        )
        for item in messages
    ]


@router.post(
    "/ai/training/datasets", response_model=TrainingDatasetView, status_code=status.HTTP_201_CREATED
)
async def create_training_dataset(
    payload: TrainingDatasetCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_role("platform_admin", "org_admin")),
) -> TrainingDatasetView:
    dataset = TrainingDataset(
        tenant_id=principal.tenant_id,
        name=payload.name,
        description=payload.description,
        source=payload.source,
        consent_scope=payload.consent_scope,
        created_by=principal.user_id,
    )
    session.add(dataset)
    await session.commit()
    await session.refresh(dataset)
    await audit(
        session,
        principal.tenant_id,
        principal.user_id,
        "ai.training_dataset.created",
        "training_dataset",
        dataset.id,
        {"name": dataset.name},
    )
    return TrainingDatasetView.model_validate(dataset, from_attributes=True)


@router.get("/ai/training/datasets", response_model=list[TrainingDatasetView])
async def list_training_datasets(
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_role("platform_admin", "org_admin")),
) -> list[TrainingDatasetView]:
    datasets = list(
        await session.scalars(
            select(TrainingDataset)
            .where(
                TrainingDataset.tenant_id == principal.tenant_id,
            )
            .order_by(TrainingDataset.created_at.desc())
            .limit(100)
        )
    )
    return [TrainingDatasetView.model_validate(item, from_attributes=True) for item in datasets]


@router.post(
    "/ai/training/datasets/{dataset_id}/examples",
    response_model=TrainingExampleView,
    status_code=status.HTTP_201_CREATED,
)
async def create_training_example(
    dataset_id: str,
    payload: TrainingExampleCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_role("platform_admin", "org_admin")),
) -> TrainingExampleView:
    dataset = await session.scalar(
        select(TrainingDataset).where(
            TrainingDataset.id == dataset_id,
            TrainingDataset.tenant_id == principal.tenant_id,
        )
    )
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Training dataset not found"
        )
    if dataset.redaction_status != "approved":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Training dataset requires redaction approval",
        )
    example = TrainingExample(
        tenant_id=principal.tenant_id,
        dataset_id=dataset_id,
        kind=payload.kind,
        input_payload=payload.input_payload,
        target_payload=payload.target_payload,
        created_by=principal.user_id,
    )
    session.add(example)
    await session.commit()
    await session.refresh(example)
    return TrainingExampleView.model_validate(example, from_attributes=True)


@router.post("/ai/training/examples/{example_id}/approve", response_model=TrainingExampleView)
async def approve_training_example(
    example_id: str,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_role("platform_admin", "org_admin")),
) -> TrainingExampleView:
    example = await session.scalar(
        select(TrainingExample).where(
            TrainingExample.id == example_id,
            TrainingExample.tenant_id == principal.tenant_id,
        )
    )
    if not example:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Training example not found"
        )
    example.status = "approved"
    await session.commit()
    await session.refresh(example)
    return TrainingExampleView.model_validate(example, from_attributes=True)


@router.post(
    "/ai/training/datasets/{dataset_id}/approve-redaction", response_model=TrainingDatasetView
)
async def approve_training_redaction(
    dataset_id: str,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_role("platform_admin", "org_admin")),
) -> TrainingDatasetView:
    dataset = await session.scalar(
        select(TrainingDataset).where(
            TrainingDataset.id == dataset_id,
            TrainingDataset.tenant_id == principal.tenant_id,
        )
    )
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Training dataset not found"
        )
    dataset.redaction_status = "approved"
    await session.commit()
    await session.refresh(dataset)
    return TrainingDatasetView.model_validate(dataset, from_attributes=True)


@router.post(
    "/ai/training/datasets/{dataset_id}/publish",
    response_model=DatasetVersionView,
    status_code=status.HTTP_201_CREATED,
)
async def publish_training_dataset(
    dataset_id: str,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_role("platform_admin", "org_admin")),
) -> DatasetVersionView:
    dataset = await session.scalar(
        select(TrainingDataset).where(
            TrainingDataset.id == dataset_id,
            TrainingDataset.tenant_id == principal.tenant_id,
        )
    )
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Training dataset not found"
        )
    if dataset.redaction_status != "approved":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Redaction approval is required before publishing",
        )
    examples = list(
        await session.scalars(
            select(TrainingExample)
            .where(
                TrainingExample.dataset_id == dataset_id,
                TrainingExample.tenant_id == principal.tenant_id,
                TrainingExample.status == "approved",
            )
            .order_by(TrainingExample.created_at.asc())
        )
    )
    if not examples:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one approved training example is required",
        )
    raw = json.dumps(
        [
            {"kind": item.kind, "input": item.input_payload, "target": item.target_payload}
            for item in examples
        ],
        sort_keys=True,
        ensure_ascii=False,
    ).encode()
    current_version = (
        int(
            await session.scalar(
                select(func.max(DatasetVersion.version)).where(
                    DatasetVersion.dataset_id == dataset_id
                )
            )
            or 0
        )
        + 1
    )
    version = DatasetVersion(
        tenant_id=principal.tenant_id,
        dataset_id=dataset_id,
        version=current_version,
        checksum_sha256=sha256_digest(raw).hexdigest(),
        example_count=len(examples),
        status="approved",
        created_by=principal.user_id,
    )
    dataset.status = "ready"
    dataset.version = current_version
    session.add(version)
    await session.commit()
    await session.refresh(version)
    return DatasetVersionView.model_validate(version, from_attributes=True)


@router.post("/ai/models", response_model=ModelVersionView, status_code=status.HTTP_201_CREATED)
async def create_model_version(
    payload: ModelVersionCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_role("platform_admin", "org_admin")),
) -> ModelVersionView:
    model = ModelVersion(
        tenant_id=principal.tenant_id,
        name=payload.name,
        provider=payload.provider,
        model_name=payload.model_name,
        version=payload.version,
        model_type=payload.model_type,
        dataset_version_id=payload.dataset_version_id,
        prompt_version=payload.prompt_version,
        created_by=principal.user_id,
    )
    session.add(model)
    await session.commit()
    await session.refresh(model)
    return ModelVersionView.model_validate(model, from_attributes=True)


@router.get("/ai/models", response_model=list[ModelVersionView])
async def list_model_versions(
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_role("platform_admin", "org_admin")),
) -> list[ModelVersionView]:
    models = list(
        await session.scalars(
            select(ModelVersion)
            .where(
                ModelVersion.tenant_id == principal.tenant_id,
            )
            .order_by(ModelVersion.created_at.desc())
            .limit(100)
        )
    )
    return [ModelVersionView.model_validate(item, from_attributes=True) for item in models]


@router.post(
    "/ai/evaluations", response_model=EvaluationRunView, status_code=status.HTTP_202_ACCEPTED
)
async def create_evaluation_run(
    payload: EvaluationRunCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_role("platform_admin", "org_admin")),
) -> EvaluationRunView:
    version = await session.scalar(
        select(DatasetVersion).where(
            DatasetVersion.id == payload.dataset_version_id,
            DatasetVersion.tenant_id == principal.tenant_id,
            DatasetVersion.status == "approved",
        )
    )
    model = None
    if payload.model_version_id:
        model = await session.scalar(
            select(ModelVersion).where(
                ModelVersion.id == payload.model_version_id,
                ModelVersion.tenant_id == principal.tenant_id,
            )
        )
    if not version or (payload.model_version_id and not model):
        raise HTTPException(status_code=404, detail="Dataset version or model version not found")
    evaluation = EvaluationRun(
        tenant_id=principal.tenant_id,
        dataset_version_id=version.id,
        model_version_id=model.id if model else None,
        created_by=principal.user_id,
    )
    session.add(evaluation)
    await session.commit()
    await session.refresh(evaluation)
    from scripts.worker import celery_app

    celery_app.send_task("supplymind.evaluations.run", args=[evaluation.id], queue="analysis")
    return EvaluationRunView.model_validate(evaluation, from_attributes=True)


@router.get("/ai/evaluations", response_model=list[EvaluationRunView])
async def list_evaluation_runs(
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_role("platform_admin", "org_admin")),
) -> list[EvaluationRunView]:
    rows = list(
        await session.scalars(
            select(EvaluationRun)
            .where(EvaluationRun.tenant_id == principal.tenant_id)
            .order_by(EvaluationRun.created_at.desc())
            .limit(100)
        )
    )
    return [EvaluationRunView.model_validate(item, from_attributes=True) for item in rows]


@router.get("/hermes/runtime", response_model=HermesRuntimeView)
async def get_hermes_runtime(
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> HermesRuntimeView:
    total_runs = int(
        await session.scalar(
            select(func.count(AnalysisRun.id)).where(
                AnalysisRun.tenant_id == principal.tenant_id,
            )
        )
        or 0
    )
    failed_runs = int(
        await session.scalar(
            select(func.count(AnalysisRun.id)).where(
                AnalysisRun.tenant_id == principal.tenant_id,
                AnalysisRun.status == "failed",
            )
        )
        or 0
    )
    pending_approvals = int(
        await session.scalar(
            select(func.count(AgentApproval.id)).where(
                AgentApproval.tenant_id == principal.tenant_id,
                AgentApproval.status == "pending",
            )
        )
        or 0
    )
    memories = int(
        await session.scalar(
            select(func.count(UserMemory.id)).where(
                UserMemory.tenant_id == principal.tenant_id,
                UserMemory.user_id == principal.user_id,
            )
        )
        or 0
    )
    evaluations = int(
        await session.scalar(
            select(func.count(EvaluationRun.id)).where(
                EvaluationRun.tenant_id == principal.tenant_id,
            )
        )
        or 0
    )
    failed_rate = round(failed_runs / total_runs * 100, 1) if total_runs else 0.0
    signals = [
        HermesEvolutionSignal(
            id="analysis_failure_rate",
            label="分析失败率",
            value=failed_rate,
            unit="%",
            status="blocked" if failed_rate >= 25 else "watch" if failed_rate else "healthy",
        ),
        HermesEvolutionSignal(
            id="memory_signals",
            label="个人化记忆",
            value=float(memories),
            unit="条",
            status="healthy" if memories else "watch",
        ),
        HermesEvolutionSignal(
            id="evaluation_runs",
            label="评测门禁",
            value=float(evaluations),
            unit="次",
            status="healthy" if evaluations else "watch",
        ),
        HermesEvolutionSignal(
            id="approval_queue",
            label="待审批改动",
            value=float(pending_approvals),
            unit="项",
            status="watch" if pending_approvals else "healthy",
        ),
    ]
    candidates = [
        HermesEvolutionCandidate(
            id="retrieval-evidence-tightening",
            title="收紧 RAG 证据引用阈值",
            target="retrieval",
            reason="根据历史回答的引用完整性，优先优化检索召回与引用覆盖。",
            gate="离线评测通过，引用完整性不得下降。",
            status="candidate" if evaluations == 0 else "adoptable",
        ),
        HermesEvolutionCandidate(
            id="memory-personalization-bootstrap",
            title="启动用户级偏好学习",
            target="memory",
            reason="把用户常问 KPI、工厂范围和时间窗口作为可撤销长期记忆。",
            gate="敏感信息过滤通过，且用户记忆开关保持开启。",
            status="candidate" if memories == 0 else "adoptable",
        ),
    ]
    if failed_runs:
        candidates.insert(
            0,
            HermesEvolutionCandidate(
                id="sql-guard-repair-loop",
                title="失败分析的 SQL Guard 修复循环",
                target="prompt",
                reason="历史运行存在失败，需要把 Guard 拒绝原因回灌到提示词候选。",
                gate="只能生成候选提示词，必须经过评测和人工审批后采用。",
                status="needs_approval" if pending_approvals else "candidate",
            ),
        )
    return HermesRuntimeView(
        status="blocked"
        if any(signal.status == "blocked" for signal in signals)
        else "learning"
        if any(signal.status == "watch" for signal in signals)
        else "watching",
        signals=signals,
        candidates=candidates,
        safeguards=[
            "候选改进默认不自动上线",
            "训练数据先脱敏再进入评测集",
            "SQL 与工具调用继续走 RBAC、审批和审计",
            "评测门禁失败时保持当前生产配置",
        ],
        updated_at=datetime.now(UTC),
    )


@router.post(
    "/ai/fine-tune-jobs", response_model=FineTuneJobView, status_code=status.HTTP_202_ACCEPTED
)
async def create_fine_tune_job(
    payload: FineTuneJobCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_role("platform_admin", "org_admin")),
) -> FineTuneJobView:
    dataset_version = await session.scalar(
        select(DatasetVersion).where(
            DatasetVersion.id == payload.dataset_version_id,
            DatasetVersion.tenant_id == principal.tenant_id,
        )
    )
    base_model = await session.scalar(
        select(ModelVersion).where(
            ModelVersion.id == payload.base_model_version_id,
            ModelVersion.tenant_id == principal.tenant_id,
        )
    )
    if not dataset_version or not base_model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Training dataset version or model version not found",
        )
    if dataset_version.status != "approved":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Training dataset version is not approved",
        )
    job = FineTuneJob(
        tenant_id=principal.tenant_id,
        dataset_version_id=dataset_version.id,
        base_model_version_id=base_model.id,
        method=payload.method,
        hyperparameters=payload.hyperparameters,
        status="blocked_no_provider",
        failure_reason="No fine-tuning provider is configured; review and configure a provider before execution.",
        created_by=principal.user_id,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    await audit(
        session,
        principal.tenant_id,
        principal.user_id,
        "ai.fine_tune.blocked",
        "fine_tune_job",
        job.id,
        {"reason": job.failure_reason},
    )
    return FineTuneJobView.model_validate(job, from_attributes=True)


@router.post("/auth/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest, session: AsyncSession = Depends(get_session)
) -> TokenResponse:
    organization = await session.scalar(
        select(Organization).where(Organization.slug == payload.organization_slug)
    )
    user = await session.scalar(select(User).where(User.email == payload.email.lower()))
    if (
        not organization
        or not organization.is_active
        or not user
        or not verify_password(payload.password, user.password_hash)
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    membership = await session.scalar(
        select(Membership).where(
            Membership.organization_id == organization.id,
            Membership.user_id == user.id,
            Membership.is_active.is_(True),
        )
    )
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Organization membership required"
        )
    await set_tenant_context(session, organization.id)
    await audit(session, organization.id, user.id, "auth.login", "user", user.id)
    raw_refresh = create_refresh_token()
    session.add(
        RefreshToken(
            token_hash=hash_refresh_token(raw_refresh),
            user_id=user.id,
            organization_id=organization.id,
            expires_at=datetime.now(UTC) + timedelta(days=get_settings().refresh_token_days),
        )
    )
    await session.commit()
    return TokenResponse(
        access_token=create_access_token(user.id, organization.id, membership.role),
        refresh_token=raw_refresh,
    )


@router.post("/auth/refresh", response_model=TokenResponse)
async def refresh(
    payload: RefreshRequest, session: AsyncSession = Depends(get_session)
) -> TokenResponse:
    stored = await session.scalar(
        select(RefreshToken).where(
            RefreshToken.token_hash == hash_refresh_token(payload.refresh_token)
        )
    )
    now = datetime.now(UTC)
    expires_at = (
        stored.expires_at.replace(tzinfo=UTC)
        if stored and stored.expires_at.tzinfo is None
        else (stored.expires_at if stored else now)
    )
    if not stored or stored.revoked_at or expires_at <= now:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        )
    membership = await session.scalar(
        select(Membership).where(
            Membership.organization_id == stored.organization_id,
            Membership.user_id == stored.user_id,
            Membership.is_active.is_(True),
        )
    )
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Organization access denied"
        )
    replacement = create_refresh_token()
    replacement_row = RefreshToken(
        token_hash=hash_refresh_token(replacement),
        user_id=stored.user_id,
        organization_id=stored.organization_id,
        expires_at=now + timedelta(days=get_settings().refresh_token_days),
    )
    session.add(replacement_row)
    stored.revoked_at = now
    stored.replaced_by = replacement_row.id
    await set_tenant_context(session, stored.organization_id)
    await audit(
        session, stored.organization_id, stored.user_id, "auth.refresh", "refresh_token", stored.id
    )
    await session.commit()
    return TokenResponse(
        access_token=create_access_token(stored.user_id, stored.organization_id, membership.role),
        refresh_token=replacement,
    )


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(payload: RefreshRequest, session: AsyncSession = Depends(get_session)) -> Response:
    stored = await session.scalar(
        select(RefreshToken).where(
            RefreshToken.token_hash == hash_refresh_token(payload.refresh_token)
        )
    )
    if stored and not stored.revoked_at:
        stored.revoked_at = datetime.now(UTC)
        await set_tenant_context(session, stored.organization_id)
        await audit(
            session,
            stored.organization_id,
            stored.user_id,
            "auth.logout",
            "refresh_token",
            stored.id,
        )
        await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/auth/organizations", response_model=list[OrganizationAccessView])
async def auth_organizations(
    principal: Principal = Depends(get_principal), session: AsyncSession = Depends(get_session)
) -> list[OrganizationAccessView]:
    rows = await session.execute(
        select(Organization, Membership.role)
        .join(Membership, Membership.organization_id == Organization.id)
        .where(
            Membership.user_id == principal.user_id,
            Membership.is_active.is_(True),
            Organization.is_active.is_(True),
        )
        .order_by(Organization.name)
    )
    return [
        OrganizationAccessView(
            id=organization.id, slug=organization.slug, name=organization.name, role=role
        )
        for organization, role in rows
    ]


@router.post("/auth/switch-organization", response_model=TokenResponse)
async def switch_organization(
    payload: OrganizationSwitchRequest,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    membership = await session.scalar(
        select(Membership).where(
            Membership.organization_id == payload.organization_id,
            Membership.user_id == principal.user_id,
            Membership.is_active.is_(True),
        )
    )
    organization = await session.scalar(
        select(Organization).where(Organization.id == payload.organization_id)
    )
    if not membership or not organization or not organization.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Organization access denied"
        )
    raw_refresh = create_refresh_token()
    session.add(
        RefreshToken(
            token_hash=hash_refresh_token(raw_refresh),
            user_id=principal.user_id,
            organization_id=organization.id,
            expires_at=datetime.now(UTC) + timedelta(days=get_settings().refresh_token_days),
        )
    )
    await set_tenant_context(session, organization.id)
    await audit(
        session,
        organization.id,
        principal.user_id,
        "auth.organization_switched",
        "organization",
        organization.id,
        {"from_organization_id": principal.tenant_id},
    )
    await session.commit()
    return TokenResponse(
        access_token=create_access_token(principal.user_id, organization.id, membership.role),
        refresh_token=raw_refresh,
    )


async def oidc_discovery() -> dict:
    issuer = get_settings().oidc_issuer
    if not issuer or not get_settings().oidc_client_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="OIDC is not configured"
        )
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(f"{issuer.rstrip('/')}/.well-known/openid-configuration")
            response.raise_for_status()
            return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="OIDC discovery failed"
        ) from exc


@router.get("/auth/oidc/start")
async def oidc_start(
    organization_slug: str, session: AsyncSession = Depends(get_session)
) -> Response:
    organization = await session.scalar(
        select(Organization).where(Organization.slug == organization_slug)
    )
    if not organization:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    metadata = await oidc_discovery()
    state, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
    session.add(
        OIDCLoginState(
            state_hash=hash_oidc_state(state),
            nonce=nonce,
            organization_id=organization.id,
            expires_at=datetime.now(UTC) + timedelta(seconds=get_settings().oidc_state_ttl_seconds),
        )
    )
    await session.commit()
    params = {
        "client_id": get_settings().oidc_client_id,
        "response_type": "code",
        "scope": "openid email profile",
        "redirect_uri": get_settings().oidc_redirect_uri,
        "state": state,
        "nonce": nonce,
    }
    return Response(
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
        headers={"location": f"{metadata['authorization_endpoint']}?{urlencode(params)}"},
    )


@router.get("/auth/oidc/callback", response_model=TokenResponse)
async def oidc_callback(
    code: str, state: str, session: AsyncSession = Depends(get_session)
) -> TokenResponse:
    login_state = await session.scalar(
        select(OIDCLoginState).where(OIDCLoginState.state_hash == hash_oidc_state(state))
    )
    now = datetime.now(UTC)
    expires_at = (
        login_state.expires_at.replace(tzinfo=UTC)
        if login_state and login_state.expires_at.tzinfo is None
        else (login_state.expires_at if login_state else now)
    )
    if not login_state or login_state.consumed_at or expires_at <= now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired OIDC state"
        )
    metadata = await oidc_discovery()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            token_response = await client.post(
                metadata["token_endpoint"],
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": get_settings().oidc_redirect_uri,
                    "client_id": get_settings().oidc_client_id,
                    "client_secret": get_settings().oidc_client_secret,
                },
            )
            token_response.raise_for_status()
            token_data = token_response.json()
            id_token = token_data["id_token"]
            header = jwt.get_unverified_header(id_token)
            jwks_response = await client.get(metadata["jwks_uri"])
            jwks_response.raise_for_status()
            jwk = next(
                (
                    key
                    for key in jwks_response.json().get("keys", [])
                    if key.get("kid") == header.get("kid")
                ),
                None,
            )
            if not jwk:
                raise ValueError("OIDC signing key not found")
            signing_key = jwt.algorithms.RSAAlgorithm.from_jwk(jwk)
            claims = jwt.decode(
                id_token,
                signing_key,
                algorithms=[header.get("alg", "RS256")],
                audience=get_settings().oidc_client_id,
                issuer=get_settings().oidc_issuer,
            )
            if (
                claims.get("iss") != get_settings().oidc_issuer
                or claims.get("nonce") != login_state.nonce
            ):
                raise ValueError("OIDC claims validation failed")
            profile = claims
            if not profile.get("email") and metadata.get("userinfo_endpoint"):
                userinfo = await client.get(
                    metadata["userinfo_endpoint"],
                    headers={"Authorization": f"Bearer {token_data['access_token']}"},
                )
                userinfo.raise_for_status()
                profile = userinfo.json()
    except (httpx.HTTPError, KeyError, ValueError, jwt.PyJWTError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="OIDC callback failed"
        ) from exc
    email = str(profile.get("email", "")).lower().strip()
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="OIDC email claim is required"
        )
    user = await session.scalar(select(User).where(User.email == email))
    if not user:
        user = User(
            email=email,
            display_name=str(profile.get("name") or email.split("@", 1)[0]),
            password_hash=hash_password(secrets.token_urlsafe(32)),
        )
        session.add(user)
        await session.flush()
    membership = await session.scalar(
        select(Membership).where(
            Membership.organization_id == login_state.organization_id, Membership.user_id == user.id
        )
    )
    if not membership:
        membership = Membership(
            organization_id=login_state.organization_id,
            user_id=user.id,
            role="viewer",
            is_active=get_settings().oidc_auto_provision,
        )
        session.add(membership)
    if not membership.is_active:
        login_state.consumed_at = now
        await audit(
            session,
            login_state.organization_id,
            user.id,
            "auth.oidc_pending_approval",
            "membership",
            membership.id,
            {"email": email},
        )
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="OIDC identity is pending organization approval",
        )
    raw_refresh = create_refresh_token()
    session.add(
        RefreshToken(
            token_hash=hash_refresh_token(raw_refresh),
            user_id=user.id,
            organization_id=login_state.organization_id,
            expires_at=now + timedelta(days=get_settings().refresh_token_days),
        )
    )
    login_state.consumed_at = now
    await set_tenant_context(session, login_state.organization_id)
    await audit(session, login_state.organization_id, user.id, "auth.oidc_login", "user", user.id)
    await session.commit()
    return TokenResponse(
        access_token=create_access_token(user.id, login_state.organization_id, membership.role),
        refresh_token=raw_refresh,
    )


@router.get("/me")
async def me(principal: Principal = Depends(get_principal)) -> Principal:
    return principal


@router.get("/organization", response_model=OrganizationSummary)
async def organization_summary(
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> OrganizationSummary:
    organization = await session.scalar(
        select(Organization).where(Organization.id == principal.tenant_id)
    )
    if not organization:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    counts = {}
    for key, model in (
        ("member_count", Membership),
        ("data_source_count", DataSource),
        ("knowledge_base_count", KnowledgeBase),
        ("report_count", Report),
    ):
        column = Membership.organization_id if model is Membership else model.tenant_id
        counts[key] = int(
            await session.scalar(
                select(func.count()).select_from(model).where(column == principal.tenant_id)
            )
            or 0
        )
    counts["active_member_count"] = int(
        await session.scalar(
            select(func.count())
            .select_from(Membership)
            .where(
                Membership.organization_id == principal.tenant_id, Membership.is_active.is_(True)
            )
        )
        or 0
    )
    counts["dashboard_count"] = int(
        await session.scalar(
            select(func.count())
            .select_from(Dashboard)
            .where(Dashboard.tenant_id == principal.tenant_id)
        )
        or 0
    )
    quota = organization.quota_config or {}
    today = datetime.now(UTC).date()
    daily_runs = int(
        await session.scalar(
            select(func.count())
            .select_from(AnalysisRun)
            .where(
                AnalysisRun.tenant_id == principal.tenant_id,
                func.date(AnalysisRun.created_at) == today,
            )
        )
        or 0
    )
    concurrent_runs = int(
        await session.scalar(
            select(func.count())
            .select_from(AnalysisRun)
            .where(
                AnalysisRun.tenant_id == principal.tenant_id,
                AnalysisRun.status.in_(["queued", "running"]),
            )
        )
        or 0
    )
    document_storage = int(
        await session.scalar(
            select(func.coalesce(func.sum(Document.file_size_bytes), 0)).where(
                Document.tenant_id == principal.tenant_id,
            )
        )
        or 0
    )
    report_storage = int(
        await session.scalar(
            select(func.count())
            .select_from(ReportExport)
            .where(
                ReportExport.tenant_id == principal.tenant_id,
                ReportExport.status == "completed",
            )
        )
        or 0
    )
    owner = (
        await session.scalar(select(User).where(User.id == organization.owner_user_id))
        if organization.owner_user_id
        else None
    )
    return OrganizationSummary(
        id=organization.id,
        slug=organization.slug,
        name=organization.name,
        owner_user_id=organization.owner_user_id,
        owner_name=owner.display_name if owner else None,
        role=principal.role,
        quota=quota,
        quota_usage={
            "concurrent_analyses": concurrent_runs,
            "daily_analysis_runs": daily_runs,
            "document_storage_bytes": document_storage,
            "report_storage_files": report_storage,
        },
        **counts,
    )


def _platform_org_view(
    organization: Organization, owner: User | None, counts: dict[str, int]
) -> PlatformOrganizationView:
    return PlatformOrganizationView(
        id=organization.id,
        slug=organization.slug,
        name=organization.name,
        owner_user_id=organization.owner_user_id,
        owner_name=owner.display_name if owner else None,
        created_at=organization.created_at,
        is_active=organization.is_active,
        quota=organization.quota_config or {},
        **counts,
    )


@router.get("/platform/organizations", response_model=list[PlatformOrganizationView])
async def list_platform_organizations(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=10, le=100),
    search: str = Query(default="", max_length=160),
    principal: Principal = Depends(require_role("platform_admin")),
    session: AsyncSession = Depends(get_session),
) -> list[PlatformOrganizationView]:
    query = (
        select(Organization)
        .order_by(Organization.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    if search.strip():
        term = f"%{search.strip()}%"
        query = query.where((Organization.name.ilike(term)) | (Organization.slug.ilike(term)))
    organizations = list(await session.scalars(query))
    result: list[PlatformOrganizationView] = []
    for organization in organizations:
        counts = {
            "member_count": int(
                await session.scalar(
                    select(func.count())
                    .select_from(Membership)
                    .where(Membership.organization_id == organization.id)
                )
                or 0
            ),
            "active_member_count": int(
                await session.scalar(
                    select(func.count())
                    .select_from(Membership)
                    .where(
                        Membership.organization_id == organization.id,
                        Membership.is_active.is_(True),
                    )
                )
                or 0
            ),
            "data_source_count": int(
                await session.scalar(
                    select(func.count())
                    .select_from(DataSource)
                    .where(DataSource.tenant_id == organization.id)
                )
                or 0
            ),
            "knowledge_base_count": int(
                await session.scalar(
                    select(func.count())
                    .select_from(KnowledgeBase)
                    .where(KnowledgeBase.tenant_id == organization.id)
                )
                or 0
            ),
            "report_count": int(
                await session.scalar(
                    select(func.count())
                    .select_from(Report)
                    .where(Report.tenant_id == organization.id)
                )
                or 0
            ),
        }
        owner = (
            await session.scalar(select(User).where(User.id == organization.owner_user_id))
            if organization.owner_user_id
            else None
        )
        result.append(_platform_org_view(organization, owner, counts))
    return result


@router.post(
    "/platform/organizations",
    response_model=PlatformOrganizationView,
    status_code=status.HTTP_201_CREATED,
)
async def create_platform_organization(
    payload: PlatformOrganizationCreate,
    principal: Principal = Depends(require_role("platform_admin")),
    session: AsyncSession = Depends(get_session),
) -> PlatformOrganizationView:
    if await session.scalar(select(Organization).where(Organization.slug == payload.slug)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="企业标识已存在")
    owner = None
    if payload.owner_user_id:
        owner = await session.scalar(select(User).where(User.id == payload.owner_user_id))
        if not owner:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="负责人不存在")
    organization = Organization(
        slug=payload.slug,
        name=payload.name,
        owner_user_id=payload.owner_user_id,
        quota_config=(payload.quota.model_dump() if payload.quota else None) or {},
    )
    if not organization.quota_config:
        organization.quota_config = {
            "max_concurrent_analyses": 4,
            "daily_analysis_runs": 100,
            "max_document_size_mb": 10,
            "retention_days": 90,
        }
    session.add(organization)
    await audit(
        session,
        principal.tenant_id,
        principal.user_id,
        "platform.organization_created",
        "organization",
        organization.id,
        {"slug": organization.slug},
    )
    await session.commit()
    return _platform_org_view(
        organization,
        owner,
        {
            "member_count": 0,
            "active_member_count": 0,
            "data_source_count": 0,
            "knowledge_base_count": 0,
            "report_count": 0,
        },
    )


@router.patch("/platform/organizations/{organization_id}", response_model=PlatformOrganizationView)
async def update_platform_organization(
    organization_id: str,
    payload: PlatformOrganizationUpdate,
    principal: Principal = Depends(require_role("platform_admin")),
    session: AsyncSession = Depends(get_session),
) -> PlatformOrganizationView:
    organization = await session.scalar(
        select(Organization).where(Organization.id == organization_id)
    )
    if not organization:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="企业不存在")
    owner = None
    if payload.name is not None:
        organization.name = payload.name
    if payload.owner_user_id is not None:
        owner = await session.scalar(select(User).where(User.id == payload.owner_user_id))
        if not owner:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="负责人不存在")
        organization.owner_user_id = owner.id
    if payload.quota is not None:
        organization.quota_config = payload.quota.model_dump()
    await audit(
        session,
        principal.tenant_id,
        principal.user_id,
        "platform.organization_updated",
        "organization",
        organization.id,
        payload.model_dump(exclude_none=True),
    )
    await session.commit()
    counts = {
        key: int(
            await session.scalar(
                select(func.count()).select_from(model).where(column == organization.id)
            )
            or 0
        )
        for key, model, column in (
            ("member_count", Membership, Membership.organization_id),
            ("active_member_count", Membership, Membership.organization_id),
            ("data_source_count", DataSource, DataSource.tenant_id),
            ("knowledge_base_count", KnowledgeBase, KnowledgeBase.tenant_id),
            ("report_count", Report, Report.tenant_id),
        )
    }
    counts["active_member_count"] = int(
        await session.scalar(
            select(func.count())
            .select_from(Membership)
            .where(Membership.organization_id == organization.id, Membership.is_active.is_(True))
        )
        or 0
    )
    owner = owner or (
        await session.scalar(select(User).where(User.id == organization.owner_user_id))
        if organization.owner_user_id
        else None
    )
    return _platform_org_view(organization, owner, counts)


@router.post(
    "/platform/organizations/{organization_id}/status", response_model=PlatformOrganizationView
)
async def update_platform_organization_status(
    organization_id: str,
    payload: PlatformOrganizationStatusUpdate,
    principal: Principal = Depends(require_role("platform_admin")),
    session: AsyncSession = Depends(get_session),
) -> PlatformOrganizationView:
    organization = await session.scalar(
        select(Organization).where(Organization.id == organization_id)
    )
    if not organization:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="企业不存在")
    organization.is_active = payload.is_active
    await audit(
        session,
        principal.tenant_id,
        principal.user_id,
        "platform.organization_status_updated",
        "organization",
        organization.id,
        {"is_active": payload.is_active},
    )
    await session.commit()
    counts = {
        "member_count": int(
            await session.scalar(
                select(func.count())
                .select_from(Membership)
                .where(Membership.organization_id == organization.id)
            )
            or 0
        ),
        "active_member_count": int(
            await session.scalar(
                select(func.count())
                .select_from(Membership)
                .where(
                    Membership.organization_id == organization.id, Membership.is_active.is_(True)
                )
            )
            or 0
        ),
        "data_source_count": int(
            await session.scalar(
                select(func.count())
                .select_from(DataSource)
                .where(DataSource.tenant_id == organization.id)
            )
            or 0
        ),
        "knowledge_base_count": int(
            await session.scalar(
                select(func.count())
                .select_from(KnowledgeBase)
                .where(KnowledgeBase.tenant_id == organization.id)
            )
            or 0
        ),
        "report_count": int(
            await session.scalar(
                select(func.count()).select_from(Report).where(Report.tenant_id == organization.id)
            )
            or 0
        ),
    }
    owner = (
        await session.scalar(select(User).where(User.id == organization.owner_user_id))
        if organization.owner_user_id
        else None
    )
    return _platform_org_view(organization, owner, counts)


@router.patch("/organization/settings", response_model=OrganizationSummary)
async def update_organization_settings(
    payload: OrganizationSettingsUpdate,
    principal: Principal = Depends(require_role("platform_admin", "org_admin")),
    session: AsyncSession = Depends(get_session),
) -> OrganizationSummary:
    organization = await session.scalar(
        select(Organization).where(Organization.id == principal.tenant_id)
    )
    owner_membership = await session.scalar(
        select(Membership).where(
            Membership.organization_id == principal.tenant_id,
            Membership.user_id == payload.owner_user_id,
            Membership.is_active.is_(True),
        )
    )
    owner = await session.scalar(select(User).where(User.id == payload.owner_user_id))
    if not organization or not owner_membership or not owner:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="负责人必须是当前组织的启用成员"
        )
    organization.owner_user_id = owner.id
    await audit(
        session,
        principal.tenant_id,
        principal.user_id,
        "organization.owner_updated",
        "organization",
        organization.id,
        {"owner_user_id": owner.id},
    )
    await session.commit()
    return await organization_summary(principal=principal, session=session)


@router.get("/organization/quotas", response_model=dict[str, int])
async def get_organization_quotas(
    principal: Principal = Depends(get_principal), session: AsyncSession = Depends(get_session)
) -> dict[str, int]:
    organization = await session.scalar(
        select(Organization).where(Organization.id == principal.tenant_id)
    )
    if not organization:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return organization.quota_config or {}


@router.patch("/organization/quotas", response_model=dict[str, int])
async def update_organization_quotas(
    payload: QuotaUpdate,
    principal: Principal = Depends(require_role("org_admin", "platform_admin")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, int]:
    organization = await session.scalar(
        select(Organization).where(Organization.id == principal.tenant_id)
    )
    if not organization:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    organization.quota_config = payload.model_dump()
    await audit(
        session,
        principal.tenant_id,
        principal.user_id,
        "organization.quota_updated",
        "organization",
        organization.id,
        payload.model_dump(),
    )
    await session.commit()
    return organization.quota_config


@router.get("/organization/permissions", response_model=PermissionMatrixView)
async def permission_matrix(principal: Principal = Depends(get_principal)) -> PermissionMatrixView:
    return PermissionMatrixView(
        roles={
            "platform_admin": {
                "manage_members": True,
                "manage_data_sources": True,
                "manage_knowledge": True,
                "run_analysis": True,
                "view_audit": True,
            },
            "org_admin": {
                "manage_members": True,
                "manage_data_sources": True,
                "manage_knowledge": True,
                "run_analysis": True,
                "view_audit": True,
            },
            "analyst": {
                "manage_members": False,
                "manage_data_sources": False,
                "manage_knowledge": False,
                "run_analysis": True,
                "view_audit": False,
            },
            "viewer": {
                "manage_members": False,
                "manage_data_sources": False,
                "manage_knowledge": False,
                "run_analysis": False,
                "view_audit": False,
            },
        }
    )


@router.get("/members", response_model=list[MemberView])
async def list_members(
    principal: Principal = Depends(require_role("org_admin", "platform_admin")),
    session: AsyncSession = Depends(get_session),
) -> list[MemberView]:
    rows = await session.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.organization_id == principal.tenant_id)
        .order_by(User.email)
    )
    return [
        MemberView(
            user_id=m.user_id,
            email=u.email,
            display_name=u.display_name,
            role=m.role,
            is_active=m.is_active,
        )
        for m, u in rows
    ]


def _invitation_status(invitation: MemberInvitation) -> str:
    if invitation.revoked_at:
        return "revoked"
    if invitation.accepted_at:
        return "accepted"
    expires_at = invitation.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= datetime.now(UTC):
        return "expired"
    return "pending"


async def _ensure_not_last_active_org_admin(
    session: AsyncSession, organization_id: str, membership: Membership
) -> None:
    """Keep every organization recoverable by retaining one active org admin."""
    if membership.role != "org_admin" or not membership.is_active:
        return
    active_admins = int(
        await session.scalar(
            select(func.count())
            .select_from(Membership)
            .where(
                Membership.organization_id == organization_id,
                Membership.role == "org_admin",
                Membership.is_active.is_(True),
            )
        )
        or 0
    )
    if active_admins <= 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="组织至少需要保留一名启用的组织管理员",
        )


@router.get("/members/invitations", response_model=list[MemberInvitationView])
async def list_invitations(
    principal: Principal = Depends(require_role("org_admin", "platform_admin")),
    session: AsyncSession = Depends(get_session),
) -> list[MemberInvitationView]:
    invitations = await session.scalars(
        select(MemberInvitation)
        .where(
            MemberInvitation.organization_id == principal.tenant_id,
        )
        .order_by(MemberInvitation.created_at.desc())
    )
    return [
        MemberInvitationView(
            id=i.id,
            email=i.email,
            role=i.role,
            status=_invitation_status(i),
            expires_at=i.expires_at,
            created_at=i.created_at,
        )
        for i in invitations
    ]


@router.post(
    "/members/invitations", response_model=MemberInvitationView, status_code=status.HTTP_201_CREATED
)
async def create_invitation(
    payload: MemberInvitationCreate,
    principal: Principal = Depends(require_role("org_admin", "platform_admin")),
    session: AsyncSession = Depends(get_session),
) -> MemberInvitationView:
    email = payload.email.strip().lower()
    existing = await session.scalar(
        select(Membership)
        .join(User, User.id == Membership.user_id)
        .where(
            Membership.organization_id == principal.tenant_id,
            User.email == email,
        )
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该邮箱已是组织成员")
    raw_token = create_refresh_token()
    invitation = MemberInvitation(
        organization_id=principal.tenant_id,
        email=email,
        role=payload.role,
        token_hash=hash_refresh_token(raw_token),
        expires_at=datetime.now(UTC) + timedelta(days=payload.expires_in_days),
        created_by=principal.user_id,
    )
    session.add(invitation)
    await audit(
        session,
        principal.tenant_id,
        principal.user_id,
        "member.invitation_created",
        "invitation",
        invitation.id,
        {"email": email, "role": payload.role},
    )
    await session.commit()
    return MemberInvitationView(
        id=invitation.id,
        email=email,
        role=invitation.role,
        status="pending",
        expires_at=invitation.expires_at,
        created_at=invitation.created_at,
        token=raw_token,
    )


@router.post("/members/invitations/{invitation_id}/resend", response_model=MemberInvitationView)
async def resend_invitation(
    invitation_id: str,
    principal: Principal = Depends(require_role("org_admin", "platform_admin")),
    session: AsyncSession = Depends(get_session),
) -> MemberInvitationView:
    invitation = await session.scalar(
        select(MemberInvitation).where(
            MemberInvitation.id == invitation_id,
            MemberInvitation.organization_id == principal.tenant_id,
        )
    )
    if not invitation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="邀请不存在")
    if invitation.accepted_at:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="邀请已使用")
    raw_token = create_refresh_token()
    invitation.token_hash = hash_refresh_token(raw_token)
    invitation.expires_at = datetime.now(UTC) + timedelta(days=7)
    invitation.revoked_at = None
    await audit(
        session,
        principal.tenant_id,
        principal.user_id,
        "member.invitation_resent",
        "invitation",
        invitation.id,
    )
    await session.commit()
    return MemberInvitationView(
        id=invitation.id,
        email=invitation.email,
        role=invitation.role,
        status="pending",
        expires_at=invitation.expires_at,
        created_at=invitation.created_at,
        token=raw_token,
    )


@router.post("/members/invitations/{invitation_id}/revoke", response_model=MemberInvitationView)
async def revoke_invitation(
    invitation_id: str,
    principal: Principal = Depends(require_role("org_admin", "platform_admin")),
    session: AsyncSession = Depends(get_session),
) -> MemberInvitationView:
    invitation = await session.scalar(
        select(MemberInvitation).where(
            MemberInvitation.id == invitation_id,
            MemberInvitation.organization_id == principal.tenant_id,
        )
    )
    if not invitation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="邀请不存在")
    current_status = _invitation_status(invitation)
    if current_status == "accepted":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="邀请已使用，不能撤销")
    if current_status == "revoked":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="邀请已撤销")
    invitation.revoked_at = datetime.now(UTC)
    await audit(
        session,
        principal.tenant_id,
        principal.user_id,
        "member.invitation_revoked",
        "invitation",
        invitation.id,
    )
    await session.commit()
    return MemberInvitationView(
        id=invitation.id,
        email=invitation.email,
        role=invitation.role,
        status="revoked",
        expires_at=invitation.expires_at,
        created_at=invitation.created_at,
    )


@router.post("/members/invitations/accept", response_model=TokenResponse)
async def accept_invitation(
    payload: MemberInvitationAccept, session: AsyncSession = Depends(get_session)
) -> TokenResponse:
    invitation = await session.scalar(
        select(MemberInvitation).where(
            MemberInvitation.token_hash == hash_refresh_token(payload.token),
        )
    )
    if not invitation or _invitation_status(invitation) != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="邀请无效、已过期或已使用"
        )
    user = await session.scalar(select(User).where(User.email == invitation.email))
    if not user:
        user = User(
            email=invitation.email,
            display_name=payload.display_name.strip(),
            password_hash=hash_password(payload.password),
        )
        session.add(user)
        await session.flush()
    membership = await session.scalar(
        select(Membership).where(
            Membership.organization_id == invitation.organization_id,
            Membership.user_id == user.id,
        )
    )
    if membership:
        membership.role = invitation.role
        membership.is_active = True
    else:
        membership = Membership(
            organization_id=invitation.organization_id,
            user_id=user.id,
            role=invitation.role,
            is_active=True,
        )
        session.add(membership)
    invitation.accepted_at = datetime.now(UTC)
    await set_tenant_context(session, invitation.organization_id)
    await audit(
        session,
        invitation.organization_id,
        user.id,
        "member.invitation_accepted",
        "invitation",
        invitation.id,
    )
    raw_refresh = create_refresh_token()
    session.add(
        RefreshToken(
            token_hash=hash_refresh_token(raw_refresh),
            user_id=user.id,
            organization_id=invitation.organization_id,
            expires_at=datetime.now(UTC) + timedelta(days=30),
        )
    )
    await session.commit()
    return TokenResponse(
        access_token=create_access_token(user.id, invitation.organization_id, membership.role),
        refresh_token=raw_refresh,
    )


@router.patch("/members/{user_id}", response_model=MemberView)
async def update_member(
    user_id: str,
    payload: MemberRoleUpdate,
    principal: Principal = Depends(require_role("org_admin", "platform_admin")),
    session: AsyncSession = Depends(get_session),
) -> MemberView:
    membership = await session.scalar(
        select(Membership).where(
            Membership.organization_id == principal.tenant_id, Membership.user_id == user_id
        )
    )
    user = await session.scalar(select(User).where(User.id == user_id))
    if not membership or not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    if (
        user_id == principal.user_id
        and payload.role != "org_admin"
        and principal.role == "org_admin"
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot remove your own admin role"
        )
    if payload.role != "org_admin":
        await _ensure_not_last_active_org_admin(session, principal.tenant_id, membership)
    membership.role = payload.role
    membership.is_active = True
    await audit(
        session,
        principal.tenant_id,
        principal.user_id,
        "member.role_updated",
        "membership",
        membership.id,
        {"user_id": user_id, "role": payload.role},
    )
    await session.commit()
    return MemberView(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=membership.role,
        is_active=membership.is_active,
    )


@router.patch("/members/{user_id}/status", response_model=MemberView)
async def update_member_status(
    user_id: str,
    payload: MemberStatusUpdate,
    principal: Principal = Depends(require_role("org_admin", "platform_admin")),
    session: AsyncSession = Depends(get_session),
) -> MemberView:
    membership = await session.scalar(
        select(Membership).where(
            Membership.organization_id == principal.tenant_id,
            Membership.user_id == user_id,
        )
    )
    user = await session.scalar(select(User).where(User.id == user_id))
    if not membership or not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    if user_id == principal.user_id and not payload.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot disable yourself"
        )
    if not payload.is_active:
        await _ensure_not_last_active_org_admin(session, principal.tenant_id, membership)
    membership.is_active = payload.is_active
    await audit(
        session,
        principal.tenant_id,
        principal.user_id,
        "member.enabled" if payload.is_active else "member.disabled",
        "membership",
        membership.id,
        {"user_id": user_id},
    )
    await session.commit()
    return MemberView(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=membership.role,
        is_active=membership.is_active,
    )


@router.delete("/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def disable_member(
    user_id: str,
    principal: Principal = Depends(require_role("org_admin", "platform_admin")),
    session: AsyncSession = Depends(get_session),
) -> Response:
    membership = await session.scalar(
        select(Membership).where(
            Membership.organization_id == principal.tenant_id, Membership.user_id == user_id
        )
    )
    if not membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    if user_id == principal.user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot disable yourself"
        )
    await _ensure_not_last_active_org_admin(session, principal.tenant_id, membership)
    membership.is_active = False
    await audit(
        session,
        principal.tenant_id,
        principal.user_id,
        "member.disabled",
        "membership",
        membership.id,
        {"user_id": user_id},
    )
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/data-sources", response_model=list[DataSourceView])
async def list_data_sources(
    principal: Principal = Depends(get_principal), session: AsyncSession = Depends(get_session)
) -> list[DataSource]:
    result = await session.scalars(
        select(DataSource).where(DataSource.tenant_id == principal.tenant_id)
    )
    return list(result)


@router.post("/data-sources/import-demo", response_model=list[DataSourceView])
async def import_demo_data_sources(
    principal: Principal = Depends(require_role("org_admin", "platform_admin")),
    session: AsyncSession = Depends(get_session),
) -> list[DataSource]:
    existing = list(
        await session.scalars(select(DataSource).where(DataSource.tenant_id == principal.tenant_id))
    )
    existing_hosts = {
        (source.engine, source.host, source.port, source.database_name) for source in existing
    }
    demo_definitions = (
        ("postgresql", "Compose Demo PostgreSQL", "demo-postgres", 5432, "supplychain"),
        ("mysql", "Compose Demo MySQL", "demo-mysql", 3306, "supplychain"),
    )
    created: list[DataSource] = []
    for engine, name, host, port, database_name in demo_definitions:
        if (engine, host, port, database_name) in existing_hosts:
            continue
        source = DataSource(
            tenant_id=principal.tenant_id,
            name=name,
            engine=engine,
            host=host,
            port=port,
            database_name=database_name,
            username="supplymind_ro",
            encrypted_password=encrypt_secret("supplymind-demo-ro"),
            allowed_tables=[],
        )
        session.add(source)
        created.append(source)
    await session.flush()
    # Demo import is a real onboarding workflow: verify connectivity, take a
    # schema snapshot, and approve the discovered tables before analysis can
    # select the source. Existing demo sources are repaired as well.
    demo_sources = [
        source for source in existing + created if source.host in {"demo-postgres", "demo-mysql"}
    ]
    for source in demo_sources:
        try:
            await test_connection(source)
            schema = await synchronize_schema(source)
            source.status = "active"
            source.last_tested_at = datetime.now(UTC)
            source.last_synced_at = datetime.now(UTC)
            source.allowed_tables = [
                str(table.get("name"))
                for table in schema.tables
                if isinstance(table, dict) and table.get("name")
            ]
            session.add(
                SchemaSnapshot(
                    tenant_id=principal.tenant_id,
                    data_source_id=source.id,
                    tables=schema.tables,
                    table_count=len(schema.tables),
                )
            )
            await audit(
                session,
                principal.tenant_id,
                principal.user_id,
                "data_source.demo_ready",
                "data_source",
                source.id,
                {"table_count": len(source.allowed_tables)},
            )
        except Exception as exc:
            source.status = "failed"
            await audit(
                session,
                principal.tenant_id,
                principal.user_id,
                "data_source.demo_failed",
                "data_source",
                source.id,
                {"reason": str(exc)[:200]},
            )
    for source in created:
        await audit(
            session,
            principal.tenant_id,
            principal.user_id,
            "data_source.demo_imported",
            "data_source",
            source.id,
            {"engine": source.engine, "host": source.host},
        )
    await session.commit()
    return existing + created


@router.get("/knowledge-bases", response_model=list[KnowledgeBaseView])
async def list_knowledge_bases(
    response: Response,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=10, le=100),
    status_filter: str | None = Query(default=None, alias="status"),
    name: str | None = Query(default=None, min_length=1, max_length=160),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> list[KnowledgeBase]:
    query = select(KnowledgeBase).where(KnowledgeBase.tenant_id == principal.tenant_id)
    if status_filter == "archived":
        query = query.where(KnowledgeBase.is_archived.is_(True))
    else:
        # Active is the safe default: archived knowledge bases must not return
        # to normal pickers after a successful delete/archive operation.
        query = query.where(KnowledgeBase.is_archived.is_(False))
    if name:
        query = query.where(KnowledgeBase.name.ilike(f"%{name}%"))
    total_query = query.with_only_columns(func.count(KnowledgeBase.id))
    response.headers["X-Total-Count"] = str(int(await session.scalar(total_query) or 0))
    response.headers["X-Page"] = str(page)
    response.headers["X-Page-Size"] = str(page_size)
    result = await session.scalars(
        query.order_by(KnowledgeBase.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(result)


@router.get("/knowledge-bases/{knowledge_base_id}", response_model=KnowledgeBaseView)
async def get_knowledge_base(
    knowledge_base_id: str,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> KnowledgeBase:
    return await get_tenant_knowledge_base(session, knowledge_base_id, principal.tenant_id)


@router.post(
    "/knowledge-bases", response_model=KnowledgeBaseView, status_code=status.HTTP_201_CREATED
)
async def create_knowledge_base(
    payload: KnowledgeBaseCreate,
    principal: Principal = Depends(require_role("org_admin", "platform_admin")),
    session: AsyncSession = Depends(get_session),
) -> KnowledgeBase:
    knowledge_base = KnowledgeBase(
        tenant_id=principal.tenant_id,
        name=payload.name,
        description=payload.description,
        created_by=principal.user_id,
    )
    session.add(knowledge_base)
    await session.flush()
    await audit(
        session,
        principal.tenant_id,
        principal.user_id,
        "knowledge_base.created",
        "knowledge_base",
        knowledge_base.id,
    )
    await session.commit()
    await session.refresh(knowledge_base)
    return knowledge_base


@router.patch("/knowledge-bases/{knowledge_base_id}", response_model=KnowledgeBaseView)
async def update_knowledge_base(
    knowledge_base_id: str,
    payload: KnowledgeBaseUpdate,
    principal: Principal = Depends(require_role("org_admin", "platform_admin")),
    session: AsyncSession = Depends(get_session),
) -> KnowledgeBase:
    knowledge_base = await get_tenant_knowledge_base(
        session, knowledge_base_id, principal.tenant_id
    )
    knowledge_base.name = payload.name
    knowledge_base.description = payload.description
    await audit(
        session,
        principal.tenant_id,
        principal.user_id,
        "knowledge_base.updated",
        "knowledge_base",
        knowledge_base.id,
    )
    await session.commit()
    return knowledge_base


@router.post("/knowledge-bases/{knowledge_base_id}/archive", response_model=KnowledgeBaseView)
async def archive_knowledge_base(
    knowledge_base_id: str,
    principal: Principal = Depends(require_role("org_admin", "platform_admin")),
    session: AsyncSession = Depends(get_session),
) -> KnowledgeBase:
    knowledge_base = await get_tenant_knowledge_base(
        session, knowledge_base_id, principal.tenant_id
    )
    knowledge_base.is_archived = not knowledge_base.is_archived
    knowledge_base.archived_at = datetime.now(UTC) if knowledge_base.is_archived else None
    await audit(
        session,
        principal.tenant_id,
        principal.user_id,
        "knowledge_base.archived" if knowledge_base.is_archived else "knowledge_base.restored",
        "knowledge_base",
        knowledge_base.id,
    )
    await session.commit()
    return knowledge_base


@router.delete("/knowledge-bases/{knowledge_base_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_knowledge_base(
    knowledge_base_id: str,
    principal: Principal = Depends(require_role("org_admin", "platform_admin")),
    session: AsyncSession = Depends(get_session),
) -> Response:
    knowledge_base = await get_tenant_knowledge_base(
        session, knowledge_base_id, principal.tenant_id
    )
    document_count = (
        await session.scalar(
            select(func.count(Document.id)).where(Document.knowledge_base_id == knowledge_base.id)
        )
        or 0
    )
    if not knowledge_base.is_archived:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="知识库必须先归档；归档后仅空知识库可以永久删除",
        )
    if document_count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="知识库包含文档，无法永久删除；请保留归档记录",
        )
    # Only archived, truly empty bases may be physically removed.
    await session.delete(knowledge_base)
    await audit(
        session,
        principal.tenant_id,
        principal.user_id,
        "knowledge_base.deleted",
        "knowledge_base",
        knowledge_base.id,
    )
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/knowledge-bases/{knowledge_base_id}/documents",
    response_model=DocumentView,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    knowledge_base_id: str,
    file: UploadFile = File(...),
    metric_name: str | None = Form(default=None, max_length=160),
    metric_definition: str | None = Form(default=None, max_length=10000),
    metric_formula: str | None = Form(default=None, max_length=2000),
    metric_unit: str | None = Form(default=None, max_length=40),
    applicable_factories: str = Form(default=""),
    applicable_product_lines: str = Form(default=""),
    effective_from: datetime | None = Form(default=None),
    replace_document_id: str | None = Form(default=None),
    principal: Principal = Depends(require_role("org_admin", "platform_admin")),
    session: AsyncSession = Depends(get_session),
) -> Document:
    knowledge_base = await get_tenant_knowledge_base(
        session, knowledge_base_id, principal.tenant_id
    )
    if knowledge_base.is_archived:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="归档知识库不能上传新文档")
    payload = await file.read()
    organization = await session.scalar(
        select(Organization).where(Organization.id == principal.tenant_id)
    )
    max_document_size = int(
        ((organization.quota_config if organization else {}) or {}).get("max_document_size_mb", 10)
    )
    if len(payload) > max_document_size * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"文档超过组织限制（{max_document_size} MB）",
        )
    try:
        extract_text(
            file.filename or "document.txt",
            file.content_type or "application/octet-stream",
            payload,
        )
    except KnowledgeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    digest = sha256(payload)
    task_key = sha256(f"{principal.tenant_id}:{knowledge_base.id}:{digest}".encode())
    existing_task = await session.scalar(
        select(IngestionTask).where(IngestionTask.task_key == task_key)
    )
    if existing_task:
        existing_document = await session.scalar(
            select(Document).where(Document.id == existing_task.document_id)
        )
        if existing_document:
            chunk_count = (
                await session.scalar(
                    select(func.count(Chunk.id)).where(
                        Chunk.document_id == existing_document.id, Chunk.level == "child"
                    )
                )
                or 0
            )
            return DocumentView.model_validate(
                {
                    **existing_document.__dict__,
                    "duplicate": True,
                    "chunk_count": chunk_count,
                    "ingestion_task_id": existing_task.id,
                }
            )
    storage_dir = Path(get_settings().document_directory)
    storage_dir.mkdir(parents=True, exist_ok=True)
    source_path = storage_dir / digest
    source_path.write_bytes(payload)
    if replace_document_id:
        document = await session.scalar(
            select(Document).where(
                Document.id == replace_document_id,
                Document.tenant_id == principal.tenant_id,
                Document.knowledge_base_id == knowledge_base.id,
            )
        )
        if not document:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="待替换文档不存在")
        if document.status in {"queued", "processing"}:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="待替换文档仍在摄取中")
        document.version += 1
        document.filename = file.filename or document.filename
        document.content_type = file.content_type or document.content_type
        document.content_sha256 = digest
        document.file_size_bytes = len(payload)
        document.source_path = str(source_path)
        document.status = "queued"
        document.error_message = None
        document.metric_name = metric_name or document.metric_name
        document.metric_definition = metric_definition or document.metric_definition
        document.metric_formula = metric_formula or document.metric_formula
        document.metric_unit = metric_unit or document.metric_unit
        document.applicable_factories = [
            item.strip() for item in applicable_factories.split(",") if item.strip()
        ] or document.applicable_factories
        document.applicable_product_lines = [
            item.strip() for item in applicable_product_lines.split(",") if item.strip()
        ] or document.applicable_product_lines
        document.effective_from = effective_from or document.effective_from
        session.add(
            DocumentVersion(
                tenant_id=principal.tenant_id,
                document_id=document.id,
                version=document.version,
                content_sha256=document.content_sha256,
                source_path=document.source_path,
                file_size_bytes=document.file_size_bytes,
                created_by=principal.user_id,
            )
        )
        task = IngestionTask(
            tenant_id=principal.tenant_id,
            document_id=document.id,
            task_key=f"{task_key}:v{document.version}",
        )
        session.add(task)
        await session.flush()
    else:
        document = None
    if document is None:
        document = Document(
            tenant_id=principal.tenant_id,
            knowledge_base_id=knowledge_base.id,
            filename=file.filename or "document.txt",
            content_type=file.content_type or "application/octet-stream",
            content_sha256=digest,
            created_by=principal.user_id,
            file_size_bytes=len(payload),
            language="zh"
            if any(
                "\u4e00" <= char <= "\u9fff" for char in payload.decode("utf-8", errors="ignore")
            )
            else "en",
            status="queued",
            source_path=str(source_path),
            metric_name=metric_name,
            metric_definition=metric_definition,
            metric_formula=metric_formula,
            metric_unit=metric_unit,
            applicable_factories=[
                item.strip() for item in applicable_factories.split(",") if item.strip()
            ],
            applicable_product_lines=[
                item.strip() for item in applicable_product_lines.split(",") if item.strip()
            ],
            effective_from=effective_from,
        )
        session.add(document)
        await session.flush()
        session.add(
            DocumentVersion(
                tenant_id=principal.tenant_id,
                document_id=document.id,
                version=document.version,
                content_sha256=document.content_sha256,
                source_path=document.source_path,
                file_size_bytes=document.file_size_bytes,
                created_by=principal.user_id,
            )
        )
        task = IngestionTask(
            tenant_id=principal.tenant_id, document_id=document.id, task_key=task_key
        )
        session.add(task)
        await session.flush()
    if get_settings().ingestion_mode == "broker":
        await audit(
            session,
            principal.tenant_id,
            principal.user_id,
            "document.ingestion_queued",
            "document",
            document.id,
            {"task_id": task.id},
        )
        await audit(
            session,
            principal.tenant_id,
            principal.user_id,
            "document.uploaded",
            "document",
            document.id,
            {"filename": document.filename},
        )
        session.add(
            create_background_task_event(
                tenant_id=principal.tenant_id,
                aggregate_type="ingestion_task",
                aggregate_id=task.id,
                event_type="document.ingestion_requested",
                payload={"task_id": task.id},
            )
        )
    else:
        try:
            await process_ingestion(session, task, document)
        except Exception as exc:
            task.status = "failed"
            task.error_message = str(exc)[:500]
            document.status = "failed"
            document.error_message = str(exc)[:500]
            await audit(
                session,
                principal.tenant_id,
                principal.user_id,
                "document.ingestion_failed",
                "document",
                document.id,
                {"reason": str(exc)[:200]},
            )
        await audit(
            session,
            principal.tenant_id,
            principal.user_id,
            "document.uploaded",
            "document",
            document.id,
            {"filename": document.filename},
        )
    await session.commit()
    await session.refresh(document)
    chunk_count = (
        await session.scalar(
            select(func.count(Chunk.id)).where(
                Chunk.document_id == document.id, Chunk.level == "child"
            )
        )
        or 0
    )
    return DocumentView.model_validate(
        {**document.__dict__, "chunk_count": chunk_count, "ingestion_task_id": task.id}
    )


@router.patch("/documents/{document_id}/metadata", response_model=DocumentView)
async def update_document_metadata(
    document_id: str,
    payload: DocumentMetadataUpdate,
    principal: Principal = Depends(require_role("org_admin", "platform_admin")),
    session: AsyncSession = Depends(get_session),
) -> DocumentView:
    document = await session.scalar(
        select(Document).where(
            Document.id == document_id, Document.tenant_id == principal.tenant_id
        )
    )
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    for key, value in payload.model_dump().items():
        setattr(document, key, value)
    await audit(
        session,
        principal.tenant_id,
        principal.user_id,
        "document.metadata_updated",
        "document",
        document.id,
        {"fields": list(payload.model_dump(exclude_unset=True))},
    )
    await session.commit()
    chunk_count = (
        await session.scalar(
            select(func.count(Chunk.id)).where(
                Chunk.document_id == document.id, Chunk.level == "child"
            )
        )
        or 0
    )
    return DocumentView.model_validate({**document.__dict__, "chunk_count": chunk_count})


@router.get("/documents/{document_id}", response_model=DocumentView)
async def get_document(
    document_id: str,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> DocumentView:
    document = await session.scalar(
        select(Document).where(
            Document.id == document_id, Document.tenant_id == principal.tenant_id
        )
    )
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    chunk_count = (
        await session.scalar(
            select(func.count(Chunk.id)).where(
                Chunk.document_id == document.id, Chunk.level == "child"
            )
        )
        or 0
    )
    return DocumentView.model_validate({**document.__dict__, "chunk_count": chunk_count})


@router.get("/documents/{document_id}/versions", response_model=list[DocumentVersionView])
async def list_document_versions(
    document_id: str,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> list[DocumentVersion]:
    document = await session.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.tenant_id == principal.tenant_id,
        )
    )
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return list(
        await session.scalars(
            select(DocumentVersion)
            .where(
                DocumentVersion.document_id == document_id,
                DocumentVersion.tenant_id == principal.tenant_id,
            )
            .order_by(DocumentVersion.version.desc())
        )
    )


@router.post("/documents/{document_id}/versions/{version}/rollback", response_model=DocumentView)
async def rollback_document_version(
    document_id: str,
    version: int,
    principal: Principal = Depends(require_role("org_admin", "platform_admin")),
    session: AsyncSession = Depends(get_session),
) -> DocumentView:
    document = await session.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.tenant_id == principal.tenant_id,
        )
    )
    target = await session.scalar(
        select(DocumentVersion).where(
            DocumentVersion.document_id == document_id,
            DocumentVersion.tenant_id == principal.tenant_id,
            DocumentVersion.version == version,
        )
    )
    if not document or not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document version not found"
        )
    if document.status in {"queued", "processing"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="请先完成或取消当前摄取任务"
        )
    document.version = target.version
    document.content_sha256 = target.content_sha256
    document.source_path = target.source_path
    document.file_size_bytes = target.file_size_bytes
    document.status = "queued"
    task = IngestionTask(
        tenant_id=principal.tenant_id,
        document_id=document.id,
        task_key=f"rollback:{document.id}:{target.version}:{secrets.token_urlsafe(8)}",
    )
    session.add(task)
    await session.flush()
    if get_settings().ingestion_mode == "broker":
        session.add(
            create_background_task_event(
                tenant_id=principal.tenant_id,
                aggregate_type="ingestion_task",
                aggregate_id=task.id,
                event_type="document.ingestion_requested",
                payload={"task_id": task.id, "reason": "version_rollback"},
            )
        )
    else:
        try:
            await process_ingestion(session, task, document)
        except Exception as exc:
            task.status = "failed"
            task.error_message = str(exc)[:500]
            document.status = "failed"
            document.error_message = str(exc)[:500]
    await audit(
        session,
        principal.tenant_id,
        principal.user_id,
        "document.version_rolled_back",
        "document",
        document.id,
        {"version": version},
    )
    await session.commit()
    chunk_count = (
        await session.scalar(
            select(func.count(Chunk.id)).where(
                Chunk.document_id == document.id, Chunk.level == "child"
            )
        )
        or 0
    )
    return DocumentView.model_validate({**document.__dict__, "chunk_count": chunk_count})


@router.get("/knowledge-bases/{knowledge_base_id}/documents/{document_id}/source")
async def get_document_source(
    knowledge_base_id: str,
    document_id: str,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> dict:
    document = await session.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.knowledge_base_id == knowledge_base_id,
            Document.tenant_id == principal.tenant_id,
        )
    )
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    chunks = list(
        await session.scalars(
            select(Chunk)
            .where(
                Chunk.document_id == document.id,
                Chunk.tenant_id == principal.tenant_id,
            )
            .order_by(Chunk.ordinal)
        )
    )
    return {
        "document_id": document.id,
        "filename": document.filename,
        "version": document.version,
        "category": document.category,
        "status": document.status,
        "chunks": [
            {
                "id": chunk.id,
                "ordinal": chunk.ordinal,
                "text": chunk.text,
                "location": chunk.location,
            }
            for chunk in chunks
        ],
    }


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: str,
    principal: Principal = Depends(require_role("org_admin", "platform_admin")),
    session: AsyncSession = Depends(get_session),
) -> Response:
    document = await session.scalar(
        select(Document).where(
            Document.id == document_id, Document.tenant_id == principal.tenant_id
        )
    )
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    if document.status in {"processing", "queued"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="请先取消摄取任务")
    task = await session.scalar(
        select(IngestionTask).where(
            IngestionTask.document_id == document.id, IngestionTask.tenant_id == principal.tenant_id
        )
    )
    if task and task.celery_task_id:
        try:
            from scripts.worker import celery_app

            celery_app.control.revoke(task.celery_task_id, terminate=False)
        except Exception:
            pass
    await audit(
        session, principal.tenant_id, principal.user_id, "document.deleted", "document", document.id
    )
    await session.delete(document)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/documents/{document_id}/archive", response_model=DocumentView)
async def archive_document(
    document_id: str,
    principal: Principal = Depends(require_role("org_admin", "platform_admin")),
    session: AsyncSession = Depends(get_session),
) -> DocumentView:
    document = await session.scalar(
        select(Document).where(
            Document.id == document_id, Document.tenant_id == principal.tenant_id
        )
    )
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    document.is_archived = not document.is_archived
    document.archived_at = datetime.now(UTC) if document.is_archived else None
    await audit(
        session,
        principal.tenant_id,
        principal.user_id,
        "document.archived" if document.is_archived else "document.restored",
        "document",
        document.id,
    )
    await session.commit()
    chunk_count = (
        await session.scalar(
            select(func.count(Chunk.id)).where(
                Chunk.document_id == document.id, Chunk.level == "child"
            )
        )
        or 0
    )
    return DocumentView.model_validate({**document.__dict__, "chunk_count": chunk_count})


@router.post("/ingestion-tasks/{task_id}/retry", response_model=IngestionTaskView)
async def retry_ingestion(
    task_id: str,
    principal: Principal = Depends(require_role("org_admin", "platform_admin")),
    session: AsyncSession = Depends(get_session),
) -> IngestionTask:
    task = await session.scalar(
        select(IngestionTask).where(
            IngestionTask.id == task_id, IngestionTask.tenant_id == principal.tenant_id
        )
    )
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Ingestion task not found"
        )
    if task.status == "processing":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Ingestion task is already processing"
        )
    task.status = "queued"
    task.dead_letter = False
    task.error_message = None
    task.next_retry_at = None
    document = await session.scalar(
        select(Document).where(
            Document.id == task.document_id, Document.tenant_id == principal.tenant_id
        )
    )
    if not document or document.is_archived:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Document is archived or unavailable"
        )
    if get_settings().ingestion_mode == "broker":
        await audit(
            session,
            principal.tenant_id,
            principal.user_id,
            "document.ingestion_retried",
            "document",
            document.id,
            {"task_id": task.id},
        )
        await session.commit()
        session.add(
            create_background_task_event(
                tenant_id=principal.tenant_id,
                aggregate_type="ingestion_task",
                aggregate_id=task.id,
                event_type="document.ingestion_requested",
                payload={"task_id": task.id, "reason": "manual_retry"},
            )
        )
    else:
        try:
            await process_ingestion(session, task, document)
        except Exception as exc:
            task.status = "failed"
            task.error_message = str(exc)[:500]
            document.status = "failed"
            document.error_message = str(exc)[:500]
    if get_settings().ingestion_mode != "broker":
        await audit(
            session,
            principal.tenant_id,
            principal.user_id,
            "document.ingestion_retried",
            "document",
            document.id,
            {"task_id": task.id},
        )
    await session.commit()
    return task


@router.post("/ingestion-tasks/{task_id}/cancel", response_model=IngestionTaskView)
async def cancel_ingestion(
    task_id: str,
    principal: Principal = Depends(require_role("org_admin", "platform_admin")),
    session: AsyncSession = Depends(get_session),
) -> IngestionTask:
    task = await session.scalar(
        select(IngestionTask).where(
            IngestionTask.id == task_id, IngestionTask.tenant_id == principal.tenant_id
        )
    )
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Ingestion task not found"
        )
    if task.status not in {"queued", "processing"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="任务当前不可取消")
    if task.celery_task_id:
        try:
            from scripts.worker import celery_app

            celery_app.control.revoke(task.celery_task_id, terminate=False)
        except Exception:
            pass
    task.status = "cancelled"
    task.error_message = "Cancelled by organization administrator"
    document = await session.scalar(
        select(Document).where(
            Document.id == task.document_id, Document.tenant_id == principal.tenant_id
        )
    )
    if document:
        document.status = "cancelled"
    await audit(
        session,
        principal.tenant_id,
        principal.user_id,
        "document.ingestion_cancelled",
        "ingestion_task",
        task.id,
    )
    await session.commit()
    return task


@router.get("/ingestion-tasks/{task_id}", response_model=IngestionTaskView)
async def get_ingestion_task(
    task_id: str,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> IngestionTask:
    task = await session.scalar(
        select(IngestionTask).where(
            IngestionTask.id == task_id, IngestionTask.tenant_id == principal.tenant_id
        )
    )
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Ingestion task not found"
        )
    return task


@router.get("/ingestion-tasks", response_model=list[IngestionTaskView])
async def list_ingestion_tasks(
    response: Response,
    task_status: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=10, le=100),
    principal: Principal = Depends(require_role("org_admin", "platform_admin")),
    session: AsyncSession = Depends(get_session),
) -> list[IngestionTask]:
    query = select(IngestionTask).where(IngestionTask.tenant_id == principal.tenant_id)
    if task_status:
        query = query.where(IngestionTask.status == task_status)
    total = int(await session.scalar(select(func.count()).select_from(query.subquery())) or 0)
    response.headers["X-Total-Count"] = str(total)
    return list(
        await session.scalars(
            query.order_by(IngestionTask.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )


@router.post("/ingestion-tasks/{task_id}/dead-letter/retry", response_model=IngestionTaskView)
async def retry_dead_letter_task(
    task_id: str,
    principal: Principal = Depends(require_role("org_admin", "platform_admin")),
    session: AsyncSession = Depends(get_session),
) -> IngestionTask:
    task = await session.scalar(
        select(IngestionTask).where(
            IngestionTask.id == task_id,
            IngestionTask.tenant_id == principal.tenant_id,
        )
    )
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Ingestion task not found"
        )
    if not task.dead_letter:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="任务不是死信状态")
    task.dead_letter = False
    task.attempts = 0
    await audit(
        session,
        principal.tenant_id,
        principal.user_id,
        "document.dead_letter_requeued",
        "ingestion_task",
        task.id,
    )
    await session.commit()
    return task


@router.post("/knowledge-bases/{knowledge_base_id}/search")
async def search_knowledge_base(
    knowledge_base_id: str,
    payload: KnowledgeSearchRequest,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> dict:
    await get_tenant_knowledge_base(session, knowledge_base_id, principal.tenant_id)
    try:
        results = await search_tenant_knowledge(
            session, principal.tenant_id, knowledge_base_id, payload.query, payload.limit
        )
    except ModelConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except ModelResponseError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    await audit(
        session,
        principal.tenant_id,
        principal.user_id,
        "knowledge.searched",
        "knowledge_base",
        knowledge_base_id,
        {"result_count": len(results)},
    )
    await session.commit()
    return {"query": payload.query, "results": results}


@router.post("/reports", response_model=ReportView, status_code=status.HTTP_201_CREATED)
async def create_report(
    payload: ReportCreate,
    principal: Principal = Depends(require_role("analyst", "org_admin", "platform_admin")),
    session: AsyncSession = Depends(get_session),
) -> ReportView:
    run = await session.scalar(
        select(AnalysisRun).where(
            AnalysisRun.id == payload.analysis_run_id, AnalysisRun.tenant_id == principal.tenant_id
        )
    )
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis run not found")
    markdown, citations = render_markdown(run, payload.title)
    report = Report(
        tenant_id=principal.tenant_id,
        analysis_run_id=run.id,
        title=payload.title or f"供应链分析报告 · {run.question[:80]}",
        markdown=markdown,
        citations=citations,
        created_by=principal.user_id,
    )
    session.add(report)
    await session.flush()
    await audit(
        session,
        principal.tenant_id,
        principal.user_id,
        "report.created",
        "report",
        report.id,
        {"analysis_run_id": run.id},
    )
    await session.commit()
    await session.refresh(report)
    return report


@router.get("/reports", response_model=list[ReportView])
async def list_reports(
    title: str | None = Query(default=None, min_length=1, max_length=240),
    status_filter: str | None = Query(default=None, alias="status"),
    created_by: str | None = Query(default=None),
    run_id: str | None = Query(default=None),
    created_from: datetime | None = Query(default=None),
    created_to: datetime | None = Query(default=None),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> list[Report]:
    query = select(Report).where(Report.tenant_id == principal.tenant_id)
    if title:
        query = query.where(Report.title.ilike(f"%{title}%"))
    if status_filter:
        query = query.where(Report.status == status_filter)
    if created_by:
        query = query.where(Report.created_by == created_by)
    if run_id:
        query = query.where(Report.analysis_run_id == run_id)
    if created_from:
        query = query.where(Report.created_at >= created_from)
    if created_to:
        query = query.where(Report.created_at <= created_to)
    result = await session.scalars(query.order_by(Report.created_at.desc()))
    return list(result)


@router.get("/reports/{report_id}", response_model=ReportView)
async def get_report(
    report_id: str,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> Report:
    report = await get_tenant_report(session, report_id, principal.tenant_id)
    run = await session.scalar(
        select(AnalysisRun).where(
            AnalysisRun.id == report.analysis_run_id,
            AnalysisRun.tenant_id == principal.tenant_id,
        )
    )
    return ReportView.model_validate(
        {
            **report.__dict__,
            "analysis_status": run.status if run else None,
            "analysis_sql": run.sql if run else None,
            "analysis_sql_draft": run.sql_draft if run else None,
            "analysis_result": run.result if run else None,
            "data_source_id": run.data_source_id if run else None,
            "knowledge_base_id": run.knowledge_base_id if run else None,
        }
    )


@router.post(
    "/reports/{report_id}/exports/pdf",
    response_model=ReportExportView,
    status_code=status.HTTP_202_ACCEPTED,
)
async def export_report_pdf(
    report_id: str,
    force: bool = Query(default=False),
    principal: Principal = Depends(
        require_role("viewer", "analyst", "org_admin", "platform_admin")
    ),
    session: AsyncSession = Depends(get_session),
) -> ReportExport:
    report = await get_tenant_report(session, report_id, principal.tenant_id)
    existing = await session.scalar(
        select(ReportExport)
        .where(
            ReportExport.report_id == report.id,
            ReportExport.tenant_id == principal.tenant_id,
            ReportExport.format == "pdf",
            ReportExport.status.in_(["queued", "running", "completed"]),
        )
        .order_by(ReportExport.created_at.desc())
    )
    if existing and not force:
        if existing.status != "completed" or export_asset_available(
            existing.storage_backend, existing.file_path, existing.object_key
        ):
            return existing
        # A completed database row must not strand a report when its artifact
        # was removed by local cleanup or object-storage retention.
        existing.status = "failed"
        existing.error_message = "Export artifact is no longer available"
        existing.finished_at = datetime.now(UTC)
    export = ReportExport(
        tenant_id=principal.tenant_id, report_id=report.id, created_by=principal.user_id
    )
    session.add(export)
    await session.flush()
    if get_settings().ingestion_mode == "broker":
        session.add(
            create_background_task_event(
                tenant_id=principal.tenant_id,
                aggregate_type="report_export",
                aggregate_id=export.id,
                event_type="report.pdf_export_requested",
                payload={"export_id": export.id},
            )
        )
    else:
        export.attempts = 1
        export.started_at = datetime.now(UTC)
        try:
            directory = Path(get_settings().report_directory)
            directory.mkdir(parents=True, exist_ok=True)
            export.file_path = str(directory / f"{report.id}-{export.id}.pdf")
            render_pdf(report.markdown, export.file_path)
            export.checksum_sha256 = sha256_digest(Path(export.file_path).read_bytes()).hexdigest()
            export.object_key = f"{export.tenant_id}/reports/{report.id}/{export.id}.pdf"
            put_file(export.file_path, export.object_key)
            export.storage_backend = "s3" if storage_configured() else "local"
            if export.storage_backend == "s3":
                export.file_path = None
            if not export_asset_available(
                export.storage_backend, export.file_path, export.object_key
            ):
                raise RuntimeError("PDF export artifact could not be verified")
            export.status = "completed"
        except (OSError, RuntimeError, ValueError) as exc:
            export.status = "failed"
            export.error_message = f"PDF 导出失败：{str(exc)[:800]}"
        finally:
            export.finished_at = datetime.now(UTC)
    await audit(
        session,
        principal.tenant_id,
        principal.user_id,
        "report.export_queued",
        "report",
        report.id,
        {"export_id": export.id, "format": "pdf"},
    )
    await session.commit()
    await session.refresh(export)
    return export


@router.get("/reports/{report_id}/exports/pdf", response_model=ReportExportView)
async def report_pdf_status(
    report_id: str,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> ReportExport:
    export = await session.scalar(
        select(ReportExport)
        .where(
            ReportExport.report_id == report_id,
            ReportExport.tenant_id == principal.tenant_id,
            ReportExport.format == "pdf",
        )
        .order_by(ReportExport.created_at.desc())
    )
    if not export:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PDF export not found")
    if export.status in {"queued", "running"} and export.celery_task_id:
        try:
            from scripts.worker import celery_app

            state = celery_app.AsyncResult(export.celery_task_id).state
            if state == "SUCCESS":
                # Celery acknowledges task execution, not artifact durability. The worker
                # is the only component allowed to mark the verified export completed.
                export.status = "failed"
                export.error_message = "PDF export task finished without a verified artifact"
            elif state in {"FAILURE", "REVOKED"}:
                export.status = "failed"
                export.error_message = "PDF export task failed"
            if export.status == "failed":
                export.updated_at = datetime.now(UTC)
                await session.commit()
        except Exception:
            pass
    return export


@router.post(
    "/reports/{report_id}/exports/{export_id}/retry",
    response_model=ReportExportView,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_report_export(
    report_id: str,
    export_id: str,
    principal: Principal = Depends(
        require_role("viewer", "analyst", "org_admin", "platform_admin")
    ),
    session: AsyncSession = Depends(get_session),
) -> ReportExport:
    report = await get_tenant_report(session, report_id, principal.tenant_id)
    export = await session.scalar(
        select(ReportExport).where(
            ReportExport.id == export_id,
            ReportExport.report_id == report_id,
            ReportExport.tenant_id == principal.tenant_id,
        )
    )
    if not export:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PDF export not found")
    if export.status != "failed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="当前导出任务不可重试")
    export.status = "queued"
    export.finished_at = None
    export.error_message = None
    export.file_path = None
    export.object_key = None
    if get_settings().ingestion_mode == "broker":
        session.add(
            create_background_task_event(
                tenant_id=principal.tenant_id,
                aggregate_type="report_export",
                aggregate_id=export.id,
                event_type="report.pdf_export_requested",
                payload={"export_id": export.id, "reason": "manual_retry"},
            )
        )
    else:
        export.attempts += 1
        export.started_at = datetime.now(UTC)
        try:
            directory = Path(get_settings().report_directory)
            directory.mkdir(parents=True, exist_ok=True)
            export.file_path = str(directory / f"{report_id}-{export.id}.pdf")
            render_pdf(report.markdown, export.file_path)
            export.checksum_sha256 = sha256_digest(Path(export.file_path).read_bytes()).hexdigest()
            export.object_key = f"{export.tenant_id}/reports/{report_id}/{export.id}.pdf"
            put_file(export.file_path, export.object_key)
            export.storage_backend = "s3" if storage_configured() else "local"
            if export.storage_backend == "s3":
                export.file_path = None
            if not export_asset_available(
                export.storage_backend, export.file_path, export.object_key
            ):
                raise RuntimeError("PDF export artifact could not be verified")
            export.status = "completed"
        except (OSError, RuntimeError, ValueError) as exc:
            export.status = "failed"
            export.error_message = f"PDF 导出失败：{str(exc)[:800]}"
        finally:
            export.finished_at = datetime.now(UTC)
    await audit(
        session,
        principal.tenant_id,
        principal.user_id,
        "report.export_retried",
        "report",
        report_id,
        {"export_id": export.id},
    )
    await session.commit()
    await session.refresh(export)
    return export


@router.get("/reports/{report_id}/exports", response_model=list[ReportExportView])
async def list_report_exports(
    report_id: str,
    response: Response,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=10, le=100),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> list[ReportExport]:
    await get_tenant_report(session, report_id, principal.tenant_id)
    query = select(ReportExport).where(
        ReportExport.report_id == report_id, ReportExport.tenant_id == principal.tenant_id
    )
    response.headers["X-Total-Count"] = str(
        int(await session.scalar(query.with_only_columns(func.count(ReportExport.id))) or 0)
    )
    response.headers["X-Page"] = str(page)
    response.headers["X-Page-Size"] = str(page_size)
    return list(
        await session.scalars(
            query.order_by(ReportExport.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )


@router.get("/reports/{report_id}/exports/pdf/download")
async def download_report_pdf(
    report_id: str,
    principal: Principal = Depends(
        require_role("viewer", "analyst", "org_admin", "platform_admin")
    ),
    session: AsyncSession = Depends(get_session),
):
    export = await session.scalar(
        select(ReportExport)
        .where(
            ReportExport.report_id == report_id,
            ReportExport.tenant_id == principal.tenant_id,
            ReportExport.format == "pdf",
            ReportExport.status == "completed",
        )
        .order_by(ReportExport.created_at.desc())
    )
    if not export:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PDF is not ready")
    if not export_asset_available(export.storage_backend, export.file_path, export.object_key):
        export.status = "failed"
        export.error_message = "Export artifact is no longer available"
        export.finished_at = datetime.now(UTC)
        await audit(
            session,
            principal.tenant_id,
            principal.user_id,
            "report.download_failed",
            "report",
            report_id,
            {"reason": "export artifact is missing", "export_id": export.id},
        )
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="PDF export artifact is missing; retry the export",
        )
    await audit(
        session,
        principal.tenant_id,
        principal.user_id,
        "report.downloaded",
        "report",
        report_id,
        {"format": "pdf"},
    )
    await session.commit()
    if export.storage_backend == "s3":
        try:
            content = get_file(export.object_key or "")
        except (OSError, RuntimeError, ValueError) as exc:
            export.error_message = "Object storage download failed"
            await audit(
                session,
                principal.tenant_id,
                principal.user_id,
                "report.download_failed",
                "report",
                report_id,
                {"reason": str(exc)[:200], "export_id": export.id},
            )
            await session.commit()
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY, detail="PDF object storage unavailable"
            ) from exc
        return Response(
            content,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{report_id}.pdf"'},
        )
    return FileResponse(export.file_path, media_type="application/pdf", filename=f"{report_id}.pdf")


@router.get("/knowledge-bases/{knowledge_base_id}/documents", response_model=list[DocumentView])
async def list_documents(
    response: Response,
    knowledge_base_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=10, le=200),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> list[DocumentView]:
    await get_tenant_knowledge_base(session, knowledge_base_id, principal.tenant_id)
    query = select(Document).where(
        Document.knowledge_base_id == knowledge_base_id, Document.tenant_id == principal.tenant_id
    )
    response.headers["X-Total-Count"] = str(
        int(await session.scalar(query.with_only_columns(func.count(Document.id))) or 0)
    )
    response.headers["X-Page"] = str(page)
    response.headers["X-Page-Size"] = str(page_size)
    documents = list(
        await session.scalars(
            query.order_by(Document.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    views = []
    for document in documents:
        count = (
            await session.scalar(
                select(func.count(Chunk.id)).where(
                    Chunk.document_id == document.id, Chunk.level == "child"
                )
            )
            or 0
        )
        views.append(DocumentView.model_validate({**document.__dict__, "chunk_count": count}))
    return views


@router.post("/data-sources", response_model=DataSourceView, status_code=status.HTTP_201_CREATED)
async def create_data_source(
    payload: DataSourceCreate,
    principal: Principal = Depends(require_role("org_admin", "platform_admin")),
    session: AsyncSession = Depends(get_session),
) -> DataSource:
    source = DataSource(
        tenant_id=principal.tenant_id,
        name=payload.name,
        engine=payload.engine,
        host=payload.host,
        port=payload.port,
        database_name=payload.database_name,
        username=payload.username,
        encrypted_password=encrypt_secret(payload.password),
        allowed_tables=payload.allowed_tables,
        tls_required=payload.tls_required,
    )
    session.add(source)
    await session.flush()
    await audit(
        session,
        principal.tenant_id,
        principal.user_id,
        "datasource.created",
        "data_source",
        source.id,
    )
    await session.commit()
    await session.refresh(source)
    return source


@router.post("/data-sources/{source_id}/test")
async def test_data_source(
    source_id: str,
    principal: Principal = Depends(require_role("org_admin", "platform_admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        source = await get_tenant_source(session, source_id, principal.tenant_id)
        ensure_source_enabled(source)
    except DataSourceError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    try:
        result = await test_connection(source)
    except DataSourceError as exc:
        source.status = "failed"
        await audit(
            session,
            principal.tenant_id,
            principal.user_id,
            "datasource.test_failed",
            "data_source",
            source.id,
            {"reason": str(exc)[:200]},
        )
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except Exception as exc:
        source.status = "failed"
        await audit(
            session,
            principal.tenant_id,
            principal.user_id,
            "datasource.test_failed",
            "data_source",
            source.id,
            {"reason": str(exc)[:200]},
        )
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "data_source_connection_failed",
                "message": "无法连接到数据源",
                "hint": "请检查主机、端口、只读账号密码和 TLS 配置后重试。",
            },
        ) from exc
    source.status = "active"
    source.last_tested_at = datetime.now(UTC)
    await audit(
        session,
        principal.tenant_id,
        principal.user_id,
        "datasource.tested",
        "data_source",
        source.id,
    )
    await session.commit()
    return result


@router.post("/data-sources/{source_id}/sync")
async def sync_data_source(
    source_id: str,
    principal: Principal = Depends(require_role("org_admin", "platform_admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        source = await get_tenant_source(session, source_id, principal.tenant_id)
        ensure_source_enabled(source)
    except DataSourceError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    task = DataSourceSyncTask(
        tenant_id=principal.tenant_id,
        data_source_id=source.id,
        created_by=principal.user_id,
        status="running",
        attempts=1,
        started_at=datetime.now(UTC),
    )
    session.add(task)
    await session.flush()
    source.status = "syncing"
    await session.commit()
    if get_settings().ingestion_mode == "broker":
        from scripts.worker import celery_app

        dispatched = celery_app.send_task("supplymind.datasource.sync_schema", args=[task.id])
        task.celery_task_id = dispatched.id
        task.status = "queued"
        await session.commit()
        return {"task_id": task.id, "celery_task_id": dispatched.id, "status": task.status}
    try:
        schema = await synchronize_schema(source)
    except DataSourceError as exc:
        task.status = "failed"
        task.error_message = str(exc)
        task.finished_at = datetime.now(UTC)
        source.status = "failed"
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except Exception as exc:
        task.status = "failed"
        task.error_message = "Schema synchronization failed"
        task.finished_at = datetime.now(UTC)
        source.status = "failed"
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Schema synchronization failed"
        ) from exc
    source.last_synced_at = datetime.now(UTC)
    snapshot = SchemaSnapshot(
        tenant_id=principal.tenant_id,
        data_source_id=source.id,
        tables=schema.tables,
        table_count=len(schema.tables),
    )
    session.add(snapshot)
    await session.flush()
    task.status = "completed"
    task.finished_at = datetime.now(UTC)
    task.snapshot_id = snapshot.id
    source.status = "active"
    await audit(
        session,
        principal.tenant_id,
        principal.user_id,
        "datasource.schema_synced",
        "data_source",
        source.id,
        {"table_count": len(schema.tables), "snapshot_id": snapshot.id},
    )
    await session.commit()
    return {"tables": schema.tables, "snapshot_id": snapshot.id, "synced_at": source.last_synced_at}


@router.get("/data-sources/{source_id}/sync-tasks", response_model=list[DataSourceSyncTaskView])
async def list_data_source_sync_tasks(
    source_id: str,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> list[DataSourceSyncTask]:
    try:
        source = await get_tenant_source(session, source_id, principal.tenant_id)
    except DataSourceError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    result = await session.scalars(
        select(DataSourceSyncTask)
        .where(
            DataSourceSyncTask.data_source_id == source.id,
            DataSourceSyncTask.tenant_id == principal.tenant_id,
        )
        .order_by(DataSourceSyncTask.created_at.desc())
        .limit(20)
    )
    return list(result)


@router.post(
    "/data-sources/{source_id}/sync-tasks/{task_id}/cancel",
    response_model=DataSourceSyncTaskView,
)
async def cancel_data_source_sync_task(
    source_id: str,
    task_id: str,
    principal: Principal = Depends(require_role("org_admin", "platform_admin")),
    session: AsyncSession = Depends(get_session),
) -> DataSourceSyncTask:
    """Cancel a queued schema scan without exposing another tenant's task."""
    try:
        source = await get_tenant_source(session, source_id, principal.tenant_id)
    except DataSourceError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    task = await session.scalar(
        select(DataSourceSyncTask).where(
            DataSourceSyncTask.id == task_id,
            DataSourceSyncTask.data_source_id == source.id,
            DataSourceSyncTask.tenant_id == principal.tenant_id,
        )
    )
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Schema sync task not found"
        )
    if task.status not in {"queued", "running"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="当前同步任务不可取消")
    if task.celery_task_id:
        try:
            from scripts.worker import celery_app

            celery_app.control.revoke(task.celery_task_id, terminate=False)
        except Exception:
            # The persisted cancellation remains authoritative if Redis is unavailable.
            pass
    task.status = "cancelled"
    task.error_message = "Schema 同步已由用户取消"
    task.finished_at = datetime.now(UTC)
    if source.status == "syncing":
        source.status = "active"
    await audit(
        session,
        principal.tenant_id,
        principal.user_id,
        "datasource.schema_sync_cancelled",
        "data_source_sync_task",
        task.id,
        {"data_source_id": source.id},
    )
    await session.commit()
    return task


@router.get("/data-sources/{source_id}/schema/tables/{table_name}")
async def get_schema_table(
    source_id: str,
    table_name: str,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        source = await get_tenant_source(session, source_id, principal.tenant_id)
    except DataSourceError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    snapshot = await session.scalar(
        select(SchemaSnapshot)
        .where(
            SchemaSnapshot.data_source_id == source.id,
            SchemaSnapshot.tenant_id == principal.tenant_id,
        )
        .order_by(SchemaSnapshot.created_at.desc())
    )
    if not snapshot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Schema snapshot not found"
        )
    table = next(
        (
            item
            for item in snapshot.tables
            if str(item.get("name", item.get("table_name", ""))) == table_name
        ),
        None,
    )
    if table is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Table not found")
    return table


@router.get("/data-sources/{source_id}", response_model=DataSourceView)
async def get_data_source(
    source_id: str,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> DataSource:
    try:
        return await get_tenant_source(session, source_id, principal.tenant_id)
    except DataSourceError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.patch("/data-sources/{source_id}/tls", response_model=DataSourceView)
async def update_data_source_tls(
    source_id: str,
    payload: DataSourceTlsUpdate,
    principal: Principal = Depends(require_role("org_admin", "platform_admin")),
    session: AsyncSession = Depends(get_session),
) -> DataSource:
    try:
        source = await get_tenant_source(session, source_id, principal.tenant_id)
    except DataSourceError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    source.tls_required = payload.tls_required
    await audit(
        session,
        principal.tenant_id,
        principal.user_id,
        "datasource.tls_updated",
        "data_source",
        source.id,
        {"tls_required": payload.tls_required},
    )
    await session.commit()
    return source


@router.get("/data-sources/{source_id}/schema", response_model=SchemaSnapshotView | None)
async def get_data_source_schema(
    source_id: str,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> SchemaSnapshot | None:
    try:
        source = await get_tenant_source(session, source_id, principal.tenant_id)
    except DataSourceError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    snapshot = await session.scalar(
        select(SchemaSnapshot)
        .where(
            SchemaSnapshot.data_source_id == source.id,
            SchemaSnapshot.tenant_id == principal.tenant_id,
        )
        .order_by(SchemaSnapshot.created_at.desc())
    )
    if snapshot is not None:
        return snapshot
    if source.status != "active":
        return None
    # Older demo sources may not have a snapshot even though they are usable.
    # Build it on first read so the schema panel never silently renders empty.
    try:
        schema = await synchronize_schema(source)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"无法读取数据源字段：{str(exc)[:180]}"
        ) from exc
    snapshot = SchemaSnapshot(
        tenant_id=principal.tenant_id,
        data_source_id=source.id,
        tables=schema.tables,
        table_count=len(schema.tables),
    )
    source.last_synced_at = datetime.now(UTC)
    if not source.allowed_tables:
        source.allowed_tables = [str(table["name"]) for table in schema.tables if table.get("name")]
    session.add(snapshot)
    await session.commit()
    await session.refresh(snapshot)
    return snapshot


@router.patch("/data-sources/{source_id}/allowlist", response_model=DataSourceView)
async def update_data_source_allowlist(
    source_id: str,
    payload: DataSourceAllowlistUpdate,
    principal: Principal = Depends(require_role("org_admin", "platform_admin")),
    session: AsyncSession = Depends(get_session),
) -> DataSource:
    try:
        source = await get_tenant_source(session, source_id, principal.tenant_id)
    except DataSourceError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    snapshot = await session.scalar(
        select(SchemaSnapshot)
        .where(
            SchemaSnapshot.data_source_id == source.id,
            SchemaSnapshot.tenant_id == principal.tenant_id,
        )
        .order_by(SchemaSnapshot.created_at.desc())
    )
    known_tables = {
        str(item.get("name", item.get("table_name", "")))
        for item in (snapshot.tables if snapshot else [])
    }
    if not known_tables or not set(payload.allowed_tables).issubset(known_tables):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="允许表必须来自最近一次 Schema 快照",
        )
    source.allowed_tables = sorted(set(payload.allowed_tables))
    await audit(
        session,
        principal.tenant_id,
        principal.user_id,
        "datasource.allowlist_updated",
        "data_source",
        source.id,
        {"allowed_tables": source.allowed_tables},
    )
    await session.commit()
    return source


@router.post("/data-sources/{source_id}/disable", response_model=DataSourceView)
async def disable_data_source(
    source_id: str,
    principal: Principal = Depends(require_role("org_admin", "platform_admin")),
    session: AsyncSession = Depends(get_session),
) -> DataSource:
    try:
        source = await get_tenant_source(session, source_id, principal.tenant_id)
    except DataSourceError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    source.status = "disabled" if source.status == "active" else "active"
    source.disabled_at = datetime.now(UTC) if source.status == "disabled" else None
    await audit(
        session,
        principal.tenant_id,
        principal.user_id,
        "datasource.disabled" if source.status == "disabled" else "datasource.enabled",
        "data_source",
        source.id,
    )
    await session.commit()
    return source


@router.delete("/data-sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_data_source(
    source_id: str,
    principal: Principal = Depends(require_role("org_admin", "platform_admin")),
    session: AsyncSession = Depends(get_session),
) -> Response:
    try:
        source = await get_tenant_source(session, source_id, principal.tenant_id)
    except DataSourceError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    referenced = (
        await session.scalar(
            select(func.count(AnalysisRun.id)).where(
                AnalysisRun.data_source_id == source.id,
                AnalysisRun.tenant_id == principal.tenant_id,
            )
        )
        or 0
    )
    if referenced:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Data source is referenced by analysis runs; disable it instead",
        )
    await audit(
        session,
        principal.tenant_id,
        principal.user_id,
        "datasource.deleted",
        "data_source",
        source.id,
    )
    await session.delete(source)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/data-sources/{source_id}/query")
async def query_data_source(
    source_id: str,
    payload: QueryRequest,
    principal: Principal = Depends(require_role("analyst", "org_admin", "platform_admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        source = await get_tenant_source(session, source_id, principal.tenant_id)
        ensure_source_enabled(source)
    except DataSourceError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    started = perf_counter()
    try:
        guarded, rows = await execute_guarded_query(source, payload.sql)
    except (DataSourceError, SQLGuardError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Query execution failed"
        ) from exc
    await audit(
        session,
        principal.tenant_id,
        principal.user_id,
        "datasource.query_executed",
        "data_source",
        source.id,
        {"tables": guarded.tables, "row_count": len(rows)},
    )
    await session.commit()
    elapsed_ms = int((perf_counter() - started) * 1000)
    return {
        "sql": guarded.sql,
        "tables": guarded.tables,
        "rows": rows,
        "row_count": len(rows),
        "max_rows": get_settings().sql_max_rows,
        "elapsed_ms": elapsed_ms,
        "timed_out": False,
        "redacted": True,
    }


async def _queue_analysis(
    payload: AnalysisRequest,
    principal: Principal,
    session: AsyncSession,
    idempotency_key: str | None,
) -> AnalysisRun:
    if not payload.knowledge_base_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "knowledge_base_required",
                "message": "必须选择知识库后才能发起真实分析",
                "hint": "请先选择一个未归档且已完成摄取的知识库。",
            },
        )
    source = await session.scalar(
        select(DataSource).where(
            DataSource.id == payload.data_source_id,
            DataSource.tenant_id == principal.tenant_id,
        )
    )
    if not source:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "data_source_not_found",
                "message": "所选数据源不存在或不属于当前组织",
            },
        )
    if source.status != "active":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "data_source_unavailable",
                "message": "所选数据源当前不可用于分析",
                "status": source.status,
                "hint": "请先测试连接并完成 Schema 同步，或启用该数据源。",
            },
        )
    knowledge_base = await session.scalar(
        select(KnowledgeBase).where(
            KnowledgeBase.id == payload.knowledge_base_id,
            KnowledgeBase.tenant_id == principal.tenant_id,
        )
    )
    if not knowledge_base:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "knowledge_base_not_found",
                "message": "所选知识库不存在或不属于当前组织",
            },
        )
    if knowledge_base.is_archived:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "knowledge_base_archived",
                "message": "归档知识库不能用于新的分析",
            },
        )
    if not source.allowed_tables:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "schema_allowlist_required",
                "message": "数据源尚未配置可查询表白名单",
                "hint": "完成 Schema 同步后选择至少一张允许查询的业务表。",
            },
        )
    if idempotency_key:
        existing = await session.scalar(
            select(AnalysisRun)
            .where(
                AnalysisRun.tenant_id == principal.tenant_id,
                AnalysisRun.idempotency_key == idempotency_key,
            )
            .order_by(AnalysisRun.created_at.desc())
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": "分析幂等键已使用",
                    "run_id": existing.id,
                    "status": existing.status,
                },
            )
    organization = await session.scalar(
        select(Organization).where(Organization.id == principal.tenant_id)
    )
    quota = (organization.quota_config if organization else {}) or {}
    concurrent = int(
        await session.scalar(
            select(func.count())
            .select_from(AnalysisRun)
            .where(
                AnalysisRun.tenant_id == principal.tenant_id,
                AnalysisRun.status.in_(["queued", "running"]),
            )
        )
        or 0
    )
    if concurrent >= int(quota.get("max_concurrent_analyses", 4)):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="已达到组织并发分析配额，请稍后重试",
        )
    daily_runs = int(
        await session.scalar(
            select(func.count())
            .select_from(AnalysisRun)
            .where(
                AnalysisRun.tenant_id == principal.tenant_id,
                func.date(AnalysisRun.created_at) == datetime.now(UTC).date(),
            )
        )
        or 0
    )
    if daily_runs >= int(quota.get("daily_analysis_runs", 100)):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="已达到组织每日分析配额，请明日再试",
        )
    conversation = None
    if payload.conversation_id:
        conversation = await session.scalar(
            select(Conversation).where(
                Conversation.id == payload.conversation_id,
                Conversation.tenant_id == principal.tenant_id,
                Conversation.created_by == principal.user_id,
            )
        )
    if conversation is None:
        conversation = Conversation(
            tenant_id=principal.tenant_id,
            title=payload.question[:80],
            created_by=principal.user_id,
        )
        session.add(conversation)
        await session.flush()
    session.add(
        ConversationMessage(
            tenant_id=principal.tenant_id,
            conversation_id=conversation.id,
            role="user",
            content=payload.question,
            metadata_json={
                "data_source_id": payload.data_source_id,
                "knowledge_base_id": payload.knowledge_base_id,
            },
        )
    )
    run = AnalysisRun(
        tenant_id=principal.tenant_id,
        conversation_id=conversation.id,
        data_source_id=payload.data_source_id,
        knowledge_base_id=payload.knowledge_base_id,
        question=payload.question,
        status="queued",
        attempts=0,
        idempotency_key=idempotency_key,
        checkpoint_thread_id=f"{principal.tenant_id}:{principal.user_id}:{conversation.id}",
        graph_version="enterprise-v2",
    )
    session.add(run)
    await session.flush()
    session.add(
        create_outbox_event(
            run,
            "analysis.requested",
            {"run_id": run.id, "conversation_id": conversation.id},
        )
    )
    await append_event(
        session,
        run,
        "queued",
        {"run_id": run.id, "conversation_id": conversation.id},
        commit=False,
    )
    await session.commit()
    try:
        from scripts.worker import celery_app

        celery_app.send_task("supplymind.outbox.dispatch", queue="analysis")
    except (OSError, RuntimeError, BrokerOperationalError):
        # The committed Outbox row is retried by Celery Beat when the broker recovers.
        pass
    return run


@router.post("/analyses", response_model=AnalysisAccepted, status_code=status.HTTP_202_ACCEPTED)
async def create_analysis(
    payload: AnalysisRequest,
    principal: Principal = Depends(require_role("analyst", "org_admin", "platform_admin")),
    session: AsyncSession = Depends(get_session),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> AnalysisAccepted:
    run = await _queue_analysis(payload, principal, session, idempotency_key)
    return AnalysisAccepted(
        run_id=run.id,
        conversation_id=run.conversation_id,
        stream_url=f"/api/v1/analyses/{run.id}/stream",
    )


@router.post("/analyses/stream")
async def stream_analysis(
    payload: AnalysisRequest,
    principal: Principal = Depends(require_role("analyst", "org_admin", "platform_admin")),
    session: AsyncSession = Depends(get_session),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> StreamingResponse:
    run = await _queue_analysis(payload, principal, session, idempotency_key)
    return StreamingResponse(
        stream_events(run.id, principal.tenant_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@a2a_router.get("/.well-known/agent-card.json")
async def a2a_agent_card() -> dict:
    base = get_settings().a2a_public_base_url.rstrip("/")
    return {
        "name": "SupplyMind Supply Chain Analyst",
        "description": "Tenant-scoped, evidence-grounded, read-only supply-chain analysis agent",
        "url": f"{base}/a2a",
        "protocolVersion": "1.0",
        "version": "2.0.0",
        "capabilities": {"streaming": True, "pushNotifications": False},
        "securitySchemes": {"bearer": {"type": "http", "scheme": "bearer", "format": "JWT"}},
        "security": [{"bearer": []}],
        "defaultInputModes": ["text/plain", "application/json"],
        "defaultOutputModes": ["text/plain", "application/json"],
        "skills": [
            {
                "id": "supply-chain-analysis",
                "name": "Read-only supply-chain analysis",
                "description": "Analyze approved business data with guarded SQL and evidence citations",
                "tags": ["supply-chain", "analytics", "sql", "read-only"],
            },
            {
                "id": "knowledge-research",
                "name": "Advanced RAG knowledge research",
                "description": "Retrieve tenant knowledge using hybrid BM25 and vector search",
                "tags": ["rag", "knowledge", "citations"],
            },
        ],
    }


def _a2a_error(request_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


@a2a_router.post("/a2a")
async def a2a_jsonrpc(
    payload: dict = Body(...),
    principal: Principal = Depends(require_role("analyst", "org_admin", "platform_admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    request_id = payload.get("id")
    method = payload.get("method")
    params = payload.get("params") or {}
    if method == "message/send":
        message = params.get("message") or {}
        parts = message.get("parts") or []
        question = "\n".join(
            str(part.get("text", "")) for part in parts if isinstance(part, dict)
        ).strip()
        metadata = {**(message.get("metadata") or {}), **(params.get("metadata") or {})}
        if (
            not question
            or not metadata.get("data_source_id")
            or not metadata.get("knowledge_base_id")
        ):
            return _a2a_error(
                request_id,
                -32602,
                "text, data_source_id and knowledge_base_id are required",
            )
        request = AnalysisRequest(
            question=question,
            data_source_id=metadata["data_source_id"],
            knowledge_base_id=metadata["knowledge_base_id"],
            conversation_id=metadata.get("conversation_id"),
        )
        run = await _queue_analysis(
            request,
            principal,
            session,
            f"a2a:{message.get('messageId') or secrets.token_urlsafe(16)}",
        )
        task = A2ATask(
            tenant_id=principal.tenant_id,
            analysis_run_id=run.id,
            context_id=message.get("contextId") or run.conversation_id,
            status="submitted",
            created_by=principal.user_id,
        )
        session.add(task)
        await session.commit()
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "id": task.id,
                "contextId": task.context_id,
                "status": {"state": "submitted"},
                "metadata": {
                    "analysis_run_id": run.id,
                    "stream_url": f"/a2a/tasks/{task.id}/stream",
                },
            },
        }
    if method in {"tasks/get", "tasks/cancel"}:
        task = await session.scalar(
            select(A2ATask).where(
                A2ATask.id == params.get("id"),
                A2ATask.tenant_id == principal.tenant_id,
            )
        )
        if not task:
            return _a2a_error(request_id, -32001, "Task not found")
        run = await session.scalar(
            select(AnalysisRun).where(
                AnalysisRun.id == task.analysis_run_id,
                AnalysisRun.tenant_id == principal.tenant_id,
            )
        )
        if method == "tasks/cancel" and run and run.status in {"queued", "running"}:
            run.status = "cancelled"
            run.finished_at = datetime.now(UTC)
            task.status = "cancelled"
            await session.commit()
            await append_event(session, run, "cancelled", {"run_id": run.id, "source": "a2a"})
        state_map = {
            "queued": "submitted",
            "running": "working",
            "completed": "completed",
            "failed": "failed",
            "cancelled": "canceled",
        }
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "id": task.id,
                "contextId": task.context_id,
                "status": {"state": state_map.get(run.status if run else "failed", "failed")},
                "artifacts": (
                    [{"artifactId": run.id, "parts": [{"data": run.result or {}}]}]
                    if run and run.status == "completed"
                    else []
                ),
            },
        }
    return _a2a_error(request_id, -32601, "Method not found")


@a2a_router.get("/a2a/tasks/{task_id}/stream")
async def a2a_task_stream(
    task_id: str,
    last_event_id: int = Header(default=0, alias="Last-Event-ID", ge=0),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    task = await session.scalar(
        select(A2ATask).where(
            A2ATask.id == task_id,
            A2ATask.tenant_id == principal.tenant_id,
        )
    )
    if not task:
        raise HTTPException(status_code=404, detail="A2A task not found")
    return StreamingResponse(
        stream_events(task.analysis_run_id, principal.tenant_id, last_event_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/analyses", response_model=list[AnalysisView])
async def list_analyses(
    response: Response,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=10, le=100),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> list[AnalysisRun]:
    query = select(AnalysisRun).where(AnalysisRun.tenant_id == principal.tenant_id)
    total = int(await session.scalar(select(func.count()).select_from(query.subquery())) or 0)
    response.headers["X-Total-Count"] = str(total)
    response.headers["X-Page"] = str(page)
    response.headers["X-Page-Size"] = str(page_size)
    result = await session.scalars(
        query.order_by(AnalysisRun.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(result)


@router.get("/analyses/{analysis_id}", response_model=AnalysisView)
async def get_analysis(
    analysis_id: str,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> AnalysisRun:
    run = await session.scalar(
        select(AnalysisRun).where(
            AnalysisRun.id == analysis_id, AnalysisRun.tenant_id == principal.tenant_id
        )
    )
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis run not found")
    return run


@router.get("/analyses/{analysis_id}/steps", response_model=list[AgentStepView])
async def get_analysis_steps(
    analysis_id: str,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> list:
    run = await session.scalar(
        select(AnalysisRun).where(
            AnalysisRun.id == analysis_id, AnalysisRun.tenant_id == principal.tenant_id
        )
    )
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis run not found")
    return list(
        await session.scalars(
            select(AgentStep)
            .where(AgentStep.analysis_run_id == run.id, AgentStep.tenant_id == principal.tenant_id)
            .order_by(AgentStep.created_at)
        )
    )


@router.get("/analyses/{analysis_id}/events")
async def get_analysis_events(
    analysis_id: str,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> dict:
    run = await session.scalar(
        select(AnalysisRun).where(
            AnalysisRun.id == analysis_id, AnalysisRun.tenant_id == principal.tenant_id
        )
    )
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis run not found")
    steps = list(
        await session.scalars(
            select(AgentStep)
            .where(AgentStep.analysis_run_id == run.id, AgentStep.tenant_id == principal.tenant_id)
            .order_by(AgentStep.created_at)
        )
    )
    return {
        "run_id": run.id,
        "status": run.status,
        "conversation_id": run.conversation_id,
        "sql": run.sql,
        "sql_draft": run.sql_draft,
        "guard_error": run.guard_error,
        "result": run.result,
        "steps": [
            AgentStepView.model_validate(step, from_attributes=True).model_dump(mode="json")
            for step in steps
        ],
        "last_event_sequence": run.last_event_sequence,
        "route": run.route,
    }


@router.get("/analyses/{analysis_id}/stream")
async def resume_analysis_stream(
    analysis_id: str,
    last_event_id: int = Header(default=0, alias="Last-Event-ID", ge=0),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    run = await session.scalar(
        select(AnalysisRun).where(
            AnalysisRun.id == analysis_id,
            AnalysisRun.tenant_id == principal.tenant_id,
        )
    )
    if not run:
        raise HTTPException(status_code=404, detail="Analysis run not found")
    return StreamingResponse(
        stream_events(run.id, principal.tenant_id, last_event_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/analyses/{analysis_id}/retry")
async def retry_analysis(
    analysis_id: str,
    principal: Principal = Depends(require_role("analyst", "org_admin", "platform_admin")),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    run = await session.scalar(
        select(AnalysisRun).where(
            AnalysisRun.id == analysis_id, AnalysisRun.tenant_id == principal.tenant_id
        )
    )
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis run not found")
    if run.status not in {"failed", "cancelled"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="当前运行不可重试")
    request = AnalysisRequest(
        data_source_id=run.data_source_id,
        knowledge_base_id=run.knowledge_base_id,
        question=run.question,
        conversation_id=run.conversation_id,
    )
    retry_key = f"retry:{run.id}:{secrets.token_urlsafe(12)}"
    await audit(
        session, principal.tenant_id, principal.user_id, "analysis.retried", "analysis_run", run.id
    )
    retried = await _queue_analysis(request, principal, session, retry_key)
    retried.retry_of_id = run.id
    await session.commit()
    return StreamingResponse(
        stream_events(retried.id, principal.tenant_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/analyses/{analysis_id}/cancel", response_model=AnalysisView)
async def cancel_analysis(
    analysis_id: str,
    principal: Principal = Depends(require_role("analyst", "org_admin", "platform_admin")),
    session: AsyncSession = Depends(get_session),
) -> AnalysisRun:
    run = await session.scalar(
        select(AnalysisRun).where(
            AnalysisRun.id == analysis_id, AnalysisRun.tenant_id == principal.tenant_id
        )
    )
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis run not found")
    if run.status not in {"queued", "running"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="当前运行不可取消")
    run.status = "cancelled"
    run.finished_at = datetime.now(UTC)
    run.error_message = "分析已由用户取消"
    await audit(
        session,
        principal.tenant_id,
        principal.user_id,
        "analysis.cancelled",
        "analysis_run",
        run.id,
    )
    await session.commit()
    await append_event(
        session,
        run,
        "cancelled",
        {"run_id": run.id, "message": "分析已由用户取消"},
    )
    return run


@router.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
async def ready(session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    settings = get_settings()
    dependencies: dict[str, str] = {}
    try:
        await session.execute(select(Organization.id).limit(1))
        dependencies["postgres"] = "ok"
    except Exception:
        dependencies["postgres"] = "error"

    redis_client = Redis.from_url(
        settings.redis_url,
        socket_connect_timeout=2,
        socket_timeout=2,
        health_check_interval=15,
    )
    try:
        await redis_client.ping()
        dependencies["redis"] = "ok"
    except Exception:
        dependencies["redis"] = "error"
    finally:
        await redis_client.aclose()

    if settings.s3_endpoint or settings.s3_access_key or settings.s3_secret_key:
        try:
            await run_in_threadpool(check_storage_ready)
            dependencies["object_storage"] = "ok"
        except Exception:
            dependencies["object_storage"] = "error"

    if any(value != "ok" for value in dependencies.values()):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "not_ready", "dependencies": dependencies},
        )
    return {"status": "ready", "dependencies": dependencies}


@router.get("/system/status")
async def system_status(
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> dict[str, object]:
    settings = get_settings()
    dependencies: dict[str, dict[str, str]] = {}
    try:
        await session.execute(select(Organization.id).limit(1))
        dependencies["postgres"] = {"status": "ok"}
    except Exception as exc:
        dependencies["postgres"] = {"status": "error", "error": type(exc).__name__}
    redis_client = Redis.from_url(settings.redis_url, socket_connect_timeout=1, socket_timeout=1)
    try:
        await redis_client.ping()
        dependencies["redis"] = {"status": "ok"}
        dependencies["worker"] = {
            "status": "configured" if settings.ingestion_mode == "broker" else "inline"
        }
    except Exception as exc:
        dependencies["redis"] = {"status": "error", "error": type(exc).__name__}
        dependencies["worker"] = {"status": "unavailable"}
    finally:
        await redis_client.aclose()
    dependencies["chat_model"] = {
        "status": "configured"
        if settings.chat_base_url and settings.chat_model and settings.chat_api_key
        else "not_configured"
    }
    dependencies["embedding_model"] = {
        "status": "configured"
        if settings.embedding_base_url and settings.embedding_model and settings.embedding_api_key
        else "not_configured"
    }
    dependencies["object_storage"] = {
        "status": "configured" if storage_configured() else "local_fallback"
    }
    dependencies["mcp"] = {"status": "configured"}
    if settings.ingestion_mode == "broker":
        try:
            from scripts.worker import celery_app

            inspector = celery_app.control.inspect(timeout=1)
            stats = inspector.stats() or {}
            active = inspector.active() or {}
            dependencies["worker"]["node_count"] = str(len(stats))
            dependencies["worker"]["active_tasks"] = str(
                sum(len(items) for items in active.values())
            )
            dependencies["worker"]["status"] = "ok" if stats else "unavailable"
        except Exception as exc:
            dependencies["worker"] = {"status": "unavailable", "error": type(exc).__name__}
    sources = list(
        await session.scalars(
            select(DataSource)
            .where(DataSource.tenant_id == principal.tenant_id)
            .order_by(DataSource.created_at)
        )
    )
    failed_ingestion = int(
        await session.scalar(
            select(func.count(IngestionTask.id)).where(
                IngestionTask.tenant_id == principal.tenant_id, IngestionTask.status == "failed"
            )
        )
        or 0
    )
    dead_letter = int(
        await session.scalar(
            select(func.count(IngestionTask.id)).where(
                IngestionTask.tenant_id == principal.tenant_id, IngestionTask.dead_letter.is_(True)
            )
        )
        or 0
    )
    failed_refresh = int(
        await session.scalar(
            select(func.count(DashboardRefreshTask.id)).where(
                DashboardRefreshTask.tenant_id == principal.tenant_id,
                DashboardRefreshTask.status == "failed",
            )
        )
        or 0
    )
    failed_sync = int(
        await session.scalar(
            select(func.count(DataSourceSyncTask.id)).where(
                DataSourceSyncTask.tenant_id == principal.tenant_id,
                DataSourceSyncTask.status == "failed",
            )
        )
        or 0
    )
    failed_exports = int(
        await session.scalar(
            select(func.count(ReportExport.id)).where(
                ReportExport.tenant_id == principal.tenant_id,
                ReportExport.status == "failed",
            )
        )
        or 0
    )
    failed_analyses = int(
        await session.scalar(
            select(func.count(AnalysisRun.id)).where(
                AnalysisRun.tenant_id == principal.tenant_id,
                AnalysisRun.status == "failed",
            )
        )
        or 0
    )
    recent_errors = list(
        await session.scalars(
            select(AuditEvent)
            .where(
                AuditEvent.tenant_id == principal.tenant_id,
                AuditEvent.action.ilike("%failed%"),
            )
            .order_by(AuditEvent.occurred_at.desc())
            .limit(10)
        )
    )
    failed_total = (
        failed_ingestion + failed_refresh + failed_sync + failed_exports + failed_analyses
    )
    dependencies["worker"]["failed_tasks"] = str(failed_total)
    dependencies["worker"]["dead_letter_tasks"] = str(dead_letter)
    dependencies["worker"]["recent_errors"] = [
        {
            "action": item.action,
            "resource_type": item.resource_type,
            "resource_id": item.resource_id,
            "occurred_at": item.occurred_at.isoformat() if item.occurred_at else None,
        }
        for item in recent_errors
    ]
    dependencies["api"] = {
        "status": "ok",
        "timeout_seconds": "2",
        "degradation_policy": "保留缓存并显示依赖异常",
    }
    degradation_policies = {
        "postgres": "拒绝写入并显示服务不可用",
        "redis": "降级为同步任务或显示刷新不可用",
        "worker": "保留 queued 状态并允许重试",
        "chat_model": "分析 fail-closed，不生成模拟结论",
        "embedding_model": "摄取失败，不进入可检索状态",
        "object_storage": "下载明确返回文件未就绪",
        "mcp": "阻断工具调用并记录审计",
    }
    for name, info in dependencies.items():
        info.setdefault("timeout_seconds", "2")
        info.setdefault("degradation_policy", degradation_policies.get(name, "显示依赖异常"))
    source_status = [
        {
            "id": source.id,
            "name": source.name,
            "host": source.host,
            "status": source.status,
            "last_tested_at": source.last_tested_at,
        }
        for source in sources
    ]
    degraded = any(item.get("status") in {"error", "unavailable"} for item in dependencies.values())
    return {
        "status": "degraded" if degraded else "ready",
        "dependencies": dependencies,
        "data_sources": source_status,
        "task_summary": {
            "failed": failed_total,
            "dead_letter": dead_letter,
            "ingestion_failed": failed_ingestion,
            "schema_sync_failed": failed_sync,
            "dashboard_refresh_failed": failed_refresh,
            "pdf_export_failed": failed_exports,
            "analysis_failed": failed_analyses,
        },
    }


@router.get("/metrics")
async def metrics() -> Response:
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
