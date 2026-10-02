# Security Gateway FYP -- Project Status

## Current Phase
Phase 7 -- Full Security Gateway and request IDs (not started; planning
not begun). Phase 6 is complete.

## Completed
- Phase 1 -- Project setup and repository structure
- Phase 2 -- PostgreSQL schema, SQLAlchemy models, Alembic migrations
- Phase 3 -- Stateful Mock DevOps Environment
- Phase 4 -- MCP Server and Five DevOps Tools
- Phase 5 -- Skeleton End-to-End Path (Single Tool, ALLOW/BLOCK Only, No ML)
- Phase 6 -- LangChain DevOps Agent + LLM Integration

## Current Repo State
- Last verified commit: `90aa16a`
"Docs-only commits (no backend/ changes) do not require a hash update here --
this field tracks the last code-verified commit, not literal HEAD."

- Planning version: Revision 6
- Phase 1 through Phase 6 are complete.
- Database schema: 11 tables, unchanged since Phase 3 (Phase 4/5/6 added none).
- Full suite: 36/36 tests passing (user-verified): 26 from Phase 1-5 plus
  10 new in `tests/test_chat_agent.py`.
- `docs/decisions.md` has 30 entries (#16-#30 cover Phase 6).
- `backend/requirements.txt` regenerated: added `langchain-google-genai==4.4.0`
  (+ `google-genai` etc.); removed unused `langchain-openai`, `openai`,
  `tiktoken` (decisions #16: Gemini, not OpenAI).
- `backend/.env` holds the real `GOOGLE_API_KEY` (git-ignored). Optional
  `GEMINI_MODEL` and `GATEWAY_BASE_URL` (default `http://127.0.0.1:8000`)
  are documented in `.env.example`.

## Phase 6 Summary (complete)
Per Section 27 / Section 6-7: a Python + LangChain agent backed by Gemini
that turns developer messages into structured tool requests and submits
them to the existing `POST /api/gateway/tool-request`. The agent never
imports MCP and never decides anything (Section 5/6).

What was built:
- `backend/app/api/gateway.py` -- the Phase 5 endpoint, moved verbatim out
  of `main.py` into an `APIRouter()` (decisions #25). Logic unchanged; the
  Phase 5 placeholder decision rule is still in place.
- `backend/app/api/chat.py` -- `POST /api/chat`. Generates
  `request_id = uuid4().hex` (32 chars, fits `String(32)`; #20/#27). Sync
  `def` on purpose (#26). `user_id` is an unvalidated placeholder (#19).
- `backend/app/main.py` -- pure bootstrap: `FastAPI()` + `include_router()`.
- `backend/app/agent/` (flat layout, decisions #28; the empty
  `prompts/`, `schemas/`, `langchain_agent/` placeholders were removed):
  `devops_agent.py` (turn loop, history), `tools.py` (specs generated from
  `mcp/schemas.py`, `$ref` inlined for Gemini), `gateway_client.py`
  (HTTP seam to the Gateway, #26), `llm.py` (Gemini factory),
  `prompts.py` (system prompt with NO security rules, #30).
- Turn semantics (#27): max one tool call per turn; ALLOW -> second LLM
  call turns the result into prose; non-ALLOW -> Gateway `reason`/`detail`
  relayed verbatim, no second LLM call; LLM failure after ALLOW returns
  HTTP 200 with an "executed, summary unavailable" reply, never a 5xx.
- Conversation history: in-memory, keyed by `user_id`, last 20 messages
  (#21, #29).
- Tests (`tests/test_chat_agent.py`, 10): all five tool specs present with
  no `$ref`; restart staging ALLOW + history row; restart production BLOCK
  with Gateway reason verbatim and no row; get_logs ALLOW with no state
  change; chit-chat makes no tool request; extra tool calls dropped;
  Gateway HTTP error relayed; per-user history; LLM failure before
  execution -> 502; LLM failure after ALLOW -> 200 + executed notice.
  LLM mocked per #24.

Verification:
- Automated: 36/36 passing.
- Manual smoke test against the real Gemini API (outside pytest, #24):
  chit-chat, get_logs staging (ALLOW), restart staging (ALLOW), restart
  production (BLOCK, reason relayed) all behaved as designed. On the first
  get_logs attempt the post-ALLOW summary LLM call failed and the fallback
  reply was returned; a retry a minute later succeeded. Cause not
  confirmed (traceback not captured; free-tier rate limit is the likely
  explanation).
- Observation: the agent's prose summary of logs contained a copying
  error ("responsefrom"). Agent reply text is not evidence; evaluation
  (Section 25, esp. E5) must rely on Gateway decisions and DB state.

What Phase 6 deliberately did NOT include (correctly deferred):
- Real authentication, identity, ownership, policy -> Phase 8.
- Rule-based risk -> Phase 9. ML -> Semester 2.
- APPROVAL_REQUIRED / human approval -> Phase 11.
- Chat-history persistence (rejected, #21).
- Multi-step / chained tool calls in one turn (#27).

## Open items for Phase 7+
- The Phase 5 placeholder rule (`BLOCK if environment == production`) is
  still live in `app/api/gateway.py`. Phase 8 replaces it entirely; do not
  extend it. The agent calls the endpoint as-is and must not change.
- Demo 8 (prompt injection, Section 29) conflicts with two earlier
  decisions: #11 forbids anomalous log content, and #27 ignores any tool
  call the model emits after a tool result. Resolve before Phase 16/17
  (needs injectable log content, a multi-step loop, and a per-request
  Gateway id scheme -- `request_id` is 32 chars, so sub-ids need design).
- `user_id` is spoofable and history is keyed by it (#19/#29). Phase 8.

## Phase 4 Summary (complete)
- `backend/app/mcp/schemas.py`, `tools.py`, `registry.py`, `server.py`
  (`execute_tool()`, plain importable Python, not HTTP -- #11) and
  `mock_devops_env/logs|metrics/generator.py` (#12). Five tools; sensitivity
  get_logs/get_metrics=LOW, restart=MEDIUM, rollback/deploy=HIGH (#1).
- No auth/policy/risk/ML in `execute_tool()`: calling it means "treated as
  pre-authorized" (FR-15).
- 12 tests in `tests/test_mcp_tools.py`.

## Phase 5 Summary (complete)
- Walking skeleton: `POST /api/gateway/tool-request` with placeholder
  rule `BLOCK if production else ALLOW`; tool-agnostic (#15); request
  contract uses `arguments.service_name` (#14).
- 3 tests in `tests/test_gateway_tool_request.py`, verified via a new
  `service_state_history` row, not by diffing `service.status`.

## Important
- Follow Planning Revision 6.
- Follow `docs/decisions.md` for locked decisions (30 entries).
- Do not reorder, remove, or add phases.
- Do not redo completed Phase 1-6 work unless explicitly requested.
- Anything genuinely undecided mid-implementation gets a new decisions.md
  entry before code, not after.
