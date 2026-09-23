from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class Incident(Base):
    """
    Optional security incident/alert tracking (Section 16 marks this table
    optional). Deliberately minimal - no logic is wired to it in Phase 2.
    Do not expand this table until something actually writes to it.
    """
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[str | None] = mapped_column(
        ForeignKey("security_requests.request_id"), nullable=True
    )
    description: Mapped[str] = mapped_column(String, nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="low")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    request: Mapped["SecurityRequest"] = relationship("SecurityRequest")

    def __repr__(self) -> str:
        return f"<Incident {self.id} severity={self.severity}>"
