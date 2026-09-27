"""
Tests for backend/app/mcp/ (Phase 4).

Uses the `db` and `test_service` fixtures from conftest.py (Phase 3) —
`test_service` is a throwaway qa_/qa- prefixed row, never a real seeded
service, so these tests can't collide with or corrupt real data.

registry.seed_tools() is idempotent and, like app/database/seed.py, is
meant to be run against the real dev DB — these tests commit it
deliberately (mirrors test_seed.py's pattern) rather than relying on the
`db` fixture's rollback-on-teardown, since the whole point is to check
repeated runs converge, not to undo them.

Scope note (decisions.md #10): these are per-phase unit tests, not the
M8/Phase 17 research evaluation (E1-E6). Do not conflate the two.
"""
import pytest

from app.database.enums import Environment, Sensitivity
from app.database.models import Tool
from app.mcp import server
from app.mcp.registry import TOOL_REGISTRY, seed_tools


# ---------------------------------------------------------------------
# Registry / seeding
# ---------------------------------------------------------------------

def test_seed_tools_creates_all_five(db):
    seed_tools(db)
    db.commit()

    rows = db.query(Tool).all()
    tool_names = {row.tool_name for row in rows}
    assert tool_names == set(TOOL_REGISTRY.keys())


def test_seed_tools_is_idempotent(db):
    seed_tools(db)
    db.commit()
    seed_tools(db)  # second run must not duplicate
    db.commit()

    for tool_name in TOOL_REGISTRY:
        matches = db.query(Tool).filter_by(tool_name=tool_name).all()
        assert len(matches) == 1, f"expected exactly one {tool_name!r}, found {len(matches)}"


def test_seed_tools_sensitivity_matches_decisions_md_1(db):
    # decisions.md #1: rollback_deployment sensitivity = HIGH (not the
    # planning doc's "Medium-High", which isn't a real enum member).
    seed_tools(db)
    db.commit()

    rollback = db.query(Tool).filter_by(tool_name="rollback_deployment").one()
    assert rollback.sensitivity == Sensitivity.HIGH

    deploy = db.query(Tool).filter_by(tool_name="deploy_service").one()
    assert deploy.sensitivity == Sensitivity.HIGH

    restart = db.query(Tool).filter_by(tool_name="restart_service").one()
    assert restart.sensitivity == Sensitivity.MEDIUM

    for read_tool in ("get_logs", "get_metrics"):
        row = db.query(Tool).filter_by(tool_name=read_tool).one()
        assert row.sensitivity == Sensitivity.LOW


# ---------------------------------------------------------------------
# execute_tool() dispatch — read-only tools
# ---------------------------------------------------------------------

def test_execute_get_logs_returns_simulated_lines(db, test_service):
    seed_tools(db)
    db.commit()

    result = server.execute_tool(
        db, "get_logs", test_service.service_name, test_service.environment, limit=5
    )
    assert result["tool"] == "get_logs"
    assert len(result["logs"]) == 5
    assert all("message" in line and "level" in line for line in result["logs"])


def test_execute_get_metrics_reflects_service_status(db, test_service):
    seed_tools(db)
    db.commit()

    test_service.status = "degraded"
    db.commit()

    result = server.execute_tool(
        db, "get_metrics", test_service.service_name, test_service.environment
    )
    assert result["metrics"]["status"] == "degraded"
    # degraded services simulate materially worse numbers (simulated_data.py)
    assert result["metrics"]["error_rate_percent"] > 1.0


def test_read_tools_never_write_state_history(db, test_service):
    from app.database.models import ServiceStateHistory

    seed_tools(db)
    db.commit()

    server.execute_tool(db, "get_logs", test_service.service_name, test_service.environment)
    server.execute_tool(db, "get_metrics", test_service.service_name, test_service.environment)

    rows = db.query(ServiceStateHistory).filter_by(service_id=test_service.id).all()
    assert rows == []


# ---------------------------------------------------------------------
# execute_tool() dispatch — state-changing tools
# ---------------------------------------------------------------------

def test_execute_restart_service_through_mcp(db, test_service):
    seed_tools(db)
    db.commit()
    test_service.status = "degraded"
    db.commit()

    result = server.execute_tool(
        db, "restart_service", test_service.service_name, test_service.environment
    )
    db.commit()

    assert result["result"]["status_after"] == "healthy"
    assert test_service.status == "healthy"


def test_execute_deploy_then_rollback_through_mcp(db, test_service):
    seed_tools(db)
    db.commit()

    server.execute_tool(
        db,
        "deploy_service",
        test_service.service_name,
        test_service.environment,
        target_version=2,
    )
    db.commit()
    assert test_service.current_version == 2
    assert test_service.known_good_version == 1  # decisions.md #9

    server.execute_tool(
        db, "rollback_deployment", test_service.service_name, test_service.environment
    )
    db.commit()
    assert test_service.current_version == 1  # reverted to known_good


def test_execute_deploy_rejects_non_positive_target_version(db, test_service):
    seed_tools(db)
    db.commit()

    with pytest.raises(ValueError):
        server.execute_tool(
            db,
            "deploy_service",
            test_service.service_name,
            test_service.environment,
            target_version=0,
        )


# ---------------------------------------------------------------------
# execute_tool() dispatch — error paths
# ---------------------------------------------------------------------

def test_execute_unknown_tool_raises(db, test_service):
    seed_tools(db)
    db.commit()

    with pytest.raises(server.ToolNotFoundError):
        server.execute_tool(
            db, "delete_everything", test_service.service_name, test_service.environment
        )


def test_execute_unknown_service_raises(db):
    seed_tools(db)
    db.commit()

    with pytest.raises(server.ServiceNotFoundError):
        server.execute_tool(db, "get_logs", "does-not-exist", Environment.STAGING)


def test_execute_disabled_tool_raises(db, test_service):
    seed_tools(db)
    db.commit()

    tool_row = db.query(Tool).filter_by(tool_name="get_metrics").one()
    tool_row.enabled = False
    db.commit()
    try:
        with pytest.raises(server.ToolDisabledError):
            server.execute_tool(
                db, "get_metrics", test_service.service_name, test_service.environment
            )
    finally:
        # restore — this row is shared, real registry state, not a
        # throwaway fixture; leaving it disabled would break every
        # other test that runs after this one.
        tool_row.enabled = True
        db.commit()