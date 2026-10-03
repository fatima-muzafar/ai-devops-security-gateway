"""
Validation stages (Section 8 / Section 11 Step 1; decisions.md #34, #41):
tool registry -> arguments -> service resolution. Read-only. Each failure
returns a reason that names its stage; the pipeline turns it into a BLOCK.
"""
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.database.enums import Environment
from app.database.models import Service, Tool
from app.mcp.schemas import TOOL_ARG_SCHEMAS

# Mirrors the keys api/mcp.py rejects (#40). Duplicated on purpose (#41): the
# Gateway must not import app.api.mcp.
RESERVED_ARGUMENT_KEYS = frozenset({"db", "tool_name"})
_TARGET_KEYS = frozenset({"service_name", "environment"})


def _q(value: Any) -> str:
    """Truncated repr: escapes control characters, bounds reason length."""
    text = repr(value)
    return text if len(text) <= 70 else text[:67] + "..."


@dataclass(frozen=True)
class ToolCheck:
    tool_id: int | None
    block_reason: str | None


@dataclass(frozen=True)
class ArgumentsCheck:
    service_name: str | None
    environment: Environment | None
    block_reason: str | None


@dataclass(frozen=True)
class ServiceCheck:
    service_id: int | None
    block_reason: str | None


def check_tool_registry(db: Session, tool_name: str) -> ToolCheck:
    row = db.query(Tool).filter_by(tool_name=tool_name).one_or_none()
    if row is None or tool_name not in TOOL_ARG_SCHEMAS:
        return ToolCheck(
            row.id if row else None,
            f"Tool registry stage: tool {_q(tool_name)} is not registered.",
        )
    if not row.enabled:
        return ToolCheck(row.id, f"Tool registry stage: tool {_q(tool_name)} is disabled.")
    return ToolCheck(row.id, None)


def check_arguments(tool_name: str, arguments: dict[str, Any]) -> ArgumentsCheck:
    service_name = arguments.get("service_name")
    env_raw = arguments.get("environment")

    environment: Environment | None = None
    if env_raw is not None:
        try:
            environment = Environment(env_raw)
        except (ValueError, TypeError):
            environment = None

    if not isinstance(service_name, str) or not service_name.strip():
        return ArgumentsCheck(
            None,
            environment,
            "Arguments stage: 'service_name' is required and must be a non-empty string.",
        )
    if env_raw is None:
        return ArgumentsCheck(service_name, None, "Arguments stage: 'environment' is required.")
    if environment is None:
        return ArgumentsCheck(
            service_name,
            None,
            f"Arguments stage: {_q(env_raw)} is not a valid environment.",
        )

    extra = {k: v for k, v in arguments.items() if k not in _TARGET_KEYS}
    reserved = sorted(RESERVED_ARGUMENT_KEYS & extra.keys())
    if reserved:
        return ArgumentsCheck(
            service_name,
            environment,
            f"Arguments stage: reserved argument key(s) {reserved}.",
        )

    try:
        TOOL_ARG_SCHEMAS[tool_name](service_name=service_name, environment=environment, **extra)
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(p) for p in err['loc']) or 'arguments'}: {err['msg']}"
            for err in exc.errors()
        )
        return ArgumentsCheck(
            service_name,
            environment,
            f"Arguments stage: invalid arguments for {_q(tool_name)} ({details}).",
        )

    return ArgumentsCheck(service_name, environment, None)


def resolve_service(db: Session, service_name: str, environment: Environment) -> ServiceCheck:
    row = (
        db.query(Service)
        .filter_by(service_name=service_name, environment=environment)
        .one_or_none()
    )
    if row is None:
        return ServiceCheck(
            None,
            f"Service stage: no service {_q(service_name)} in environment '{environment.value}'.",
        )
    return ServiceCheck(row.id, None)