# Modular monolith boundaries

`app/modules` is the domain boundary for the SupplyMind backend. Each module owns
its schemas, services, API router, background tasks, and migration changes.
Shared infrastructure stays in `app/core`, `app/db`, and `app/services`.

Rules for new work:

1. A module may depend on `app/core`, `app/db`, and declared ports from another module.
2. A module must not import another module's SQLAlchemy internals directly; use a service or port.
3. Every tenant resource requires both a service-layer tenant predicate and a database RLS policy.
4. API handlers stay thin: validate input, resolve principal, call a domain service, and map the result.
5. Background tasks receive an idempotency key and persist state transitions before doing external work.

When a module exposes an API, keep the endpoint contract stable and cover both
the domain service and the API behavior with tests.
