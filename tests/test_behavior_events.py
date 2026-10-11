"""
Phase 10 Stage 1 (decisions.md #65-#67, #75): off-hours rule, the shared writer, and the
behavior_events schema (source / request_id / 'failed'). Explicit timestamps everywhere.
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import or_, text
from sqlalchemy.exc import IntegrityError

from app.database.behavior import add_behavior_event, is_off_hours
from app.database.enums import Environment, EventOutcome, EventSource, Role
from app.database.models import BehaviorEvent, Service, Tool
from qa_cleanup import delete_behavior_events

UTC = timezone.utc
PKT = timezone(timedelta(hours=5))


# ---- is_off_hours: boundaries are in UTC+5, [09:00, 18:00) ------------------------------
@pytest.mark.parametrize(
    "ts, expected",
    [
        (datetime(2026, 10, 12, 3, 59, 59, tzinfo=UTC), True),    # 08:59:59 PKT
        (datetime(2026, 10, 12, 4, 0, 0, tzinfo=UTC), False),     # 09:00:00 PKT (inclusive start)
        (datetime(2026, 10, 12, 12, 59, 59, tzinfo=UTC), False),  # 17:59:59 PKT
        (datetime(2026, 10, 12, 13, 0, 0, tzinfo=UTC), True),     # 18:00:00 PKT (exclusive end)
        (datetime(2026, 10, 12, 19, 0, 0, tzinfo=UTC), True),     # 00:00 PKT next local day
        (datetime(2026, 10, 12, 20, 30, 0, tzinfo=UTC), True),    # 01:30 PKT
        (datetime(2026, 10, 12, 9, 0, 0, tzinfo=PKT), False),     # non-UTC aware input, 09:00 local
        (datetime(2026, 10, 12, 8, 59, 0, tzinfo=PKT), True),
        (datetime(2026, 10, 10, 5, 0, 0, tzinfo=UTC), False),     # a Saturday: all seven days
        (datetime(2026, 10, 11, 5, 0, 0, tzinfo=UTC), False),     # a Sunday
    ],
)
def test_is_off_hours_boundaries(ts, expected):
    assert is_off_hours(ts) is expected


def test_is_off_hours_rejects_naive_datetime():
    with pytest.raises(ValueError):
        is_off_hours(datetime(2026, 10, 12, 10, 0, 0))


# ---- fixtures: cleanup tears down BEFORE make_user / test_service (FK order) -------------
@pytest.fixture
def event_world(db, make_user, test_service, ag001_agent):
    user = make_user("qa_evt_user", Role.SENIOR_DEVELOPER)
    tools = {t.tool_name: t for t in db.query(Tool).all()}
    user_id, service_id = user.id, test_service.id
    yield {"user": user, "service": test_service, "agent": ag001_agent, "tools": tools}
    db.rollback()
    delete_behavior_events(
        db, or_(BehaviorEvent.identity_id == user_id, BehaviorEvent.service_id == service_id)
    )
    db.commit()


def _add(db, w, **kw):
    args = dict(
        identity_id=w["user"].id,
        agent_id=w["agent"].id,
        service=w["service"],
        tool=w["tools"]["get_logs"],
        outcome=EventOutcome.ALLOWED,
        timestamp=datetime(2026, 10, 12, 6, 0, tzinfo=UTC),
    )
    args.update(kw)
    return add_behavior_event(db, **args)


# ---- writer ------------------------------------------------------------------------------
def test_writer_stores_computed_flag_for_both_sources(db, event_world):
    in_hours = datetime(2026, 10, 12, 6, 0, tzinfo=UTC)   # 11:00 PKT
    off_hours = datetime(2026, 10, 12, 20, 0, tzinfo=UTC)  # 01:00 PKT
    for source in (EventSource.LIVE, EventSource.SYNTHETIC):
        _add(db, event_world, timestamp=in_hours, source=source)
        _add(db, event_world, timestamp=off_hours, source=source)
    db.commit()
    rows = db.query(BehaviorEvent).filter_by(identity_id=event_world["user"].id).all()
    assert len(rows) == 4
    for r in rows:
        assert r.off_hours_flag is is_off_hours(r.timestamp)
    assert {(r.source, r.off_hours_flag) for r in rows} == {
        (EventSource.LIVE, False), (EventSource.LIVE, True),
        (EventSource.SYNTHETIC, False), (EventSource.SYNTHETIC, True),
    }


def test_caller_cannot_pass_the_flag(db, event_world):
    with pytest.raises(TypeError):
        _add(db, event_world, off_hours_flag=True)


def test_writer_uses_the_explicit_timestamp_and_service_environment(db, event_world):
    ts = datetime(2026, 1, 5, 7, 30, tzinfo=UTC)  # far from "now": never the server default
    ev = _add(db, event_world, timestamp=ts)
    db.commit()
    db.refresh(ev)
    assert ev.timestamp == ts
    assert ev.environment == event_world["service"].environment == Environment.STAGING
    assert ev.source == EventSource.LIVE and ev.request_id is None


def test_writer_rejects_naive_timestamp(db, event_world):
    with pytest.raises(ValueError):
        _add(db, event_world, timestamp=datetime(2026, 10, 12, 6, 0))


@pytest.mark.parametrize(
    "tool, outcome, versions, ok",
    [
        ("deploy_service", EventOutcome.ALLOWED, (1, 2), True),
        ("rollback_deployment", EventOutcome.ALLOWED, (2, 1), True),
        ("restart_service", EventOutcome.ALLOWED, (1, 1), False),   # restart never carries versions
        ("get_logs", EventOutcome.ALLOWED, (1, None), False),
        ("deploy_service", EventOutcome.BLOCKED, (1, 2), False),
        ("deploy_service", EventOutcome.FAILED, (1, 2), False),
        ("deploy_service", EventOutcome.ALLOWED, (None, None), True),  # missing MCP dict: NULL (#66)
    ],
)
def test_writer_version_rules(db, event_world, tool, outcome, versions, ok):
    kwargs = dict(
        tool=event_world["tools"][tool], outcome=outcome,
        version_before=versions[0], version_after=versions[1],
    )
    if ok:
        ev = _add(db, event_world, **kwargs)
        assert (ev.version_before, ev.version_after) == versions
    else:
        with pytest.raises(ValueError):
            _add(db, event_world, **kwargs)


# ---- schema (#65, #66, #75) --------------------------------------------------------------
def _raw_insert(db, w, outcome="allowed", extra_cols="", extra_vals=""):
    db.execute(
        text(
            "INSERT INTO behavior_events (identity_id, agent_id, service_id, environment, "
            f"tool_id, outcome, off_hours_flag{extra_cols}) "
            f"VALUES (:i, :a, :s, 'staging', :t, :o, false{extra_vals})"
        ),
        {"i": w["user"].id, "a": w["agent"].id, "s": w["service"].id,
         "t": w["tools"]["get_logs"].id, "o": outcome},
    )


def test_failed_outcome_is_accepted(db, event_world):
    ev = _add(db, event_world, tool=event_world["tools"]["restart_service"], outcome=EventOutcome.FAILED)
    db.commit()
    db.refresh(ev)
    assert ev.outcome == EventOutcome.FAILED


def test_bogus_outcome_is_rejected(db, event_world):
    with pytest.raises(IntegrityError):
        _raw_insert(db, event_world, outcome="bogus")
    db.rollback()


def test_bogus_source_is_rejected(db, event_world):
    with pytest.raises(IntegrityError):
        _raw_insert(db, event_world, extra_cols=", source", extra_vals=", 'bogus'")
    db.rollback()


def test_source_defaults_to_live_when_omitted(db, event_world):
    _raw_insert(db, event_world)
    db.commit()
    row = db.query(BehaviorEvent).filter_by(identity_id=event_world["user"].id).one()
    assert row.source == EventSource.LIVE


def test_request_id_must_reference_an_audit_row(db, event_world):
    with pytest.raises(IntegrityError):
        _raw_insert(db, event_world, extra_cols=", request_id", extra_vals=", 'NO-SUCH-REQUEST'")
    db.rollback()
