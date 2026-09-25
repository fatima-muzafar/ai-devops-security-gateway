from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.database.enums import Environment, EventOutcome


class BehaviorEvent(Base):
    __tablename__ = "behavior_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    identity_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"), nullable=False)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"), nullable=False)
    environment: Mapped[Environment] = mapped_column(
        SAEnum(Environment, native_enum=False, create_constraint=True, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    tool_id: Mapped[int] = mapped_column(ForeignKey("tools.id"), nullable=False)
    outcome: Mapped[EventOutcome] = mapped_column(
        SAEnum(EventOutcome, native_enum=False, create_constraint=True, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # CRITICAL: snapshot of services.current_version AT THE TIME of this
    # action — not computed later via a live join to services. If you skip
    # this and join to services.current_version when building features in
    # Semester 2, every historical version_change_delta will silently use
    # TODAY's version instead of the version at the time of the past action.
    # Null for read-only tools (get_logs, get_metrics) that don't touch version.
    version_before: Mapped[int | None] = mapped_column(Integer, nullable=True)
    version_after: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Section 10: off_hours_flag - whether this timestamp fell outside the
    # configured working-hours window. Computed at write time, stored, not
    # derived later.
    off_hours_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    identity: Mapped["User"] = relationship("User")
    agent: Mapped["Agent"] = relationship("Agent")
    service: Mapped["Service"] = relationship("Service")
    tool: Mapped["Tool"] = relationship("Tool")

    def __repr__(self) -> str:
        return f"<BehaviorEvent identity={self.identity_id} tool={self.tool_id} outcome={self.outcome}>"
