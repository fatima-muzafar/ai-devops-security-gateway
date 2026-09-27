"""
Tool registry (Section 12 / the `tools` table).

Two things live here, deliberately kept together since they must never
drift apart:

1. TOOL_REGISTRY — the in-process source of truth: for each tool name,
   its sensitivity, the callable that implements it, and its argument
   schema. `server.py` dispatches through this.
2. seed_tools(db) — writes/updates the matching rows in the `tools`
   table (Tool model: tool_name, sensitivity, enabled, schema_def),
   idempotent like `app/database/seed.py` (decisions.md #8 pattern:
   query by natural key, update-in-place if changed, never duplicate).

"Unregistered or disabled tools cannot execute" (Section 12) is enforced
by `server.py` checking the `tools` table row, not by only trusting this
in-process dict — the DB row is the actual authorization-relevant record
(Section 16: `tools` table = "Tool registry, sensitivity, enabled
state").
"""
from sqlalchemy.orm import Session

from app.database.enums import Sensitivity
from app.database.models import Tool
from app.mcp import tools as tool_impls
from app.mcp.schemas import TOOL_ARG_SCHEMAS

TOOL_REGISTRY: dict[str, dict] = {
    "get_logs": {
        "sensitivity": Sensitivity.LOW,
        "callable": tool_impls.get_logs,
    },
    "get_metrics": {
        "sensitivity": Sensitivity.LOW,
        "callable": tool_impls.get_metrics,
    },
    "restart_service": {
        "sensitivity": Sensitivity.MEDIUM,
        "callable": tool_impls.restart_service,
    },
    "rollback_deployment": {
        # Section 12 lists "Medium-High"; decisions.md #1 resolves this
        # to HIGH, matching the three-tier Sensitivity enum actually
        # implemented (LOW/MEDIUM/HIGH — no MEDIUM_HIGH member exists).
        "sensitivity": Sensitivity.HIGH,
        "callable": tool_impls.rollback_deployment,
    },
    "deploy_service": {
        "sensitivity": Sensitivity.HIGH,
        "callable": tool_impls.deploy_service,
    },
}


def seed_tools(db: Session) -> None:
    """Idempotent: safe to re-run. Creates missing tool rows; if a row
    already exists but its sensitivity/schema_def has drifted from
    TOOL_REGISTRY (e.g. this file changed after the row was seeded),
    updates it in place rather than skipping — the DB should never be
    stale relative to the code that dispatches through it. `enabled` is
    only set to True on first creation; it is never forced back to True
    on an existing row, so a tool an admin disabled at runtime is not
    silently re-enabled by re-running seeding."""
    for tool_name, meta in TOOL_REGISTRY.items():
        schema_def = TOOL_ARG_SCHEMAS[tool_name].model_json_schema()
        existing = db.query(Tool).filter_by(tool_name=tool_name).one_or_none()
        if existing:
            existing.sensitivity = meta["sensitivity"]
            existing.schema_def = schema_def
            continue
        db.add(
            Tool(
                tool_name=tool_name,
                sensitivity=meta["sensitivity"],
                enabled=True,
                schema_def=schema_def,
            )
        )


if __name__ == "__main__":
    from app.database.base import SessionLocal

    session = SessionLocal()
    try:
        seed_tools(session)
        session.commit()
        print(f"Tool registry seeded/updated: {len(TOOL_REGISTRY)} tools.")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()