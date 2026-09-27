"""
MCP server (Section 8 / Section 12): the controlled tool-execution layer.

`execute_tool()` is the one entrypoint. It:
  1. Looks up the tool in the `tools` table — unregistered or disabled
     tools cannot execute (Section 12, FR-14).
  2. Validates the supplied arguments against that tool's Pydantic
     schema (schemas.py) — malformed arguments never reach a mutation
     function.
  3. Resolves the target Service by (service_name, environment).
  4. Dispatches to the matching function in tools.py.

What this deliberately does NOT do (STATUS.md Phase 4 Boundary):
authentication, identity/role/ownership checks, environment policy,
rule/ML risk, or the ALLOW/BLOCK/APPROVAL_REQUIRED decision (Section
11). In the finished system only the Gateway calls this, after it has
already made that decision (FR-15). Until the Gateway exists (Phase
7+), calling execute_tool() directly means "this action is being
treated as pre-authorized" — true only for Phase 4 testing, never a
statement about real authorization.
"""
from sqlalchemy.orm import Session

from app.database.enums import Environment
from app.database.models import Service, Tool
from app.mcp.registry import TOOL_REGISTRY
from app.mcp.schemas import TOOL_ARG_SCHEMAS


class MCPError(Exception):
    """Base class for MCP-layer failures. Distinct from a Gateway BLOCK:
    these mean "this request cannot even be dispatched" (unknown tool,
    disabled tool, unknown service, bad arguments) — not a security
    decision."""


class ToolNotFoundError(MCPError):
    pass


class ToolDisabledError(MCPError):
    pass


class ServiceNotFoundError(MCPError):
    pass


def execute_tool(
    db: Session,
    tool_name: str,
    service_name: str,
    environment: Environment,
    **kwargs,
) -> dict:
    if tool_name not in TOOL_REGISTRY:
        raise ToolNotFoundError(f"'{tool_name}' is not a known MCP tool.")

    tool_row = db.query(Tool).filter_by(tool_name=tool_name).one_or_none()
    if tool_row is None:
        raise ToolNotFoundError(
            f"'{tool_name}' is not registered in the tools table "
            f"(did you run app.mcp.registry.seed_tools?)."
        )
    if not tool_row.enabled:
        raise ToolDisabledError(f"'{tool_name}' is registered but disabled.")

    schema_cls = TOOL_ARG_SCHEMAS[tool_name]
    validated_args = schema_cls(service_name=service_name, environment=environment, **kwargs)

    service = (
        db.query(Service)
        .filter_by(service_name=service_name, environment=environment)
        .one_or_none()
    )
    if service is None:
        raise ServiceNotFoundError(
            f"No service '{service_name}' in environment '{environment.value}'."
        )

    call_kwargs = validated_args.model_dump(exclude={"service_name", "environment"})
    tool_callable = TOOL_REGISTRY[tool_name]["callable"]
    return tool_callable(db, service, **call_kwargs)