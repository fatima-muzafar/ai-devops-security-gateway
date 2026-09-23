from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.database.enums import Environment


class Service(Base):
    __tablename__ = "services"
    __table_args__ = (
        UniqueConstraint("service_name", "environment", name="uq_service_environment"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    service_name: Mapped[str] = mapped_column(String(64), nullable=False)
    environment: Mapped[Environment] = mapped_column(
        SAEnum(Environment, native_enum=False, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )

    # Section 13 (Revision 6): monotonically increasing integer deployment-
    # sequence counters, NOT semver strings. version_change_delta is computed
    # elsewhere as |current_version - target_version|, plain integer
    # subtraction. Do not change this to String.
    current_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    known_good_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="healthy", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    owner: Mapped["User"] = relationship("User")

    def __repr__(self) -> str:
        return f"<Service {self.service_name}/{self.environment} v{self.current_version}>"
