from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Enum as SAEnum, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.database.enums import Decision, RiskLevel


class RiskAssessment(Base):
    __tablename__ = "risk_assessments"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[str] = mapped_column(
        ForeignKey("security_requests.request_id"), nullable=False
    )

    # Section 11 Steps 2-3: computed independently, then
    # final_risk_level = max(rule_risk_level, ml_risk_level).
    # Kept as three separate columns (not one score) so E2's evaluation
    # can show rule vs ML contribution separately.
    rule_risk_level: Mapped[RiskLevel] = mapped_column(
        SAEnum(RiskLevel, native_enum=False, create_constraint=True, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    ml_risk_level: Mapped[RiskLevel] = mapped_column(
        SAEnum(RiskLevel, native_enum=False, create_constraint=True, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    final_risk_level: Mapped[RiskLevel] = mapped_column(
        SAEnum(RiskLevel, native_enum=False, create_constraint=True, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    decision: Mapped[Decision] = mapped_column(
        SAEnum(Decision, native_enum=False, create_constraint=True, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    reasons: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    is_production: Mapped[bool] = mapped_column(Boolean, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    request: Mapped["SecurityRequest"] = relationship("SecurityRequest")

    def __repr__(self) -> str:
        return f"<RiskAssessment {self.request_id} final={self.final_risk_level}>"
