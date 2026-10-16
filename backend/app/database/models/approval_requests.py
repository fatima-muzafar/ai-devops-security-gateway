from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum as SAEnum, ForeignKey, String, Text, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.database.enums import ApprovalStatus


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"
    __table_args__ = (UniqueConstraint("request_id", name="uq_approval_requests_request_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[str] = mapped_column(
        ForeignKey("security_requests.request_id"), nullable=False
    )
    status: Mapped[ApprovalStatus] = mapped_column(
        SAEnum(ApprovalStatus, native_enum=False, create_constraint=True, values_callable=lambda e: [x.value for x in e]),
        default=ApprovalStatus.PENDING,
        nullable=False,
    )
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reason: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # decisions.md #81: set on approve AND reject (was approved_at).
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # #81/#84: service versions at request time; revalidation compares against them.
    state_snapshot: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict, server_default=text("'{}'")
    )
    # #81: NULL = revalidation not run; "passed" or the BLOCK reason.
    revalidation: Mapped[str | None] = mapped_column(Text, nullable=True)

    request: Mapped["SecurityRequest"] = relationship("SecurityRequest")
    reviewer: Mapped["User"] = relationship("User")

    def __repr__(self) -> str:
        return f"<ApprovalRequest {self.request_id} status={self.status}>"
