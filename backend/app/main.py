from contextlib import asynccontextmanager
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware

from app.api import a2a_router, router
from app.core.config import get_settings
from app.core.security import encrypt_secret, hash_password
from app.db import SessionLocal, engine
from app.models import Base, DataSource, Membership, Organization, User
from app.modules.audit.router import router as audit_router
from app.modules.dashboards.router import router as dashboards_router
from app.observability import HTTP_REQUEST_DURATION, HTTP_REQUESTS, configure_telemetry


async def seed_demo_data() -> None:
    async with SessionLocal() as session:
        base_tables = [
            "suppliers",
            "materials",
            "purchase_orders",
            "production_work_orders",
            "inventory_balances",
            "quality_inspections",
            "sales_orders",
            "delivery_plans",
        ]
        existing = await session.scalar(select(Organization.id).limit(1))
        if existing:
            organizations = list(
                await session.scalars(select(Organization).order_by(Organization.slug))
            )
            primary = next((item for item in organizations if item.slug == "demo-factory"), None)
            secondary = next((item for item in organizations if item.slug == "demo-south"), None)
            if not primary:
                primary = Organization(slug="demo-factory", name="示范制造集团")
                session.add(primary)
                await session.flush()
            if not secondary:
                secondary = Organization(slug="demo-south", name="南方制造事业部")
                session.add(secondary)
                await session.flush()
            account_specs = [
                (
                    "platform@demo.local",
                    "平台管理员",
                    "platform_admin",
                    [primary.id, secondary.id],
                    True,
                ),
                ("admin@demo.local", "示范组织管理员", "org_admin", [primary.id], False),
                ("analyst@demo.local", "示范分析师", "analyst", [primary.id], False),
                ("viewer@demo.local", "示范只读成员", "viewer", [primary.id], False),
                ("south-admin@demo.local", "南方组织管理员", "org_admin", [secondary.id], False),
                ("south-analyst@demo.local", "南方分析师", "analyst", [secondary.id], False),
                ("south-viewer@demo.local", "南方只读成员", "viewer", [secondary.id], False),
            ]
            for email, display_name, role, tenant_ids, platform_admin in account_specs:
                user = await session.scalar(select(User).where(User.email == email))
                if not user:
                    user = User(
                        email=email,
                        display_name=display_name,
                        password_hash=hash_password("ChangeMe123!"),
                        is_platform_admin=platform_admin,
                    )
                    session.add(user)
                    await session.flush()
                for tenant_id in tenant_ids:
                    membership = await session.scalar(
                        select(Membership).where(
                            Membership.organization_id == tenant_id, Membership.user_id == user.id
                        )
                    )
                    if not membership:
                        session.add(
                            Membership(organization_id=tenant_id, user_id=user.id, role=role)
                        )
            for organization in (primary, secondary):
                # Earlier local builds shipped one legacy demo source pointing at
                # a compose service that no longer exists. Repair it in place so
                # existing demo workspaces keep their report and audit history.
                legacy_source = await session.scalar(
                    select(DataSource).where(
                        DataSource.tenant_id == organization.id,
                        DataSource.host == "demo-data",
                        DataSource.database_name == "manufacturing_demo",
                    )
                )
                if legacy_source:
                    legacy_source.host = "demo-postgres"
                    legacy_source.port = 5432
                    legacy_source.database_name = "supplychain"
                    legacy_source.username = "supplymind_ro"
                    legacy_source.encrypted_password = encrypt_secret("supplymind-demo-ro")
                    legacy_source.allowed_tables = base_tables + [
                        "manufacturing_quality_events",
                        "steel_plate_defects",
                    ]
                    legacy_source.status = "active"
                if not organization.owner_user_id:
                    owner_membership = await session.scalar(
                        select(Membership).where(
                            Membership.organization_id == organization.id,
                            Membership.role == "org_admin",
                            Membership.is_active.is_(True),
                        )
                    )
                    if owner_membership:
                        organization.owner_user_id = owner_membership.user_id
                for engine_name, host, port in (
                    ("postgresql", "demo-postgres", 5432),
                    ("mysql", "demo-mysql", 3306),
                ):
                    tables = base_tables + (
                        ["manufacturing_quality_events", "steel_plate_defects"]
                        if engine_name == "postgresql"
                        else []
                    )
                    source = await session.scalar(
                        select(DataSource).where(
                            DataSource.tenant_id == organization.id, DataSource.host == host
                        )
                    )
                    if source:
                        source.allowed_tables = tables
                        source.status = "active"
                    else:
                        session.add(
                            DataSource(
                                tenant_id=organization.id,
                                name=f"{organization.name} · {engine_name.upper()} 演示库",
                                engine=engine_name,
                                host=host,
                                port=port,
                                database_name="supplychain",
                                username="supplymind_ro",
                                encrypted_password=encrypt_secret("supplymind-demo-ro"),
                                allowed_tables=tables,
                            )
                        )
                for source in list(
                    await session.scalars(
                        select(DataSource).where(
                            DataSource.tenant_id == organization.id,
                            DataSource.host == "demo-postgres",
                        )
                    )
                ):
                    source.allowed_tables = base_tables + [
                        "manufacturing_quality_events",
                        "steel_plate_defects",
                    ]
                    source.status = "active"
                retail_source = await session.scalar(
                    select(DataSource).where(
                        DataSource.tenant_id == organization.id,
                        DataSource.host == "retail-postgres",
                    )
                )
                if retail_source:
                    retail_source.name = "UCI 在线零售真实数据"
                    retail_source.allowed_tables = ["retail_transactions"]
                    retail_source.status = "active"
                else:
                    session.add(
                        DataSource(
                            tenant_id=organization.id,
                            name="UCI 在线零售真实数据",
                            engine="postgresql",
                            host="retail-postgres",
                            port=5432,
                            database_name="online_retail",
                            username="supplymind_ro",
                            encrypted_password=encrypt_secret("supplymind-demo-ro"),
                            allowed_tables=["retail_transactions"],
                        )
                    )
            await session.commit()
            return
        organizations = [
            Organization(slug="demo-factory", name="示范制造集团"),
            Organization(slug="demo-south", name="南方制造事业部"),
        ]
        users = [
            User(
                email="platform@demo.local",
                display_name="平台管理员",
                password_hash=hash_password("ChangeMe123!"),
                is_platform_admin=True,
            ),
            User(
                email="admin@demo.local",
                display_name="示范组织管理员",
                password_hash=hash_password("ChangeMe123!"),
            ),
            User(
                email="analyst@demo.local",
                display_name="示范分析师",
                password_hash=hash_password("ChangeMe123!"),
            ),
            User(
                email="viewer@demo.local",
                display_name="示范只读成员",
                password_hash=hash_password("ChangeMe123!"),
            ),
            User(
                email="south-admin@demo.local",
                display_name="南方组织管理员",
                password_hash=hash_password("ChangeMe123!"),
            ),
            User(
                email="south-analyst@demo.local",
                display_name="南方分析师",
                password_hash=hash_password("ChangeMe123!"),
            ),
            User(
                email="south-viewer@demo.local",
                display_name="南方只读成员",
                password_hash=hash_password("ChangeMe123!"),
            ),
        ]
        session.add_all([*organizations, *users])
        await session.flush()
        primary, secondary = organizations
        platform, admin, analyst, viewer, south_admin, south_analyst, south_viewer = users
        primary.owner_user_id = admin.id
        secondary.owner_user_id = south_admin.id
        session.add_all(
            [
                Membership(organization_id=primary.id, user_id=platform.id, role="platform_admin"),
                Membership(
                    organization_id=secondary.id, user_id=platform.id, role="platform_admin"
                ),
                Membership(organization_id=primary.id, user_id=admin.id, role="org_admin"),
                Membership(organization_id=primary.id, user_id=analyst.id, role="analyst"),
                Membership(organization_id=primary.id, user_id=viewer.id, role="viewer"),
                Membership(organization_id=secondary.id, user_id=south_admin.id, role="org_admin"),
                Membership(organization_id=secondary.id, user_id=south_analyst.id, role="analyst"),
                Membership(organization_id=secondary.id, user_id=south_viewer.id, role="viewer"),
            ]
        )
        for organization in organizations:
            for engine, host, port in (
                ("postgresql", "demo-postgres", 5432),
                ("mysql", "demo-mysql", 3306),
            ):
                tables = base_tables + (
                    ["manufacturing_quality_events", "steel_plate_defects"]
                    if engine == "postgresql"
                    else []
                )
                session.add(
                    DataSource(
                        tenant_id=organization.id,
                        name=f"{organization.name} · {engine.upper()} 演示库",
                        engine=engine,
                        host=host,
                        port=port,
                        database_name="supplychain",
                        username="supplymind_ro",
                        encrypted_password=encrypt_secret("supplymind-demo-ro"),
                        allowed_tables=tables,
                    )
                )
            session.add(
                DataSource(
                    tenant_id=organization.id,
                    name="UCI 在线零售真实数据",
                    engine="postgresql",
                    host="retail-postgres",
                    port=5432,
                    database_name="online_retail",
                    username="supplymind_ro",
                    encrypted_password=encrypt_secret("supplymind-demo-ro"),
                    allowed_tables=["retail_transactions"],
                )
            )
        await session.commit()


@asynccontextmanager
async def lifespan(_: FastAPI):
    from app.agents.runtime import runtime

    settings.validate_trial_runtime()
    # PostgreSQL schema is owned by Alembic; automatic metadata creation is only
    # retained for isolated SQLite development/test databases.
    if settings.database_url.startswith("sqlite") and (
        settings.auto_create_schema or settings.is_development
    ):
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
    if settings.is_development:
        await seed_demo_data()
    await runtime.start()
    yield
    await runtime.stop()
    await engine.dispose()


settings = get_settings()
OPENAPI_TAGS = [
    {"name": "认证与组织", "description": "登录、令牌轮换、组织切换和组织设置。"},
    {"name": "成员与审计", "description": "成员邀请、角色状态和审计查询。"},
    {"name": "数据源", "description": "数据源连接、Schema 同步、白名单和只读查询。"},
    {"name": "知识库", "description": "知识库、文档摄取、分类、向量化和检索。"},
    {"name": "分析会话", "description": "分析运行、SSE 事件、SQL Guard、重试和取消。"},
    {"name": "Hermes 框架", "description": "外层 Agent 编排、自进化信号、候选改进和安全门禁。"},
    {"name": "报告中心", "description": "报告正文、PDF 导出、对象存储和下载。"},
    {"name": "供应链大屏", "description": "五类供应链指标、趋势、排行和刷新。"},
    {"name": "系统状态", "description": "健康检查、依赖状态和指标。"},
    {"name": "平台接口", "description": "未归类的平台基础接口。"},
]

app = FastAPI(
    title="SupplyChain Agent API",
    version="0.1.0",
    description="SupplyMind 多租户供应链分析平台 API。所有业务资源按组织隔离，跨组织资源统一返回 404。\n\n认证方式：Bearer Access Token；访问令牌失效时使用 refresh token 轮换。",
    openapi_tags=OPENAPI_TAGS,
    lifespan=lifespan,
)
configure_telemetry("supplymind-api")
if settings.otel_exporter_otlp_endpoint:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(app, excluded_urls="/api/v1/health/live,/api/v1/metrics")


class TraceIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        trace_id = request.headers.get("x-trace-id") or str(uuid4())
        response = await call_next(request)
        response.headers["x-trace-id"] = trace_id
        return response


app.add_middleware(TraceIdMiddleware)


def _api_tag(path: str) -> str:
    if path.startswith("/api/v1/auth") or path.startswith("/api/v1/organization"):
        return "认证与组织"
    if path.startswith("/api/v1/members") or path.startswith("/api/v1/audit"):
        return "成员与审计"
    if path.startswith("/api/v1/data-sources"):
        return "数据源"
    if (
        path.startswith("/api/v1/knowledge")
        or path.startswith("/api/v1/ingestion")
        or path.startswith("/api/v1/documents")
    ):
        return "知识库"
    if path.startswith("/api/v1/analyses"):
        return "分析会话"
    if path.startswith("/api/v1/hermes"):
        return "Hermes 框架"
    if path.startswith("/api/v1/reports"):
        return "报告中心"
    if path.startswith("/api/v1/dashboards"):
        return "供应链大屏"
    if (
        path.startswith("/api/v1/health")
        or path.startswith("/api/v1/system")
        or path.startswith("/api/v1/metrics")
    ):
        return "系统状态"
    return "平台接口"


def _custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        tags=OPENAPI_TAGS,
    )
    for path, operations in schema.get("paths", {}).items():
        tag = _api_tag(path)
        for operation in operations.values():
            if isinstance(operation, dict):
                operation["tags"] = [tag]
    app.openapi_schema = schema
    return schema


app.openapi = _custom_openapi
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def metrics_middleware(request, call_next):
    trace_id = request.headers.get("x-trace-id") or uuid4().hex
    started = perf_counter()
    response = await call_next(request)
    route = getattr(request.scope.get("route"), "path", request.url.path)
    HTTP_REQUESTS.labels(request.method, route, str(response.status_code)).inc()
    HTTP_REQUEST_DURATION.labels(request.method, route).observe(perf_counter() - started)
    response.headers["X-Trace-Id"] = trace_id
    return response


app.include_router(router)
app.include_router(a2a_router)
app.include_router(audit_router)
app.include_router(dashboards_router)
