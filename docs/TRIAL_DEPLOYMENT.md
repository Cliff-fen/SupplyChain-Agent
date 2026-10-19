# 内网试运行部署

本手册仅覆盖单机 Docker Compose 试运行，不包含 OIDC、Kubernetes、多地域灾备或生产 SLA。

## 发布前

1. 从 `.env.trial.example` 创建本机 `.env.trial`，填入随机 JWT、Fernet 凭据密钥、模型与对象存储密钥；该文件不得提交。
2. 生成不可变镜像标签，例如 `2026.08.21-rc1`。试运行启动会拒绝开发默认 JWT、默认凭据密钥和缺失的 S3 凭据。
3. 运行 `docker compose --env-file .env.trial -f docker-compose.yml -f docker-compose.trial.yml config --quiet`。

## 发布步骤

```powershell
$env:SUPPLYMIND_RELEASE_TAG = '2026.08.21-rc1'
$env:SUPPLYMIND_TRIAL_ENV_FILE = '.env.trial'
docker compose --env-file .env.trial -f docker-compose.yml -f docker-compose.trial.yml build
docker compose --env-file .env.trial -f docker-compose.yml -f docker-compose.trial.yml run --rm migrate
docker compose --env-file .env.trial -f docker-compose.yml -f docker-compose.trial.yml up -d
```

迁移是显式发布步骤；API 镜像启动不会执行 Alembic。启动后检查 `/api/v1/health/live` 和 `/api/v1/health/ready`，并在管理员、分析师、只读成员和第二组织账号下执行浏览器验收。

异步任务由 Worker 和 Beat 共同处理。看门狗每分钟检查超时任务：摄取任务在未耗尽尝试次数时重新入队；同步、刷新、PDF 与分析会转为失败并显示可恢复原因，避免永远显示“处理中”。

## 备份与恢复演练

发布前导出 PostgreSQL，并镜像 MinIO bucket；恢复时先停止 API/Worker/Beat，再恢复数据库和对象文件，最后以相同镜像标签启动。完整回滚操作见 [TRIAL_ROLLBACK.md](TRIAL_ROLLBACK.md)。
