"""
Phase 10: behavior_events writer + off-hours rule (decisions.md #65, #66, #67).

ONE write path for BOTH live pipeline events and synthetic generator events, so the stored
off_hours_flag and the NULL-version rules cannot drift between them. Callers cannot pass the
flag: it is always computed here from the explicit timestamp.

The working-hours constants below are FROZEN before Phase 16 (#67): changing them afterwards
invalidates E2. A change needs one UPDATE recomputing off_hours_flag from timestamp.
"""
from datetime import datetime, time, timedelta, timezone

from sqlalchemy.orm import Session

from app.database.enums import EventOutcome, EventSource
from app.database.models import BehaviorEvent, Service, Tool

# #67: fixed UTC+5 (no zoneinfo/tzdata dependency on Windows), 09:00 <= t < 18:00 local,
# all seven days.
WORK_TZ = timezone(timedelta(hours=5), "PKT")
WORK_START = time(9, 0)
WORK_END = time(18, 0)

# #66: only these tools touch a version; every other event stores NULL versions.
VERSION_TOOLS = frozenset({"deploy_service", "rollback_deployment"})


def is_off_hours(ts: datetime) -> bool:
    """True when `ts` falls outside [WORK_START, WORK_END) in WORK_TZ. `ts` must be
    timezone-aware (a naive timestamp would silently be read in some other zone)."""
    if ts.tzinfo is None or ts.utcoffset() is None:
        raise ValueError("is_off_hours requires a timezone-aware datetime.")
    local_time = ts.astimezone(WORK_TZ).time()
    return not (WORK_START <= local_time < WORK_END)


def add_behavior_event(
    db: Session,
    *,
    identity_id: int,
    agent_id: int,
    service: Service,
    tool: Tool,
    outcome: EventOutcome,
    timestamp: datetime,
    version_before: int | None = None,
    version_after: int | None = None,
    source: EventSource = EventSource.LIVE,
    request_id: str | None = None,
) -> BehaviorEvent:
    """Add one behavior_events row to the session. Does NOT commit or flush (the caller owns
    the transaction: #70 live hook commits separately, #71 generator commits once).

    - timestamp is explicit and timezone-aware (never the server default), so the stored
      timestamp and off_hours_flag describe the same instant.
    - environment comes from the service row (#66).
    - versions are only meaningful for an ALLOWED deploy_service / rollback_deployment (#66);
      anything else carrying a version is a caller bug and raises.
    """
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("add_behavior_event requires a timezone-aware timestamp.")
    if (version_before is not None or version_after is not None) and not (
        outcome == EventOutcome.ALLOWED and tool.tool_name in VERSION_TOOLS
    ):
        raise ValueError(
            "version_before/version_after are only stored for an ALLOWED "
            f"{sorted(VERSION_TOOLS)} event (got outcome={outcome.value!r}, tool={tool.tool_name!r})."
        )

    event = BehaviorEvent(
        identity_id=identity_id,
        agent_id=agent_id,
        service_id=service.id,
        environment=service.environment,
        tool_id=tool.id,
        outcome=outcome,
        timestamp=timestamp,
        version_before=version_before,
        version_after=version_after,
        off_hours_flag=is_off_hours(timestamp),
        source=source,
        request_id=request_id,
    )
    db.add(event)
    return event
