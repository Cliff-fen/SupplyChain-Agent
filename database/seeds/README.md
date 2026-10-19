# Supply-chain demo seed contract

The demo database must expose these business areas:

- suppliers and supplier delivery performance
- purchase orders and purchase-order lines
- materials and bills of material
- production work orders and completion records
- batches and traceability
- inventory balances and shortage risk
- quality inspections and non-conformance
- sales orders and order lines
- delivery plans and fulfillment milestones

Seed scripts must be versioned, repeatable, and idempotent. They must create a
dedicated read-only account for analysis examples and must never be used as the
platform database seed. The current platform demo seed remains in
`backend/app/main.py` until the tenancy module extraction is complete.

Equivalent starter scripts are available at `postgresql/001_supply_chain.sql`
and `mysql/001_supply_chain.sql`. The PostgreSQL script contains the complete
demo schema; the MySQL script covers the core supplier, material, production,
and inventory path and can be extended for additional datasource scenarios.

## Synthetic test fixtures

`postgresql/002_supply_chain_test_data.sql` and
`mysql/002_supply_chain_test_data.sql` add extra suppliers, materials, work
orders, inventory snapshots, quality records, and sales orders. They use business
codes as idempotency keys and contain synthetic data only. Fresh Compose
databases run both files automatically; for an existing volume, run the matching
file once with `psql` or `mysql`.

## Knowledge-base import

The original, publicly-referenced summaries in `docs/knowledge-base/` can be
imported into both demo organizations with:

```powershell
docker compose build api worker
docker compose up -d api worker
docker compose exec -T api python -m scripts.seed_demo_content
```

The importer is idempotent. With Embedding settings it completes ingestion and
stores vectors; without them it leaves tasks queued so no fake vectors are
written. The Compose API and worker mount the knowledge-base directory read-only.

## Verified public manufacturing data

The UCI SECOM importer downloads the official archive, validates its SHA-256,
and loads 1,567 real semiconductor-process observations into
`manufacturing_quality_events`. It is independent of the synthetic order
fixtures and can be rerun safely:

```powershell
docker compose exec -T api python -m scripts.import_uci_secom
```

## Verified public transaction data

The UCI Online Retail II importer downloads the official Excel archive and loads
more than one million real, anonymized retail transaction rows into
`retail_transactions`. It is a separate analysis table: retail customers,
countries, and stock codes are not misrepresented as the demo factory's
suppliers, factories, or work orders. Re-running it is idempotent by source-row
identifier.

```powershell
docker compose exec -T api python -m scripts.import_uci_online_retail
```
