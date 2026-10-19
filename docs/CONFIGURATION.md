# SupplyChain Agent 配置与密钥说明

本项目使用仓库根目录的 `.env` 作为本地 Docker Compose 配置文件。仓库只提交 `.env.example` 和 `.env.trial.example`，真实 `.env`、`.env.trial` 和任何生产密钥都不能提交。

## 快速配置

首次运行：

```powershell
Copy-Item .env.example .env
docker compose up -d --build
```

打开 `http://localhost:5173`，使用 `admin@demo.local`、`ChangeMe123!`、组织 `demo-factory` 登录。

不配置 Chat 和 Embedding 密钥时，平台、登录、数据源和报告列表仍可运行；真实分析、Embedding 和 RAG 检索会明确失败并显示 Trace ID，不会返回模拟结论。

## 必须自己设置的密钥

在 `.env` 中修改以下字段：

| 变量 | 用途 | 本地开发 | 试运行/生产 |
| --- | --- | --- | --- |
| `SUPPLYMIND_JWT_SECRET` | JWT 签名密钥 | 建议替换 | 必须替换 |
| `SUPPLYMIND_CREDENTIAL_KEY` | 数据源密码加密密钥，Fernet 格式 | 建议替换 | 必须替换 |
| `SUPPLYMIND_CHAT_API_KEY` | Chat 模型 API 密钥 | 需要真实分析时填写 | 必须由企业批准 |
| `SUPPLYMIND_EMBEDDING_API_KEY` | Embedding 模型 API 密钥 | 需要知识库检索时填写 | 必须由企业批准 |
| `SUPPLYMIND_S3_ACCESS_KEY` | MinIO/S3 访问密钥 | 可用本地默认 | 必须替换 |
| `SUPPLYMIND_S3_SECRET_KEY` | MinIO/S3 访问密钥 | 可用本地默认 | 必须替换 |
| `SUPPLYMIND_OIDC_CLIENT_SECRET` | 企业单点登录客户端密钥 | 可不配置 | 启用 OIDC 时必须填写 |

生成本地随机密钥：

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

第一条结果填入 `SUPPLYMIND_JWT_SECRET`。第二条结果填入 `SUPPLYMIND_CREDENTIAL_KEY`。

如果本机 Python 没有安装 `cryptography`，可以先构建后使用 API 镜像生成 Fernet 密钥：

```powershell
docker compose build api
docker compose run --rm api python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Chat 模型配置

真实分析需要 OpenAI-compatible Chat 接口。填写：

```dotenv
SUPPLYMIND_CHAT_BASE_URL=https://your-approved-chat-endpoint/v1
SUPPLYMIND_CHAT_MODEL=your-approved-chat-model
SUPPLYMIND_CHAT_API_KEY=your-chat-api-key
```

要求：

- `SUPPLYMIND_CHAT_BASE_URL` 必须包含兼容 API 前缀，以你的模型服务文档为准。
- `SUPPLYMIND_CHAT_MODEL` 必须是该服务已经开通的模型名。
- 密钥只写入 `.env`、部署 Secret 或企业密钥管理系统，不写入代码、文档提交或截图。

未配置或调用失败时，分析接口会 fail-closed，前端显示失败原因和 Trace ID。

## Embedding 配置

知识库上传后的向量化和检索需要 Embedding 接口。填写：

```dotenv
SUPPLYMIND_EMBEDDING_BASE_URL=https://your-approved-embedding-endpoint/v1
SUPPLYMIND_EMBEDDING_MODEL=your-approved-embedding-model
SUPPLYMIND_EMBEDDING_API_KEY=your-embedding-api-key
SUPPLYMIND_EMBEDDING_DIMENSION=1024
```

`SUPPLYMIND_EMBEDDING_DIMENSION` 必须和模型实际输出维度一致。维度不一致会导致向量写入或检索失败。

## 中文数据与 PDF 导出

Chat 的普通请求、流式请求和 SQL 规划分别支持
`SUPPLYMIND_CHAT_TIMEOUT_SECONDS`（默认 45 秒）、
`SUPPLYMIND_CHAT_STREAM_TIMEOUT_SECONDS`（默认 60 秒）和
`SUPPLYMIND_PLANNER_TIMEOUT_SECONDS`（默认 30 秒）。网络中转较慢时可单独增加，
不改变路由、模型、回答和重试逻辑；验收记录必须注明实际值。

前端发布镜像仅包含静态构建产物，通过非 root Nginx 提供页面，支持业务页面深链接。
`VITE_API_BASE_URL` 是构建参数；生产域名应通过
`docker build --build-arg VITE_API_BASE_URL=https://your-domain/api/v1 ./frontend`
注入。运行时修改同名环境变量不能改写已经构建的 JavaScript。

PDF 由后端 Worker 异步生成，并嵌入中文字体。无需为 PDF 单独配置字体或密钥。标准 Markdown 表格会渲染为 PDF 表格，而不是原始的 `|` 分隔文本。

平台的 MySQL 连接固定请求 `utf8mb4`。对于新建或接入的 MySQL 数据源，应确认数据库、表和连接用户均使用 `utf8mb4`；否则源数据可能在进入分析前已经出现乱码。

已经完成的 PDF 导出是不可变对象，不会在应用升级后自动改写。需要按当前渲染规则重建时，在报告中心打开详情并点击“重新生成 PDF”。此操作会创建一条新的导出记录，不会删除原始文件。若任务失败，可在导出历史中重试，并通过 `docker compose logs -f worker` 查看失败原因。

## 企业 Agent 配置

默认 Compose 会启动 API、Worker、Celery Beat 和独立 MCP Server。MCP 内置工具地址为
`http://mcp-server:8001/mcp`，业务 Worker 仅通过这个地址访问 Schema、只读 SQL、检索、图表和导出申请。

| 变量 | 用途 | 安全要求 |
| --- | --- | --- |
| `SUPPLYMIND_MCP_SERVICE_SECRET` | 签发 MCP 短期租户令牌 | 试运行和生产必须独立随机生成 |
| `SUPPLYMIND_MCP_ALLOWED_HOSTS` | 外部 Streamable HTTP MCP 主机白名单 | 只填经批准的域名或内部服务名 |
| `SUPPLYMIND_MCP_STDIO_CATALOG_JSON` | stdio MCP 静态目录 | 只能由部署人员维护，不接受浏览器传入命令 |
| `SUPPLYMIND_RERANK_*` | 可选专用重排接口 | 为空时回退 LLM 重排，再回退 RRF |
| `SUPPLYMIND_OTEL_EXPORTER_OTLP_ENDPOINT` | GenAI Trace OTLP HTTP 地址 | 例如 `http://otel-collector:4318/v1/traces` |

长期记忆默认开启，可在控制台“Agent 平台”中由用户关闭、查看或删除。服务端只接受预定义的偏好类别，并拒绝凭据和明显敏感信息。

## Compose Profiles

基础启动使用 `docker compose up -d --build`。需要模型网关时启动：

```powershell
docker compose --profile enterprise-ai up -d
```

在 `.env` 配置上游模型后，将 API 的 `SUPPLYMIND_CHAT_BASE_URL` 和
`SUPPLYMIND_EMBEDDING_BASE_URL` 设置为 `http://litellm:4000/v1`，模型名分别设为
`planner`、`answer`、`router` 或 `embedding`，API Key 设为 `LITELLM_MASTER_KEY`。

需要 Trace、Phoenix、Prometheus 和 Grafana 时启动：

```powershell
docker compose --profile observability up -d
```

同时设置 `SUPPLYMIND_OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318/v1/traces`。
Phoenix 在 `http://localhost:6006`，Prometheus 在 `http://localhost:9090`，Grafana 在
`http://localhost:3000`。生产应锁定镜像版本并将密码改为 Secret。

## 评测配置

`POST /api/v1/ai/evaluations` 会对已批准数据集版本创建异步评测。Router、SQL Guard、
Citation Precision/Recall、Faithfulness 与 Answer Relevance 的门槛由 `.env` 中的
`SUPPLYMIND_EVAL_*` 控制。提交代码前可运行：

```powershell
docker compose exec -T api python -m scripts.evaluation_gate
```

## 对象存储配置

本地 Docker Compose 默认启动 MinIO：

```dotenv
SUPPLYMIND_S3_ENDPOINT=http://minio:9000
SUPPLYMIND_S3_BUCKET=supplymind
SUPPLYMIND_S3_ACCESS_KEY=supplymind
SUPPLYMIND_S3_SECRET_KEY=change-this-in-production
```

本地开发可以使用默认值。试运行和生产必须替换为企业对象存储或独立 MinIO 的真实凭据。

## OIDC 单点登录配置

本地账号登录不需要 OIDC。要启用企业单点登录，填写：

```dotenv
SUPPLYMIND_OIDC_ISSUER=https://your-idp.example.com
SUPPLYMIND_OIDC_CLIENT_ID=your-client-id
SUPPLYMIND_OIDC_CLIENT_SECRET=your-client-secret
SUPPLYMIND_OIDC_REDIRECT_URI=http://localhost:5173/auth/callback
SUPPLYMIND_OIDC_AUTO_PROVISION=false
```

试运行和生产环境要把 `SUPPLYMIND_OIDC_REDIRECT_URI` 改为真实前端域名，例如：

```dotenv
SUPPLYMIND_OIDC_REDIRECT_URI=https://supplymind.example.com/auth/callback
```

## 数据源安全配置

数据源连接必须受主机和网段限制：

```dotenv
SUPPLYMIND_DATASOURCE_ALLOWED_HOSTS=localhost,127.0.0.1,demo-postgres,demo-mysql
SUPPLYMIND_DATASOURCE_ALLOWED_CIDRS=127.0.0.0/8,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16
```

本地演示使用 Compose 网络内的 `demo-postgres` 和 `demo-mysql`。企业环境应只允许经过审批的数据库主机或网段，并且只使用只读账号。

## 试运行配置

试运行使用 `.env.trial.example`：

```powershell
Copy-Item .env.trial.example .env.trial
```

填完 `.env.trial` 后，按 [TRIAL_DEPLOYMENT.md](TRIAL_DEPLOYMENT.md) 启动。试运行会拒绝开发默认 JWT、默认凭据加密密钥和缺失的对象存储凭据。

## 密钥安全规则

- 不提交 `.env`、`.env.trial`、截图里的密钥或运行日志中的密钥。
- 不把真实密钥写到 README、Issue、Commit message 或聊天记录。
- 开发密钥与生产密钥必须分离，禁止共用生产密钥。
- 密钥疑似泄露后，立即在模型服务、对象存储和身份提供商中轮换。
- 生产环境优先使用 Kubernetes Secret、云厂商 Secret Manager 或企业密钥管理系统。

## 配置验收

```powershell
docker compose up -d --build
Invoke-RestMethod http://localhost:8000/api/v1/health/ready
powershell -ExecutionPolicy Bypass -File scripts/acceptance-report.ps1 -RunTests
```

需要完整浏览器验收时：

```powershell
$env:PLAYWRIGHT_BASE_URL="http://localhost:5173"
npm --prefix frontend run test:e2e
```
