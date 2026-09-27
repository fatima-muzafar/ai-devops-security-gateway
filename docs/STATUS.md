# Security Gateway FYP — Project Status

## Current Phase
Phase 6 — LangChain DevOps Agent + LLM Integration

## Completed
- Phase 1 — Project setup and repository structure
- Phase 2 — PostgreSQL schema, SQLAlchemy models, Alembic migrations
- Phase 3 — Stateful Mock DevOps Environment
- Phase 4 — MCP Server and Five DevOps Tools
- Phase 5 — Skeleton End-to-End Path (Single Tool, ALLOW/BLOCK Only, No ML)

## Current Repo State
- Last verified commit: `0c34b1a`
- Planning version: Revision 6
- Phase 1 through Phase 5 are complete.
- Database schema and migrations are implemented and verified (11 tables
  — unchanged since Phase 3; Phase 4/5 added no new tables).
- Seed data (4 users, 6 services) is implemented, idempotent, and
  verified against `docs/decisions.md` #8.
- Service state mutation (restart/rollback/deploy) and history logging
  are implemented in `backend/mock_devops_env/services/actions.py` and
  covered by unit tests.
- MCP server, tool registry, and the five tools are implemented in
  `backend/app/mcp/` and `backend/mock_devops_env/logs|metrics/`, and
  covered by `tests/test_mcp_tools.py` — 12 tests, all passing (user-
  verified).
- The Phase 5 HTTP skeleton (`backend/app/main.py`,
  `POST /api/gateway/tool-request`) is implemented and covered by
  `tests/test_gateway_tool_request.py` — 3 tests, all passing
  (user-verified against a running Postgres instance).
- `docs/decisions.md` has 15 entries (decisions #14–#15 added during
  Phase 5: the `arguments.service_name` request-contract key, and the
  tool-agnostic dispatch design of the Phase 5 endpoint).


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
  `backend/app/main.py` or FastAPI app existed yet. The HTTP surface was
  Phase 5's job (`docs/decisions.md` #11).
- Any authentication, identity, ownership, policy, rule risk, or ML —
  `execute_tool()` performs no security decision. Calling it directly
  means "this action is being treated as pre-authorized," valid only for
  Phase 4/5 testing (FR-15).
- The LangChain agent (Phase 6) and human approval workflow (Phase 11)
  — untouched.

## Phase 5 Summary (complete)
Per Section 27: "Skeleton end-to-end path: one tool, ALLOW/BLOCK only,
no ML." Purpose: prove the request → decision → MCP →
observable-state-change pipeline works end-to-end over HTTP, before
Phase 7 builds the real Security Gateway on top of it. A walking
skeleton, not a preview of the final Gateway — the decision rule below
was never meant to survive past this phase.

What was built:
- `backend/app/main.py` — first FastAPI app bootstrap for this repo.
  Route is defined directly on the `FastAPI()` app instance; no
  `app/api/` router module was introduced (deliberately deferred —
  see "Open items for Phase 6" below, not a locked decision).
- `POST /api/gateway/tool-request` (Section 17) — accepts a structured
  tool request (`request_id`, `user_id`, `agent_id`, `tool`,
  `arguments`), applies the Phase 5 placeholder decision rule, and on
  ALLOW calls `app.mcp.server.execute_tool()`.
- Placeholder decision rule: `BLOCK if environment == production else
  ALLOW`. Confirmed temporary — this is NOT Section 8's real policy
  engine and NOT ownership/role checking. Phase 8 replaces this rule
  entirely; it does not extend it.
- The endpoint is tool-agnostic (dispatches any tool name through
  `execute_tool()`, not hardcoded to `restart_service`), per
  `docs/decisions.md` #15. Only `restart_service` is exercised in
  tests, per this phase's original scope.
- Request contract: `arguments.service_name` (not Section 17's example
  key `arguments.service`), matching the schema actually implemented
  in Phase 4 (`mcp/schemas.py`, `ServiceTargetArgs`). Locked in
  `docs/decisions.md` #14.
- Tests (`tests/test_gateway_tool_request.py`) — 3 tests: staging
  restart ALLOWs and produces a `service_state_history` row; production
  restart BLOCKs and produces no row; an unregistered tool name returns
  HTTP 400 via `MCPError`, distinct from an ALLOW/BLOCK decision
  (`docs/decisions.md` #11).

**Verification method used:** per the corrected method below, success
was verified by asserting a new `service_state_history` row with
`change_type='restart'` and matching `service_id` — not by diffing
`service.status`, since a freshly created test service is already
`"healthy"` (Section 13 seed state) and a restart leaves `status`
unchanged either way.

What Phase 5 deliberately did NOT include (correctly deferred):
- The LangChain agent → Phase 6 (the endpoint was called directly via
  pytest/TestClient — no agent exists yet).
- Real identity, ownership, or environment-policy checks → Phase 8.
- Rule-based risk engine → Phase 9.
- ML / Isolation Forest → Phase 10, Semester 2.
- APPROVAL_REQUIRED / human approval workflow → Phase 11 (ALLOW/BLOCK
  only, per Section 27 — no third decision state yet).
- A dedicated `app/api/` router module — one endpoint does not justify
  the extra indirection yet (see "Open items for Phase 6").

## Open items for Phase 6
- Phase 6 introduces `POST /api/chat` (Section 17) alongside the
  existing `POST /api/gateway/tool-request` — this is the first point
  the repo has more than one HTTP route. Revisit then, driven by actual
  need, whether routes should move into `app/api/` router modules. This
  was explicitly left open at the end of Phase 5, not decided either
  way — do not treat it as settled in either direction.
- The Phase 5 placeholder decision rule must not be extended or reused
  by the Phase 6 agent integration. Phase 6 calls the existing endpoint
  as-is; it does not touch decision logic. Phase 8 owns replacing the
  rule.

## Important
- Follow Planning Revision 6.
- Follow `docs/decisions.md` for locked decisions (15 entries as of
  Phase 5 completion).
- Do not reorder, remove, or add phases.
- Do not redo completed Phase 1–5 work unless explicitly requested.

## Next Task
Start Phase 6: Python LangChain DevOps agent + LLM integration (Section
27, Section 6/7). The agent proposes structured tool requests and sends
them to the existing `POST /api/gateway/tool-request` endpoint — it
does not call `execute_tool()` or MCP directly (Section 5/6: the agent
never bypasses the Gateway). Confirm before starting: LLM
provider/model choice for this phase, and whether `.env` already has
the required API key configured.