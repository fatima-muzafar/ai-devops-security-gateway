"""
Live behavior-event hook (decisions.md #66, #69, #70).

Called by the pipeline AFTER the final outcome of a request is known and its audit evidence is
already committed. It writes one behavior_events row through the shared writer
(app.database.behavior.add_behavior_event, #67) and commits SEPARATELY.

FAIL-OPEN (#70): telemetry is not audit evidence (security_requests is). Any exception here is
rolled back and logged as a warning; the HTTP response and the decision never change. The cost
is a possible gap in an identity's N = 5 window (under-detection), which a test pins.

Logged iff the request has an authenticated user AND a resolved agent, tool, service and
environment (the #57 structural filter, #69). Equivalent stage set: ALLOW (executed or failed)
plus Ownership/Policy BLOCKs. NOT logged: Authentication BLOCKs, mismatched-claim rows,
Agent/Tool/Arguments/Service BLOCKs, 409 duplicates, unexpected 500s.
"""
import logging
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.database.behavior import VERSION_TOOLS, add_behavior_event
from app.database.enums import EventOutcome, EventSource
from app.database.models import Service, Tool

logger = logging.getLogger(__name__)


def is_loggable(verdict) -> bool:
    return all(
        v is not None
        for v in (
            verdict.user_id,
            verdict.agent_id,
            verdict.tool_id,
            verdict.service_id,
            verdict.environment,
        )
    )


def _versions(tool_name: str, result: Any, request_id: str) -> tuple[int | None, int | None]:
    """#66: copy version_before/after from the MCP result dict for deploy/rollback ONLY.
    execute_tool returns {..., "result": {"version_before": ..., "version_after": ...}} and the
    Gateway passes that dict through as `result`. Missing/non-int -> NULL + warning."""
    if tool_name not in VERSION_TOOLS:
        return None, None
    inner = result.get("result") if isinstance(result, dict) else None
    before = inner.get("version_before") if isinstance(inner, dict) else None
    after = inner.get("version_after") if isinstance(inner, dict) else None
    if isinstance(before, int) and isinstance(after, int):
        return before, after
    logger.warning(
        "behavior event for %s (%s): MCP result lacks integer version_before/version_after; "
        "storing NULL versions (#66).",
        request_id,
        tool_name,
    )
    return None, None


def record_behavior_event(
    db: Session,
    verdict,
    *,
    request_id: str,
    timestamp: datetime,
    outcome: EventOutcome,
    result: Any = None,
) -> None:
    """Never raises. `outcome` is ALLOWED only after a successful MCP execution; `result` is
    the MCP result dict (used for deploy/rollback versions)."""
    try:
        if not is_loggable(verdict):
            return
        service = db.get(Service, verdict.service_id)
        tool = db.get(Tool, verdict.tool_id)
        if service is None or tool is None:  # cannot happen after a resolved verdict
            logger.warning("behavior event for %s skipped: service/tool row vanished.", request_id)
            return
        before, after = (
            _versions(tool.tool_name, result, request_id)
            if outcome == EventOutcome.ALLOWED
            else (None, None)
        )
        add_behavior_event(
            db,
            identity_id=verdict.user_id,
            agent_id=verdict.agent_id,
            service=service,
            tool=tool,
            outcome=outcome,
            timestamp=timestamp,
            version_before=before,
            version_after=after,
            source=EventSource.LIVE,
            request_id=request_id,
        )
        db.commit()
    except Exception:  # fail-open (#70): telemetry must never change a response
        db.rollback()
        logger.warning("behavior event write failed for %s; response unchanged.", request_id, exc_info=True)
