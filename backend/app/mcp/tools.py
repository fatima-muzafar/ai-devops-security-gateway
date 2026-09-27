"""
The five MCP tools (Section 12).

Naming note: these functions are deliberately named identically to the
tool names in the planning doc (`get_logs`, `get_metrics`,
`restart_service`, `rollback_deployment`, `deploy_service`) so
`registry.py`'s tool_name -> callable mapping and `Tool.tool_name` rows
stay obviously in sync. The three state-changing tools wrap
`mock_devops_env.services.actions` (Phase 3, imported qualified as
`env_actions` to avoid shadowing these same names) rather than
duplicating any mutation logic — Phase 4 owns tool packaging only, not
state-mutation rules (STATUS.md Phase 4 Boundary; decisions.md #9 locks
the known_good_version semantics inside actions.py itself).

Every tool returns a plain, JSON-serializable dict — never the raw ORM
object — since this is the boundary layer a future HTTP route / Gateway
response will eventually serialize.
"""
from sqlalchemy.orm import Session

from app.database.models import Service
from mock_devops_env.logs import generator as env_logs
from mock_devops_env.metrics import generator as env_metrics
from mock_devops_env.services import actions as env_actions


def _history_to_dict(history) -> dict:
    return {
        "change_type": history.change_type.value,
        "version_before": history.version_before,
        "version_after": history.version_after,
        "status_before": history.status_before,
        "status_after": history.status_after,
    }


def get_logs(db: Session, service: Service, limit: int = 20) -> dict:
    """Low sensitivity, read-only (Section 12). No state mutation, no
    service_state_history row (decisions.md #7)."""
    return {
        "tool": "get_logs",
        "service": service.service_name,
        "environment": service.environment.value,
        "logs": env_logs.generate_logs(service, limit=limit),
    }


def get_metrics(db: Session, service: Service) -> dict:
    """Low sensitivity, read-only (Section 12). No state mutation."""
    return {
        "tool": "get_metrics",
        "service": service.service_name,
        "environment": service.environment.value,
        "metrics": env_metrics.generate_metrics(service),
    }


def restart_service(db: Session, service: Service) -> dict:
    """Medium sensitivity (Section 12). Wraps
    env_actions.restart_service() — updates status only, never version."""
    history = env_actions.restart_service(db, service)
    return {
        "tool": "restart_service",
        "service": service.service_name,
        "environment": service.environment.value,
        "result": _history_to_dict(history),
    }


def rollback_deployment(db: Session, service: Service) -> dict:
    """High sensitivity (decisions.md #1). Wraps
    env_actions.rollback_deployment() — reverts current_version to
    known_good_version; does not itself change known_good_version
    (locked semantics, decisions.md #9)."""
    history = env_actions.rollback_deployment(db, service)
    return {
        "tool": "rollback_deployment",
        "service": service.service_name,
        "environment": service.environment.value,
        "result": _history_to_dict(history),
    }


def deploy_service(db: Session, service: Service, target_version: int) -> dict:
    """High sensitivity (Section 12). Wraps env_actions.deploy_service()
    — advances current_version to target_version and sets
    known_good_version to the version being replaced (decisions.md #9).
    Raises ValueError via env_actions if target_version <= 0."""
    history = env_actions.deploy_service(db, service, target_version=target_version)
    return {
        "tool": "deploy_service",
        "service": service.service_name,
        "environment": service.environment.value,
        "result": _history_to_dict(history),
    }