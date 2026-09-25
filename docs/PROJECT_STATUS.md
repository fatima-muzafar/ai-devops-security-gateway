# Security Gateway FYP — Project Status

**Repo:** https://github.com/fatima-muzafar/ai-devops-security-gateway
**Last verified commit:** `fe9f1c5` ("Fix missing CHECK constraints on enum columns; add decisions.md to docs/")
**Verified by:** pulling the repo directly and reading file contents / diffing against generated originals — not taken on the user's word.
**Planning doc version:** Security_Gateway_FYP_Plan_v6.docx (Revision 6)

## How to use this file

If you are an AI assistant picking this project up in a new chat:
1. Do not trust this file blindly. It records state as of the commit above.
   Between then and now, more commits may exist. **Pull the repo and run
   `git log --oneline -5` before doing anything else** to confirm this file
   is still current. If the latest commit hash doesn't match, treat every
   claim below as unverified until re-checked.
2. Do not re-litigate decisions already made below (see "Locked decisions").
   They were deliberately chosen, not defaults left unexamined.
3. Do not re-flag items in "Known quirks — not bugs." They were investigated
   and confirmed harmless; re-raising them wastes a turn re-deriving the
   same conclusion.
4. Always verify claims against the live repo/DB before telling the user
   something is "done" — this project's working pattern is evidence-based
   confirmation (pull, diff, run `\d table`, run a failing INSERT), not
   trusting a checklist the user pastes in.

---

## Phase 1 — Repo & Environment Setup — COMPLETE

Per Section 28 (repository structure) and general Phase 1 scope (setup only,
no code).

**Delivered:**
- Repo `ai-devops-security-gateway` structure matches Section 28: `frontend/`
  (with `app/`, `components/`, `lib/`), `backend/app/` (with `agent/`,
  `gateway/`, `mcp/`, `approvals/`, `database/`, `api/`), `backend/mock_devops_env/`,
  `backend/ml/`, `tests/`, `docs/` — all present, empty dirs hold `.gitkeep`.
- Python venv gitignored, not committed.
- `backend/requirements.txt` — all 12 required packages present (fastapi,
  uvicorn, SQLAlchemy 2.0.54, alembic, psycopg2-binary, python-jose,
  python-multipart, scikit-learn, langchain, langchain-openai, pydantic,
  python-dotenv).
- `.env.example` committed with placeholders only; `.env` gitignored,
  confirmed via `git log --all --full-history -- backend/.env` returning
  nothing (no secret ever committed).
- `docker-compose.yml` at repo root, Postgres 16, container name
  `devops_gateway_db`.
- Alembic initialized at `backend/app/database/migrations/`, `env.py` loads
  `.env` via `python-dotenv` and overrides `sqlalchemy.url` at runtime.
- Frontend: Next.js + TypeScript + Tailwind + App Router scaffold present.
- `node_modules/`, `venv/` confirmed gitignored and untracked.

**Bugs found and fixed during Phase 1 review:**
- `backend/requirements.txt` was originally UTF-16LE with BOM (classic
  Windows PowerShell `pip freeze` artifact) — would fail to parse on any
  non-Windows machine. Fixed to UTF-8.
- `tests/`, `docs/`, `frontend/components/`, `frontend/lib/` were initially
  missing entirely (not just empty — absent from git). Added with
  `.gitkeep`.

**Commits:** `b075b36`, `b6bc108`, `b898e32` (initial), `1af4bdc` (fixes).

---

## Phase 2 — SQLAlchemy Models (Section 16 + Section 13) — COMPLETE

**Locked decisions (do not re-ask):**
- SQLAlchemy 2.0-style (`Mapped[]` / `mapped_column()`), not legacy `Column()`.
- One model file per table: `backend/app/database/models/{table}.py`.
- **10 tables built**, including `incidents` (Section 16 marks it optional —
  user explicitly chose to include it rather than defer).
- `rollback_deployment` sensitivity = **HIGH**, not "Medium-High" as Section
  12's table literally reads. Rationale recorded in `docs/decisions.md`:
  Section 11's decision table treats production + irreversible/high-impact
  actions as the top tier; rollback mutates `current_version` the same way
  `deploy_service` does.
- Enum-like columns (`role`, `environment`, `sensitivity`, `rule_risk_level`,
  `ml_risk_level`, `final_risk_level`, `decision`, `status`, `outcome`) are
  implemented as Python `enum.Enum` + SQLAlchemy
  `Enum(..., native_enum=False, create_constraint=True, values_callable=...)`.
  This compiles to `VARCHAR` + a Postgres `CHECK` constraint — not a native
  Postgres `ENUM` type (which is painful to `ALTER` later).
- `policies` table has **no `service_id` FK** — policy (role/action/
  environment) is deliberately kept separate from ownership (Section 9's
  separately-checked ownership mechanism). Do not collapse these.
- `services.current_version` / `known_good_version` are `Integer`, per
  Section 13 (Revision 6) — never `String`/semver.
- `behavior_events` stores `version_before` / `version_after` as a
  **snapshot at event time**, not a live join to `services.current_version`.
  This was flagged early as the highest-risk design choice in this table —
  get it wrong and every historical feature computed in Semester 2 uses
  today's version instead of the version at the time of the past action.
- `security_requests.request_id` is a `String(32)` primary key (format like
  `"REQ-2001"` per Section 17), not an autoincrement int — it's the join key
  for `risk_assessments`, `approval_requests`, `incidents`.

**Files (all in `backend/app/database/`):**
- `base.py` — shared `Base` declarative class, engine, session, imported by
  both the app and Alembic's `env.py`.
- `enums.py` — all Python enums (`Role`, `Environment`, `Sensitivity`,
  `RiskLevel`, `Decision`, `ApprovalStatus`, `EventOutcome`).
- `models/users.py`, `agents.py`, `services.py`, `tools.py`, `policies.py`,
  `security_requests.py`, `risk_assessments.py`, `approval_requests.py`,
  `behavior_events.py`, `incidents.py` — one class each.
- `models/__init__.py` — imports all 10 so `Base.metadata` sees them
  (required for Alembic autogenerate to detect anything).
- `migrations/env.py` — `target_metadata` changed from `None` to
  `Base.metadata`.
- `migrations/versions/0b6eff3ade85_...py` — initial migration, creates all
  10 tables.
- `migrations/versions/6b86e1e35917_...py` — **hand-written** migration
  adding 14 CHECK constraints (see bug below). Not autogenerated — Alembic
  autogenerate cannot detect new CHECK constraints on existing columns; this
  is a documented Alembic limitation, confirmed empirically during this
  project, not an error either party made.

**Bug found and fixed during Phase 2 review:**
- First pass used `SAEnum(..., native_enum=False)` without
  `create_constraint=True`. In SQLAlchemy 1.4+, `Enum.create_constraint`
  defaults to `False` (changed from 1.3's default of `True`, to avoid
  forcing `ALTER` pain on existing tables). Result: all 14 enum-like columns
  across the 10 tables were created as plain `VARCHAR` with **zero**
  database-level validation — confirmed via `\d services` showing no
  `Check constraints:` section at all. Fixed by adding
  `create_constraint=True` to all 14 `SAEnum(...)` calls, then hand-writing
  the migration since autogenerate didn't pick up the change.
- **Verified working, not just present:** ran a live `INSERT` against
  `services.environment` with an invalid-but-short value (`'testenv'`,
  avoiding the `VARCHAR(10)` length trap that a longer bad value would hit
  first) — Postgres correctly returned
  `ERROR: new row for relation "services" violates check constraint "ck_services_environment"`.
  Both `\d` output and actual runtime behavior confirmed for `services` and
  `risk_assessments`. The other 6 constrained tables were not individually
  runtime-tested with a bad INSERT (only checked via `\d`-equivalent
  reasoning from the migration file review) — if paranoid, spot-check one
  more before Phase 3.

**Known quirks — investigated, confirmed harmless, do not re-flag:**
- Enum-backed `VARCHAR` columns are auto-sized to the longest enum member
  (e.g. `environment VARCHAR(10)` for `"production"`,
  `decision VARCHAR(17)` for `"APPROVAL_REQUIRED"`). Adding a longer enum
  value later would need a column-width migration too, not just updating
  the Python enum. Not an issue now; worth remembering if enums grow.
- `requirements.txt` is UTF-8 **with BOM** (not the UTF-16 problem from
  Phase 1 — a different, harmless artifact). `pip`'s `auto_decode` strips
  BOMs correctly; left as-is.
- A failed `INSERT` (e.g. the CHECK-constraint test above) still advances
  the table's `id` sequence, since `nextval()` runs before constraint
  checking and isn't rolled back on failure. Expected Postgres behavior —
  don't "fix" sequence gaps.

**Commits:** `5ae1112` (initial 10-table schema + migration),
`fe9f1c5` (CHECK constraint fix + `docs/decisions.md` added).

---

## Explicitly NOT built yet (scope guard for Phase 3+)

Per Section 27's phase breakdown, Phase 2 is schema/models/migrations only.
As of commit `fe9f1c5`, confirmed **absent** from the repo:
- No FastAPI routes / API endpoints.
- No Gateway logic (auth, policy, risk engine, decision engine — Section 8/11).
- No LangChain agent code (Section 6/7).
- No MCP server or tool implementations (Section 12).
- No seed/fixture data (the 5 tools from Section 12 are not yet inserted
  anywhere).

If any of the above shows up in a future `git status`/`find` and wasn't
explicitly signed off in a later revision of this file, flag it — it means
scope crept ahead of the phase.

## Next: Phase 3 (Section 27, Semester 1)

"Stateful mock DevOps environment: 3 services x 2 environments, integer
version counters (Section 13)."

This is the mock environment module (`backend/mock_devops_env/`), not more
schema work — the schema already exists from Phase 2. Phase 3 needs to:
- Implement the actual stateful mock service objects (not just DB rows).
- Seed the 3 services x 2 environments = 6 combinations from Section 13's
  table (`auth-service`, `payment-service`, `notification-service`, each
  staging + production), with seeded owners matching Section 13's example
  (`senior_developer_1`, `senior_developer_2`, `admin`, `junior_developer_1`).
- Wire state mutation logic (restart/deploy/rollback change version/status/
  history) — but per Section 27, MCP tool wiring is Phase 4, not Phase 3.
  Confirm this boundary before writing tool-execution code in Phase 3.

Do not start Gateway logic, agent code, or MCP tools in Phase 3 — that's
Phases 4/6/7 per the fixed implementation order (Section 27), and Revision
6 explicitly states no phases were added, removed, or reordered.
