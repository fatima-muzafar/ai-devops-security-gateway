# Security Gateway FYP -- Project Status

## Current Phase
Current Phase: Phase 8 COMPLETE -- Authentication, identity, policy, ownership, environment.
Next: Phase 9 (rule-based risk engine). Decisions #1-#52 locked.

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
- Phase 8 -- Authentication, Identity, Policy, Ownership, Environment
  - Stage 1 -- gateway/auth.py (argon2 + PyJWT), POST /api/auth/login, seed password
    upgrade, policies seeded (25 rows, #46/#50), no migration
  - Stage 2 -- bearer-token identity at chat and the Gateway (identity.py rewritten,
    api/deps.py, token forwarded by the agent); auth failures are audited BLOCKs
    (#44, #45, #51)
  - Stage 3 -- gateway/ownership.py, gateway/policy.py (placeholder removed), pipeline
    order, matrix + ownership tests (#52)

## Current Repo State
- Last verified commit: `2b73f92`
"Docs-only commits (no backend/ changes) do not require a hash update here --
this field tracks the last code-verified commit, not literal HEAD."

- Planning version: Revision 6
- Phase 1 through Phase 8 are complete.
- Database: "11 tables. Migration a8d41c7e5b92 applied (audit columns on security_requests,
  no new table -- #32, #39). Phase 8 added no migration; `policies` already had
  `requires_approval` (#50)."
- Full suite: "180/180 passing after Phase 8 (user-verified)."
- `docs/decisions.md` has 52 entries (#1-#52; #42-#52 are Phase 8).
- Real `GOOGLE_API_KEY`, `MCP_INTERNAL_TOKEN`, `JWT_SECRET` and `SEED_USER_PASSWORD` live in
  git-ignored `backend/.env` (Gemini free tier #16; MCP token #37/#40; JWT #42; seed #43).
- Phase 8 smoke (real Gemini, real uvicorn): login, chat allow, Policy BLOCK, Ownership
  BLOCK, approval-bound BLOCK (user-verified).

## INTERIM STATE (Phase 8 -> Phase 11) -- read before trusting any result
Until rule risk (Phase 9) is consumed by the decision engine (Phase 11), senior_developer and
admin production restart and rollback on rows they own are ALLOW (mock state only). Do not
read Phase 8-10 results for those cases as final (#48). Concretely: admin owns auth-service
and payment-service production; senior_developer_1 owns notification-service production.
Production deploy is NOT affected: it is an approval-bound fail-closed BLOCK (#48).

## Phase 8 Summary (complete)
Pipeline order (evaluate() is read-only and short-circuits on the first failing stage):
Authentication -> Agent identification -> Tool registry -> Arguments -> Service ->
Ownership -> Policy. Every BLOCK reason names its stage (#34, #41, #45).
- Authentication: PyJWT HS256 pinned, `JWT_SECRET` read at request time (unset, <32 chars or
  "changeme" fails closed); 60-minute tokens, no role claim, no refresh; argon2 passwords;
  `POST /api/auth/login` with one generic 401 (#42, #43). Seed passwords come from
  `SEED_USER_PASSWORD`; valid argon2 hashes are never overwritten.
- Identity: `/api/chat` requires a bearer token (401/503); the agent forwards it to the
  Gateway; the Gateway verifies it itself. The body `user_id` is only a claim and must equal
  the token subject. Role is always read from `users` (#44, #51).
- Auth failures at the Gateway are audited BLOCK decisions (HTTP 200), not 401 (#45). On a
  valid token with a mismatched claim the audit FK records the AUTHENTICATED user.
- Ownership: `services.owner_id == authenticated user.id` for the specific
  (service, environment) row, all five tools, admin does NOT bypass (#47, #52).
- Policy: 25 permit rows (junior 5, senior 10, admin 10), default-deny, only production
  deploy carries `requires_approval`; the approval-bound case is a fail-closed BLOCK until
  Phase 11 (#46, #48, #50). `seed_policies` reconciles the table to the matrix.
- Response contract unchanged (BLOCK -> {request_id, decision, reason}; ALLOW ->
  {request_id, decision, result}); no `risk_level` field yet (#38).
- Tests: autouse JWT and MCP seams, session-scoped `seed_policies`, `make_user`,
  `auth_headers`; full 3x5x2 matrix against throwaway services (#49, #52). Tests share the
  dev DB (#41), so seeds used by tests must stay convergent.
- Demo 3 consequence (#45): no junior owns a production row, so "junior deploys to
  production" blocks at Ownership. Use junior_developer_1 + deploy_service +
  notification-service STAGING to show a Policy-stage block.
- Known limitations (state in report): no brute-force protection or lockout; no token
  revocation (`users` has no status column, bounded by expiry); the agent holds the user's
  token, so a compromised agent acts as that user within that user's permissions;
  `agent_id` is identified, not authenticated; unauthenticated callers can write BLOCK audit
  rows and occupy request_ids (no rate limiting, no cleanup); one shared dev password for
  the four seeded users; the MCP trust boundary is logical, not a network boundary (#37).

## Phase 7 Summary (complete; stages superseded by Phase 8 are marked)
The Phase 5 skeleton endpoint became the real Gateway pipeline.
`POST /api/gateway/tool-request` (sync `def`, thin) -> `gateway/pipeline.py`:
- `evaluate()` is read-only. Phase 7 order was identity lookup -> tool registry ->
  arguments -> service -> placeholder policy. SUPERSEDED in Phase 8: the identity stage is
  now real authentication and the placeholder production rule is gone (see above).
- `handle_tool_request()` writes exactly ONE `security_requests` row and COMMITS it BEFORE
  any MCP call (#35). Unresolved FKs are NULL; `raw_request` keeps the submitted payload.
  Duplicate request_id -> 409, original row untouched (#36). request_id max 32 chars -> 422.
- ALLOW only: the Gateway calls MCP over HTTP via `McpClient` (injected through
  `get_mcp_client`) at `POST /mcp/tools/execute`, protected by `X-Internal-Token` vs
  `MCP_INTERNAL_TOKEN` (fail closed, generic 403). Then `execution_status` -> executed.
  Non-200 or `McpUnavailableError` -> `execution_status=failed` + HTTP 502 (never a 200 ALLOW).
- Known limitations (#41): a timeout after MCP already ran is recorded as `failed`; other
  unexpected exceptions leave the row `not_executed` (500).

## Phase 6 Summary (complete)
Python + LangChain agent on Gemini; proposes ONE structured tool request per chat turn and
submits it to `POST /api/gateway/tool-request` via an HTTP seam (`agent/gateway_client.py`).
Never imports MCP. Layout: `app/api/{gateway,chat}.py` (router split, #25), `app/agent/` flat
(#28), `main.py` pure bootstrap. `request_id = uuid4().hex` (#27). BLOCK/HTTP-error text
relayed verbatim (#23). LLM failure after ALLOW -> HTTP 200 "executed, summary unavailable"
(#27). System prompt has no security rules on purpose (#30). LLM mocked in tests (#24).
Phase 8: the agent now receives and forwards the caller's bearer token; history is keyed by
the authenticated username (#44).
Agent reply text is not evidence; evaluation uses Gateway decisions and DB state.

## Phase 4 / 5 Summary (complete, condensed)
- Phase 4: `app/mcp/{schemas,tools,registry,server}.py`, `execute_tool()` is a plain Python
  dispatcher (#11), mock logs/metrics generators (#12). Sensitivity: get_logs/get_metrics
  LOW, restart MEDIUM, rollback/deploy HIGH (#1). No security logic inside `execute_tool()`.
- Phase 5: walking-skeleton Gateway endpoint, tool-agnostic (#15), contract uses
  `arguments.service_name` (#14). Its placeholder rule (`BLOCK if production`) was removed
  in Phase 8.

## Open items
- Demo 8 (prompt injection) conflicts with #11 (no anomalous log content) and #27 (tool
  calls after a tool result are ignored). Resolve before Phase 16/17.
- The interim production ALLOW (above) closes in Phase 11, when the decision mapping
  consumes rule_risk_level. Phase 9 only COMPUTES and records risk.
- Decide in Phase 9 Step 0: whether the response gains a `risk_level` field (#38 says none
  until Phase 9; the Phase 6 agent depends on the current contract), and where the
  "repeated denied requests" rule reads history from before `behavior_events` exists
  (Phase 10).
- Full suite took ~84 s after Phase 8 Stage 2 (was ~8 s). Likely argon2 hashing in tests;
  not diagnosed. Optional: `pytest tests -q --durations=8`.

## Next Task -- Phase 9
Rule-based risk engine (Section 10, Section 11 Step 2): fixed `rule_risk_level`
{LOW, MEDIUM, HIGH} per condition (production targeting, sensitive tool, repeated denials,
approval-required operations), max of simultaneous conditions; the enumerated
rule-catchable sequence list (deploy then rollback on one service, N consecutive denials
then a success, identical destructive action repeated within a window); `risk_assessments`
writes. Phase 9 does NOT add APPROVAL_REQUIRED, ML or `behavior_events`. Before coding:
read Planning Sections 10, 11 (Steps 2-4), 16 (`risk_assessments`) and decisions #1, #38,
#46, #48; resolve the open items above; write new decisions.md entries BEFORE code.

## Important
- Follow Planning Revision 6 and `docs/decisions.md` (52 entries).
- Do not reorder, remove, or add phases. Do not redo Phase 1-8 unless asked.
- Anything genuinely undecided mid-implementation gets a new decisions.md
  entry BEFORE code, not after.