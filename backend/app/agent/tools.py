"""
Tool specs handed to the LLM via bind_tools (decisions.md #17, #22, #28).

Argument schemas come from mcp/schemas.py (TOOL_ARG_SCHEMAS) -- never
duplicated here. Only the human-readable descriptions live in this file.
Specs are plain dicts so the function names are the real tool names
(passing the Pydantic classes would name them `GetLogsArgs`, etc.).
"""
from typing import Any

from app.mcp.schemas import TOOL_ARG_SCHEMAS

TOOL_DESCRIPTIONS: dict[str, str] = {
    "get_logs": "Read recent log lines of a service in an environment. Read-only.",
    "get_metrics": "Read current metrics of a service in an environment. Read-only.",
    "restart_service": "Restart a service in an environment.",
    "rollback_deployment": "Roll a service back to its last known-good version.",
    "deploy_service": "Deploy a specific integer version of a service.",
}


def _inline_refs(node: Any, defs: dict[str, Any]) -> Any:
    """Replace every {"$ref": "#/$defs/X"} with the definition itself.
    Gemini function declarations do not reliably accept JSON-Schema refs."""
    if isinstance(node, dict):
        if "$ref" in node:
            resolved = _inline_refs(defs[node["$ref"].rsplit("/", 1)[-1]], defs)
            siblings = {k: _inline_refs(v, defs) for k, v in node.items() if k != "$ref"}
            return {**resolved, **siblings}
        return {k: _inline_refs(v, defs) for k, v in node.items() if k != "$defs"}
    if isinstance(node, list):
        return [_inline_refs(item, defs) for item in node]
    return node


def build_tool_specs() -> list[dict[str, Any]]:
    specs = []
    for name, model in TOOL_ARG_SCHEMAS.items():
        schema = model.model_json_schema()
        defs = schema.get("$defs", {})
        specs.append(
            {
                "name": name,
                "description": TOOL_DESCRIPTIONS[name],
                "parameters": _inline_refs(schema, defs),
            }
        )
    return specs