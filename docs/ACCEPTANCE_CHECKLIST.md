# SupplyChain Agent 交付验收清单

逐项操作、证据和能力口径见 [可核查的验收方法](ACCEPTANCE_PROTOCOL.md)。本清单是部署模板，
实际通过状态以每次部署的私有验收报告及命令输出为准，不能直接把未运行项目勾选为通过。

## 环境

- [ ] Docker Desktop 可启动 Compose 核心服务。
- [ ] API `/api/v1/health/live` 返回 `ok`，`/api/v1/health/ready` 返回 `ready`。
- [ ] 前端首页可打开，MinIO 控制台可登录。
- [ ] `pytest`、Ruff、前端 build、`docker compose config` 和容器化 `helm lint` 通过。

测试模式约定：后端单元/集成测试显式使用 `SUPPLYMIND_INGESTION_MODE=eager`；Compose 验收必须使用 `broker` 并检查 Worker 将任务推进到 `completed`。

## 功能

- [ ] 管理员可登录、刷新令牌、退出并管理成员角色。
- [ ] 组织管理员可创建 MySQL/PostgreSQL 数据源并执行连接测试、Schema 同步。
- [ ] 只读账号、主机/CIDR、Schema/表白名单和 SQL AST 规则均生效。
- [ ] 文档上传后完成分块、Embedding，检索返回引用位置和分数。
- [ ] 分析运行产生 Router、Handoff、Subagent、RAG、SQL Guard、结果与报告事件。
- [ ] SSE 使用 `Last-Event-ID` 在刷新或断线后恢复，事件按组织隔离。
- [ ] 长期记忆可以查看、创建、删除、关闭，并拒绝不允许的类别或敏感内容。
- [ ] MCP Server 管理、连接测试、白名单校验和报告导出审批可用。
- [ ] A2A Agent Card、任务提交、状态查询、取消与流式结果使用 JWT 鉴权。
- [ ] PDF 下载校验组织和角色，另一个组织收到 `404`。
- [ ] 大屏显示五类预置指标，并支持时间、工厂、产品线筛选。
- [ ] 大屏刷新返回任务 ID，任务详情能显示 queued/running/completed/failed、失败原因和最近完成时间。
- [ ] 大屏异常项可带入分析模板和工厂上下文。

## 安全与可靠性

- [ ] JWT 过期、刷新令牌重放、OIDC state 重放均被拒绝。
- [ ] 多语句、写操作、系统表、危险函数、越权表和超配额请求均被拒绝。
- [ ] Celery 任务重复投递不会产生重复文档块或报告文件。
- [ ] API、Worker、模型、MCP、SQL 和任务错误可在审计或日志中追踪。
- [ ] Prometheus 可抓取 `/api/v1/metrics`；Graph、模型、MCP 与 RAG Span 可在 Phoenix 查看。
- [ ] Outbox、Worker 重启、浏览器刷新和 Redis 短暂不可用后可恢复分析任务。
- [ ] 评测 Worker 与 `python -m scripts.evaluation_gate` 达到 Router、SQL Guard、Citation、Faithfulness、Relevance 门槛。

## 核心 E2E

组织管理员接入演示库后，分析师提问“近 30 天各工厂生产达成率与缺料风险”。验收记录必须包含运行 ID、SQL 草案、Guard 结果、查询行数、图表、RAG 引用、Markdown/PDF 报告和审计事件；其他组织成员无法读取其中任何资源。

记录每次部署的运行 ID、配置 Profile 和验收命令输出；不要提交模型密钥、业务结果或客户数据。
