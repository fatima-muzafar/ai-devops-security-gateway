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