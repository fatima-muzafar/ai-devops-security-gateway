# Security Gateway FYP -- Project Status

## Current Phase
Current Phase: Phase 12 COMPLETE -- security dashboard v1: two read-only admin endpoints, CORS and a
Next.js app (hero, login, DevOps agent chat, three admin panels, approve/reject). No ML. Optional
Stage 3 (summary charts, #100) NOT built.
Next: Phase 13 (dataset finalization and ML feature engineering).
Decisions #1-#110 locked.

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
- Phase 11 -- Human Approval Workflow, TOCTOU Revalidation, Decision Mapping
  - Step 0 -- decisions #78-#87 (approved with 5 changes: self-approval limitation text, grep of
    approved_at before the rename, no-approval-loop rule + tests, pending-row note, test list
    re-verified against the real code)
  - Stage 1 -- migration e7c1a4b9d2f6, gateway/decision.py, policy.evaluate_policy(),
    gateway/revalidation.py, approvals/service.py, resolve_pending_event(), #86 fix in risk.py;
    #88; commit `2c30142`
  - Stage 2 -- wiring: pipeline + audit enforce the decision, api/approvals.py,
    approvals/execution.py, check_policy removed; 16 existing tests + 1 of Stage 1 edited, 26 new
    tests; #89; commit `d936b95`
  - Stage 3 -- close-out: smoke (real uvicorn; direct AND real-Gemini chat mode) verified by DB
    query; this file
- Phase 12 -- Security Dashboard v1
  - Step 0 -- decisions #90-#100 (v1 scope, admin-only reads, event fields, endpoint shapes, token in
    memory, CORS, manual refresh, approve/reject reuse, frontend structure, optional charts)
  - Stage 1 -- backend: GET /api/security/events, GET /api/mock/services, CORS, 48 tests; #101;
    commits `d19cbf8` (decisions) and `4e96b8d` (code)
  - Stage 2 -- frontend core: login, three panels, approve/reject, one CSS file; #102-#104;
    commits `ce3ebc6`, `872a6d9`, `82076aa`
  - Extras requested by the user: hero landing view (#105, `2ca0f63`, `3034415`), restyle like the
    user's reference (#106, `4e3eac2`, `51e1834`), visible Log out button (#107, `f5835d9`),
    chat screen for the DevOps agent (#108-#110, `cf96973` decisions, `a0c158e` code)
  - Stage 3 (optional charts, #100) -- NOT built
  - Close-out -- smoke (real uvicorn + real browser) passed; this file

## Current Repo State
- Last verified commit: `a0c158e` (Phase 12: chat screen, the last code commit). The last BACKEND
  change is `4e96b8d` (Phase 12 Stage 1); every later commit touches only frontend/ and docs/.
"Docs-only commits (no backend/ changes) do not require a hash update here --
this field tracks the last code-verified commit, not literal HEAD."

- Planning version: Revision 6
- Phase 1 through Phase 12 are complete.
- Database: 11 tables. Migration e7c1a4b9d2f6 is the head (Phase 11: approval_requests renames
  approved_at -> decided_at, adds UNIQUE(request_id), state_snapshot JSON NOT NULL and
  revalidation Text NULL -- #81). Before it: d5b2f8a1c7e3 (Phase 10, #65, #66, #75), a8d41c7e5b92
  (audit columns, #32, #39). Phases 8 and 9 added no migration; Phase 11 Stage 2 added none.
- Full suite: 468/468 passing after Phase 12 Stage 1 (user-verified): 420 (Phase 1-11) + 48 new in
  tests/test_dashboard_api.py. No backend change after that commit. (Phase 11 detail: 327 (Phase 1-10) + 68 (Stage 1,
  tests/test_approval_logic.py) + 25 net (Stage 2: 26 new in tests/test_approval_flow.py + 1 new
  in test_gateway_risk_wiring.py, minus 1 removed Stage 1 test and 1 removed parametrize case).)
- No migration in Phase 12; the head is still e7c1a4b9d2f6 and there are still 11 tables.
- `docs/decisions.md` has 110 entries (#1-#110; #90-#110 are Phase 12).
- `npm run lint` (no errors) and `npm run build` (Next.js 16.3.6 Turbopack: compiled, TypeScript
  finished, static routes `/` and `/_not-found`) PASSED (user-verified, output pasted after `f5835d9`
  and again with the chat screen applied, before commit `a0c158e`).
  The dashboard was also run with `npm run dev` at http://localhost:3000 and checked by hand.
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

- Phase 11 smoke (user-verified, real uvicorn, checked by DB query via the UNTRACKED
  `phase11_smoke/{smoke.py,run_sql.py,report.sql}`, a Python driver, not PowerShell): `--mode direct`
  37/37 checks and `--mode chat` (real Gemini picked the right tool every time) 37/37. Covered:
  owned staging restart still ALLOW; production deploy -> APPROVAL_REQUIRED with nothing run,
  pending approval + snapshot + HIGH risk row + one `pending` event; admin listing with risk
  (senior 403, no token 401); admin approve -> revalidation `passed` -> MCP -> version 1->2 /
  2->3 with known_good = old current (#9), decision stays APPROVAL_REQUIRED + executed, the same
  event row resolved to `allowed` with versions, second approve 409; production restart rejected
  (revalidation NULL, no restart row, event `blocked`, approve-after-reject 409); TOCTOU (version
  bumped in the DB between request and approval) -> `revalidation_failed` naming the field, no MCP
  call, event `blocked`; admin self-approval 403, self-reject OK. report.sql tables agreed.

## INTERIM STATE (Phase 9 -> Phase 11) -- CLOSED in Phase 11; read before trusting OLD rows
Risk is now ENFORCED (#78): LOW -> ALLOW, MEDIUM/HIGH or a policy approval flag -> APPROVAL_REQUIRED.
Senior/admin production restart and rollback are no longer ALLOW; production deploy is no longer a
fail-closed BLOCK (#48 is retired). What still matters for evaluation data:
- Rows written in Phase 9-10 with the marker "interim: not enforced" (decision=ALLOW although final
  risk was MEDIUM/HIGH) are NOT valid for E5 or Approval Routing Accuracy: exclude them or regenerate
  (#58). New rows never carry the marker.
- Phase 9-10 results for production state changes are superseded; do not read them as final.
- Live behavior_events written before Phase 11 for approval-bound deploys are `blocked` (#69);
  they are not training data. Since Phase 11 such a request logs `pending` and is resolved later (#85).
- ml_risk_level is STILL a fixed LOW stub with the marker "ml=stub" until Phase 14 (#59): rows before
  Phase 14 are excluded from E2.

## Phase 12 Summary (complete)
Backend (Stage 1; #91-#94, #96, #101; routers app/api/security.py and app/api/mock.py, admin only via
`require_admin` imported from api/approvals.py, role read from the DB, read only, no new table):
- GET /api/security/events?limit=50&decision=: newest first (created_at desc, request_id desc), limit
  default 50 / max 200 (else 422), decision filter validated against the Decision enum. Returns
  request_id, created_at, requester, agent, service_name, environment, tool, decision, reason,
  execution_status, risk {rule_risk_level, ml_risk_level, final_risk_level, reasons} or null,
  approval_status or null. The query selects COLUMNS only: raw_request and arguments are never loaded.
- GET /api/mock/services: service_name, environment, current_version, known_good_version, status, owner
  username; ordered by service_name then environment ("production" before "staging").
- CORS (main.py, #96): CORS_ALLOWED_ORIGINS (default http://localhost:3000), "*" dropped, GET/POST,
  Authorization + Content-Type, no credentials. http://127.0.0.1:3000 is a DIFFERENT origin.
- Tests: tests/test_dashboard_api.py (48): 401/403/503, role read from the DB, exact rows, order, ties,
  limit, filter, no leaks, one row per request, nothing written, seeded six services, CORS.
Frontend (Stages 2 and extras; Next.js 16.3.6, React 19, Tailwind import only, no UI or chart library):
- ONE route "/" (#90). components/dashboard.tsx holds the view (hero | login | dashboard). The JWT lives
  in React memory only (#95): a reload logs out; any 401 from a panel returns to login ("Session
  expired"); a login 401 is a login error (#104). Panels: Security Events, Approvals (status select,
  Approve/Reject using the existing endpoints, #98), Mock Services; each has Refresh and loading /
  error / empty states (#97). After approve/reject all panels reload. All values render as plain text.
- All backend calls go through lib/api.ts (NEXT_PUBLIC_API_BASE_URL, default http://127.0.0.1:8000);
  the UI never references the MCP route (Section 5). usePanelData derives loading from keys (#104).
- ALL styling is in app/dashboard.css (#99, #102): the user's palette tokens plus --accent-rgb (#105);
  placeholders --border, --ok, --bad, --warn, --radius are PROVISIONAL (#102). Dark only, no animation.
- Hero landing view (#105): static, content kept true to what is built. Restyle (#106): left icon
  sidebar, top header, glowing table header, risk LEVEL bar (LOW 4 / MEDIUM 8 / HIGH 12 ticks plus the
  text label; not a score). Visible Log out button beside the username (#107).
- Chat screen (#108-#110, components/chat-panel.tsx): the sidebar has Chat | Dashboard | Log out; Chat
  is the first view after login for EVERY role (the UI does not know the role); both views stay
  mounted (the inactive one is hidden). It calls only POST /api/chat through lib/api.ts. The agent
  reply is rendered as PLAIN TEXT (untrusted LLM output, #92); it shows the Gateway decision badge,
  a muted "agent proposed: <tool_request JSON>" line and the request_id. One message at a time,
  "Thinking..." while waiting, 2000-character UI cap (UX only), three example chips that only fill the
  input. A non-admin who opens Dashboard sees the server's "Forbidden." in each panel (#98).
Smoke (user-verified, real uvicorn + real browser): S1 (service state read), S2 (four production
requests -> APPROVAL_REQUIRED with the generic reason and no risk level), S3 (second approve of the
same approval -> HTTP 409; the first attempt failed only because the 60-minute admin token had
expired, the re-run with a fresh token passed). B1-B13 (browser: pending list and risk bars, admin
self-approval 403, self-reject, reject needs a reason, reject, approve + executed, version V -> V+1 with
known_good = V, TOCTOU revalidation failure naming a version field, approved/rejected views, events
columns, no /mcp request in the Network tab, Log out, junior sees "Forbidden.") were reported as all
PASS by the user; their screen output was not pasted to the assistant.
Chat smoke C1-C9 (user-verified in the browser; real Gemini + real uvicorn; C2-C6 outputs pasted):
senior_developer_1: logs of auth-service staging -> ALLOW with the logs; logs of notification-service
staging -> Ownership BLOCK (that row's staging owner is junior_developer_1, #8; Demo 6 shown by
accident); production restart of notification-service -> APPROVAL_REQUIRED; Dashboard -> "Forbidden."
in all three panels. admin: approved that request -> "Approved and executed", pending list empty.
junior_developer_1: deploy to notification-service staging -> Policy-stage BLOCK (role not permitted
to use deploy_service). Tab switch kept the messages, F5 returned to the hero, no /mcp request
(C7-C9 reported PASS, output not pasted). The assistant's first C2 expectation (ALLOW for
senior_developer_1 on notification-service staging) was WRONG; the Gateway was right.
- Known limitations (state in the final report):
  - The dashboard is admin only (#91): a senior developer cannot see their own requests.
  - The token is memory only (#95): a reload logs out; no refresh, no revocation (#42). The "Session
    expired" screen was NOT tested. There are NO automated frontend tests (#99); only the hand smoke.
  - Events show the latest 50 only, no pagination or filter UI (#93); leftover QA-... test rows
    appear. The approvals list has no pagination (#83). Refresh is manual (#97).
  - The risk bar shows the LEVEL, not a measured score (#106). Status colours and the border colour are
    placeholders (#102). --accent-rgb must be changed together with --accent (#105).
  - The hero page is presentation only; its text must stay true (#105): no ML claim before Phase 14.
  - `npm install` printed 4 vulnerabilities (3 high, 1 critical) in dependencies; NOT investigated
    [unverified]. Do not run `npm audit fix --force` blindly (it can change the Next.js version).
  - The seeded admin still cannot approve its own production request (#82); the UI only shows the 403.
  - POST /api/chat has min_length=1 and NO maximum message length (backend, unchanged in Phase 12);
    the 2000-character cap in the UI is not a control. The server keeps the last 20 messages per user
    (#29) and the UI cannot clear them; the transcript on screen is lost on logout or reload.
  - After every login three read-only admin GETs run even while Chat is shown; a non-admin gets three
    403s there (#108). The chat example chips use notification-service STAGING, which only
    junior_developer_1 owns: for other users they show an Ownership BLOCK (kept on purpose).
  - Simulated log lines have levels that do not match their text (random generator, #11); ML never
    reads log content.
  - No ML summary charts (#100 not built). Charts, if built later, are an illustration, never E1-E6
    evidence (the counts include test traffic).
- Process notes: all decisions #90-#110 were written before the code that uses them. #106 copied the
  reference's icon-only exit control as the only log out control, which the user could not find; #107
  fixed it. The assistant never ran any code in Phase 12 (no sandbox runs); every test, build and
  smoke result above comes from the user's own runs.

## Phase 11 Summary (complete)
Decision mapping (#78): `gateway/decision.py::decide_from_risk()` is pure: policy flag -> APPROVAL_REQUIRED;
LOW -> ALLOW; MEDIUM/HIGH -> APPROVAL_REQUIRED. There is NO BLOCK-class yet (Phase 15 decides). A policy
DENY is still a Step 1 BLOCK. `policy.evaluate_policy()` returns PolicyResult(block_reason,
requires_approval); `check_policy` is deleted. `assess_risk(requires_approval=...)` gets the real flag.
- APPROVAL_REQUIRED (#79, #80): response {request_id, decision, reason} with the generic reason
  "Approval stage: this action requires human approval; the request is pending review." No
  `risk_level` anywhere in a Gateway response. ONE commit writes security_requests
  (APPROVAL_REQUIRED, not_executed), risk_assessments (decision APPROVAL_REQUIRED, no interim marker)
  and approval_requests (pending + state_snapshot {current_version, known_good_version}); a failure
  rolls all three back (HTTP 500, no MCP). MCP is never called. A `pending` behavior event is
  written (own commit, fail-open). security_requests.decision is NEVER rewritten later.
- Endpoints (#83, app/api/approvals.py, sync def, admin only, role read from the DB): GET
  /api/approvals?status=pending|approved|rejected (oldest first; request, requester, agent, service,
  env, tool, arguments, reviewer, reason, revalidation, risk); POST /api/approvals/{id}/approve and
  /reject (reject needs a reason). 401 / 403 / 404 / 409 (already decided) / 422 / 502 (MCP failure).
- Decision logic (#82, app/approvals/service.py): admin only; reviewer must not be the requester
  (self-approval 403; an admin MAY reject their own request); ONE atomic UPDATE ... WHERE
  status='pending' so a double approve is 409; the human decision is committed BEFORE revalidation.
- Revalidation (#84, gateway/revalidation.py, read-only, only after an approval): requester and
  agent re-looked-up in the DB (the token is not stored), tool registered+enabled, stored arguments,
  service row, ownership, policy still permits, and the version snapshot unchanged (both fields, all
  three state-changing tools). policy requires_approval=True counts as SATISFIED (no approval loop).
  Risk is not recomputed. Fail -> BLOCK-style result (approval stays `approved`, revalidation holds the
  reason, execution_status stays not_executed, MCP not called). Pass -> "passed", MCP, then
  executed/failed (failed -> HTTP 502). Responses (#89): outcome executed | revalidation_failed |
  rejected.
- behavior_events (#85): ONE row per request: `pending` at request time, updated in place to allowed
  (+versions for deploy/rollback) / failed / blocked (rejected or revalidation-failed); timestamp
  stays the request time. `resolve_pending_event()` is fail-open.
- #86: "executed" in the S1/S3 history means execution_status=EXECUTED whatever the decision, so
  approved executions count (they were invisible because they filtered decision=ALLOW).
- Migration e7c1a4b9d2f6 (#81); round trip, an upgrade with an existing row (decided_at kept,
  state_snapshot '{}') and two migration mutants were checked in the sandbox.
- Tests: tests/test_approval_logic.py (68, Stage 1: decide, evaluate_policy, every revalidation
  check, approvals service, pending-event update, #86) and tests/test_approval_flow.py (26, Stage 2:
  Demo 4 end to end over HTTP and the real MCP seam, reject, TOCTOU for version/ownership/policy,
  401/403/404/409/422, self-approval, MCP 500 and unavailable -> 502, one-commit rollback, duplicate
  request_id, listing order and filters, #86 end to end, the policy flag alone forcing approval).
  Helpers: qa_cleanup.delete_approvals(); delete_requests() deletes approvals first; make_user
  teardown deletes approvals it REVIEWED (reviewer_id FK).
- Existing tests changed on purpose, list approved before editing (red-first run showed 14 behaviour
  reds + 2 direct check_policy callers, exactly as predicted): test_gateway_policy (matrix x6 and 2
  edge cases), test_gateway_risk_wiring (4), test_gateway_tool_request (1), test_chat_agent (1),
  test_behavior_live_hook (2) and one Stage 1 test removed.
- Mutation checks (sandbox, all killed): Stage 1 33 code mutants + 2 migration mutants; Stage 2 34
  mutants (pipeline, audit, execution, router, main). Scripts are not part of the repo.
- Known limitations (state in the final report):
  - The seeded admin CANNOT get approval for its own production restart/rollback (only one admin,
    #8, #82); it can only reject them. The report MUST say so.
  - "Re-authenticate the requester" is a DB re-lookup: the requester token is not stored (#44, #51);
    only the approver is freshly authenticated at approve time (#84).
  - Revalidation fails closed on ANY version change, strict even for a restart (#84).
  - No approval expiry, no requester status endpoint, no notifications, no pagination on GET
    (#83). A pending approval stays pending forever (#85).
  - A crash between the approve commit and the MCP call leaves the request approved +
    not_executed; there is no retry endpoint (a replay is 409, so nothing can run twice, #89).
  - Approved-then-failed and revalidation-blocked requests do not feed S2 or #57 (#86).
  - A staging rollback soon after a staging deploy now needs an admin (rule S1 = MEDIUM, #53): plan
    demos and smoke tests for it.
  - Section 17's example (risk_level in the response) differs: #79. Section 28's `gateway/` and
    `approvals/` layout is flat (#38, #88).
  - Fail-open pending write (#85): a swallowed write leaves no row to resolve (a warning only).
  - The planning doc still says the window is per (identity, service, environment): #55 supersedes
    it and the final report MUST say so.
  - Full suite ~90-135 s (argon2 hashing in `make_user`, not diagnosed).
- Process notes: #88 (Stage 1 implementation details) was written AFTER the Stage 1 code but before any
  Stage 2 code (a third slip of the standing rule, after #76/#77); #89 was written before its code.
  During Stage 1 the mutation harness left one file mutated in the working tree once (caught by
  diffing a backup, restored before the patch was built); after that it ran on a throwaway copy. The
  smoke driver is Python (`phase11_smoke/`, UNTRACKED like `phase10_smoke/`) because PowerShell could
  not be run in the sandbox. The sandbox smoke dry-run was skipped on purpose (usage limit); the first
  real run was the user's and passed.

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
- Demo 8 (prompt injection) conflicts with #11 (no anomalous log content) and #27 (tool calls after a
  tool result are ignored). Resolve before Phase 16/17 (decide in that phase's Step 0). The chat screen
  does not change this: one tool call per turn still holds.
- Evaluation data mix (decide in Phase 13 Step 0 for training data, again before Phase 16 for E1-E6):
  tests, smoke runs, the dashboard and the chat all write to the SAME dev DB (#41). It holds QA-... test
  rows, smoke rows, old "interim: not enforced" rows (#58), live chat rows and the synthetic set.
  Training and evaluation must not mix with them: use a separate evaluation DB, or tag and exclude
  rows by rule (source marker #65, request_id prefixes). Nothing to do before then.
- Phase 12 optional follow-ups (not required): Stage 3 summary charts (#100: counts only, 3 plain
  bars, "demo data" label); sessionStorage if the reload logout annoys (#95); a service_state_history
  view (#94); event filters or pagination (#93); investigate the 4 npm vulnerabilities; change the
  chat example chips so they fit the viva user (#109); a server-side maximum message length for
  /api/chat (a backend change, needs its own decision).
- Phase 13 (dataset/features): training reads source='synthetic', inference windows read
  source='live' only (#65). Anomaly/staged categories, labels and sequence ids need a
  `scenario`/label column or a side file, i.e. another migration (#64). Apply the #68 gate (version
  feature value AND Isolation Forest score must move, ablation with vs without). Decide volume and
  the state-change/rollback mix (sparse, see Phase 10 limitations) and whether a (user_id,
  timestamp) index is needed (#75). NEW from Phase 11 (#85): decide how windows treat old `pending`
  rows that were never decided, and how `blocked` rows from rejections and revalidation failures
  count as behaviour.
- Phase 14: a live window shorter than N = 5 may be incomplete because the hooks are fail-open (#70,
  #85); decide how the model treats short windows.
- Phase 15: do not designate production rollback as a BLOCK-class "irreversible" action (#54). NOTE:
  there are NO BLOCK-class rows yet (#78): every HIGH production action goes to APPROVAL_REQUIRED
  today. Decide which, if any, become BLOCK (Section 11 Step 4, last row).
- Phase 16: FREEZE `gateway/risk_constants.py` AND the `app/database/behavior.py` working-hours
  constants (#67) -- a later change invalidates E2. Rewrite Demo 7 per #61 (one identity alternating
  across its two owned rows plus a separate denied attempt on a third service). Demo 4 now works as
  written (senior_developer_1 -> notification-service/production deploy -> admin approves); an admin's
  own production request cannot be approved (#82). E6 approve-then-execute trials (Section 25, target
  15-20): generate them by changing state between request and approval (current_version,
  known_good_version, ownership, policy, tool disabled) and approving with a SECOND admin (throwaway
  user; do not seed one, #8).
- E3 (latency) must measure the Phase 9 history queries (reads 0, restart/deploy 3, rollback 4), the
  Phase 10 hook (two reloads + one INSERT + one COMMIT per logged request, #70, #77) AND the Phase 11
  additions: the three-row approval commit, the pending event, and approve = decision commit +
  revalidation queries + MCP + resolve.
- Final report must state: #82 (admin self-approval), #84 (re-lookup, strict snapshot), #79 (no
  risk_level in responses), #55 (window key), #91 (admin-only dashboard), #95 (memory token), #102
  (provisional colours), #106 (risk bar shows a level), #109 (chat reply as plain text, no maximum
  message length, server-side memory) and the other known limitations listed above.
- Full suite takes ~90-135 s locally. Likely argon2 hashing in `make_user`; not diagnosed. Optional:
  `pytest tests -q --durations=8`.

## Next Task -- Phase 13
Dataset finalization and ML feature engineering (Section 27 Phase 13; Sections 10, 23, 24; M4). Before
coding: read Planning Sections 10, 23, 24, 25 (E2, E6) and decisions #55, #59, #64-#68, #73-#75, #85;
resolve the Phase 13 items in Open items (label/scenario column or side file, volume and mix, index,
pending and blocked rows, the #68 gate, and the evaluation data mix). Write new decisions.md entries BEFORE the first line of code,
for all of them including small details. Phase 13 adds no new phases; the Isolation Forest is Phase 14.
Any existing test that must change is listed and approved first. Phase 12 added no backend change after
`4e96b8d`, so the Phase 13 backend baseline is 468/468 passing.

## Important
- Follow Planning Revision 6 and `docs/decisions.md` (110 entries).
- Do not reorder, remove, or add phases. Do not redo Phase 1-12 unless asked.
- Anything genuinely undecided mid-implementation gets a new decisions.md
  entry BEFORE code, not after.
  