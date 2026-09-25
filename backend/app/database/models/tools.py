from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Enum as SAEnum, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.enums import Sensitivity


class Tool(Base):
    __tablename__ = "tools"

    id: Mapped[int] = mapped_column(primary_key=True)
    tool_name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    sensitivity: Mapped[Sensitivity] = mapped_column(
        SAEnum(Sensitivity, native_enum=False, create_constraint=True, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    schema_def: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<Tool {self.tool_name} sensitivity={self.sensitivity}>"
