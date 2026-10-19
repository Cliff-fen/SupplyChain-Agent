# Database Assets

This directory contains database documentation and repeatable demonstration-data
assets. It does not replace the executable Alembic directory at
`backend/alembic`; Alembic is the only supported schema migration mechanism.

## Platform database

The platform PostgreSQL/pgvector database stores organizations, memberships,
data-source metadata, knowledge bases, analysis runs, Agent steps, reports,
dashboards, and audit events. It must never receive a full copy of a customer's
source database.

## User data sources

MySQL 8+ and PostgreSQL 14+ connections are external, read-only source systems.
Credentials, host/CIDR rules, allowed schemas/tables, connection timeouts, and
SQL Guard policies are enforced by the API before a query is executed.

## Layout

- `migrations/`: migration index and verification notes; executable revisions remain in `backend/alembic/versions`.
- `seeds/`: supply-chain demonstration database contract and idempotent seed entry point.

See `docs/ARCHITECTURE.md` for ownership and runtime boundaries.
