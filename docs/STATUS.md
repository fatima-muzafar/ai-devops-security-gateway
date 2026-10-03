# Security Gateway FYP -- Project Status

## Current Phase
Phase 7 -- Phase 7 -- Stage 2 (MCP seam) COMPLETE; Stage 3 (Gateway pipeline) next. Decisions #31-#40 locked.

## Completed
- Phase 1 -- Project setup and repository structure
- Phase 2 -- PostgreSQL schema, SQLAlchemy models, Alembic migrations
- Phase 3 -- Stateful Mock DevOps Environment
- Phase 4 -- MCP Server and Five DevOps Tools
- Phase 5 -- Skeleton End-to-End Path (Single Tool, ALLOW/BLOCK Only, No ML)
- Phase 6 -- LangChain DevOps Agent + LLM Integration
- Phase 7 Stage 1 -- DB layer (migration a8d41c7e5b92, ExecutionStatus, AG001 seed)
- Phase 7 Stage 2 -- MCP seam (/mcp/tools/execute, McpClient, token auth)

## Current Repo State
- Last verified commit: `8a88180`
"Docs-only commits (no backend/ changes) do not require a hash update here --
this field tracks the last code-verified commit, not literal HEAD."

- Planning version: Revision 6
- Phase 1 through Phase 6 are complete.
- Database: "11 tables. Migration a8d41c7e5b92 applied (audit columns on security_requests, no  new table -- #32, #39)."
- Full suite: "55/55 passing after Phase 7 Stage 2 (user-verified)."
- `docs/decisions.md has 40 entries (#31-#40 are Phase 7).
- Real `GOOGLE_API_KEY` in git-ignored `backend/.env` (Gemini free tier, #16).

## Phase 7 Goal / Decisions Locked
Per Section 27 / Section 8: turn the Phase 5 skeleton endpoint into the real
Gateway pipeline: ordered stages, hard-check short-circuit, request-id rules,
audit persistence, and an internal MCP HTTP seam. Summary (reasoning in
`docs/decisions.md` #31-#38):
- #31 Boundary: Phase 7 = pipeline, validation, identity LOOKUP (username /
  agent_name, not authentication), audit, MCP seam. Phase 8 = JWT, role /
  ownership / environment policy. The Phase 5 production-BLOCK rule stays as a
  labelled placeholder stage (`gateway/policy.py`), reason text unchanged.
- #32 One Alembic migration on `security_requests`: 4 FKs nullable; add
  `raw_request` JSON, `reason` Text, `execution_status` (not_executed |
  executed | failed). `risk_assessments` untouched.
- #33 Seed agent `AG001`; tests need user + agent fixtures.
- #34 Validation failures are BLOCK decisions (HTTP 200 + reason, audited),
  not HTTP 400. 422 only for unparseable body; 409 for duplicate request_id;
  502 when ALLOWED execution fails. Old unknown-tool-400 test is replaced.
- #35 One audit INSERT with the final decision, committed BEFORE the MCP call;
  then UPDATE `execution_status`.
- #36 request_id max 32 chars; duplicate -> 409.
- #37 `POST /mcp/tools/execute`, `X-Internal-Token` vs env
  `MCP_INTERNAL_TOKEN` (fail closed), Gateway -> MCP over HTTP via `McpClient`.
  Corrects #11 (Phase 5 did not create this route).
- #38 Flat `backend/app/gateway/` modules; response contract unchanged.
- #40 get_mcp_client() exists, and that the Gateway must map both non-200 and McpUnavailableError to execution_status=failed plus HTTP 502.

## Next Task (implement in 3 stages; run pytest and commit after each)
1. DB layer: `ExecutionStatus` enum, `SecurityRequest` model changes, Alembic
   migration (revises the current head), seed AG001. Existing tests must
   still pass. (done)
2. MCP seam: `app/api/mcp.py` route + token check, `gateway/mcp_client.py`,
   conftest wiring (env token + dependency override), tests incl. the
   "direct MCP access without token is rejected" case.(done)
3. Gateway pipeline: `app/gateway/*`, thin `app/api/gateway.py`, audit rows,
   fixture/test updates (users + AG001, unknown-tool BLOCK, duplicate id 409,
   BLOCK audited with NULL FKs, ALLOW audited as executed).
Nothing beyond this: no JWT, no real policy, no risk, no ML, no approval.

## Phase 6 Summary (complete)
Python + LangChain agent on Gemini; proposes ONE structured tool request per
chat turn and submits it to `POST /api/gateway/tool-request` via an HTTP seam
(`agent/gateway_client.py`). Never imports MCP. Layout: `app/api/{gateway,chat}.py`
(router split, #25), `app/agent/` flat (#28), `main.py` pure bootstrap.
`request_id = uuid4().hex` (#27). BLOCK/HTTP-error text relayed verbatim (#23).
LLM failure after ALLOW -> HTTP 200 "executed, summary unavailable" (#27).
System prompt has no security rules on purpose (#30). 10 tests, LLM mocked
(#24). Smoke-tested against real Gemini: chit-chat, get_logs ALLOW, restart
staging ALLOW, restart production BLOCK all correct; one transient summary-call
failure then success on retry (cause unconfirmed, likely rate limit).
Agent reply text is not evidence; evaluation uses Gateway decisions and DB state.

## Phase 4 / 5 Summary (complete, condensed)
- Phase 4: `app/mcp/{schemas,tools,registry,server}.py`, `execute_tool()` is a
  plain Python dispatcher (#11), mock logs/metrics generators (#12). Sensitivity:
  get_logs/get_metrics LOW, restart MEDIUM, rollback/deploy HIGH (#1). No
  security logic inside `execute_tool()`.
- Phase 5: walking-skeleton Gateway endpoint, placeholder rule
  `BLOCK if production else ALLOW`, tool-agnostic (#15), contract uses
  `arguments.service_name` (#14). Verified by `service_state_history` rows.

## Open items
- Demo 8 (prompt injection) conflicts with #11 (no anomalous log content) and
  #27 (tool calls after a tool result are ignored). Resolve before Phase 16/17.
- `user_id` is spoofable; history is keyed by it (#19/#29). Phase 8 fixes
  identity; Phase 7 only adds lookup.
- Phase 8 needs the `policies` table seeded (it is empty today).

## Important
- Follow Planning Revision 6 and `docs/decisions.md` (38 entries).
- Do not reorder, remove, or add phases. Do not redo Phase 1-6 unless asked.
- Anything genuinely undecided mid-implementation gets a new decisions.md
  entry BEFORE code, not after.
