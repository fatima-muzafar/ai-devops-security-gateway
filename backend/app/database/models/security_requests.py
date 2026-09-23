from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum as SAEnum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.database.enums import Decision, Environment


class SecurityRequest(Base):
    __tablename__ = "security_requests"

    # String PK to match the Section 17 example format ("REQ-2001"),
    # not an auto-increment int. This is the join key used by
    # risk_assessments, approval_requests (and optionally incidents).
    request_id: Mapped[str] = mapped_column(String(32), primary_key=True)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"), nullable=False)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"), nullable=False)
    environment: Mapped[Environment] = mapped_column(
        SAEnum(Environment, native_enum=False, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    tool_id: Mapped[int] = mapped_column(ForeignKey("tools.id"), nullable=False)
    arguments: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # Nullable: a row exists the moment the agent submits the request;
    # the Gateway fills this in once Steps 1-4 (Section 11) complete.
    decision: Mapped[Decision | None] = mapped_column(
        SAEnum(Decision, native_enum=False, values_callable=lambda e: [x.value for x in e]),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["User"] = relationship("User")
    agent: Mapped["Agent"] = relationship("Agent")
    service: Mapped["Service"] = relationship("Service")
    tool: Mapped["Tool"] = relationship("Tool")

    def __repr__(self) -> str:
        return f"<SecurityRequest {self.request_id} decision={self.decision}>"
