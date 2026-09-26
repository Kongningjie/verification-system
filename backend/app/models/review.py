import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import UTCDateTime
from app.schemas.execution import ResultConclusion

if TYPE_CHECKING:
    from app.models.task import VerificationTask


class ReviewRecord(Base):
    __tablename__ = "review_record"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id: Mapped[str] = mapped_column(
        ForeignKey("verification_task.id", ondelete="CASCADE"), index=True
    )
    result_id: Mapped[str] = mapped_column(
        ForeignKey("check_result.id", ondelete="CASCADE"), index=True
    )
    reviewer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    previous_conclusion: Mapped[ResultConclusion] = mapped_column(
        Enum(ResultConclusion, native_enum=False), nullable=False
    )
    new_conclusion: Mapped[ResultConclusion] = mapped_column(
        Enum(ResultConclusion, native_enum=False), nullable=False
    )
    comment: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=lambda: datetime.now(UTC), nullable=False
    )

    task: Mapped["VerificationTask"] = relationship(back_populates="review_records")
