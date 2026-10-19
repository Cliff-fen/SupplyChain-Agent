# Helm 部署说明

Helm chart 位于 `infra/helm/supplymind`，默认只部署 API、Worker 和前端，不在集群内创建 PostgreSQL、Redis 或对象存储。

API 与 Worker 的文档/报告目录共同挂载持久卷。默认申请 ReadWriteMany；部署前应通过
`persistence.storageClassName` 选择支持该访问模式的存储类，或通过 `persistence.existingClaim`
使用预建共享卷。仅有 ReadWriteOnce 的集群不能直接按默认多副本部署。镜像使用 UID/GID 10001，
已有卷需迁移相应访问权限。前端 API 地址通过镜像构建参数 `VITE_API_BASE_URL` 注入，
修改运行时 ConfigMap 不会重写静态 JavaScript。

## Chart 校验

发布前必须执行 lint 和模板渲染。开发机不要求预装 Helm，可使用临时容器完成校验：

```powershell
docker run --rm -v "${PWD}:/work" -w /work alpine/helm:3.16.3 lint infra/helm/supplymind
docker run --rm -v "${PWD}:/work" -w /work alpine/helm:3.16.3 template supplymind infra/helm/supplymind > .helm-rendered.yaml
Remove-Item .helm-rendered.yaml -ErrorAction SilentlyContinue
```

如果 Docker Hub 暂时不可用，可在可访问镜像仓库中使用相同版本的 Helm 3.16 镜像；不得将渲染产物提交到仓库。

本项目也提供 `scripts/helm-smoke.ps1`，会使用本机 Helm 执行 lint/template；传入 `-RunCluster` 才会执行安装和回滚。执行前必须确认 `kubectl config current-context` 指向可用集群。

生产环境应先创建密钥并通过 `existingSecret` 注入，例如：

```bash
kubectl create secret generic supplymind-secrets \
  --from-literal=SUPPLYMIND_JWT_SECRET='generate-a-long-random-value' \
  --from-literal=SUPPLYMIND_CREDENTIAL_KEY='generate-a-fernet-compatible-key' \
  --from-literal=SUPPLYMIND_CHAT_API_KEY='...' \
  --from-literal=SUPPLYMIND_EMBEDDING_API_KEY='...' \
  --from-literal=SUPPLYMIND_S3_ACCESS_KEY='...' \
  --from-literal=SUPPLYMIND_S3_SECRET_KEY='...' \
  --from-literal=SUPPLYMIND_OIDC_CLIENT_SECRET='...'
helm upgrade --install supplymind infra/helm/supplymind \
  --set configMap.SUPPLYMIND_DATABASE_URL='postgresql+psycopg://...' \
  --set configMap.SUPPLYMIND_REDIS_URL='redis://...' \
  --set configMap.SUPPLYMIND_S3_ENDPOINT='https://s3.example.com' \
  --set configMap.SUPPLYMIND_CHAT_BASE_URL='https://chat.example.com/v1' \
  --set configMap.SUPPLYMIND_CHAT_MODEL='approved-chat-model' \
  --set configMap.SUPPLYMIND_EMBEDDING_BASE_URL='https://embedding.example.com/v1' \
  --set configMap.SUPPLYMIND_EMBEDDING_MODEL='approved-embedding-model' \
  --set ingress.enabled=true
```

PostgreSQL 16 + pgvector、Redis、S3 兼容存储和 OIDC Provider 由企业平台提供；将其连接地址写入 ConfigMap，将凭据写入 Secret 或外部 Secret 管理器。API 使用 `/api/v1/health/live` 和 `/api/v1/health/ready` 探针，Worker 使用进程探针，前端使用 HTTP 探针。

完整变量说明见 [CONFIGURATION.md](CONFIGURATION.md)。
