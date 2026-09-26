import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import UTCDateTime
from app.schemas.report import ReportFormat, ReportStatus

if TYPE_CHECKING:
    from app.models.task import VerificationTask


class Report(Base):
    __tablename__ = "report"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id: Mapped[str] = mapped_column(
        ForeignKey("verification_task.id", ondelete="CASCADE"), index=True
    )
    format: Mapped[ReportFormat] = mapped_column(
        Enum(ReportFormat, native_enum=False), nullable=False
    )
    status: Mapped[ReportStatus] = mapped_column(
        Enum(ReportStatus, native_enum=False), nullable=False
    )
    relative_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=lambda: datetime.now(UTC), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    task: Mapped["VerificationTask"] = relationship(back_populates="reports")
