"""
Phase 10: synthetic NORMAL-behavior generator for behavior_events (decisions.md #64, #71-#74).

On demand, seeded, deterministic. Run from backend/:

    python -m ml.data.generator --seed 42 --anchor 2026-10-11T00:00:00+00:00 --days 30

Design (see decisions.md):
- NORMAL behavior only (#64). Anomalous/staged categories and labels are Phase 13.
- Direct inserts through app.database.behavior.add_behavior_event(), NOT through the Gateway
  (#71): the Gateway cannot take explicit timestamps and would pollute the history the Phase 9
  rules read. Rows are tagged source='synthetic' (#65).
- Identities are the seeded users acting only on rows they own, only with tools the policy
  matrix permits without approval (#72). Profiles are keyed by ROLE, not username.
- Every non-read event (executed state change, failed, blocked) comes from ONE per-identity
  schedule whose spacing exceeds the largest Phase 9 window, imported from risk_constants (#73).
  Reads may be dense. State changes are never off-hours; ~3% of reads are.
- Versions follow decisions.md #9 and #68: a normal deploy targets current+1; rollback only
  when current > known_good. They are stored only for executed deploy/rollback (#66).

Split in two: plan_normal_events() is PURE (no DB); generate_normal_events() loads the rows,
purges the BEING-GENERATED identities' old synthetic rows and inserts the plan (no commit).
"""
from __future__ import annotations

import argparse
import random
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.database.behavior import WORK_END, WORK_START, WORK_TZ, add_behavior_event
from app.database.enums import Environment, EventOutcome, EventSource, Role
from app.database.models import Agent, BehaviorEvent, Service, Tool, User
from app.database.seed import SEED_POLICIES, SEED_USERS
from app.gateway.risk_constants import DENIAL_WINDOW, S1_WINDOW, S2_WINDOW, S3_WINDOW

ServiceKey = tuple[str, Environment]  # (service_name, environment) = one services row
Policy = dict[tuple[Role, str, Environment], bool]  # value = requires_approval

ALL_TOOLS = (
    "get_logs",
    "get_metrics",
    "restart_service",
    "rollback_deployment",
    "deploy_service",
)
READ_TOOL_WEIGHTS = (("get_logs", 0.55), ("get_metrics", 0.45))
STATE_TOOL_WEIGHTS = {"restart_service": 6, "deploy_service": 3, "rollback_deployment": 1}

# #73: any two non-read events of one identity are spaced by MORE than the largest Phase 9
# window (imported, never copied), plus jitter.
NON_READ_MIN_GAP = max(DENIAL_WINDOW, S1_WINDOW, S2_WINDOW, S3_WINDOW) + timedelta(minutes=1)
SLOT_JITTER_MAX_SECONDS = 90 * 60
SLOT_START_SPREAD_SECONDS = 3 * 3600

# Uncalibrated profile numbers (#74). Final volume is a Phase 13 call.
READS_PER_DAY = (8, 20)
OFF_HOURS_READ_FRACTION = 0.03
MAX_STATE_SLOTS_PER_DAY = {Role.JUNIOR_DEVELOPER: 1, Role.SENIOR_DEVELOPER: 3, Role.ADMIN: 2}
BLOCKED_SLOT_PROBABILITY = 0.05
FAILED_SLOT_PROBABILITY = 0.01  # cumulative threshold is BLOCKED + FAILED

_WORK_START_S = WORK_START.hour * 3600
_WORK_SECONDS = (WORK_END.hour - WORK_START.hour) * 3600


@dataclass(frozen=True)
class Identity:
    key: str  # username
    role: Role


@dataclass(frozen=True)
class Row:
    key: ServiceKey
    owner_key: str  # owner's username


@dataclass(frozen=True)
class PlannedEvent:
    user_key: str
    service_key: ServiceKey
    tool_name: str
    outcome: EventOutcome
    timestamp: datetime  # timezone-aware UTC
    version_before: int | None = None
    version_after: int | None = None


@dataclass
class GenerationReport:
    total: int = 0
    by_identity: Counter = field(default_factory=Counter)
    by_outcome: Counter = field(default_factory=Counter)
    purged: int = 0


def _permitted(policy: Policy, role: Role, tool: str, env: Environment) -> bool:
    """Permitted WITHOUT approval. Approval-bound pairs (production deploy, #48) are excluded
    from normal data: Phase 11 turns them into 'pending', not normal executions."""
    key = (role, tool, env)
    return key in policy and not policy[key]


def _denied_pairs(identity: Identity, rows: list[Row], policy: Policy) -> list[tuple[Row, str]]:
    """Ownership- or Policy-stage denials only (#69 stage set). Owned + approval-bound is
    neither a normal execution nor a plain denial, so it is excluded."""
    denied: list[tuple[Row, str]] = []
    for row in rows:
        env = row.key[1]
        for tool in ALL_TOOLS:
            if row.owner_key != identity.key:
                denied.append((row, tool))  # Ownership BLOCK
            elif (identity.role, tool, env) not in policy:
                denied.append((row, tool))  # Policy BLOCK
    return denied


def _local_midnights(anchor: datetime, days: int) -> list[datetime]:
    first = anchor.astimezone(WORK_TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    return [first - timedelta(days=i) for i in range(days + 1)]


def _plan_identity(
    identity: Identity,
    rows: list[Row],
    policy: Policy,
    rng: random.Random,
    window_start: datetime,
    anchor: datetime,
    days: int,
) -> list[PlannedEvent]:
    owned = [r for r in rows if r.owner_key == identity.key]
    if not owned:
        raise ValueError(f"Identity {identity.key!r} owns no service rows; nothing to generate.")

    # ---- Phase A: schedule (times and kinds), independent of simulated state ------------
    items: list[tuple[datetime, str, object]] = []  # (utc ts, "read"|"state", payload)
    for midnight in _local_midnights(anchor, days):
        for _ in range(rng.randint(*READS_PER_DAY)):
            if rng.random() < OFF_HOURS_READ_FRACTION:
                s = rng.randrange(24 * 3600 - _WORK_SECONDS)  # the 15 off-hours hours
                s = s if s < _WORK_START_S else s + _WORK_SECONDS
            else:
                s = _WORK_START_S + rng.randrange(_WORK_SECONDS)
            row = rng.choice(owned)
            tool = rng.choices([t for t, _ in READ_TOOL_WEIGHTS], [w for _, w in READ_TOOL_WEIGHTS])[0]
            items.append(((midnight + timedelta(seconds=s)).astimezone(timezone.utc), "read", (row, tool)))

        t = midnight + timedelta(seconds=_WORK_START_S + rng.randrange(SLOT_START_SPREAD_SECONDS))
        work_end = midnight + timedelta(seconds=_WORK_START_S + _WORK_SECONDS)
        for _ in range(rng.randint(0, MAX_STATE_SLOTS_PER_DAY[identity.role])):
            if t >= work_end:
                break
            r = rng.random()
            kind = (
                "blocked"
                if r < BLOCKED_SLOT_PROBABILITY
                else "failed"
                if r < BLOCKED_SLOT_PROBABILITY + FAILED_SLOT_PROBABILITY
                else "executed"
            )
            items.append((t.astimezone(timezone.utc), "state", kind))
            t = t + NON_READ_MIN_GAP + timedelta(seconds=rng.randrange(SLOT_JITTER_MAX_SECONDS))

    items = [it for it in items if window_start <= it[0] < anchor]
    items.sort(key=lambda it: it[0])

    # ---- Phase B: walk chronologically, assigning tools and simulated versions ----------
    sim: dict[ServiceKey, list[int]] = {r.key: [1, 1] for r in owned}  # [current, known_good]
    denied = _denied_pairs(identity, rows, policy)
    events: list[PlannedEvent] = []
    for ts, what, payload in items:
        if what == "read":
            row, tool = payload  # type: ignore[misc]
            events.append(PlannedEvent(identity.key, row.key, tool, EventOutcome.ALLOWED, ts))
            continue

        kind = payload
        if kind == "blocked":
            if denied:
                row, tool = rng.choice(denied)
                events.append(PlannedEvent(identity.key, row.key, tool, EventOutcome.BLOCKED, ts))
            continue

        candidates: list[tuple[Row, str]] = []
        for row in owned:
            cur, kg = sim[row.key]
            for tool in STATE_TOOL_WEIGHTS:
                if not _permitted(policy, identity.role, tool, row.key[1]):
                    continue
                if tool == "rollback_deployment" and not cur > kg:
                    continue
                candidates.append((row, tool))
        if not candidates:
            continue
        row, tool = rng.choices(candidates, [STATE_TOOL_WEIGHTS[t] for _, t in candidates])[0]

        if kind == "failed":  # ALLOW + MCP failure: state unknown, simulated state unchanged
            events.append(PlannedEvent(identity.key, row.key, tool, EventOutcome.FAILED, ts))
            continue

        cur, kg = sim[row.key]
        if tool == "deploy_service":
            after = cur + 1  # #68: normal deploy = current + 1
            sim[row.key] = [after, cur]  # #9: known_good = the version being replaced
            events.append(PlannedEvent(identity.key, row.key, tool, EventOutcome.ALLOWED, ts, cur, after))
        elif tool == "rollback_deployment":
            sim[row.key] = [kg, kg]  # #9: rollback does not change known_good
            events.append(PlannedEvent(identity.key, row.key, tool, EventOutcome.ALLOWED, ts, cur, kg))
        else:  # restart: never touches a version
            events.append(PlannedEvent(identity.key, row.key, tool, EventOutcome.ALLOWED, ts))
    return events


def plan_normal_events(
    identities: list[Identity],
    rows: list[Row],
    *,
    seed: int,
    anchor: datetime,
    days: int,
    policy: Policy | None = None,
) -> list[PlannedEvent]:
    """PURE: the full normal-behavior plan. Deterministic in (seed, anchor, days, inputs); each
    identity has its own RNG so adding an identity never changes another's data."""
    if anchor.tzinfo is None or anchor.utcoffset() is None:
        raise ValueError("anchor must be timezone-aware (it never defaults to 'now', #74).")
    if days < 1:
        raise ValueError("days must be >= 1.")
    policy = SEED_POLICIES if policy is None else policy
    anchor = anchor.astimezone(timezone.utc)
    window_start = anchor - timedelta(days=days)

    events: list[PlannedEvent] = []
    for identity in identities:
        rng = random.Random(f"{seed}:{identity.key}")
        events.extend(_plan_identity(identity, rows, policy, rng, window_start, anchor, days))
    events.sort(key=lambda e: (e.timestamp, e.user_key))
    return events


def generate_normal_events(
    db: Session,
    *,
    seed: int,
    anchor: datetime,
    days: int,
    usernames: list[str] | None = None,
    service_ids: list[int] | None = None,
) -> GenerationReport:
    """Purge source='synthetic' rows of the identities BEING GENERATED, then insert the plan.
    Live rows and other identities' synthetic rows are never touched (#71). Does NOT commit:
    the caller owns the one transaction."""
    usernames = list(usernames) if usernames is not None else [u for u, _ in SEED_USERS]
    users = db.query(User).filter(User.username.in_(usernames)).all()
    missing = sorted(set(usernames) - {u.username for u in users})
    if missing:
        raise ValueError(f"Unknown usernames (seed the users first): {missing}")

    q = db.query(Service)
    if service_ids is not None:
        q = q.filter(Service.id.in_(service_ids))
    services = q.all()
    if not services:
        raise RuntimeError("No service rows found (run `python -m app.database.seed` first).")
    owner_names = {u.id: u.username for u in db.query(User).filter(User.id.in_({s.owner_id for s in services}))}

    agent = db.query(Agent).filter_by(agent_name="AG001").order_by(Agent.id).first()
    if agent is None:
        raise RuntimeError("Agent AG001 not found (run `python -m app.database.seed` first).")
    tools = {t.tool_name: t for t in db.query(Tool).filter(Tool.tool_name.in_(ALL_TOOLS))}
    if set(tools) != set(ALL_TOOLS):
        raise RuntimeError(f"Tool registry incomplete (missing {sorted(set(ALL_TOOLS) - set(tools))}).")

    svc_by_key: dict[ServiceKey, Service] = {(s.service_name, s.environment): s for s in services}
    rows = [Row(key, owner_names[s.owner_id]) for key, s in svc_by_key.items()]
    user_by_name = {u.username: u for u in users}
    identities = [Identity(u.username, u.role) for u in users]

    plan = plan_normal_events(identities, rows, seed=seed, anchor=anchor, days=days)

    report = GenerationReport()
    report.purged = (
        db.query(BehaviorEvent)
        .filter(
            BehaviorEvent.source == EventSource.SYNTHETIC,
            BehaviorEvent.identity_id.in_([u.id for u in users]),
        )
        .delete(synchronize_session=False)
    )
    for ev in plan:
        add_behavior_event(
            db,
            identity_id=user_by_name[ev.user_key].id,
            agent_id=agent.id,
            service=svc_by_key[ev.service_key],
            tool=tools[ev.tool_name],
            outcome=ev.outcome,
            timestamp=ev.timestamp,
            version_before=ev.version_before,
            version_after=ev.version_after,
            source=EventSource.SYNTHETIC,
        )
        report.by_identity[ev.user_key] += 1
        report.by_outcome[ev.outcome.value] += 1
    report.total = len(plan)
    db.flush()
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate synthetic NORMAL behavior_events (decisions.md #64).")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--anchor", required=True, help="ISO-8601 with offset, e.g. 2026-10-11T00:00:00+00:00")
    p.add_argument("--days", type=int, default=30)
    args = p.parse_args(argv)
    try:
        args.anchor = datetime.fromisoformat(args.anchor)
    except ValueError:
        p.error(f"--anchor is not an ISO-8601 datetime: {args.anchor!r}")
    if args.anchor.tzinfo is None or args.anchor.utcoffset() is None:
        p.error("--anchor must include a UTC offset (it never defaults to 'now').")
    if args.days < 1:
        p.error("--days must be >= 1.")
    return args


def main(argv: list[str] | None = None) -> int:
    from app.database.base import SessionLocal

    args = parse_args(argv)
    db = SessionLocal()
    try:
        report = generate_normal_events(db, seed=args.seed, anchor=args.anchor, days=args.days)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    print(f"Purged {report.purged} old synthetic rows; inserted {report.total}.")
    print("By identity:", dict(report.by_identity))
    print("By outcome:", dict(report.by_outcome))
    return 0


if __name__ == "__main__":
    sys.exit(main())
