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