# Migration Index

| Revision | Purpose |
| --- | --- |
| `0001_initial_and_rls` | Initial metadata schema and tenant RLS policies |
| `0002_agent_step_trace` | Agent stage trace fields and indexes |
| `0003_dashboards` | Tenant dashboard definitions, widgets, cache metadata, and RLS |

Run migrations from `backend/` with `alembic upgrade head`. Do not edit a
published revision; add a new revision for every schema change.
