# SupplyChain Agent 交付运行手册

## 空环境启动

1. 复制 `.env.example` 为 `.env`，按 [CONFIGURATION.md](CONFIGURATION.md) 设置 `SUPPLYMIND_JWT_SECRET`、`SUPPLYMIND_CREDENTIAL_KEY`，以及真实 Chat/Embedding/OIDC/S3 配置。
2. 执行 `docker compose up -d --build`。
3. 检查 `docker compose ps`，API、Worker、frontend、postgres、redis、minio 和演示数据源必须健康。
4. 执行 `docker compose exec -T api alembic upgrade head`。
5. 验证 `/api/v1/health/live` 和 `/api/v1/health/ready`。

## 统一验收

```powershell
docker compose exec -T api pytest -q
docker compose exec -T api ruff check app/modules/dashboards/router.py app/modules/dashboards/schemas.py
docker compose exec -T api alembic current
docker compose config --quiet
npm --prefix frontend run build
npm --prefix frontend test
npm --prefix frontend run test:e2e
helm lint infra/helm/supplymind
helm template supplymind infra/helm/supplymind > supplymind-manifest.yaml
```

登录验收使用 `admin@demo.local`、`analyst@demo.local`、`viewer@demo.local` 和 `south-admin@demo.local`，密码由 Compose 本地演示配置提供。生产环境禁止使用演示种子和默认密码。

## 回滚

执行 `docker compose exec -T api alembic downgrade <previous_revision>`，确认 API 停止写入新字段后，再回滚镜像。禁止直接删除数据库卷；先备份 PostgreSQL 和 MinIO 对象。

## 真实能力限制

Chat 或 Embedding 未配置时，分析和检索必须显示 fail-closed 错误并带 Trace ID；系统不得返回模拟结论、假向量或静态报告。

CI 对后端 pytest/compileall、前端单元测试、前端生产构建、Playwright E2E 和 Helm lint/template 执行同样检查；任何一步失败都不得发布镜像。
