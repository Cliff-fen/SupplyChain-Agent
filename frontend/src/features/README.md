# Feature modules

Business screens are grouped by domain: identity, datasources, knowledge, analysis,
reports, dashboards, audit, and system. Each domain owns its views and local state
while shared API/SSE calls remain in `src/services`.

Each business domain also owns `pages`, `components`, `api`, `hooks`, `types`, and
tests. New functionality should stay inside the owning domain folder, with shared
transport code in `src/services` and shared UI in `src/components` or
`src/design-system`.
