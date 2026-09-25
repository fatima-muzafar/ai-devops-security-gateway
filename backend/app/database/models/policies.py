from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.database.enums import Environment, Role


class Policy(Base):
    __tablename__ = "policies"

    id: Mapped[int] = mapped_column(primary_key=True)
    role: Mapped[Role] = mapped_column(
        SAEnum(Role, native_enum=False, create_constraint=True, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    tool_id: Mapped[int] = mapped_column(ForeignKey("tools.id"), nullable=False)
    environment: Mapped[Environment] = mapped_column(
        SAEnum(Environment, native_enum=False, create_constraint=True, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    allowed: Mapped[bool] = mapped_column(Boolean, nullable=False)

    # Section 11 Step 2: a policy row can independently force
    # APPROVAL_REQUIRED regardless of computed risk level
    # (e.g. "production deploy always requires approval"). This is a policy
    # flag, evaluated in Step 4 — it is not itself a risk level.
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    tool: Mapped["Tool"] = relationship("Tool")

    def __repr__(self) -> str:
        return f"<Policy role={self.role} tool_id={self.tool_id} env={self.environment}>"
