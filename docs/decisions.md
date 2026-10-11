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

## Phase 6 Decisions — LangChain DevOps Agent + LLM Integration

## 16. LLM Provider — Gemini (Free Tier)
Section 27 names "LLM API" generically; provider was never fixed. Resolved:
Google Gemini, via Google AI Studio's free-tier API key — zero cost, no
billing account required.

Trade-off accepted knowingly: free tier is rate-limited
(requests/minute). Fine for Phase 6 development and demo use. Revisit if
a later phase (e.g. bulk ML/evaluation trials, Section 25) needs high
request volume against the LLM itself — unlikely, since E1–E6 generate
*tool-request* traffic programmatically, not LLM calls per trial.

Key stored in `backend/.env` as `GOOGLE_API_KEY`, which must already be
in `.gitignore` (same pattern as other secrets per `decisions.md` #8's
placeholder-password handling).

## 17. Agent Tool Exposure — All Five Tools, Limited Test Scope
The agent is given structured-request-generation ability for all five
MCP tools (`get_logs`, `get_metrics`, `restart_service`,
`rollback_deployment`, `deploy_service`), sourced directly from the
existing `mcp/schemas.py` Pydantic schemas (`TOOL_ARG_SCHEMAS`) — no
duplicate schema definitions.

Phase 6 *testing*, however, stays narrow: `restart_service` (state-
changing, matches Phase 5's existing coverage) and `get_logs` (read-
only, exercises a second tool type). The other three tools are reachable
through the agent but not exercised by Phase 6 tests — same scoping
principle as `decisions.md` #15 (execute_tool() supports all five; a
given phase only needs to *test* what proves that phase's point).

## 18. `/api/chat` Endpoint — Built in Phase 6
Section 17 lists `POST /api/chat` ("Developer <-> DevOps Agent") but
Section 27's phase list doesn't assign it explicitly. Resolved: built in
Phase 6, alongside the agent itself — without it, the agent has no real
entry point to test against (Phase 5's endpoint was tested directly via
TestClient with no agent in front of it; Phase 6 needs the reverse).

Per `STATUS.md`'s existing open item: whether this joins
`POST /api/gateway/tool-request` under a shared `app/api/` router module
remains undecided, revisited only when actual need forces it (two
routes now exist — this may be that trigger, but is not decided here).

## 19. Placeholder Identity — `user_id` / `agent_id`
No real authentication exists yet (Phase 8's job). Resolved for Phase 6:
`/api/chat` accepts `user_id` as a plain, unvalidated field in the
request body. `agent_id` is a hardcoded constant in the agent's own code
(`"AG001"`, matching Section 17's worked example) — not supplied by the
caller, since there is exactly one agent (Section 2, "Agent: One
autonomous DevOps AI agent").

Same trust posture as Phase 5's placeholder decision rule: input is
taken at face value. Phase 8 replaces this with real auth; it does not
extend this placeholder.

## 20. `request_id` Generation — Owned by the Chat Endpoint, Not the Agent
Resolved: `/api/chat` generates a UUID `request_id` per incoming HTTP
request, before invoking the agent. The agent itself does not generate
request IDs.

Reason: request tracking (Section 4: "Request IDs connect the agent
request, Gateway checks, risk assessment, approval, MCP execution,
state change, and audit evidence") is an HTTP/system-layer
responsibility, not a reasoning-layer one — keeps the agent's job purely
"understand + propose a tool call," consistent with Section 6's agent
responsibilities list.

## 21. Conversation History — In-Memory Only, No New DB Table
Explicitly considered and rejected: a persistent chat/conversation table.

Reasoning: conversation *content* (what the developer typed) is not a
Section 10 ML feature input — no behavioral feature depends on message
text, only on tool-request *patterns* (frequency, sequence, timing),
which `behavior_events` already exists to capture (Section 16), starting
Phase 10. Adding a chat-history table now would (a) duplicate what
`behavior_events` is designed to own once Phase 10 builds it, and (b)
is not listed among Section 16's 11 tables — a genuine scope addition,
not a clarification, and therefore out of scope per the project's own
"do not add modules/tables unless explicitly asked" rule.

Phase 6 conversation context (for the LLM's own multi-turn understanding
within one session) is held in memory only, not persisted. If a later
phase needs persistent behavioral logging, that is `behavior_events`
(Phase 10) — not a new table invented here.

## 22. Agent Design Pattern — Structured Tool-Calling via `bind_tools`
Resolved: the agent uses LangChain's structured tool-calling
(`bind_tools`), backed by Gemini's native function-calling, with tool
schemas sourced from `mcp/schemas.py`. No custom prompt-parsing or
regex-based intent extraction is written.

Matches Section 7's intent directly: "LangChain... simplifies agent
orchestration, prompt management, tool schemas, and model/tool
interaction without requiring the team to build a custom agent
framework."

## 23. Gateway Decision Relay — Verbatim `reason`, No New Explanation Logic
When the Gateway returns BLOCK (or a non-ALLOW outcome generally), the
agent relays the Gateway's own `reason` field (already part of Section
17's response shape) to the developer in natural language — it does not
generate its own independent explanation of why the action was denied.

Reason: the Gateway is the authoritative source of the decision and its
justification (Section 5: Gateway is the security boundary); having the
agent re-derive or guess at a reason risks the agent's explanation
drifting from the Gateway's actual logic, especially once Phase 8/9 add
real policy and risk reasons.

## 24. Phase 6 Test Strategy — LLM Responses Are Mocked, Not Live
Automated tests (`pytest`) for the agent do not call the real Gemini
API. The LLM's tool-call output (LangChain's `AIMessage` with
`tool_calls`) is mocked/stubbed in tests, so the suite stays
deterministic, fast, and independent of Gemini's free-tier rate limit
(`docs/decisions.md` #16) — especially important since the full suite
is re-run repeatedly (as it was after Phase 5, 26/26).

This does not replace real-world verification: a one-off manual smoke
test (curl/Postman against a running `uvicorn` instance, hitting the
real Gemini API) is done separately, outside the automated suite, to
confirm the actual integration works end-to-end. That manual check is
not part of `pytest` and is not repeated on every test run.

Scope: this governs Phase 6's own agent-level tests only. It does not
set a project-wide policy about mocking external services in future
phases (e.g. Phase 10's ML work) — that gets decided when it's actually
relevant.

## 25. API Routing Structure — Split into app/api/ Router Modules
Resolved the question STATUS.md left open at the end of Phase 5. That
point has now arrived: Phase 6 adds a second route (`/api/chat`).

Decision: routes move into `backend/app/api/` — matching Section 28's
repository structure, which already lists `api/` as a sibling of
`agent/`, `gateway/`, `mcp/` under `app/`. This is pre-existing planned
structure, not a new architectural call; Phase 5 simply hadn't reached
the trigger condition (more than one route) to justify filling it in.

- `backend/app/api/gateway.py` — existing
  `POST /api/gateway/tool-request`, moved out of `main.py`, wrapped in
  an `APIRouter()`.
- `backend/app/api/chat.py` — new `POST /api/chat`.
- `backend/app/main.py` — becomes pure bootstrap: `FastAPI()` instance
  + `include_router()` calls only.

  <!-- APPEND to docs/decisions.md, after #25. Written BEFORE code (standing rule). -->

## 26. Agent -> Gateway Transport — HTTP via an Injected `GatewayClient`
Section 4/7/17 draw the path as Agent -> `POST /api/gateway/tool-request`.
Resolved: the agent talks to the Gateway through a thin `GatewayClient`
wrapping an httpx-compatible client (`.post(path, json=...)`). Production
uses a real `httpx.Client` against `GATEWAY_BASE_URL` (default
`http://127.0.0.1:8000`); tests inject Starlette's `TestClient(app)`
(which is an httpx client), so no network or second server is needed.

Rejected: calling the Gateway handler as an in-process Python function.
It would make `app/agent/` import Gateway/MCP-adjacent code, so the
"agent never touches MCP" boundary (Section 5/6) would rest on
discipline instead of on an HTTP seam. Phase 7 will also move Gateway
logic into `app/gateway/`; an HTTP seam means the agent does not change.

Consequence: `POST /api/chat` MUST be a sync `def` endpoint. An
`async def` handler making a blocking httpx call back into the same
uvicorn event loop would deadlock.

Also: Gemini model name comes from `GEMINI_MODEL` (default in
`agent/llm.py`), not hardcoded, so a retired free-tier model name is an
`.env` change, not a code change.

## 27. Agent Turn Semantics — One Tool Call per Turn
- At most ONE tool call is submitted to the Gateway per chat turn. If the
  model emits several, the first is submitted; the rest are dropped and
  the reply says so. (Executing several would need one Gateway
  `request_id` each — see below — and is Phase 7+ scope at the earliest.)
- ALLOW: the Gateway result is fed back to the LLM (one extra LLM call)
  to produce the natural-language reply (Section 6). Any tool call the
  model emits in that second response is IGNORED and logged — no chained
  execution in Phase 6.
- Non-ALLOW (BLOCK, or HTTP 400/422 from the Gateway): NO second LLM
  call; the Gateway's own `reason` (or `detail` for HTTP errors) is
  relayed verbatim (extends #23).
- If the second LLM call fails AFTER an ALLOW, the tool has already run.
  The agent returns a deterministic "ALLOWED and executed, summary
  unavailable" reply with HTTP 200 — never a 5xx, because a 5xx invites a
  retry of a state-changing action. A failure of the FIRST LLM call
  (nothing executed) returns HTTP 502.
- `request_id` = `uuid.uuid4().hex` (32 chars), not the hyphenated form.
  Clarifies #20: `security_requests.request_id` is `String(32)` (#2) and
  a hyphenated UUID is 36 chars.
- KNOWN CONSEQUENCE for Demo 8 (prompt injection, Section 29): with
  injected log content, the agent cannot propose a follow-on tool call
  after reading logs, because tool calls after a tool result are ignored.
  Revisit before Demo 8/E4 (needs a multi-step loop and a per-request
  Gateway id scheme). Not solved here on purpose.

## 28. Agent Module Layout — Flat, Not Section 28's Subfolders
Section 28 lists `agent/[prompts/, schemas/, langchain_agent/]`. Resolved:
flat module, same reasoning as #13 — three one-file packages would be
indirection with no ownership boundary:
`agent/prompts.py`, `agent/tools.py` (tool specs generated from
`mcp/schemas.py`; no `schemas/` folder because #17 forbids duplicate
schema definitions), `agent/gateway_client.py`, `agent/llm.py`,
`agent/devops_agent.py`.

Tool specs are passed to `bind_tools` as dicts (`name`, `description`,
`parameters`), NOT as the Pydantic classes — passing the classes would
name the functions `GetLogsArgs` etc. `$ref`/`$defs` are inlined because
Gemini function declarations do not reliably accept JSON-Schema refs
(the `Environment` enum is emitted as a `$ref` by Pydantic).

## 29. Conversation History — Keyed by `user_id`, Bounded
Resolves how #21's in-memory history is keyed: by `user_id` (no
`session_id` field added to `/api/chat`), process-local dict, last 20
messages, storing only the developer's text and the agent's final reply
(not tool-call/ToolMessage internals). Lost on restart; not shared across
workers; `user_id` is unvalidated (#19), so any caller can write into any
user's context. Acceptable placeholder; Phase 8 replaces identity.

## 30. System Prompt Contains No Security Instructions
The agent's system prompt describes the role, the tools, the services and
the one-tool-per-turn limit. It deliberately does NOT say "never touch
production" or "check permissions". Reason: Section 25 E1/E4 measure what
the Gateway prevents. A prompt that makes the agent self-censor shrinks
the set of unsafe requests the agent proposes, which understates the
unprotected-baseline unauthorized-execution rate and muddies E4. Any
future prompt change must keep this property.

<!-- APPEND to docs/decisions.md, after #30. Written BEFORE code (standing rule). -->

## Phase 7 Decisions -- Full Security Gateway and Request IDs

## 31. Phase 7 / Phase 8 Boundary
Section 27 names Phase 7 "Full Security Gateway and request IDs" and Phase 8
"Authentication, identity, policy, ownership, environment checks". Resolved:

Phase 7 implements, for real:
- the Gateway pipeline as an orchestrator of ordered stages (Section 8) with
  hard-check short-circuit (Section 11 Step 1) and ALLOW/BLOCK decisions;
- request_id rules (#36);
- validation: tool registered + enabled, arguments schema (TOOL_ARG_SCHEMAS),
  target service resolves;
- identity LOOKUP: `user_id` -> `users.username`, `agent_id` ->
  `agents.agent_name` (status "active"); unknown -> BLOCK. This is identity
  resolution (needed so the audit row's foreign keys can be filled), NOT
  authentication: no password, no JWT, anyone can still claim any username;
- audit persistence in `security_requests` (#32, #35);
- the internal MCP HTTP seam (#37).

Phase 7 does NOT implement (still deferred): JWT/passwords, role / ownership /
environment policy and the `policies` table (Phase 8); rule risk (Phase 9);
ML (Semester 2); approval / TOCTOU / APPROVAL_REQUIRED (Phase 11);
`behavior_events` and `risk_assessments` writes (Phase 10 / Phase 9).

The Phase 5 rule `BLOCK if environment == production` stays, relocated
into a clearly labelled placeholder policy stage (`gateway/policy.py`) with
its reason text UNCHANGED. Phase 8 replaces that stage; it does not extend it.

## 32. Schema Change -- One Alembic Migration on `security_requests`
First migration since Phase 3. The existing table could not audit exactly the
requests Section 15 cares about (unknown user, unregistered tool, invalid
args): four NOT NULL foreign keys, no place for a BLOCK reason, no execution
outcome. Resolved (no new table; the 11-table count is unchanged):
- `user_id`, `agent_id`, `service_id`, `tool_id` become NULLABLE (null = the
  submitted value did not resolve to a row).
- NEW `raw_request` JSON NOT NULL (server default `{}`): the payload exactly as
  submitted, so unresolved requests still leave evidence.
- NEW `reason` Text, nullable: the Gateway's reason (set for every BLOCK).
- NEW `execution_status` NOT NULL default `not_executed`; Python enum
  `ExecutionStatus` {not_executed, executed, failed} + CHECK constraint, per #4.
  Section 22: a failed tool call is never recorded as executed.
`decision` stays nullable (intended for later phases, e.g. pending approval);
Phase 7 always writes it. `risk_assessments` is NOT touched: its NOT NULL risk
levels cannot represent a hard-check BLOCK (Section 11: no risk scoring on
Step 1 failures); it is Phase 9's table.

## 33. Seeds and Test Fixtures
- `agents` gets one seeded row, `agent_name="AG001"`, status "active", in
  `seed.py` (idempotent; matched by `agent_name`). `agents.agent_name` has no
  UNIQUE constraint, so lookups use `.first()`, not `.one_or_none()`.
- Because the Gateway now resolves identity, every Phase 5/6 test that calls the
  Gateway needs an existing user and the AG001 agent in the test DB. Fixtures
  provide them; the tests' `user_id` values are updated accordingly.

## 34. Gateway Validation Failures Are BLOCK Decisions, Not HTTP Errors
Supersedes the part of #11 that kept unknown-tool as an HTTP 400 "not a
security decision": Section 11 Step 1 lists unregistered/disabled tool and
malformed request as BLOCK. Resolved taxonomy:
- BLOCK (HTTP 200, `decision: BLOCK`, `reason`, audited): unknown/inactive
  user; unknown agent / missing agent_id; tool not registered; tool disabled;
  arguments missing `service_name`/`environment`; invalid environment;
  arguments failing the tool schema; target service not found; placeholder
  policy (production). First failing stage short-circuits; `reason` names it.
  Stage order follows Section 8: identity -> tool registry -> arguments ->
  service -> policy.
- HTTP 422, no decision, no audit row: FastAPI cannot parse the body at all
  (missing request_id / user_id / tool, request_id too long).
- HTTP 409, no new row: duplicate `request_id` (#36).
- ALLOW but execution fails (MCP error/unreachable): audit row gets
  `execution_status=failed`; response is HTTP 502 with a `detail`, NOT a 200
  ALLOW, so the Phase 6 agent relays the failure instead of narrating a result
  that never happened.
- Test impact (deliberate): `test_unknown_tool_returns_400_not_a_security_decision`
  becomes an "unknown tool is BLOCKed and audited" test.
- The MCP route still validates its own inputs (defense in depth); an MCPError
  there remains an execution failure, never a security decision (#11, kept).

## 35. Audit Write Order
The pipeline is read-only. After it produces a verdict, the Gateway writes
exactly ONE `security_requests` INSERT (request_id, resolved FKs or NULL,
raw_request, arguments, decision, reason, execution_status=not_executed) and
COMMITS it BEFORE any MCP call. Then, only on ALLOW, it calls MCP and UPDATEs
`execution_status` to executed/failed and commits. A crash mid-execution
therefore still leaves the audit evidence.
Refinement of the approved sketch ("insert with NULL decision, then update"):
because the pipeline reads but never writes, an early NULL-decision insert
would add an UPDATE and a half-filled-row state with no information gain.
The audit-before-execute guarantee is identical.

## 36. request_id Rules
- `max_length=32` validated at the HTTP boundary (matches `String(32)`, #2;
  `uuid4().hex` is 32, #27). Longer -> 422.
- `request_id` is the PK; a duplicate raises IntegrityError on insert and is
  returned as HTTP 409; the original row is untouched (replay-safe). A 409 is
  not a decision and is not audited as a new row.

## 37. MCP HTTP Seam -- `POST /mcp/tools/execute` (Section 17, FR-15)
Corrects #11, whose last sentence implied Phase 5 created this route: Phase 5
created only the Gateway route. Resolved: Phase 7 creates it
(`backend/app/api/mcp.py`), and the Gateway reaches MCP only over HTTP,
mirroring the agent->Gateway seam (#26).
- Auth: header `X-Internal-Token` compared (constant-time) to env
  `MCP_INTERNAL_TOKEN`. If the env var is unset the route rejects everything
  (fail closed). Missing/wrong token -> HTTP 403, tool not executed. This is
  the testable "direct MCP access attempt -> Reject" row of Section 15.
  A shared static token is internal service auth, not user auth (that is
  Phase 8).
- Body: `{request_id, tool, arguments}`; the route calls `execute_tool()`,
  commits, returns `{result}`. It makes no security decision (#11).
- Gateway side: `gateway/mcp_client.py` (`McpClient`, httpx-compatible, adds the
  token, base URL from `MCP_BASE_URL`, default `http://127.0.0.1:8000`).
  Injected via a FastAPI dependency so tests substitute a TestClient-backed one.
- Consequence: Gateway route and MCP route must stay sync `def` (self-calls
  inside one uvicorn process, same reasoning as #26).
- Limitation, stated honestly: both routes live in one FastAPI process, so this
  is a logical trust boundary (token-protected route), not a network one.

## 38. Gateway Package Layout and Response Contract
Flat, per #13/#28: `backend/app/gateway/{pipeline,identity,validation,policy,
audit,mcp_client}.py`. `app/api/gateway.py` becomes thin: parse request ->
`pipeline` -> response. Section 28's `gateway/[auth/, validation/, ...]`
subfolders are not created; split a module only when it outgrows one file.
Response contract unchanged (the Phase 6 agent depends on it): BLOCK ->
`{request_id, decision, reason}`; ALLOW -> `{request_id, decision, result}`.
No `risk_level` field until Phase 9.

## 39. `security_requests.environment` Becomes Nullable
Extends #32. #34 BLOCKs and audits requests whose `environment` is missing or not a valid
Environment value. A NOT NULL enum column (with CHECK, #4) cannot store those rows.
Resolved: `environment` becomes NULLABLE, same convention as the four FKs
(null = the submitted value did not resolve to a valid Environment). The unparsed value is
still preserved in `raw_request`. Same migration as #32; no new table.

## 40. Phase 7 Stage 2 -- MCP Route and McpClient Details Left Open by #37
- Token: `MCP_INTERNAL_TOKEN` is read from the environment at REQUEST time, never
  cached. Missing header, wrong token, unset env var and EMPTY env var all return
  the same HTTP 403 body `{"detail": "Forbidden."}` (fail closed, no info leak). An
  empty token is explicitly rejected: `compare_digest("", "")` would otherwise be
  True. Comparison is `hmac.compare_digest` on UTF-8 bytes, so a non-ASCII header
  cannot raise a TypeError.
- Ordering: the token check is a route dependency, so it runs before body-schema
  errors. Only an unparseable JSON body can still produce a 422 before the 403.
  Accepted: it leaks nothing but "this route exists".
- Arguments mirror the Gateway route: `service_name` and `environment` are popped
  from `arguments`; missing or invalid -> 422. Extra keys named `db` or
  `tool_name` -> 422, because they would collide with `execute_tool()`'s own
  parameters and raise a TypeError (HTTP 500).
- Status mapping: pydantic ValidationError -> 422; MCPError -> 400; anything else
  -> 500 with nothing committed. Success -> `{"result": <execute_tool dict>}`; that
  dict already has its own "result" key, so callers see `body["result"]["result"]`,
  the same nesting the Gateway route returns today.
- `McpClient.execute()` returns `McpResponse(status_code, body)`, mirroring
  `GatewayClient`. It raises `McpUnavailableError` for transport errors and when
  no token is configured (nothing is sent). Stage 3 maps BOTH a non-200 response
  and `McpUnavailableError` to `execution_status=failed` + HTTP 502 (#34).
- An empty `MCP_BASE_URL` counts as unset (`or` default), because `.env.example`
  ships it empty.
- Stage 2 does not change the Gateway route: it still calls `execute_tool()`
  in-process. Until Stage 3 the new route is live and token-protected but unused,
  so FR-15 is not yet enforced on the Gateway path.

  ## 41. Phase 7 Stage 3 -- Gateway Pipeline Details Left Open by #34-#38
- Layout: `gateway/pipeline.py` holds `GatewayRequest`, `Verdict`, `evaluate()` (read-only)
  and `handle_tool_request()` (evaluate -> audit -> MCP -> response dict). `api/gateway.py`
  only parses, calls it, and maps `DuplicateRequestError` -> 409, `ExecutionFailedError` -> 502.
  `raw_request` is the validated body re-serialised (`agent_id` null and `arguments` {} if omitted).
- Identity: user is checked first, then agent; the stage short-circuits. FKs record only what
  resolved before the first failing stage (unknown user -> user_id AND agent_id NULL). `users`
  has no status column, so only "unknown user" exists. An agent whose status != "active" is a
  BLOCK. Agent lookup is `ORDER BY id ... first()` because `agent_name` is not UNIQUE (#33).
- Arguments: `environment` is recorded on the audit row as soon as it parses to a valid
  Environment, even if a later check fails. `service_name` is checked first for the reason text.
- Reserved argument keys (`db`, `tool_name`) are a Gateway BLOCK. The MCP route rejects them
  with 422 (#40), so without this an ALLOWED request would fail predictably at execution.
  The constant is duplicated in `gateway/validation.py` on purpose: the Gateway does not
  import `app.api.mcp`.
- Reasons name their stage. Values from the request are echoed via truncated `repr()` (70
  chars) so control characters cannot reach a Text column. The placeholder policy reason is the
  unchanged Phase 5 text and carries no "stage" prefix.
- Order is fixed (#34): the service stage precedes the policy stage. Observable change from
  Phase 5: production for a service that has no production row is a Service-stage BLOCK.
- Duplicate request_id: IntegrityError -> rollback -> if a row with that id exists, 409;
  otherwise the error is re-raised (never misreported as a duplicate). The pipeline may run
  before the insert fails, but MCP is never reached on a duplicate.
- ALLOW rows keep `reason` NULL (#32 requires a reason only for BLOCK).
- MCP failure: any non-200 response or `McpUnavailableError` -> `execution_status=failed`
  + HTTP 502. Known limitation: a timeout after MCP already ran is also recorded as failed
  (outcome unknown). Any other unexpected exception propagates (500) and leaves the row
  `not_executed`.
- Tests: `tests/conftest.py` gets an autouse MCP seam (random token + `get_mcp_client`
  override), a get-or-create `ag001_agent`, and `test_service_production`. `test_service`
  teardown deletes audit rows referencing its user/services before deleting them.

  <!-- APPEND to docs/decisions.md, after #41. Written BEFORE code (standing rule). -->

## Phase 8 Decisions -- Authentication, Identity, Policy, Ownership, Environment

## 42. Login Endpoint and JWT Scheme
Section 17 lists no login route; FR-01/Section 22/Section 19 require real authentication.
Resolved: add `POST /api/auth/login` (`{username, password}` -> `{access_token,
token_type, expires_in}`) in `backend/app/api/auth.py`. No registration, refresh,
logout, reset or lockout. Recorded here only; the planning doc is not edited (#14 precedent).
- Library: PyJWT, HS256, `algorithms=["HS256"]` pinned on decode (rejects `alg=none`).
  Requires `exp` and `sub`. python-jose is in requirements.txt but unused; not removed.
- Secret: `JWT_SECRET` (the existing `.env.example` key). Read at REQUEST time, never
  cached (as #40). Unset, empty, shorter than 32 chars, or equal to "changeme" -> fail
  closed: login returns HTTP 503 `{"detail": "Authentication is not configured."}`;
  the Gateway BLOCKs with "Authentication stage: authentication is not configured.";
  chat returns 503. Generate the secret locally; never commit it.
- Claims: `sub` = username, `iat`, `exp`. NO role claim: the Gateway reads
  `users.role` from the DB on every request. Expiry 60 minutes, no refresh.
- Login failure: one generic 401 body for unknown user and wrong password; unknown
  users verify against a dummy hash to even out timing. Login attempts are not
  audited in `security_requests` (keyed by tool-request `request_id`).
- Limitations (state in report): no brute-force protection; no token revocation
  (`users` has no status column, #41), bounded only by expiry.
- Rejected: RS256 (key management, single process), refresh tokens (scope).

## 43. Password Hashing and Seed Passwords
- Library: `argon2-cffi`, default parameters. Fallback `bcrypt` only if the Windows
  install fails. passlib rejected (unmaintained).
- `users.hashed_password` is String(255): argon2 fits, NO migration.
- `seed.py` reads `SEED_USER_PASSWORD` from the environment. No password appears in
  code, tests or `.env.example` (key name only, empty value). If unset: users are
  created with an unusable non-argon2 hash (login impossible) and a warning is printed.
- Existing users whose hash does not start with `$argon2` (the Phase 3 placeholder)
  are upgraded when the variable is set; valid argon2 hashes are NEVER overwritten.
  Deliberate asymmetry with seed.py's skip-only pattern, same as `seed_tools` (#11).
- One shared dev password for all seeded users: acceptable for a sandbox, stated as a
  limitation. Tests hash random per-test passwords with the real hasher.

## 44. Identity Propagation (supersedes the trust posture of #19 and #29)
- `/api/chat` requires `Authorization: Bearer <jwt>`; `user_id` is removed from its
  body (extra body fields are ignored, never read). Missing/invalid -> HTTP 401.
- The agent forwards the same token to the Gateway via `GatewayClient`. The token is
  never put in prompts, conversation history or `raw_request`.
- The Gateway verifies the token itself and trusts nothing from chat. The Gateway body
  keeps `user_id` (Section 17 shape) as a CLAIM that must equal the token `sub`; a
  mismatch is a BLOCK at the Authentication stage. The acting identity is always the
  token subject, and the role is always read from the DB.
- Audit FKs: auth failures (missing/invalid/expired token, unknown subject, not
  configured) record user_id and agent_id NULL. On a VALID token with a mismatched
  `user_id` claim, `user_id` records the AUTHENTICATED user's id, agent_id stays NULL
  (agent stage not reached), and the claimed value stays in `raw_request`.
- Conversation history is keyed by the authenticated username (fixes #29's
  cross-user write hole); still process-local, last 20 messages.
- `agent_id` stays the hardcoded "AG001" (#19): identified, not authenticated
  (Section 8: "authenticate the developer and identify the agent"). No agent credential.
- Limitations (state in report): the agent holds the user's token, so a compromised
  agent acts as that user, bounded by that user's permissions; anyone with a valid
  token can call the Gateway directly claiming AG001 and gains no permissions by it;
  UNAUTHENTICATED callers can write BLOCK audit rows and occupy request_ids (no rate
  limiting, no cleanup).

## 45. Pipeline Order, Authentication Failures and Reason Wording
Order (Section 8, as #34): Authentication -> Agent identification -> Tool registry ->
Arguments -> Service -> Ownership -> Policy. "Environment permission" is the
environment column of the policy row (Section 11 Step 1), not a separate stage.
- Authentication failure at the Gateway is a BLOCK decision (HTTP 200, audited), per
  Section 11 Step 1; a 401 would hide it from E1/E4 decision counts. 401 is used only
  by `/api/chat` and `/api/auth/login`, where no Gateway decision exists.
- Reasons (values via truncated `repr()`, #41): "Authentication stage: missing bearer
  token." / "...invalid token." / "...token expired." / "...token subject is not a
  known user." / "...request user_id does not match the authenticated user." /
  "...authentication is not configured."
- Agent-stage reasons keep their existing "Identity stage:" text, minus "unknown user".
- "Ownership stage: user 'x' is not assigned to 'svc' in 'env'." (owner not named.)
- "Policy stage: role 'r' is not permitted to use 'tool' in 'env'."
- Tool/Arguments/Service reasons unchanged. The Phase 5 placeholder reason is retired.
- Consequence for Demo 3: no junior owns a production row, so "junior deploys to
  production" blocks at Ownership. Use junior_developer_1 + deploy_service +
  notification-service STAGING to show a Policy-stage block.
- Rejected: Policy before Ownership (deviates from Section 8 for a cosmetic gain).

## 46. Policy Matrix and Storage
Default-deny: only permit rows are stored; no matching row = deny. S=staging,
P=production.
- junior_developer: get_logs S,P; get_metrics S,P; restart S. (5 rows)
- senior_developer: get_logs S,P; get_metrics S,P; restart S,P; rollback S,P;
  deploy S; deploy P with approval flag. (10 rows)
- admin: all five tools S,P; deploy P with approval flag. (10 rows)
Total 25. Junior reads are permitted in both environments (Section 9 states no
environment limit; ownership gates them). ONLY production deploy carries the
approval flag (Section 11 Step 2 example). Flagging every production mutation would
make rule/ML risk irrelevant for production and gut E2 and Production Protection Rate.
- Seed reconciles: `seed_policies` makes the table equal this matrix (inserts missing,
  updates the flag, DELETES rows outside it) so a stale permit cannot survive a matrix
  change. Safe to run in tests because it converges to the same set.
- Storage shape: [PENDING -- confirm at Stage 1 start by reading the policies model.
  If an approval-flag column already exists, no migration. If not, ONE migration
  adds `requires_approval` Boolean NOT NULL default false. No `service_id` (#3).]

## 47. Service Ownership
- "Assigned" = `services.owner_id == authenticated user.id` for the specific
  (service_name, environment) row. Separate stage in `gateway/ownership.py` (#3);
  applies to all five tools (Section 9 clarification).
- Admin does NOT bypass ownership (Section 9: "any role + unassigned service -> BLOCK").
  Cost: admin cannot act on rows owned by others (auth/payment staging); admin's role
  is approvals in Phase 11.
- Consequence of #8: the only non-admin production row is notification-service/
  production (senior_developer_1). E1/E4 generate programmatic traffic; #8 unchanged.

## 48. Approval-Bound Cases Before Phase 11
A permitted policy row with the approval flag set is a fail-closed BLOCK at the Policy
stage: "Policy stage: 'tool' in 'env' requires human approval; the approval workflow
is not implemented yet (Phase 11). Request blocked." Phase 11 turns this branch into
APPROVAL_REQUIRED (Section 11 Step 4, first row); its tests change then, as in #34.
INTERIM STATE (record in STATUS.md): until Phase 9/11, senior_developer and admin
production restart and rollback on rows they own are ALLOW (mock state only). Do not
read Phase 8-10 results for those cases as final.
- Rejected: ALLOW (unsafe), omitting the rows (loses Phase 11 input).

## 49. Phase 8 Tests and Fixtures
- conftest.py: autouse random `JWT_SECRET` seam (as the MCP token seam); `make_user(role)`
  with a random per-test password hashed by the real hasher; `auth_headers(user)` issues
  a token directly (not via login); autouse idempotent `seed_policies`.
- Stage 2 migrates every Phase 5-7 Gateway/chat test to bearer tokens (placeholder
  policy still in force, so production tests keep the placeholder reason). `_FakeHttp.post`
  gains `headers=None`. Stage 3 rewrites the placeholder tests against role/ownership/policy.
- New groups: login; token failures (missing, invalid, expired, alg=none, unconfigured);
  spoofed `user_id`; ownership on read and write tools; the full 3x5x2 matrix; the
  approval-bound BLOCK; the audit row for an auth failure; two agent tests for Gateway
  HTTP 502 and 409 (the open STATUS.md item).
- Tests share the dev DB (#41), so seeds used by tests must stay convergent.

## 50. Policies Table Storage Shape (resolves the PENDING note in #46)
The `policies` model already has `tool_id` (FK), `role`, `environment`, `action`
String(32) NOT NULL, `allowed` Boolean NOT NULL and `requires_approval` Boolean NOT
NULL. NO migration is needed for Phase 8.
- Only rows with allowed=True are stored. The Policy-stage lookup MUST require
  allowed=True; no matching row = deny. Seed reconciliation deletes any row outside
  the #46 matrix, including allowed=False rows.
- `action` is set to the tool name (same value as `tools.tool_name`): `tool_id`
  already identifies the tool and no separate action vocabulary exists.
- `seed_policies` resolves `tool_id` by tool_name and requires the tool registry to be
  seeded first. A missing tool raises a clear error; it never creates tool rows.
- Stage 1 puts this in `seed.py` (`SEED_POLICIES`, `seed_policies`), run by
  `python -m app.database.seed`.

  ## 51. Phase 8 Stage 2 -- Identity Wiring Details Left Open by #42-#45
- Token extraction: `Authorization: Bearer <token>`. Any other scheme (Basic, ...), an
  empty token or no header counts as "missing bearer token". Helper module
  `backend/app/api/deps.py` (flat, #38): `get_bearer_token` (shared by the Gateway and
  chat routes) and `require_caller` (chat only).
- Gateway: the missing-token check runs BEFORE the "not configured" check, so a request
  with no token is always "missing bearer token". Auth BLOCKs are HTTP 200, audited.
- Chat (`require_caller`): signature + exp + the subject must exist in `users` (one read
  query, session rolled back immediately so no connection is held during the agent turn).
  Missing/invalid/expired/unknown subject -> one generic 401 `{"detail": "Not
  authenticated."}`; unconfigured JWT_SECRET -> 503. No LLM call happens on 401/503.
- `GatewayRequest` gains `token` (repr=False). The token is never put in `raw_request`,
  reasons, logs, prompts or history. `Caller.token` is also repr=False.
- `resolve_identity(db, token, claimed_user_id, agent_name)` replaces the Phase 7
  function (same name, no username lookup). `IdentityResult` carries the `User` row so
  Stage 3 (ownership/policy) needs no second lookup; `user_id` is a property.
- Reasons: "Authentication stage: ..." per #45. The Phase 7 "Identity stage: unknown
  user." no longer exists; agent-stage texts are unchanged.
- `GatewayClient.submit(tool_request, token=None)` sends the Bearer header; the agent
  receives the token from chat (`handle_message(..., token=...)`).
- Stage 2 keeps the placeholder policy (BLOCK if production). Any authenticated user
  can still act on any staging service until Stage 3 adds ownership and policy.
- Tests added with this stage: the two agent tests for Gateway HTTP 502 and 409 from
  #49 (the open STATUS.md item), plus token-forwarding and history-isolation tests.

  ## 52. Phase 8 Stage 3 -- Ownership and Policy Stage Details Left Open by #45-#48, #50
- Ownership: `gateway/ownership.py::check_ownership(db, user, service_id, service_name,
  environment)` returns a BLOCK reason or None. It loads the Service with `db.get` (already
  in the session identity map after the service stage, so no extra query) and compares
  `owner_id` to the authenticated user's id. A missing row fails closed, same reason.
- Policy: `gateway/policy.py::check_policy(db, role, tool_name, environment)`. The role comes
  from the users row (never the token, #42/#44). The lookup joins `policies` to `tools` by
  tool_name and requires allowed=True. No row -> "not permitted". If several allowed rows
  match (the table has no UNIQUE constraint) and ANY has requires_approval, the
  approval-bound BLOCK wins (fail closed). `action` is not consulted (#50).
- Reasons exactly as #45/#48: role and environment in single quotes; user, service and tool
  via truncated repr (#41). `_q` is imported from gateway/validation.py, not duplicated.
- The placeholder (`evaluate_placeholder_policy`, `PLACEHOLDER_PRODUCTION_REASON`) is deleted.
- Final Phase 8 order: Authentication/agent -> Tool -> Arguments -> Service -> Ownership -> Policy.
- Tests: conftest gains a session-scoped autouse `seed_policies` (converges to the same set,
  #46). The placeholder-production tests are rewritten to use deploy_service in production
  (approval-bound BLOCK, #48), because production restart is now ALLOW for an owning
  admin/senior (interim, #48). New `tests/test_gateway_policy.py`: the 3x5x2 matrix against
  3 throwaway services (one per role, each owning a staging and a production row), ownership
  on read and write tools, admin no-bypass, ownership-before-policy, role read from the DB,
  fail-closed duplicate policy rows. The Stage 2 test that expected a non-owner ALLOW now
  expects an Ownership BLOCK naming the token subject.
  
  Phase 9 Decisions -- Rule-Based Risk Engine
53. rule_risk_level Assignment

Fixed level per condition (Section 10, 11 Step 2); highest simultaneous level wins; final = max(rule, ml) unchanged. Baseline LOW; only these rows raise it:

LOW: every read in any env (exempt from all rows below); owned, permitted staging restart/rollback/deploy. Tool sensitivity (#1) does not set the level directly.
Production targeting, state-changing: restart = MEDIUM; rollback, deploy = HIGH.
Policy requires_approval flag = HIGH (recorded for Phase 11; unreachable now, #48).
Repeated denials (#57) = MEDIUM; S1 = MEDIUM; S2 = HIGH; S3 = MEDIUM (#56). Why: Step 4 sends MEDIUM+ to approval, so ML changes outcomes only where rule level is LOW; Scenario B/Demo 2 need an owned staging restart to ALLOW. Rejected: sensitivity 1:1 (gates every staging restart); production reads MEDIUM. Limitations: after Phase 11 every production state change goes to approval (closes the STATUS interim state); who approves an admin's own request is a Phase 11 Step 0 item; reads never escalate on rules. Status: conditions locked by plan; levels new.
54. Sensitivity Mapping -- Staging Rollback/Deploy Stay LOW

Sensitivity (#1: rollback/deploy HIGH) raises rule level only together with production targeting (#53). A staging rollback/deploy on an owned row is LOW. #1 is unchanged: the tools.sensitivity column stays HIGH; it is an input, not the level. Why: Step 4 maps HIGH non-production to APPROVAL_REQUIRED; HIGH would put every staging deploy behind a human, contradicting Section 9 ("deploy on staging" is a senior permission; only production "may" need approval) and removing ML headroom on the outside-hours deploy and rapid-rollback anomalies Section 23 is built around. Rejected: HIGH or MEDIUM for staging deploy/rollback (same human-gating outcome). Limitations: Section 10's "sensitive tools" narrows to production x sensitivity; ownership, policy and S1/S3 cover staging misuse; the mock is reversible. Phase 15 must not designate production rollback as BLOCK-class "irreversible" -- it is the main mitigation action. Status: new decision (narrows the reading of Section 10).

55. Sliding-Window Key -- Per Identity (effective Phase 10; no window code in Phase 9)

The N = 5 window is the last 5 actions per user_id; service, environment, tool and outcome are per-action features. Rolling time-window counts are per identity too. N = 5 unchanged. Why: Demo 9 / Section 23 (a sequence "across two services" inside the N = 5 window) and FR-08 need a window that can span services; a per-(identity, service, environment) window cannot hold one. "Distinct services touched" is a rolling time-window count and could already be per identity; it is not the conflict. Superseded plan text: Sections 8, 10 and 34 (window per identity/service/environment) and Section 21 FR-08 (states no key; read per identity). Planning doc not edited (#14 precedent); the final report MUST state this deviation. Rejected: per-tuple window (blind to Demo 9); both windows (scope growth, Section 31). Limitations: an identity with two owned rows gets mixed windows, diluting per-row patterns; #56 keeps per-row keys for the Phase 9 rules. Phase 10 Step 0 fixes the per-action record. Status: new decision. Phase 9 rules do not use this window.

56. History Source and Sequence-Rule Keys

History comes from security_requests (not service_state_history, #7). created_at exists: no migration; tests insert explicit created_at. evaluate() reads BEFORE the #35 insert, so a request never counts itself. Executed = ALLOW + execution_status=executed; windows wall-clock.

S1: key (user_id, service_id); 10 min; incoming rollback after an executed deploy.
S3: key (user_id, tool_name, service_id), restart/rollback/deploy; 5 min; >=2 prior executed, so the third escalates.
S2: key user_id (all services/tools); 10 min; incoming state-changing request whose 3 most recent prior requests are all qualifying denials (#57) or ALLOW+failed, none executed. Fires before the incoming outcome is known. Its denial branch is a subset of #57's trigger; S2 adds the ALLOW+failed branch and HIGH (#53). Strictly consecutive: see #62. Limitations: counts/windows uncalibrated -- freeze in one constants module before Phase 16 (later change invalidates E2); S2 evadable by one interleaved executed read; fast synthetic traffic trips S3/#57; S1 flags a user rolling back their own bad deploy. Rejected: service_state_history, new table. Status: patterns locked by plan; keys/counts new.
57. Repeated Denials

A denial = Ownership- or Policy-stage BLOCK of the AUTHENTICATED user. Filter on security_requests: decision = BLOCK AND user_id, tool_id, service_id all non-null; given the pipeline order (#45, #52) and FK rules (#41, #44) only those two stages match. A test asserts matched rows also carry the "Ownership stage:" / "Policy stage:" reason prefixes. Trigger: >=3 such rows (any tool) for the user in the prior 10 min, incoming request state-changing: MEDIUM (#53). Not counted: Authentication BLOCKs (user_id NULL), claimed user_id in raw_request (never used -- else an unauthenticated caller could raise a victim's risk, #44), mismatched-claim rows (service_id NULL), Tool/Arguments/Service BLOCKs (malformed-args noise), ALLOW+failed (counts only in S2). Limitations: #48 approval-bound Policy BLOCKs are counted (miscount until Phase 11); spoofing and unregistered-tool probing feed no Phase 9 signal. Rejected: all BLOCKs; claimed user_id; a blocked_stage column (schema change for one rule). Status: condition locked by plan (Section 10); N = 3, 10 min and stage set are new.

58. risk_assessments Rows and Write Order

Only requests passing every Step 1 stage get a row (Section 11); no row for any BLOCK, including the #48 approval-bound BLOCK (stops at Policy before risk; deviation until Phase 11). evaluate() stays read-only and returns the assessment in the Verdict. handle_tool_request() inserts security_requests then risk_assessments in ONE commit, before any MCP call (#35). decision = the enacted decision (ALLOW in Phase 9); reasons lists triggered condition ids. Duplicate request_id rolls both back: 409 (#36). A FAILED risk write rolls back the audit row too: HTTP 500, MCP not called, no trace of the request (accepted limitation; fails closed). Limitations: until Phase 11, rows with final MEDIUM/HIGH carry decision=ALLOW and reasons gets "interim: not enforced" -- exclude from E5 and Approval Routing Accuracy or regenerate after Phase 11; a risk-write bug fails all ALLOW traffic; no risk evidence for production deploys. Rejected: a row per request (breaks Step 1); separate commit; a would-be decision (fabricates enforcement). Status: Step 1 exclusion locked by plan; write order new (extends #35).

59. ml_risk_level Stub

Until Phase 14, ml_risk_level is a fixed constant LOW from one stub function with no model import. Every risk_assessments row carries "ml=stub" in reasons; final = max(rule, LOW) = rule. Rows from before Phase 14 are excluded from E2. Why: Section 27 Phase 11 ("defaulted to LOW until Phase 14"); the level columns are NOT NULL (#32), so NULL needs a migration. Rejected: NULL; random placeholder scores. Limitations: a stub LOW is indistinguishable from a real ML LOW without the marker; losing the marker contaminates E2 data. Status: default locked by plan; marker new.

60. Response Contract -- No risk_level Until Phase 11

ALLOW stays {request_id, decision, result}; BLOCK unchanged. Supersedes #38's "no risk_level field until Phase 9": the field is not added until Phase 11, with APPROVAL_REQUIRED. Phase 11 Step 0 decides whether it appears only on APPROVAL_REQUIRED or not at all. Why: no consumer (the Phase 6 agent reads only decision/reason/result, #23, #38); tests assert exact key sets; E1-E6 and the dashboard read risk_assessments; an ALLOW showing HIGH during the interim would look like a bug; exposing scores to the agent hands a manipulated LLM a readout of the scoring boundary. Limitations: Section 17's example (with risk_level) deviates until Phase 11; smoke tests must query the database to see risk. Rejected: additive risk_level on ALLOW now. Status: new decision (#14 precedent).

61. E2 and Demo 7 Wording

Lateral movement onto an unowned service is an Ownership BLOCK (Section 11 Step 1): deterministic, not evidence for the ML. Demo 7 as written (one identity, three services) cannot succeed for any seeded identity (#8, #47): senior_developer_1 owns auth staging + notification production; admin owns auth + payment production; junior_developer_1 and senior_developer_2 own one row each. Rewrite Demo 7 as rapid alternation across one identity's two owned rows plus a separate denied attempt on a third service. Phase 10 may log blocked attempts (outcome=blocked) as features; they never change a Step 1 BLOCK, and E2 excludes Step-1-blocked requests (E1/E4). E2 reports separately (Section 10): (a) permitted-scope rule-catchable (S1-S3, denials); (b) permitted-scope ML-only. Production state-change outcomes are rule-driven (MEDIUM and HIGH both route to approval, Step 4, unless Phase 15 designates BLOCK rows); ML's outcome-changing room is LOW-rule actions: reads and owned staging state changes. Limitations: "distinct services touched" maxes at 2 (1 for two identities) -- weak feature; E2 positives are limited to three owned staging rows + reads; Section 15's "Ownership + ML" row overstates the ML role. Status: new decision (wording only; plan unchanged).

62. S2 Run Is Strictly Consecutive (refines #56)

S2 looks at the user's 3 most recent prior security_requests rows inside the 10-minute window, of ANY kind. It fires only if all 3 qualify (a #57 denial, or ALLOW + execution_status=failed). Any other row between them -- an executed request, a Tool/Arguments/Service BLOCK, a mismatched-claim row -- breaks the run. Both the denial filter and the qualifying test are built from one shared SQL expression (gateway/risk.py), so S2 and #57 cannot drift apart. Why: skipping noise rows needs a second stage allow-list that could diverge from #57's structural filter; a broken run costs only a false negative, and #57 still catches the non-consecutive case at MEDIUM. S2 is the "tight burst" signal (HIGH), #57 the "sustained" one. Rejected: skipping non-qualifying noise rows (extra filter, extra drift risk). Limitations: an LLM that malforms one argument set mid-run, or an attacker interleaving one read, resets S2. Accepted and listed in the report. Status: new decision (refines #56).

## 63. Phase 9 Stage 2 -- Wiring Details Left Open by #58
- evaluate() stays read-only: after Policy passes it calls assess_risk() and returns it as
  Verdict.risk (None for every BLOCK). ToolCheck gains `sensitivity` (default None, set on the
  usable-tool path) so the engine reads the registry value (#1, #11), not a copy in risk.py.
- requires_approval is passed as False: an approval-bound policy row BLOCKs at Policy before
  risk is reached (#48). Phase 11 feeds the real flag when that branch becomes APPROVAL_REQUIRED.
- audit.record_decision() owns BOTH inserts and the single commit (#58). IntegrityError keeps
  the #36 duplicate handling (rollback, then 409 only if the row exists). Any other exception
  rolls back explicitly and re-raises (HTTP 500, MCP never reached).
- Interim marker: reasons gets "interim: not enforced" only when decision=ALLOW and final risk
  is MEDIUM/HIGH; LOW rows stay clean so E5/Approval Routing filters can key on it.
- Test rule: risk_assessments.request_id is a FK, so EVERY test teardown that deletes audit
  rows must go through tests/qa_cleanup.py::delete_requests(). A new raw delete of
  security_requests in a test will fail with an FK error once a risk row exists.
Limitations: a bug in risk computation or the risk write fails ALL allowed traffic (500) --
accepted (#58); production-deploy attempts still leave no risk evidence until Phase 11.
Status: new decision (implementation detail; no plan change).

Phase 10 Decisions -- Behavior-Event Logging and Synthetic Generation
64. Scope -- Normal-Behavior Generator, On Demand

Planning Phase 10 says "continuous synthetic generation". Resolved: a seeded, deterministic, on-demand CLI producing NORMAL behavior only; no daemon or scheduler. Anomalous/staged categories, labels and sequence ids are Phase 13 (Section 27). Why: Section 23 trains Isolation Forest primarily on normal data. "Accumulate early" only binds LIVE rows (the live hook, #70, is what cannot be backfilled; service_state_history must not be used to derive it, #7). Seeded rows with explicit timestamps can be generated any time. Phase 10 adds no ML, no APPROVAL_REQUIRED, no response-contract or Phase 9 change. Limitations: reads "continuous" loosely; the report says so. Rejected: daemon; anomalies now (labels need a schema Phase 13 owns). Status: new decision (interpretation of Phase 10 wording).

65. source Marker

New column behavior_events.source: Python enum EventSource {live, synthetic} + CHECK ck_behavior_events_source (#4), NOT NULL, server default 'live'. Why: #59 (a lost marker contaminates data); also makes the generator purgeable. Constraint for Phase 13/14: training reads source='synthetic'; inference windows (#55) read source='live' only, so a live Demo 9 window is never padded with old synthetic rows. Rejected: request_id IS NULL as an implicit marker; separate synthetic users (owner_id is a single FK, #8). Status: new decision.

66. Per-Action Record (resolves Phase 10 Step 0 item 1; uses the real columns)

Columns as built: identity_id (= users.id, the #55 window key), agent_id (NOT NULL; live = resolved agent row, synthetic = the AG001 row, generator fails clearly if missing), service_id, environment (from the service row), tool_id, outcome, timestamp, version_before/after, off_hours_flag. Added by #75: source, request_id. The N = 5 window is a query: last 5 rows per identity_id ordered by (timestamp, id); no window column. EventOutcome gains failed; pending stays unused until Phase 11. Mapping: ALLOW executed = allowed; ALLOW + MCP failure = failed; Ownership/Policy BLOCK = blocked. version_before/after are copied from the MCP result dict for deploy and rollback only; NULL for reads, restart, blocked and failed. If the dict lacks them for deploy/rollback: store NULL, log a warning (fail-open, #70); a test on the real MCP seam asserts non-null. The writer always sets timestamp explicitly (never server_default) so timestamp and stored flag share one instant. Rejected: stored delta; window/sequence-id columns. Status: field set locked by plan (Sections 10, 16); mapping/NULL rules new.

67. off_hours_flag -- Stored, One Pure Function

The column exists NOT NULL ("computed at write time, stored"). is_off_hours(ts) is pure: fixed UTC+5 (no zoneinfo/tzdata dependency on Windows), working hours 09:00 <= t < 18:00 local, all seven days. Constants live in one module and are FROZEN before Phase 16 (a later change invalidates E2). add_behavior_event() calls it for BOTH live and synthetic rows and stores the result; callers cannot pass the flag. Why: Section 10; one code path prevents live/synthetic drift. Limitations: late-night live testing is flagged off-hours (harmless, live rows are not training data, #65); changing the window later needs one UPDATE recomputing flags from timestamp. Rejected: derive-at-read; zoneinfo; weekend logic. Status: new decision.

68. version_change_delta -- Derived; Normal Deploy = current+1

Not stored: |version_after - version_before| at feature time, NULL treated as 0. deploy_service accepts an arbitrary positive target_version (actions.py); normal deploys use current+1 (Section 13 counter) and a large jump is the anomaly signal. The generator emits only transitions the real mock can produce (no train/serve skew). Phase 13 gate: with large-jump anomalies, check that the feature value moves AND that the Isolation Forest score moves (ablation: score with vs without the feature). Why: [Likely] sklearn IF splits inside the training range, so a value beyond the max isolates no faster than the max; with normal delta in {0,1}, a jump of 50 may score like a normal deploy on that axis. Fallbacks if no lift (Phase 13, not now): jitter normal target to +1..+2, or drop the feature. Status: new decision.

69. Which Live Requests Are Logged (Step 0 item 3, #61)

Log iff the request has an authenticated user and a resolved agent, service and tool (the #57 structural filter). ALLOW executed -> allowed; ALLOW + MCP failure/unavailable -> failed; Ownership/Policy BLOCK -> blocked. Not logged: Authentication BLOCKs, mismatched-claim rows, Tool/Arguments/Service BLOCKs, 409, unexpected 500. Logging never changes a decision (#61); Step 1 BLOCKs stay excluded from E2. Limitations: until Phase 11, #48 approval-bound production-deploy BLOCKs log as blocked (same miscount as #57); Phase 11 remaps them to pending, and pre-Phase-11 live rows of that kind are not training data. Status: permitted by plan (#61); stage set new.

70. Live Write -- Own Commit, After the Outcome, Fail-Open

After the final outcome the pipeline calls add_behavior_event() and commits SEPARATELY from the #58 audit commit. BLOCK: after the audit commit. ALLOW: after the execution_status update, before returning; the 502 path logs failed before raising. Any exception: rollback, warning log, response unchanged. Timestamp is captured at pipeline start; request_id links the row (#75). Why: outcome and versions do not exist pre-MCP; telemetry is not audit evidence (security_requests is), so unlike #58 a write bug must not fail traffic. Limitations: a swallowed failure leaves a window gap (under-detection; a test asserts a failing writer still returns the normal response and logs); one extra INSERT+COMMIT per request, E3 must measure it; the pinned history-query-count test counts only assess_risk queries and is unaffected. Rejected: inside the #58 commit; BackgroundTasks; a test-only disable flag. Status: new decision (extends #35/#58).

71. Generator Path

Direct inserts through the shared add_behavior_event(), not through the Gateway. Why: security_requests.created_at is DB-set, so explicit/past timestamps are impossible via the Gateway; it would also pollute the history S1/S2/S3/#57 read (#56) and mutate mock state. CLI under backend/ml/data/ (Section 28) with --seed, --anchor, --days. A re-run purges source='synthetic' rows of the identities BEING GENERATED, then regenerates, in one transaction; live rows are never touched. Tests share the dev DB (#41, #49): generator tests use throwaway identities/services (make_user pattern) and must never purge the real synthetic set; the CLI targets the four seeded users. Limitation: synthetic events skip Gateway validation; the #72 test compensates. Status: new decision.

72. Identities and Scope

Profiles are keyed by ROLE and the identity's owned (service, environment) rows read from the DB, not by username. Only owned rows (#47), only tools the seeded matrix permits (#46), no production deploy (approval-bound, #48), rollback only when simulated current > known_good. A test asserts every generated action is owned and permitted against the seeded matrix. No new users/services (#8). Limitations: 4 identities, 6 rows; junior and senior_2 own one row each, so "distinct services" is weak (#61); synthetic precision/recall are optimistic (Section 23 limitation applies). Status: new decision.

73. Normal Data Avoids Rule-Catchable Patterns by Construction (Step 0 item 2, #56)

Phase 9 rules read security_requests, never behavior_events, so direct inserts cannot trip them. Spacing is for label hygiene: normal data must not contain named S1/S2/S3/#57 patterns (Section 10 division; E2 split). Rule: any two state-changing actions of one identity are spaced by more than the largest window IMPORTED from risk_constants.py (not copied), with jitter; blocked/failed events are rare and isolated (at most one per identity per interval longer than the #57 window), so S2/#57 cannot arise. Reads may be dense. One test asserts the minimum gap against the imported constant. Rejected: a second in-memory implementation of S1-S3/#57 (drift). Limitation: normal destructive actions look more regular than real usage. Status: new decision.

74. Timestamps, Volume, Version Simulation

Explicit UTC timestamps; --anchor never defaults to "now" (reproducible). Default 30 days; activity inside the #67 working window plus about 3% off-hours events, reads only, never state changes. Target a few thousand events; final volume is a Phase 13 call. Per-service simulated (current, known_good) counters start at (1,1) and follow #9 (deploy: known_good = current, current = target; rollback: current = known_good). A parity test replays one sequence through the real actions.py functions (db, service) on a throwaway service and asserts equal versions. Limitation: the simulator duplicates #9 logic; the parity test is the drift guard. Status: new decision.

75. Migration and Test Impact

ONE migration (revises the current head; Stage 1 confirms with alembic heads): (a) source + CHECK (#65); (b) request_id String(32), nullable, FK -> security_requests.request_id (the Section 16 clarification names request_id as the join key; synthetic rows are NULL); (c) drop and recreate ck_behavior_events_outcome as {allowed, blocked, pending, failed}. No new table (11 stays). Downgrade first deletes failed rows (regenerable telemetry), or restoring the old CHECK fails. Index deferred to Phase 13/14. Test impact: live events FK-reference security_requests, so tests/qa_cleanup.py::delete_requests() deletes behavior_events (same request_id subquery) BEFORE risk_assessments/security_requests (#63 lesson); any raw security_requests delete in a test fails once an event row exists. Status: request_id locked by plan; rest new.

76. Phase 10 Stage 1 -- Implementation Details Left Open by #64-#75

Settled while coding Stage 1; recorded before commit, not before the first line (process slip).

Writer: add_behavior_event(db, *, identity_id, agent_id, service, tool, outcome, timestamp, ...) takes the Service and Tool OBJECTS (environment and tool_id come from them, #66). It does not flush or commit. It raises ValueError on a naive timestamp, and on versions for anything other than an ALLOWED deploy_service/rollback_deployment (#66). Live NULL-versions-with-warning (#66) is the caller's fail-open path (Stage 2), so the writer accepts (None, None) for those tools.
Generator: ONE per-identity schedule feeds every non-read event (executed, failed, blocked), so the #73 spacing holds across all of them. Per local day: 8-20 reads (~3% off-hours); 0..N state slots (N = 1 junior, 3 senior, 2 admin); each slot is 5% blocked, 1% failed, else executed. Blocked = an Ownership or Policy denial only (not owned, or tool absent from the matrix); owned approval-bound pairs are excluded (Phase 11 makes them pending, not denials). Failed leaves the simulated state unchanged. Tool weights restart 6 / deploy 3 / rollback 1 (rollback only if current > known_good). Reads 55% get_logs / 45% get_metrics.
RNG: random.Random(f"{seed}:{username}") per identity, so adding an identity never changes another's data. Window = [anchor - days, anchor); local days are UTC+5 midnights (#67). Defaults: --seed 42, --days 30; --anchor is required.
generate_normal_events(db, *, seed, anchor, days, usernames=None, service_ids=None): service_ids restricts the universe (tests use throwaway services). The simulator starts at (1,1) and never reads the services table.
Tests: tests/qa_cleanup.py gains delete_behavior_events(); delete_requests() is UNCHANGED in Stage 1 (it gains the live-event delete in Stage 2, #75). A generator test fixture must depend on make_user so it tears down (events, history, services) before the users are deleted.
Known property (state in report): executed state changes are ~6.6% of events (about 18-39 per identity per 30 days); rollbacks are rare (3 in 30 days). Restart/deploy-frequency features are sparse on normal data. Volume/mix is a Phase 13 call (#74). Status: new decision (implementation detail; no plan change).
