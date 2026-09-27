"""
Argument schemas for the five MCP tools (Section 12 / Section 17).

These validate the arguments a tool request carries. This is schema
validation only — the Gateway's own "schema + business validation" step
(Section 8, Section 11 Step 1) is a distinct, later concern (Phase 7+)
that also checks things these schemas cannot, e.g. whether the service
exists, is owned by the requester, etc. Phase 4 schemas only guarantee
"this argument shape is well-formed."
"""
from pydantic import BaseModel, Field

from app.database.enums import Environment


class ServiceTargetArgs(BaseModel):
    """Shared by every tool: all five act on one (service, environment)."""

    service_name: str = Field(..., min_length=1, description="e.g. 'payment-service'")
    environment: Environment


class GetLogsArgs(ServiceTargetArgs):
    limit: int = Field(default=20, ge=1, le=200)


class GetMetricsArgs(ServiceTargetArgs):
    pass


class RestartServiceArgs(ServiceTargetArgs):
    pass


class RollbackDeploymentArgs(ServiceTargetArgs):
    pass


class DeployServiceArgs(ServiceTargetArgs):
    target_version: int = Field(
        ..., gt=0, description="Positive integer version counter (Section 13)"
    )


# tool_name -> argument schema, used by both the registry (schema_def
# seeding) and the server (request validation before dispatch).
TOOL_ARG_SCHEMAS: dict[str, type[BaseModel]] = {
    "get_logs": GetLogsArgs,
    "get_metrics": GetMetricsArgs,
    "restart_service": RestartServiceArgs,
    "rollback_deployment": RollbackDeploymentArgs,
    "deploy_service": DeployServiceArgs,
}