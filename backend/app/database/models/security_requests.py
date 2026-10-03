from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum as SAEnum, ForeignKey, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.database.enums import Decision, Environment, ExecutionStatus


class SecurityRequest(Base):
    __tablename__ = "security_requests"

    # String PK to match the Section 17 example format ("REQ-2001"),
    # not an auto-increment int. This is the join key used by
    # risk_assessments, approval_requests (and optionally incidents).
    request_id: Mapped[str] = mapped_column(String(32), primary_key=True)

    # decisions.md #32 / #39: NULL means the submitted value did not resolve
    # to a row (or, for environment, to a valid Environment value). The raw
    # submitted payload is preserved in `raw_request`.
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    agent_id: Mapped[int | None] = mapped_column(ForeignKey("agents.id"), nullable=True)
    service_id: Mapped[int | None] = mapped_column(ForeignKey("services.id"), nullable=True)
    environment: Mapped[Environment | None] = mapped_column(
        SAEnum(Environment, native_enum=False, create_constraint=True, values_callable=lambda e: [x.value for x in e]),
        nullable=True,
    )
    tool_id: Mapped[int | None] = mapped_column(ForeignKey("tools.id"), nullable=True)
    arguments: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # decisions.md #32: payload exactly as submitted, so unresolved requests
    # (unknown user, unregistered tool, invalid args) still leave evidence.
    raw_request: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict, server_default=text("'{}'")
    )

    # Nullable: intended for later phases (e.g. pending approval).
    # Phase 7 always writes it.
    decision: Mapped[Decision | None] = mapped_column(
        SAEnum(Decision, native_enum=False, create_constraint=True, values_callable=lambda e: [x.value for x in e]),
        nullable=True,
    )

    # decisions.md #32: the Gateway's reason; set for every BLOCK.
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # decisions.md #32 / Section 22: a failed tool call is never recorded as executed.
    execution_status: Mapped[ExecutionStatus] = mapped_column(
        SAEnum(ExecutionStatus, native_enum=False, create_constraint=True, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
        default=ExecutionStatus.NOT_EXECUTED,
        server_default=ExecutionStatus.NOT_EXECUTED.value,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["User | None"] = relationship("User")
    agent: Mapped["Agent | None"] = relationship("Agent")
    service: Mapped["Service | None"] = relationship("Service")
    tool: Mapped["Tool | None"] = relationship("Tool")

    def __repr__(self) -> str:
        return f"<SecurityRequest {self.request_id} decision={self.decision}>"