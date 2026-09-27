# Security Gateway FYP — Project Status

## Current Phase
Phase 5 — Skeleton End-to-End Path (Single Tool, ALLOW/BLOCK Only, No ML)

## Completed
- Phase 1 — Project setup and repository structure
- Phase 2 — PostgreSQL schema, SQLAlchemy models, Alembic migrations
- Phase 3 — Stateful Mock DevOps Environment
- Phase 4 — MCP Server and Five DevOps Tools

## Current Repo State
- Last verified commit: `5708b97`
- Planning version: Revision 6
- Phase 1 through Phase 4 are complete.
- Database schema and migrations are implemented and verified (11 tables
  — unchanged since Phase 3; Phase 4 added no new tables, see
  `docs/decisions.md` #7).
- Seed data (4 users, 6 services) is implemented, idempotent, and
  verified against `docs/decisions.md` #8.
- Service state mutation (restart/rollback/deploy) and history logging
  are implemented in `backend/mock_devops_env/services/actions.py` and
  covered by unit tests.
- MCP server, tool registry, and the five tools are implemented in
  `backend/app/mcp/` and `backend/mock_devops_env/logs|metrics/`, and
  covered by `tests/test_mcp_tools.py` — 12 tests, all passing (user-
  verified).
- `docs/decisions.md` has 12 entries  ( since Phase 5 builds directly on the `execute_tool()` contract #11 documents).

## Verify First
Before trusting this file, `git log --oneline -5` and confirm the
latest commit matches "Last verified commit" above.

## Phase 4 Summary (complete)
What was built:
- `backend/app/mcp/schemas.py` — Pydantic argument schemas per tool
  (`TOOL_ARG_SCHEMAS`), also used to auto-generate `Tool.schema_def`.
- `backend/app/mcp/tools.py` — the five tool functions
  (`get_logs`, `get_metrics`, `restart_service`, `rollback_deployment`,
  `deploy_service`). The three state-changing tools wrap
  `mock_devops_env.services.actions` (Phase 3); the two read-only tools
  wrap the mock-environment log/metric generators (below).
- `backend/mock_devops_env/logs/generator.py` and
  `backend/mock_devops_env/metrics/generator.py` — simulated content for
  `get_logs()`/`get_metrics()`, deterministic per `(service.id,
  current_version)`. Placed under `mock_devops_env/` per Section 28's
  structure, not under `app/mcp/` — `docs/decisions.md` #12.
- `backend/app/mcp/registry.py` — `TOOL_REGISTRY` (dispatch map +
  sensitivity) and `seed_tools()`, an idempotent, update-in-place seeder
  for the `tools` table (`get_logs`/`get_metrics` = LOW,
  `restart_service` = MEDIUM, `rollback_deployment`/`deploy_service` =
  HIGH — `docs/decisions.md` #1).
- `backend/app/mcp/server.py` — `execute_tool()`, the single dispatch
  entrypoint: checks the tool is registered + enabled, validates
  arguments, resolves the target `Service`, calls the matching tool
  function. Plain importable Python — not an HTTP endpoint
  (`docs/decisions.md` #11).
- Unit tests (`tests/test_mcp_tools.py`) — 12 tests, all passing.

What Phase 4 deliberately did NOT include (correctly deferred):
- Any HTTP endpoint (`POST /mcp/tools/execute`, Section 17) — no
  `backend/app/main.py` or FastAPI app exists yet. The HTTP surface is
  Phase 5's job (`docs/decisions.md` #11).
- Any authentication, identity, ownership, policy, rule risk, or ML —
  `execute_tool()` performs no security decision. Calling it directly
  means "this action is being treated as pre-authorized," valid only for
  Phase 4 testing (FR-15).
- The LangChain agent (Phase 6) and human approval workflow (Phase 11)
  — untouched.

## Phase 5 Goal
Per Section 27: "Skeleton end-to-end path: one tool, ALLOW/BLOCK only,
no ML." Purpose: prove the request → decision → MCP →
observable-state-change pipeline works end-to-end over HTTP, before
Phase 7 builds the real Security Gateway on top of it. A walking
skeleton, not a preview of the final Gateway.

**Confirmed for this phase:**
- Tool: `restart_service` (Section 6's canonical worked example,
  Section 18 Scenario B, Section 9's baseline ALLOW case).
- Decision rule: `BLOCK if environment == production else ALLOW`.
  Explicitly a temporary placeholder — this is NOT Section 8's real
  policy engine, NOT ownership/role checking. That's Phase 8's job.
  Do not let this rule survive past Phase 5; Phase 8 replaces it
  entirely, it doesn't extend it.

Build:
- `backend/app/main.py` — first FastAPI app bootstrap for this repo.
- One HTTP endpoint (Section 17: `POST /api/gateway/tool-request`)
  accepting a structured tool request (Section 17's example payload:
  `request_id`, `user_id`, `tool`, `arguments`), applying the placeholder
  rule above, and on ALLOW calling `app.mcp.server.execute_tool()`.

**Verification method (corrected):** do NOT verify success by diffing
`service.status` before/after. A freshly seeded service is already
`"healthy"` (Section 13 seed state), so a restart on it leaves `status`
unchanged either way — a status diff proves nothing on a healthy
service. Verify instead by asserting a new `service_state_history` row
was created with `change_type='restart'` and matching `service_id`
(decisions.md #7) — that row's existence is what actually proves the
HTTP request reached MCP and executed, independent of whether the
restart happened to change any visible field.

## Phase 5 Boundary
Phase 5 is ONLY the minimal end-to-end HTTP skeleton for `restart_service`.

Do NOT implement yet:
- The LangChain agent → Phase 6 (the endpoint is called directly via
  pytest/curl/Postman — no agent exists yet).
- Real identity, ownership, or environment-policy checks → Phase 8.
- Rule-based risk engine → Phase 9.
- ML / Isolation Forest → Phase 10, Semester 2.
- APPROVAL_REQUIRED / human approval workflow → Phase 11 (ALLOW/BLOCK
  only, per Section 27 — no third decision state yet).
- HTTP wiring for the other four tools — `execute_tool()` already
  supports all five (Phase 4); only `restart_service` needs to be
  exercised through the new HTTP path to prove the skeleton works.

## Important
- Follow Planning Revision 6.
- Follow `docs/decisions.md` for locked decisions (12 entries as of
  Phase 4 completion).
- Do not reorder, remove, or add phases.
- Do not redo completed Phase 1–4 work unless explicitly requested.

## Next Task
Confirm the Phase 5 open question (tool = `restart_service`, placeholder
rule = BLOCK if environment == production else ALLOW — both already
confirmed), then start Phase 5 implementation: `main.py` bootstrap + one
HTTP endpoint + `execute_tool()` call + `service_state_history`-based
test verification.