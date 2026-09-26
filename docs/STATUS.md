# Security Gateway FYP — Project Status

## Current Phase
Phase 4 — MCP Server and Five DevOps Tools

## Completed
- Phase 1 — Project setup and repository structure
- Phase 2 — PostgreSQL schema, SQLAlchemy models, Alembic migrations
- Phase 3 — Stateful Mock DevOps Environment

## Current Repo State
- Last verified commit: `<FILL IN AFTER PUSH — run: git log --oneline -5>`
- Planning version: Revision 6
- Phase 1, Phase 2, and Phase 3 are complete.
- Database schema and migrations are implemented and verified (11 tables
  as of Phase 3 — see `docs/decisions.md` #7).
- Seed data (4 users, 6 services) is implemented, idempotent, and
  verified against `docs/decisions.md` #8.
- Service state mutation (restart/rollback/deploy) and history logging
  are implemented in `backend/mock_devops_env/services/actions.py` and
  covered by unit tests in `tests/`.

## Verify First
Before trusting this file, `git log --oneline -5` and confirm the
latest commit matches "Last verified commit" above.

## Phase 3 Summary (complete)
What was built:
- `service_state_history` table — unified restart/rollback/deploy log
  (`docs/decisions.md` #7).
- Seed script (`backend/app/database/seed.py`) — 4 users, 6 services,
  ownership mapping locked in `docs/decisions.md` #8.
- Mutation logic (`backend/mock_devops_env/services/actions.py`) —
  `restart_service()`, `rollback_deployment()`, `deploy_service()`.
  `known_good_version` semantics locked in `docs/decisions.md` #9.
- Unit tests (`tests/test_seed.py`, `tests/test_restart_rollback.py`,
  `tests/test_deploy.py`) — 11 tests, all passing. Scope note in
  `docs/decisions.md` #10: these are per-phase unit tests, NOT the M8 /
  Phase 17 research evaluation (E1–E6). Do not conflate the two in the
  final report.

What Phase 3 deliberately did NOT include (correctly deferred):
- Simulated log/metric content generation for `get_logs()` /
  `get_metrics()` — these are read-only MCP tools, built in Phase 4.
- Any MCP tool wiring, Gateway logic, auth, or ML — untouched, per the
  Phase 3 Boundary below (still accurate, kept for reference).

## Phase 4 Goal
Build the MCP server and the five registered DevOps tools:
- `get_logs()` — Low sensitivity, read-only. Needs simulated log content
  (not built in Phase 3 — build it here).
- `get_metrics()` — Low sensitivity, read-only. Needs simulated metric
  content (same as above).
- `restart_service()` — Medium sensitivity. Wire to
  `mock_devops_env.services.actions.restart_service()`.
- `rollback_deployment()` — Medium-High sensitivity. Wire to
  `mock_devops_env.services.actions.rollback_deployment()`.
- `deploy_service()` — High sensitivity. Wire to
  `mock_devops_env.services.actions.deploy_service()`.
- Verify state transitions end-to-end through the MCP layer (Section 27,
  Phase 4).
- Tool registry entries (name, schema, sensitivity, enabled) per
  Section 12 / the `tools` table.

## Phase 4 Boundary
Phase 4 is ONLY the MCP server and the five tools.

Do NOT implement yet:
- LangChain agent → Phase 6
- Security Gateway (auth, validation, policy, risk, decision) → Phase 7+
- Authentication/policy/risk logic → Phase 8+
- ML → Semester 2

MCP accepts execution only from the trusted Gateway path in the finished
system (FR-15) — but the Gateway doesn't exist yet (Phase 7+), so Phase 4
tools will necessarily be callable directly for testing purposes. This is
expected and temporary; do not treat it as the final trust boundary.

## Important
- Follow Planning Revision 6.
- Follow `docs/decisions.md` for locked decisions (10 entries as of
  Phase 3 completion).
- Do not reorder, remove, or add phases.
- Do not redo completed Phase 1/2/3 work unless explicitly requested.

## Next Task
Start Phase 4 implementation: MCP server + five tool definitions, per
the Phase 4 Goal above.