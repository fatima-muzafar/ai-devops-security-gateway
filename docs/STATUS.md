# Security Gateway FYP -- Project Status

## Current Phase
Phase 7 COMPLETE (Stages 1-3). Next: Phase 8 -- Authentication, identity,
policy, ownership, environment checks. Decisions #1-#41 locked.

## Completed
- Phase 1 -- Project setup and repository structure
- Phase 2 -- PostgreSQL schema, SQLAlchemy models, Alembic migrations
- Phase 3 -- Stateful Mock DevOps Environment
- Phase 4 -- MCP Server and Five DevOps Tools
- Phase 5 -- Skeleton End-to-End Path (Single Tool, ALLOW/BLOCK Only, No ML)
- Phase 6 -- LangChain DevOps Agent + LLM Integration
- Phase 7 -- Full Security Gateway and Request IDs
  - Stage 1 -- DB layer (migration a8d41c7e5b92, ExecutionStatus, AG001 seed)
  - Stage 2 -- MCP seam (/mcp/tools/execute, McpClient, token auth)
  - Stage 3 -- Gateway pipeline (gateway/{identity,validation,policy,audit,pipeline}.py,
    thin api/gateway.py, audit rows, conftest/test updates)

## Current Repo State
- Last verified commit: `017dd86`
"Docs-only commits (no backend/ changes) do not require a hash update here --
this field tracks the last code-verified commit, not literal HEAD."

- Planning version: Revision 6
- Phase 1 through Phase 7 are complete.
- Database: "11 tables. Migration a8d41c7e5b92 applied (audit columns on security_requests, no new table -- #32, #39)."
- Full suite: "76/76 passing after Phase 7 (user-verified)."
- `docs/decisions.md` has 41 entries (#31-#41 are Phase 7).
- Real `GOOGLE_API_KEY` and `MCP_INTERNAL_TOKEN` in git-ignored `backend/.env`
  (Gemini free tier, #16; MCP token, #37/#40).
- Manual smoke test (real Gemini, real uvicorn): chit-chat, get_logs staging
  ALLOW, restart staging ALLOW, restart production BLOCK, all correct;
  audit rows in `security_requests` match (user-verified).

## Phase 7 Summary (complete)
The Phase 5 skeleton endpoint is now the real Gateway pipeline.
`POST /api/gateway/tool-request` (sync `def`, thin) -> `gateway/pipeline.py`:
- `evaluate()` is read-only and short-circuits on the first failing stage:
  identity (user by username, agent by agent_name with status "active",
  missing agent_id -> BLOCK) -> tool registry (registered, enabled) ->
  arguments (service_name + environment present, valid Environment, tool
  schema, reserved keys) -> service resolves -> placeholder policy
  (`gateway/policy.py`: BLOCK if production, Phase 5 reason text unchanged).
  Every BLOCK reason names its stage (#34, #41).
- `handle_tool_request()` writes exactly ONE `security_requests` row and
  COMMITS it BEFORE any MCP call (#35). Unresolved FKs are NULL; `raw_request`
  keeps the submitted payload. Duplicate request_id -> 409, original row
  untouched (#36). request_id max 32 chars -> 422 above that.
- ALLOW only: Gateway calls MCP over HTTP via `McpClient` (injected through
  `get_mcp_client`) at `POST /mcp/tools/execute`, protected by
  `X-Internal-Token` vs `MCP_INTERNAL_TOKEN` (fail closed, generic 403).
  Then `execution_status` -> executed. Non-200 or `McpUnavailableError` ->
  `execution_status=failed` + HTTP 502 `detail` (never a 200 ALLOW).
- Response contract unchanged: BLOCK -> {request_id, decision, reason};
  ALLOW -> {request_id, decision, result} (same nesting as Phase 5).
  No `risk_level` field until Phase 9.
- Tests: autouse conftest MCP seam (random token + `get_mcp_client` override),
  `ag001_agent` (get-or-create), `test_service_production`; test_service
  teardown deletes audit rows before deleting its user/services. Phase 5/6
  tests were changed on purpose (agent_id required, production tests need a
  production row, unknown tool is a BLOCK, missing argument is a BLOCK not an
  HTTP 422, replayed request_id is a 409). Chat tests: 11.
- Known limitations (#41): a timeout after MCP already ran is recorded as
  `failed`; other unexpected exceptions leave the row `not_executed` (500).
  Both routes share one FastAPI process, so the MCP trust boundary is logical
  (token-protected route), not a network boundary (#37).
- NOT in Phase 7 (still deferred): JWT/passwords, role/ownership/environment
  policy and the `policies` table (Phase 8); rule risk and `risk_assessments`
  writes (Phase 9); `behavior_events` (Phase 10); ML (Semester 2);
  approval / TOCTOU / APPROVAL_REQUIRED (Phase 11).

## Next Task -- Phase 8
Authentication (JWT, real password hashing replacing the seed placeholder),
role / service-ownership / environment policy, seed the `policies` table.
Phase 8 REPLACES `gateway/policy.py` (placeholder production rule) and
`gateway/identity.py` (username/agent_name lookup, not authentication); it does
not extend them. Before coding: read Planning Section 9 and decisions #3, #8,
#19, #29, #31; write new decisions.md entries BEFORE code.

## Phase 6 Summary (complete)
Python + LangChain agent on Gemini; proposes ONE structured tool request per
chat turn and submits it to `POST /api/gateway/tool-request` via an HTTP seam
(`agent/gateway_client.py`). Never imports MCP. Layout: `app/api/{gateway,chat}.py`
(router split, #25), `app/agent/` flat (#28), `main.py` pure bootstrap.
`request_id = uuid4().hex` (#27). BLOCK/HTTP-error text relayed verbatim (#23).
LLM failure after ALLOW -> HTTP 200 "executed, summary unavailable" (#27).
System prompt has no security rules on purpose (#30). LLM mocked in tests (#24).
Smoke-tested against real Gemini; one transient summary-call failure then
success on retry (cause unconfirmed, likely rate limit).
Agent reply text is not evidence; evaluation uses Gateway decisions and DB state.

## Phase 4 / 5 Summary (complete, condensed)
- Phase 4: `app/mcp/{schemas,tools,registry,server}.py`, `execute_tool()` is a
  plain Python dispatcher (#11), mock logs/metrics generators (#12). Sensitivity:
  get_logs/get_metrics LOW, restart MEDIUM, rollback/deploy HIGH (#1). No
  security logic inside `execute_tool()`.
- Phase 5: walking-skeleton Gateway endpoint, placeholder rule
  `BLOCK if production else ALLOW`, tool-agnostic (#15), contract uses
  `arguments.service_name` (#14). Verified by `service_state_history` rows.
  Superseded by Phase 7's pipeline; the production rule survives only as the
  labelled placeholder in `gateway/policy.py`.

## Open items
- Demo 8 (prompt injection) conflicts with #11 (no anomalous log content) and
  #27 (tool calls after a tool result are ignored). Resolve before Phase 16/17.
- `user_id` is spoofable; history is keyed by it (#19/#29). Phase 8 fixes
  identity; Phase 7 only added lookup.
- Phase 8 needs the `policies` table seeded (it is empty today).
- Phase 6 agent behaviour on a Gateway HTTP 502 (MCP failure) or 409
  (duplicate id) is not covered by an automated test; only the 422 relay path
  is. Check `agent/devops_agent.py` handling before relying on it.

## Important
- Follow Planning Revision 6 and `docs/decisions.md` (41 entries).
- Do not reorder, remove, or add phases. Do not redo Phase 1-7 unless asked.
- Anything genuinely undecided mid-implementation gets a new decisions.md
  entry BEFORE code, not after.