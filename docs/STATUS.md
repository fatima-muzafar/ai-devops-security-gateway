# Security Gateway FYP — Project Status

## Current Phase
Phase 6 — LangChain DevOps Agent + LLM Integration (planning locked,
implementation not yet started)

## Completed
- Phase 1 — Project setup and repository structure
- Phase 2 — PostgreSQL schema, SQLAlchemy models, Alembic migrations
- Phase 3 — Stateful Mock DevOps Environment
- Phase 4 — MCP Server and Five DevOps Tools
- Phase 5 — Skeleton End-to-End Path (Single Tool, ALLOW/BLOCK Only, No ML)

## Current Repo State
- Last verified commit: `a2cccae`
"Docs-only commits (no backend/ changes) do not require a hash update here — this field tracks the last code-verified commit, not literal HEAD."

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
- Full suite re-verified after Phase 5: 26/26 tests passing (user-
  verified), confirming no regression against Phase 1–4 work.
- `backend/.env` now has a real `GOOGLE_API_KEY` (Google AI Studio free
  tier, `docs/decisions.md` #16). `.env` remains git-ignored;
  `.env.example` carries only the placeholder `GOOGLE_API_KEY=changeme`.
- `docs/decisions.md` has 23 entries (decisions #16–#23 added during
  Phase 6 planning — see "Phase 6 Goal / Decisions Locked" below).
  **No Phase 6 code has been written yet** — these are pre-implementation
  decisions only, following the same decisions.md-before-code sequence
  used in Phase 5 (#14/#15 landed before `main.py`).

## Phase 6 Goal / Decisions Locked
Per Section 27 / Section 6-7: build the Python + LangChain DevOps agent,
backed by an LLM, that understands developer natural-language requests
and proposes structured tool requests to the *existing*
`POST /api/gateway/tool-request` endpoint (Phase 5) — the agent never
calls `execute_tool()` or MCP directly (Section 5/6).

The following were decided before any implementation, to avoid the kind
of rework a mid-phase design change would cause. Full reasoning for each
is in `docs/decisions.md` #16–#23; summarized here:

- **#16 — LLM provider:** Gemini, free tier via Google AI Studio.
  Rate-limited but zero-cost; acceptable for Phase 6 scope.
- **#17 — Tool exposure:** agent gets structured-request schemas for all
  five MCP tools (sourced from `mcp/schemas.py`), but Phase 6 *testing*
  only exercises `restart_service` and `get_logs`.
- **#18 — `POST /api/chat`:** built in Phase 6, as the agent's HTTP entry
  point (Section 17).
- **#19 — Identity placeholders:** `user_id` is a plain, unvalidated
  field in the `/api/chat` request body; `agent_id` is a hardcoded
  constant (`"AG001"`) in agent code. No real auth (Phase 8's job).
- **#20 — `request_id` generation:** owned by the `/api/chat` endpoint
  (UUID per HTTP request), not by the agent.
- **#21 — Conversation history:** in-memory only for this phase. No new
  DB table — explicitly considered and rejected; behavioral/ML history
  belongs to `behavior_events` (Phase 10, Section 16), not a chat-log
  table. Not a Section 16 table, so adding one now would be scope
  creep.
- **#22 — Agent design pattern:** LangChain structured tool-calling
  (`bind_tools`) against Gemini's native function-calling. No custom
  prompt-parsing.
- **#23 — Gateway decision relay:** on BLOCK or other non-ALLOW
  responses, the agent relays the Gateway's own `reason` field verbatim
  in natural language — it does not generate its own independent
  explanation.

**Still open, not decided by the above:** whether `/api/chat` and
`/api/gateway/tool-request` move into an `app/api/` router module. Left
open at the end of Phase 5 specifically to be revisited once a second
route existed (see "Open items for Phase 6" below) — this note records
that the trigger condition has now arrived, not that the question has
been resolved either way.

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
- Whether `/api/chat` and `/api/gateway/tool-request` move into an
  `app/api/` router module. Two HTTP routes now exist (as of this
  planning pass, before `/api/chat` is even implemented), which was the
  stated trigger to revisit this — but revisiting is not the same as
  deciding. Decide this when actually wiring `/api/chat`, not before.
- The Phase 5 placeholder decision rule must not be extended or reused
  by the Phase 6 agent integration. Phase 6 calls the existing endpoint
  as-is; it does not touch decision logic. Phase 8 owns replacing the
  rule.

## Important
- Follow Planning Revision 6.
- Follow `docs/decisions.md` for locked decisions (23 entries as of
  Phase 6 planning).
- Do not reorder, remove, or add phases.
- Do not redo completed Phase 1–5 work unless explicitly requested.
- Phase 6 decisions (#16–#23) are locked ahead of code, same discipline
  as Phase 5's #14/#15 — do not relitigate them mid-implementation
  without a genuinely new reason.

Implement Phase 6: backend/app/main.py additions / app/agent/ module
(LangChain agent + Gemini integration), POST /api/chat endpoint, tests
covering restart_service and get_logs proposals end-to-end through the
existing Gateway skeleton (LLM responses mocked in tests per
decisions.md #24 — no real Gemini API calls in the automated suite).
Decisions #16–#24 govern the design; no further design discussion
needed before starting — implementation can begin.