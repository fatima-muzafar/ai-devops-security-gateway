"""
Phase 10 Stage 1 (decisions.md #64, #71-#74): the synthetic NORMAL-behavior generator.

Pure-plan tests use the real seed map (SEED_USERS / SEED_SERVICES / SEED_POLICIES) and need
no DB. DB tests use THROWAWAY identities and services (qa_gen_*) and never purge the real
synthetic set (#71). Explicit anchor and timestamps everywhere; nothing depends on "now".
"""
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import or_

from app.database.behavior import add_behavior_event, is_off_hours
from app.database.enums import Environment, EventOutcome, EventSource, Role
from app.database.models import Agent, BehaviorEvent, Service, ServiceStateHistory, Tool, User
from app.database.seed import SEED_POLICIES, SEED_SERVICES, SEED_USERS
from app.gateway.risk_constants import DENIAL_WINDOW, S1_WINDOW, S2_WINDOW, S3_WINDOW
from mock_devops_env.services import actions as env_actions
from ml.data.generator import (
    ALL_TOOLS,
    NON_READ_MIN_GAP,
    Identity,
    Row,
    generate_normal_events,
    parse_args,
    plan_normal_events,
)
from qa_cleanup import delete_behavior_events

UTC = timezone.utc
ANCHOR = datetime(2026, 10, 11, 0, 0, tzinfo=UTC)
READS = {"get_logs", "get_metrics"}
IDENTITIES = [Identity(u, r) for u, r in SEED_USERS]
ROWS = [Row((n, e), o) for n, e, o in SEED_SERVICES]
ROLE = {i.key: i.role for i in IDENTITIES}
OWNER = {r.key: r.owner_key for r in ROWS}


def _plan(days=30, seed=7, **kw):
    return plan_normal_events(IDENTITIES, ROWS, seed=seed, anchor=ANCHOR, days=days, **kw)


@pytest.fixture(scope="module")
def plan30():
    return _plan(30)


@pytest.fixture(scope="module")
def plan365():
    return _plan(365)


def _is_non_read(e):
    return not (e.outcome == EventOutcome.ALLOWED and e.tool_name in READS)


# ---- determinism and window -------------------------------------------------------------
def test_same_inputs_give_identical_plan(plan30):
    assert plan30 == _plan(30)
    assert len(plan30) > 1000


def test_different_seed_gives_a_different_plan(plan30):
    assert plan30 != _plan(30, seed=8)


def test_identity_streams_are_independent(plan30):
    solo = plan_normal_events(
        [i for i in IDENTITIES if i.key == "senior_developer_1"], ROWS, seed=7, anchor=ANCHOR, days=30
    )
    assert solo == [e for e in plan30 if e.user_key == "senior_developer_1"]


def test_timestamps_are_aware_utc_and_inside_the_window(plan30):
    start = ANCHOR - timedelta(days=30)
    for e in plan30:
        assert e.timestamp.tzinfo is not None and e.timestamp.utcoffset() == timedelta(0)
        assert start <= e.timestamp < ANCHOR


def test_naive_anchor_and_bad_days_are_rejected():
    with pytest.raises(ValueError):
        plan_normal_events(IDENTITIES, ROWS, seed=1, anchor=datetime(2026, 10, 11), days=5)
    with pytest.raises(ValueError):
        plan_normal_events(IDENTITIES, ROWS, seed=1, anchor=ANCHOR, days=0)


def test_identity_without_owned_rows_fails_clearly():
    with pytest.raises(ValueError, match="owns no service rows"):
        plan_normal_events([Identity("nobody", Role.ADMIN)], ROWS, seed=1, anchor=ANCHOR, days=3)


# ---- #73: spacing by construction -------------------------------------------------------
def test_non_read_events_are_spaced_beyond_the_largest_phase9_window(plan365):
    largest = max(DENIAL_WINDOW, S1_WINDOW, S2_WINDOW, S3_WINDOW)
    assert NON_READ_MIN_GAP > largest
    by_user = defaultdict(list)
    for e in plan365:
        if _is_non_read(e):
            by_user[e.user_key].append(e.timestamp)
    assert len(by_user) == len(IDENTITIES)
    for user, stamps in by_user.items():
        stamps.sort()
        gaps = [b - a for a, b in zip(stamps, stamps[1:])]
        assert gaps and min(gaps) > largest, f"{user}: min gap {min(gaps)} <= {largest}"


# ---- #72: owned + permitted by the real seeded matrix -----------------------------------
def test_every_action_is_owned_and_permitted_or_a_real_denial(plan365):
    for e in plan365:
        role, env = ROLE[e.user_key], e.service_key[1]
        owned = OWNER[e.service_key] == e.user_key
        key = (role, e.tool_name, env)
        if e.outcome in (EventOutcome.ALLOWED, EventOutcome.FAILED):
            assert owned, e
            assert key in SEED_POLICIES, e
            assert SEED_POLICIES[key] is False, f"approval-bound action generated as normal: {e}"
        else:  # BLOCKED: an Ownership or Policy denial, never an approval-bound case
            assert e.outcome == EventOutcome.BLOCKED
            assert (not owned) or (key not in SEED_POLICIES), e


def test_no_production_deploy_is_ever_executed(plan365):
    for e in plan365:
        if e.tool_name == "deploy_service" and e.service_key[1] == Environment.PRODUCTION:
            assert e.outcome == EventOutcome.BLOCKED  # only as an Ownership denial


def test_all_outcome_kinds_and_tools_appear(plan365):
    assert {e.outcome for e in plan365} == {EventOutcome.ALLOWED, EventOutcome.BLOCKED, EventOutcome.FAILED}
    executed = {e.tool_name for e in plan365 if e.outcome == EventOutcome.ALLOWED}
    assert executed == set(ALL_TOOLS)


def test_generator_honours_a_restricted_policy():
    """The permitted set comes from the policy argument, not from a hardcoded profile."""
    policy = {k: v for k, v in SEED_POLICIES.items() if not (k[0] == Role.JUNIOR_DEVELOPER and k[1] == "restart_service")}
    events = _plan(60, policy=policy)
    junior_state = [e for e in events if e.user_key == "junior_developer_1" and e.tool_name == "restart_service"]
    assert all(e.outcome == EventOutcome.BLOCKED for e in junior_state)  # now a Policy denial


# ---- #66/#68/#74: versions ---------------------------------------------------------------
def test_version_rules_and_independent_replay(plan365):
    state = {}  # (user, row) -> [current, known_good], an independent re-statement of #9
    for e in plan365:
        applies = e.outcome == EventOutcome.ALLOWED and e.tool_name in ("deploy_service", "rollback_deployment")
        if not applies:
            assert e.version_before is None and e.version_after is None, e
            continue
        cur, kg = state.setdefault((e.user_key, e.service_key), [1, 1])
        assert e.version_before == cur, e
        if e.tool_name == "deploy_service":
            assert e.version_after == cur + 1  # #68: normal deploy = current + 1
            state[(e.user_key, e.service_key)] = [cur + 1, cur]
        else:
            assert cur > kg, "rollback generated with nothing to roll back to"
            assert e.version_after == kg
            state[(e.user_key, e.service_key)] = [kg, kg]
    assert any(  # an EXECUTED rollback: blocked rollbacks on non-owned rows must not satisfy this
        e.tool_name == "rollback_deployment" and e.outcome == EventOutcome.ALLOWED for e in plan365
    )
    assert any(e.tool_name == "deploy_service" and e.outcome == EventOutcome.ALLOWED for e in plan365)


# ---- #67/#74: off-hours ------------------------------------------------------------------
def test_state_changes_are_never_off_hours_and_a_few_reads_are(plan365):
    reads = [e for e in plan365 if e.tool_name in READS and e.outcome == EventOutcome.ALLOWED]
    for e in plan365:
        if e.tool_name not in READS and e.outcome != EventOutcome.BLOCKED:
            assert not is_off_hours(e.timestamp), e
    off = sum(1 for e in reads if is_off_hours(e.timestamp))
    assert 0.01 < off / len(reads) < 0.06  # target ~3%


# ---- CLI ---------------------------------------------------------------------------------
def test_cli_requires_an_aware_anchor():
    with pytest.raises(SystemExit):
        parse_args([])  # --anchor missing: never defaults to "now"
    with pytest.raises(SystemExit):
        parse_args(["--anchor", "2026-10-11T00:00:00"])  # naive
    with pytest.raises(SystemExit):
        parse_args(["--anchor", "yesterday"])
    args = parse_args(["--anchor", "2026-10-11T00:00:00+00:00", "--days", "7", "--seed", "3"])
    assert args.anchor == ANCHOR and args.days == 7 and args.seed == 3


# ---- DB: throwaway identities -----------------------------------------------------------
@pytest.fixture
def gen_world(db, make_user, ag001_agent):
    """senior owns qa-gen-a staging+production; junior owns qa-gen-b staging; `other` owns
    qa-gen-c staging and is NOT generated. Teardown deletes events/history/services BEFORE
    make_user deletes the users (this fixture depends on make_user, so it tears down first)."""
    senior = make_user("qa_gen_senior", Role.SENIOR_DEVELOPER)
    junior = make_user("qa_gen_junior", Role.JUNIOR_DEVELOPER)
    other = make_user("qa_gen_other", Role.SENIOR_DEVELOPER)
    svc = {}
    for key, name, env, owner in [
        ("a_stg", "qa-gen-a", Environment.STAGING, senior),
        ("a_prod", "qa-gen-a", Environment.PRODUCTION, senior),
        ("b_stg", "qa-gen-b", Environment.STAGING, junior),
        ("c_stg", "qa-gen-c", Environment.STAGING, other),
    ]:
        s = Service(service_name=name, environment=env, current_version=1, known_good_version=1,
                    owner_id=owner.id, status="healthy")
        db.add(s)
        svc[key] = s
    db.commit()
    world = {
        "senior": senior, "junior": junior, "other": other, "svc": svc,
        "service_ids": [s.id for s in svc.values()],
        "tools": {t.tool_name: t for t in db.query(Tool).all()},
        "agent": ag001_agent,
    }
    user_ids = [senior.id, junior.id, other.id]
    service_ids = world["service_ids"]
    yield world
    db.rollback()
    delete_behavior_events(
        db, or_(BehaviorEvent.identity_id.in_(user_ids), BehaviorEvent.service_id.in_(service_ids))
    )
    db.query(ServiceStateHistory).filter(ServiceStateHistory.service_id.in_(service_ids)).delete(
        synchronize_session=False
    )
    db.query(Service).filter(Service.id.in_(service_ids)).delete(synchronize_session=False)
    db.commit()


def _gen(db, w, days=30, seed=7, usernames=("qa_gen_senior", "qa_gen_junior")):
    return generate_normal_events(
        db, seed=seed, anchor=ANCHOR, days=days, usernames=list(usernames), service_ids=w["service_ids"]
    )


def test_generate_inserts_synthetic_rows_with_stored_flag_and_ag001(db, gen_world):
    report = _gen(db, gen_world)
    db.commit()
    rows = db.query(BehaviorEvent).filter(
        BehaviorEvent.identity_id.in_([gen_world["senior"].id, gen_world["junior"].id])
    ).all()
    assert len(rows) == report.total > 200
    ag001 = db.query(Agent).filter_by(agent_name="AG001").order_by(Agent.id).first()
    for r in rows:
        assert r.source == EventSource.SYNTHETIC and r.request_id is None
        assert r.agent_id == ag001.id
        assert r.off_hours_flag is is_off_hours(r.timestamp)
        assert r.environment == db.get(Service, r.service_id).environment
    assert Counter(r.identity_id for r in rows).keys() == {gen_world["senior"].id, gen_world["junior"].id}


def test_rerun_is_idempotent_and_replaces_only_the_generated_identities_synthetic_rows(db, gen_world):
    w = gen_world
    other_row = add_behavior_event(
        db, identity_id=w["other"].id, agent_id=w["agent"].id, service=w["svc"]["c_stg"],
        tool=w["tools"]["get_logs"], outcome=EventOutcome.ALLOWED,
        timestamp=ANCHOR - timedelta(days=1), source=EventSource.SYNTHETIC,
    )
    live_row = add_behavior_event(
        db, identity_id=w["senior"].id, agent_id=w["agent"].id, service=w["svc"]["a_stg"],
        tool=w["tools"]["get_logs"], outcome=EventOutcome.ALLOWED,
        timestamp=ANCHOR - timedelta(days=1), source=EventSource.LIVE,
    )
    db.commit()
    other_id, live_id = other_row.id, live_row.id

    first = _gen(db, w)
    db.commit()
    ids_after_first = {r.id for r in db.query(BehaviorEvent).filter_by(source=EventSource.SYNTHETIC, identity_id=w["senior"].id)}
    second = _gen(db, w)
    db.commit()
    ids_after_second = {r.id for r in db.query(BehaviorEvent).filter_by(source=EventSource.SYNTHETIC, identity_id=w["senior"].id)}

    assert second.total == first.total and second.purged == first.total
    assert ids_after_first.isdisjoint(ids_after_second)  # purged and regenerated, not appended
    assert db.get(BehaviorEvent, other_id) is not None   # not generated -> untouched
    assert db.get(BehaviorEvent, live_id) is not None    # live rows are never touched
    assert db.query(BehaviorEvent).filter_by(identity_id=w["senior"].id, source=EventSource.LIVE).count() == 1


def test_unknown_username_fails_clearly(db, gen_world):
    with pytest.raises(ValueError, match="Unknown usernames"):
        generate_normal_events(db, seed=1, anchor=ANCHOR, days=3, usernames=["qa_gen_senior", "no_such_user"],
                               service_ids=gen_world["service_ids"])


def test_simulated_versions_match_the_real_actions_functions(db, gen_world):
    """Parity (#74): replay the stored deploy/rollback sequence for one row through the REAL
    mock-environment functions and require identical versions at every step."""
    w = gen_world
    _gen(db, w, days=120, usernames=("qa_gen_senior",))
    db.commit()
    stg = w["svc"]["a_stg"]
    events = (
        db.query(BehaviorEvent, Tool.tool_name)
        .join(Tool, Tool.id == BehaviorEvent.tool_id)
        .filter(
            BehaviorEvent.identity_id == w["senior"].id,
            BehaviorEvent.service_id == stg.id,
            BehaviorEvent.outcome == EventOutcome.ALLOWED,
            Tool.tool_name.in_(["deploy_service", "rollback_deployment"]),
        )
        .order_by(BehaviorEvent.timestamp, BehaviorEvent.id)
        .all()
    )
    names = [n for _, n in events]
    assert "deploy_service" in names and "rollback_deployment" in names
    for ev, name in events:
        assert stg.current_version == ev.version_before
        if name == "deploy_service":
            env_actions.deploy_service(db, stg, target_version=ev.version_after)
        else:
            env_actions.rollback_deployment(db, stg)
        assert stg.current_version == ev.version_after
    db.rollback()
