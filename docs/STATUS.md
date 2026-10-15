# Security Gateway FYP -- Project Status

## Current Phase
Current Phase: Phase 10 COMPLETE -- behavior-event logging (live hook) + synthetic NORMAL-behavior
generator. No ML, no enforcement change.
Next: Phase 11 (human approval workflow, TOCTOU revalidation, Section 11 decision mapping end to end).
Decisions #1-#77 locked.

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
- Phase 9 -- Rule-Based Risk Engine
  - Step 0 -- decisions #53-#61 (levels, window key, history source, denials, write order,
    ML stub, response contract, E2/Demo 7 wording)
  - Stage 1 -- gateway/risk.py + risk_constants.py: pure, read-only `assess_risk()`; #62
  - Stage 2 -- pipeline wiring: Verdict.risk, audit writes security_requests + risk_assessments
    in ONE commit before MCP; tests/qa_cleanup.py; #63
  - Stage 3 -- close-out: real-Gemini smoke verified by DB query; this file
- Phase 10 -- Behavior-Event Logging and Synthetic Generation
  - Step 0 -- decisions #64-#75 (scope, source marker, per-action record, off-hours, version
    delta, which requests are logged, live write, generator path, identities, spacing,
    timestamps/volume, migration)
  - Stage 1 -- migration d5b2f8a1c7e3 (source, request_id FK, 'failed'); app/database/behavior.py
    (is_off_hours + add_behavior_event); ml/data/generator.py; #76
  - Stage 2 -- gateway/behavior_log.py live hook (fail-open, own commit), pipeline wiring,
    qa_cleanup.delete_requests() deletes live events; #77
  - Stage 3 -- close-out: generator run on the dev DB + real-Gemini smoke verified by DB query;
    this file

## Current Repo State
- Last verified commit: `86fc7ad`
"Docs-only commits (no backend/ changes) do not require a hash update here --
this field tracks the last code-verified commit, not literal HEAD."

- Planning version: Revision 6
- Phase 1 through Phase 10 are complete.
- Database: "11 tables. Migration d5b2f8a1c7e3 is the head (Phase 10: behavior_events gains
  `source` + CHECK, nullable `request_id` FK to security_requests, and 'failed' in the outcome
  CHECK -- #65, #66, #75). Before it: a8d41c7e5b92 (audit columns on security_requests, #32, #39).
  Phases 8 and 9 added no migration."
- Full suite: "327/327 passing after Phase 10 (user-verified): 261 (Phase 1-9) + 27 (writer/schema) + 18 (generator) + 21 (live hook)."
- `docs/decisions.md` has 77 entries (#1-#77; #64-#77 are Phase 10).
- Real `GOOGLE_API_KEY`, `MCP_INTERNAL_TOKEN`, `JWT_SECRET` and `SEED_USER_PASSWORD` live in
  git-ignored `backend/.env` (Gemini free tier #16; MCP token #37/#40; JWT #42; seed #43).
- Phase 8 smoke (real Gemini, real uvicorn): login, chat allow, Policy BLOCK, Ownership
  BLOCK, approval-bound BLOCK (user-verified).
- Phase 9 smoke (real Gemini, real uvicorn): staging restart LOW, production restart MEDIUM +
  interim marker (ALLOW), production deploy BLOCK with no risk row (user-verified).
- Phase 10 smoke (user-verified, real Gemini + real uvicorn, checked by DB query): generator on
  the dev DB (`--seed 42 --anchor 2026-10-11T00:00:00+00:00 --days 30`) inserted 1844 synthetic
  rows, re-run purged and re-inserted the same count, all invariant checks 0, minimum gap between
  non-read events above the 10-minute window. Live: 7 events for 7 loggable requests (owned
  staging read, restart, deploy 1->2, rollback 2->1 = allowed; Ownership BLOCK, Policy BLOCK,
  approval-bound production-deploy BLOCK = blocked); versions only on deploy/rollback and equal to
  service_state_history; the no-token Gateway call was audited but NOT logged; loggable requests =
  live events; synthetic total unchanged; the stored off_hours_flag agreed with an independent
  SQL re-computation of the UTC+5 rule (all smoke rows were off-hours: the in-hours live branch
  is covered by unit tests and the synthetic rows only).

## INTERIM STATE (Phase 9 -> Phase 11) -- read before trusting any result
Risk is COMPUTED AND RECORDED, NOT ENFORCED until Phase 11. Every request that passes the Step 1
stages gets a `risk_assessments` row, but the decision is still ALLOW for any final level
(#58). Concretely: senior_developer and admin production restart and rollback on rows they own
are ALLOW with final MEDIUM/HIGH and the marker "interim: not enforced" in `reasons`. Admin
owns auth-service and payment-service production; senior_developer_1 owns
notification-service production. Production deploy is NOT affected: it is an approval-bound
fail-closed BLOCK (#48) and gets NO risk row (it stops at Policy, before risk).
- Exclude "interim: not enforced" rows from E5 and Approval Routing Accuracy, or regenerate
  them after Phase 11 (#58). Rows before Phase 14 carry "ml=stub" and are excluded from E2 (#59).
- Phase 10 addition (#69): until Phase 11, an approval-bound production-deploy BLOCK is logged in
  behavior_events as outcome=blocked (Phase 11 remaps it to pending). Live rows of that kind
  written before Phase 11 are not training data. `pending` exists in the CHECK but is unused.
- Do not read Phase 9-10 results for production state changes as final.

## Phase 10 Summary (complete)
Two writers, ONE write path: `app.database.behavior.add_behavior_event()` (no flush/commit) is
used by the live hook and the generator, so the stored `off_hours_flag` and the NULL-version rules
cannot drift. It requires a timezone-aware timestamp and raises on versions for anything other
than an ALLOWED deploy_service/rollback_deployment (#66, #76). `is_off_hours(ts)`: fixed UTC+5,
09:00 <= t < 18:00, all seven days; constants FROZEN before Phase 16 (#67).
- Schema (#65, #66, #75): `source` {live, synthetic} NOT NULL default 'live' + CHECK;
  `request_id` String(32) nullable FK -> security_requests (NULL for synthetic); outcome CHECK is
  {allowed, blocked, pending, failed}. Downgrade deletes 'failed' rows first. No index yet.
  The N = 5 window is a QUERY (last 5 rows per identity_id by (timestamp, id)); no window column;
  `version_change_delta` and the window are derived, nothing derived is stored (#66, #68).
- Live hook (`gateway/behavior_log.py`, #69, #70, #77): logged iff user, agent, tool, service and
  environment all resolved (= ALLOW executed/failed, plus Ownership/Policy BLOCKs). ALLOW executed
  -> allowed; ALLOW + MCP failure -> failed (written before the 502); BLOCK -> blocked. NOT logged:
  Authentication, mismatched-claim, Agent/Tool/Arguments/Service BLOCKs, 409, 422, unexpected 500.
  Written AFTER the audit commit and after MCP, in its OWN commit, FAIL-OPEN (rollback + warning,
  response unchanged). Versions are copied from `result["result"]` for an executed deploy/rollback
  only (both ints, else NULL + warning). Event timestamp = pipeline start. ~2 ms median locally.
- Generator (`ml/data/generator.py`, #64, #71-#74): NORMAL behavior only, on demand, deterministic
  (`--seed`, required `--anchor`, `--days`; per-identity RNG). Direct inserts, source='synthetic',
  agent AG001. Seeded users act only on rows they own with tools the matrix permits without
  approval; no production deploy; normal deploy = current+1; rollback only when current >
  known_good; ~3% off-hours reads, never off-hours state changes. Every non-read event comes from
  one schedule spaced by MORE than the largest Phase 9 window (imported from risk_constants).
  A re-run purges only the generated identities' synthetic rows; live rows are never touched.
- Tests: `tests/test_behavior_events.py` (27), `tests/test_behavior_generator.py` (18),
  `tests/test_behavior_live_hook.py` (21). `tests/qa_cleanup.py::delete_requests()` now deletes
  live events first (request_id subquery); `delete_behavior_events()` removes synthetic rows. A
  generator test fixture must depend on `make_user` so it tears down before the users are deleted.
  Mutation checks (16 + a migration downgrade for Stage 1, 12 for Stage 2) were all caught; the
  scripts are not part of the repo.
- Known limitations (state in report): the normal profile numbers are mine and UNCALIBRATED, so
  synthetic precision/recall are optimistic (Section 23); only 4 identities / 6 rows (junior and
  senior_2 own one row each, "distinct services" is weak, #61/#72); executed state changes are only
  ~6.6% of generated events (18-39 per identity per 30 days) and rollbacks are rare (3 in 30
  days), so restart/deploy-frequency features are sparse on normal data; normal destructive actions
  look more regular than real usage (#73); synthetic events skip Gateway validation (#71, covered
  by the #72 test); the generator reads "continuous" loosely (#64); fail-open means a swallowed
  write leaves a hole in that identity's window (under-detection, #70); "timestamp at pipeline
  start" cannot be told apart from "at the hook" by a test (#77); late-night live testing is
  flagged off-hours (#67); the planning doc still says the window is per (identity, service,
  environment): #55 supersedes it and the final report MUST say so.
- Process notes: decisions #76 and #77 were recorded alongside the code, before commit, not before
  the first line (a deviation from the standing rule). Pre-existing test leak: unauthenticated
  BLOCK rows (`QA-R-auth...`, `QA-W-x...`, no user or service) are not removed by any teardown;
  harmless, but do not count rows in the dev DB expecting zero.

## Phase 9 Summary (complete)
`gateway/risk.py::assess_risk()` is pure and read-only; `evaluate()` calls it only after every
Step 1 stage passed and returns it as `Verdict.risk` (None for any BLOCK). `audit.record_decision()`
inserts security_requests + risk_assessments in ONE commit BEFORE any MCP call (#58, #63).
- rule_risk_level (#53, #54): reads LOW and exempt from every condition; owned staging
  restart/rollback/deploy LOW; production state change MEDIUM (restart) / HIGH (rollback, deploy)
  via the registry sensitivity (#1); policy approval flag HIGH (unreachable now, #48);
  repeated denials MEDIUM; S1 MEDIUM; S2 HIGH; S3 MEDIUM; highest wins.
- Sequence rules (#56, #62), history read from `security_requests` before the current row exists:
  S1 deploy->rollback per (user, service) 10 min; S2 three consecutive qualifying rows per user
  10 min (strictly consecutive); S3 third identical destructive action per (user, tool, service)
  5 min. Repeated denials (#57): >=3 Ownership/Policy BLOCKs of the authenticated user in 10 min,
  selected structurally (BLOCK with user_id, tool_id, service_id all non-null).
- ml_risk_level is a fixed LOW stub with the marker "ml=stub" (#59); final = max(rule, ml).
- Response contract UNCHANGED: no `risk_level` until Phase 11 (#60).
- All counts/windows live in `gateway/risk_constants.py`: uncalibrated; FREEZE before Phase 16.
- Per-request history-query cost (pinned by a test): reads 0, restart/deploy 3, rollback 4. E3
  must measure this.
- Tests: `tests/test_risk_engine.py` (engine, explicit created_at, boundaries, a real-pipeline
  check of the #57 filter) and `tests/test_gateway_risk_wiring.py` (rows, ordering, rollback,
  409). Every test teardown that deletes audit rows MUST use `tests/qa_cleanup.py::
  delete_requests()` (risk_assessments FK, #63).
- Known limitations (state in report): a bug in risk computation or the risk write fails ALL
  allowed traffic with HTTP 500 and leaves no trace of the request (fail closed, #58); S2 is
  evaded by one interleaved executed request or noise row (#62); window comparison uses the
  Python clock against DB-set `created_at` (fine on one host); #48 approval-bound Policy BLOCKs
  count toward repeated denials until Phase 11 (#57); "distinct services touched" is a weak
  feature (max 2); Section 15's "Ownership + ML" row overstates the ML role (#61); the planning
  doc still says the window is per (identity, service, environment): #55 supersedes it for
  Phase 10+ and the final report MUST state the deviation.

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
- Phase 11 Step 0 must decide: the interim production ALLOW closes when the decision mapping
  consumes final_risk_level (Section 11 Step 4): whether `risk_level` appears in the response (only
  on APPROVAL_REQUIRED, or not at all, #60); who approves an admin's own production request (admin
  owns two production rows, #47); how the #48 approval-bound BLOCK becomes APPROVAL_REQUIRED and
  feeds `requires_approval=True` into assess_risk (#63). Phase 10 adds: what behavior_events row(s)
  an APPROVAL_REQUIRED request writes (outcome `pending` exists but is unused, #66, #69), what an
  approved-then-executed or rejected request logs, and that the #69 interim `blocked` rows for
  approval-bound deploys are remapped and excluded from training.
- Phase 13 (dataset/features): training reads source='synthetic', inference windows read
  source='live' only (#65). Anomaly/staged categories, labels and sequence ids are Phase 13's
  (#64): this needs a `scenario`/label column or a side file, i.e. another migration. Apply the #68
  gate: with large-jump anomalies check that the version feature value moves AND that the Isolation
  Forest score moves (ablation with vs without the feature); fallbacks are jitter on the normal

  deploy target or dropping the feature. Decide volume and the state-change/rollback mix (sparse,
  see Phase 10 limitations). Decide whether a (user_id, timestamp) index is needed (#75).
- Phase 14: a live window shorter than N = 5 may be incomplete because the hook is fail-open
  (#70); decide how the model treats short windows.
- Phase 15: do not designate production rollback as a BLOCK-class "irreversible" action (#54).
- Phase 16: FREEZE `gateway/risk_constants.py` AND the `app/database/behavior.py` working-hours
  constants (#67) -- a later change invalidates E2. Rewrite Demo 7 per #61 (one identity
  alternating across its two owned rows plus a separate denied attempt on a third service).
- E3 (latency) must measure the Phase 9 history queries (reads 0, restart/deploy 3, rollback 4)
  AND the Phase 10 hook (two reloads + one INSERT + one COMMIT per logged request, #70, #77).
- Full suite takes ~55-60 s locally (was ~8 s before Phase 8 Stage 2). Likely argon2 hashing in
  `make_user`; not diagnosed. Optional: `pytest tests -q --durations=8`.

## Next Task -- Phase 11
Human approval workflow (Section 27 Phase 11; Sections 11, 14): approval queue, approve/reject,
TOCTOU-style revalidation immediately before MCP execution, and the Section 11 Step 4 decision
mapping implemented end to end (`ml_risk_level` stays a LOW stub until Phase 14, #59). Before
coding: read Planning Sections 11, 14, 17 and decisions #47, #48, #53, #54, #58, #59, #60, #63,
#69; resolve the Phase 11 Step 0 items in Open items; write new decisions.md entries BEFORE code
(this time actually before the first line, see the Phase 10 process notes). Phase 11 changes
existing tests on purpose (the #48 approval-bound BLOCK becomes APPROVAL_REQUIRED, as #34 did).

## Important
- Follow Planning Revision 6 and `docs/decisions.md` (77 entries).
- Do not reorder, remove, or add phases. Do not redo Phase 1-10 unless asked.
- Anything genuinely undecided mid-implementation gets a new decisions.md
  entry BEFORE code, not after.
  