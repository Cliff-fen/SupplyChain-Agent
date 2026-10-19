# 部署与回滚手册

## Compose

```powershell
docker compose config --quiet
docker compose up -d --build
docker compose ps
docker compose logs --tail=100 api worker
```

发生版本问题时，使用 Git 回滚到上一个已验收 commit，再重新构建 API/Worker 和前端。不要删除 PostgreSQL、Redis 或 MinIO 数据卷；回滚前先备份数据库。

## Kubernetes

```powershell
helm lint infra/helm/supplymind
helm upgrade --install supplymind infra/helm/supplymind --set ingress.enabled=true
kubectl rollout status deployment/supplymind-api
kubectl rollout status deployment/supplymind-worker
kubectl rollout undo deployment/supplymind-api
```

生产集群使用外部 PostgreSQL/pgvector、Redis、S3 兼容存储和 OIDC Provider。连接地址进入 ConfigMap，密钥通过 `existingSecret` 或外部 Secret 管理器注入。回滚后检查健康探针、Celery 队列积压、报告对象存储和审计写入。
