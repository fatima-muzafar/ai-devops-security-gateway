from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.database.enums import ChangeType


class ServiceStateHistory(Base):
    """decisions.md #7: unified history table for restart/rollback/deploy.

    One row = one state-changing transition that actually happened to a
    service. Only ALLOWED transitions produce a row here — per Section 5 /
    Section 11 of the planning doc, BLOCK means no MCP call and no mock
    state change, so a blocked request has nothing to record. Phase 3 has
    no Gateway yet, so every mutation made while testing Phase 3 in
    isolation is, by definition, an allowed transition.

    This table is the mock environment's own state-transition log. It is
    distinct from behavior_events (Phase 10+), which is the security/ML
    feature-extraction input keyed by identity, not by service.
    """

    __tablename__ = "service_state_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"), nullable=False)

    change_type: Mapped[ChangeType] = mapped_column(
        SAEnum(ChangeType, native_enum=False, create_constraint=True, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )

    # Nullable: restart_service() does not touch version, so both are None
    # when change_type == RESTART. Populated for DEPLOY and ROLLBACK, which
    # mutate services.current_version (Section 13).
    version_before: Mapped[int | None] = mapped_column(Integer, nullable=True)
    version_after: Mapped[int | None] = mapped_column(Integer, nullable=True)

    status_before: Mapped[str] = mapped_column(String(32), nullable=False)
    status_after: Mapped[str] = mapped_column(String(32), nullable=False)

    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    service: Mapped["Service"] = relationship("Service")

    def __repr__(self) -> str:
        return (
            f"<ServiceStateHistory service={self.service_id} "
            f"{self.change_type} v{self.version_before}->{self.version_after}>"
        )