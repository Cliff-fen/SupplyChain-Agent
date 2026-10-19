# SupplyChain Agent API Reference

Base URL: `/api/v1`
Authentication: `Authorization: Bearer <access_token>`
Every response includes `X-Trace-ID`. Pass the same value in `X-Trace-ID` when correlating client retries.

## Authentication and Organizations

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/auth/login` | Login with `email`, `password`, `organization_slug`. |
| POST | `/auth/refresh` | Rotate a refresh token and issue a new access token. Reuse of an old token is rejected. |
| GET | `/auth/organizations` | List organizations available to the current user. |
| POST | `/auth/switch-organization` | Issue a token with a new organization context. |
| GET | `/auth/oidc/start?organization_slug=` | Start OIDC authorization with state and nonce. |
| GET | `/auth/oidc/callback?code=&state=` | Validate OIDC claims; new identities remain pending unless `SUPPLYMIND_OIDC_AUTO_PROVISION=true`. |
| GET | `/members` | List members in the current organization. |
| POST | `/members/invitations` | Create an invitation. |
| POST | `/members/invitations/{id}/resend` | Rotate and resend an invitation token. |
| POST | `/members/invitations/accept` | Consume a one-time invitation token. |
| PATCH | `/members/{user_id}` | Change a member role. |
| PATCH | `/members/{user_id}/status` | Enable or disable a member. |

## Data Sources and Schema

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/data-sources` | Create a PostgreSQL/MySQL connection definition. Secrets are encrypted at rest. |
| POST | `/data-sources/{id}/test` | Test a read-only connection. |
| POST | `/data-sources/{id}/sync` | Queue a real Schema synchronization task. |
| GET | `/data-sources/{id}/sync-tasks` | Read queued/running/completed/failed sync tasks. |
| PATCH | `/data-sources/{id}/tls` | Update the organization-admin TLS requirement for a source. |
| GET | `/data-sources/{id}/schema` | Read the latest Schema snapshot. |
| GET | `/data-sources/{id}/schema/tables/{table}` | Read one table's columns, keys, indexes and sampling limit. |
| PATCH | `/data-sources/{id}/allowlist` | Save tables selected from the latest Schema snapshot. |
| POST | `/data-sources/{id}/query` | Execute a read-only, Guard-validated query with row/time limits. |
| PATCH | `/data-sources/{id}/status` | Disable or re-enable a source. Disabled sources cannot be queried or analyzed. |

## Knowledge and Retrieval

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/knowledge-bases?page=&page_size=&status=&name=` | Filter knowledge bases. |
| POST | `/knowledge-bases` | Create a knowledge base. |
| POST | `/knowledge-bases/{id}/documents` | Upload Markdown, TXT or PDF and start ingestion. |
| GET | `/knowledge-bases/{id}/documents` | List documents, classification and embedding status. |
| GET | `/documents/{id}/versions` | List tenant-scoped document versions and checksums. |
| POST | `/documents/{id}/versions/{version}/rollback` | Queue a controlled rollback and re-ingest the selected version. |
| PATCH | `/documents/{id}/metadata` | Update metric name, definition, formula, unit, applicable scope and effective date. |
| GET | `/knowledge-bases/{id}/documents/{document_id}/source` | Read version, chunks and source locations. |
| POST | `/knowledge-bases/{id}/search` | Real embedding retrieval. Missing/failed Embedding returns an explicit error. |
| POST | `/ingestion-tasks/{id}/retry` | Retry a failed ingestion task. |
| POST | `/ingestion-tasks/{id}/cancel` | Cancel a queued/processing task. |
| GET | `/ingestion-tasks/{id}` | Read task state and failure details. |
| GET | `/ingestion-tasks?status=failed` | Paginated failed/dead-letter task inspection. |
| POST | `/ingestion-tasks/{id}/dead-letter/retry` | Requeue a dead-letter task after operator review. |

## Analysis and Reports

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/analyses` | Create an idempotent asynchronous analysis and return its recoverable stream URL. |
| GET | `/analyses/{id}/stream` | Replay durable SSE events. Send `Last-Event-ID` to resume after a disconnect. |
| POST | `/analyses/stream` | Backward-compatible endpoint that creates an analysis and streams events in one response. |
| GET | `/analyses/{id}` | Read run status, SQL draft/final SQL, Guard error and result. |
| GET | `/analyses/{id}/steps` | Read the persisted Agent trace. |
| GET | `/analyses/{id}/events` | Recover a run after an SSE disconnect. |
| POST | `/analyses/{id}/retry` | Retry a failed/cancelled run with lineage. |
| POST | `/analyses/{id}/cancel` | Cancel a queued/running run. |
| GET | `/reports` | Filter by title, status, creator, time and analysis run ID. |
| GET | `/reports/{id}` | Read Markdown, citations and run metadata. |
| POST | `/reports/{id}/exports/pdf` | Queue a PDF export. Add `?force=true` to create a new export using the latest renderer even when a completed export already exists. |
| GET | `/reports/{id}/exports/pdf` | Read queued/running/completed/failed export status. |
| POST | `/reports/{id}/exports/{export_id}/retry` | Retry a failed export. |
| GET | `/reports/{id}/exports/pdf/download` | Download the completed local or MinIO/S3 object. |

## Agent Runtime, Memory and Tooling

| Method | Path | Purpose |
| --- | --- | --- |
| GET/PATCH | `/me/memory/settings` | Read or change the current user's long-term-memory setting. |
| GET/POST | `/me/memories` | List or add tenant/user-scoped allowlisted memories. |
| PATCH/DELETE | `/me/memories/{id}` | Edit or remove one memory. |
| DELETE | `/me/memories` | Clear all memories for the current user. |
| GET/POST | `/mcp/servers` | List or register an approved external MCP Server (organization admin). |
| PATCH/DELETE | `/mcp/servers/{id}` | Enable, update or remove a registered Server. |
| POST | `/mcp/servers/{id}/test` | Discover tools through the configured transport. |
| GET | `/agent-approvals?status=pending` | List pending tool approvals. |
| POST | `/agent-approvals/{id}/approve` | Approve an export or other side-effecting tool request. |
| POST | `/agent-approvals/{id}/reject` | Reject an approval request. |
| POST | `/ai/evaluations` | Queue evaluation for an approved dataset version. |
| GET | `/ai/evaluations` | Read evaluation status, metrics and failed gates. |

## A2A

`GET /.well-known/agent-card.json` exposes the read-only Agent Card. `POST /a2a`
accepts JSON-RPC `message/send`, `tasks/get` and `tasks/cancel`; use
`GET /a2a/tasks/{id}/stream` with `Last-Event-ID` for task events. A2A uses the
same JWT organization boundary and does not expose write tools or credentials.

## Dashboards, Audit and Status

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/dashboards/supply-chain` | Read five real SQL-aggregated supply-chain components. |
| GET | `/dashboards/supply-chain/config` | Read organization-level refresh/widget configuration. |
| PATCH | `/dashboards/supply-chain/config` | Update organization-level refresh/widget configuration (org/platform admin only). |
| GET | `/dashboards/supply-chain/dimensions` | Read dynamic factory/product-line/supplier filters. |
| POST | `/dashboards/supply-chain/refresh` | Queue an organization-admin refresh task. |
| GET | `/dashboards/supply-chain/refresh/{task_id}` | Read refresh status and failure reason. |
| GET | `/audit` | Filter by action, resource, actor, time range, pagination and run ID. Returns `X-Total-Count`, `X-Page-Offset` and `X-Page-Limit` headers. |
| GET | `/audit/{event_id}` | Read one tenant-scoped audit event. Sensitive values are redacted; another organization receives `404`. |
| GET | `/system/status` | Read PostgreSQL, Redis, Worker, Chat, Embedding, MinIO, MCP and source status, including failed/dead-letter task counts and recent error summaries. |
| GET | `/health/live` | Liveness check. |
| GET | `/health/ready` | Dependency readiness check. |

## Cross-organization behavior

All resource queries include the JWT organization context and service-layer `tenant_id`. A resource belonging to another organization is returned as `404`, including reports, exports, data sources, documents, analyses, dashboard tasks and audit records.

## Verification order

1. `docker compose config --quiet`
2. `docker compose up -d`
3. `docker compose exec -T api alembic upgrade head`
4. `docker compose exec -T api pytest -q`
5. `npm run build` in `frontend`
6. Run the browser path in `docs/ACCEPTANCE_CHECKLIST.md`.
