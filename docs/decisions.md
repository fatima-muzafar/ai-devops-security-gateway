# Locked Project Decisions

## 1. Rollback Sensitivity
`rollback_deployment` sensitivity = HIGH.

Reason:
Section 11 treats production + irreversible/high-impact actions as the top tier.
Rollback mutates `current_version` similarly to `deploy_service`.

## 2. Database / Schema
- SQLAlchemy 2.0 style (`Mapped[]`, `mapped_column()`).
- One model file per table.
- 10 database tables are included, including `incidents`.
- `services.current_version` and `known_good_version` use Integer.
- `behavior_events.version_before` and `version_after` are historical snapshots.
- `security_requests.request_id` is a String(32) request identifier.

## 3. Policy / Ownership
- `policies` does NOT have a `service_id` foreign key.
- Policy checking and service ownership checking remain separate.

## 4. Enum Validation
Enum-like database fields use Python enums with database CHECK constraints.
Do not replace this with native PostgreSQL ENUMs unless explicitly decided.

## 5. Phase Boundaries
- Phase 3 = Stateful Mock DevOps Environment only.
- MCP tools = Phase 4.
- LangChain agent = Phase 6.
- Security Gateway = Phase 7+.
- ML = Semester 2.

## 6. Phase Order
Follow Planning Revision 6.
Do not add, remove, reorder, or skip phases without explicit approval.

## 7. Mock Environment State History
- The "10 tables" line in Decision #2 was a factual snapshot of Phase 2's
  output, not a ceiling on later phases. Phase 3 adds an 11th table:
  `service_state_history`.
- ONE unified table covers restart, rollback, and deploy transitions —
  do NOT create separate `deployment_history` / `restart_history` tables.
  A restart and a deploy are both "a state transition on a service at a
  point in time"; splitting them is needless duplication for an FYP.
- Schema: `service_state_history(id, service_id FK, change_type
  enum[deploy|restart|rollback], version_before, version_after
  [nullable — null for restart], status_before, status_after, timestamp)`.
- Follows Decision #4: Python enum + CHECK constraint, not native
  PostgreSQL ENUM.
- Only ALLOWED transitions produce a row. Per Section 5/11 of the
  planning doc, BLOCK means no MCP call and no state change, so a
  blocked request has nothing to record here.
- Distinct from `behavior_events` (Phase 10+): `service_state_history` is
  the mock environment's own state-transition log, keyed by service.
  `behavior_events` is the security/ML feature-extraction input, keyed by
  identity. Do not merge these or use one to derive the other.
- Migration: `c3f7a9d21b04_add_service_state_history.py`
  (revises `6b86e1e35917`).

## 8. Seed Data — Service Ownership Mapping
Section 13's planning doc lists two names per service in the "Seeded
owner example" column (e.g. `auth-service | senior_developer_1, admin`).
`services.owner_id` is a single, non-nullable FK — one owner per
`(service_name, environment)` row, not two owners of one row. Resolved
by splitting the two names across the staging/production rows for that
service, confirmed as final:

| Service | Staging owner | Production owner |
|---|---|---|
| auth-service | senior_developer_1 | admin |
| payment-service | senior_developer_2 | admin |
| notification-service | junior_developer_1 | senior_developer_1 |

Seed users required: `junior_developer_1`, `senior_developer_1`,
`senior_developer_2`, `admin` (4 users, matching Role enum values).
`hashed_password` is a placeholder string at seed time — real password
hashing is Phase 8 (Authentication), not Phase 3.

Seed script: `backend/app/database/seed.py`. Idempotent — safe to re-run,
does not duplicate or overwrite existing rows.

## 9. known_good_version Update Semantics
Section 12/13 of the planning doc never specifies what happens to
`known_good_version` after a deploy. Resolved and confirmed:

- `deploy_service()` sets `known_good_version = current_version`
  **before** applying the new `current_version` — i.e. known_good always
  becomes "the version being replaced," not the new version just
  deployed.
- `rollback_deployment()` sets `current_version = known_good_version`
  and does NOT itself change `known_good_version`.
- Net effect: `known_good_version` tracks "last known stable" one step
  behind, standard CI/CD semantics — rollback always reverts to whatever
  was running immediately before the most recent deploy, not to v1
  forever.
- Verified end-to-end on `payment-service`: seed (`1,1`) → deploy to
  version 2 (`current=2, known_good=1`) → rollback (`current=1,
  known_good=1`), with matching rows in `service_state_history`.

Implementation: `backend/mock_devops_env/services/actions.py`.

## 10. Testing vs. Research Evaluation — Not the Same Activity
Basic unit tests written per-phase as code is built; M8/Phase 17 remains
the dedicated research-evaluation phase (E1–E6) — these are not the same
activity.

## 11. MCP Server Scope (Phase 4)
- Phase 4's "MCP server" is an importable Python dispatcher
  (`execute_tool()` in `backend/app/mcp/server.py`), NOT an HTTP
  endpoint. Section 17's `POST /mcp/tools/execute` route is deferred —
  it requires a FastAPI app bootstrap (`backend/app/main.py`,
  `backend/app/api/`) that doesn't exist yet and isn't listed in
  STATUS.md's Phase 4 Goal. The HTTP surface lands in Phase 5, whose "skeleton end-to-end path: one tool, ALLOW/BLOCK only, no ML" is definitionally the first point an HTTP request needs to reach MCP. Phase 7 then adds the Gateway in front of that existing route — it does not create the route.
- `Tool.schema_def` is populated from each tool's Pydantic model via
  `.model_json_schema()`, not a hand-maintained dict, so the DB schema
  and the real validation logic cannot drift apart.
- `seed_tools()` differs from `seed.py`'s user/service seeding on
  purpose: it updates `sensitivity` in place on re-run (so tuning a
  tool's sensitivity in `registry.py` propagates to the DB without a
  migration), but never force-sets `enabled = True` on an existing row —
  an admin-disabled tool stays disabled across reseeds. This asymmetry
  from `seed.py`'s skip-only pattern is deliberate, not an inconsistency
  between the two scripts.
- MCP dispatch errors (`ToolNotFoundError`, `ServiceNotFoundError`, etc.)
  are a separate error taxonomy from Gateway ALLOW/BLOCK/APPROVAL_REQUIRED
  decisions — Section 11's decision engine isn't running code yet. "MCP
  couldn't dispatch the call" is not a security decision and must not be
  conflated with one once the Gateway exists.
- `get_logs()` / `get_metrics()` simulated content is deterministic from
  `(service.id, current_version)` — same version always returns the same
  simulated logs/metrics. Intentionally simple and final: no Section 10
  ML feature depends on log/metric *content*, only on request *patterns*
  (frequency, sequences, timing) captured later via `behavior_events`.
  Do not add anomalous-content generation here — if ML ever needs richer
  signal, it comes from behavioral features, not simulated log text.

  ## 12. mock_devops_env/logs and /metrics — File Naming
Section 28 names the `logs/` and `metrics/` folders under
`mock_devops_env/` but not the file inside each. Resolved: one file per
folder, named `generator.py` (parallel to `services/actions.py`) —
`mock_devops_env/logs/generator.py::generate_logs()` and
`mock_devops_env/metrics/generator.py::generate_metrics()`. `app/mcp/tools.py`
imports both qualified (`env_logs`, `env_metrics`), same pattern as
`env_actions` for the three state-changing tools.

## 13. mock_devops_env/state — Not Used, Superseded
Section 28's repository structure lists `mock_devops_env/state/` as a
folder, but no phase (Section 27) ever assigns work to it, and no
decisions.md entry ever referenced it. Resolved: this folder is not
needed. State tracking is fully handled by two things already built in
Phase 3: (1) current state lives directly on the `Service` model
(`current_version`, `known_good_version`, `status`), and (2) state
transition history lives in the unified `service_state_history` table
(decisions.md #7). A separate `state/` module would duplicate one of
these with no clear ownership boundary. Folder removed as of Phase 4
cleanup; do not recreate it unless a future phase has a concrete,
distinct reason to.

## 14. Gateway HTTP Request Contract — Argument Key Naming
Section 17's worked example uses `"service"` as the arguments key
(`{"service": "payment-service", "environment": "production"}`), but
the schema actually implemented in Phase 4 (`mcp/schemas.py`,
`ServiceTargetArgs`) uses `service_name`. This was never reconciled in
the planning doc.

Resolved: `POST /api/gateway/tool-request`'s `arguments` object uses
`service_name`, matching the implemented schema — not Section 17's
example key. `execute_tool()` requires `service_name` to resolve the
target `Service`; the doc's example predates the actual schema and is
superseded by it.

This is now the locked request contract. Phase 6 (LangChain agent
generating structured tool requests) and Phase 7 (real Security
Gateway) must produce/consume `arguments.service_name`, not
`arguments.service`.

Implementation: `backend/app/main.py`, `ToolRequestIn`.

## 15. Gateway HTTP Endpoint — Tool-Agnostic by Design
Phase 5's endpoint dispatches through `execute_tool()` generically
(any registered tool name), rather than being hardcoded to accept only
`restart_service`. This extends decision #11's existing design intent
(`execute_tool()` already supports all five tools) up to the HTTP
layer, rather than adding a redundant tool-name check that duplicates
what the tool registry already enforces.

STATUS.md's Phase 5 scope ("only restart_service needs to be exercised
through the new HTTP path") governs *test coverage*, not what the
endpoint accepts — an unregistered/disabled tool is already correctly
rejected via `MCPError` → HTTP 400 (decisions.md #11's error
taxonomy), independent of this endpoint.