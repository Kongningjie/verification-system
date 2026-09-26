import uuid
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import Enum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import UTCDateTime


class TaskStatus(StrEnum):
    CREATED = "CREATED"
    VALIDATING = "VALIDATING"
    PARSING = "PARSING"
    GENERATING_CHECKLIST = "GENERATING_CHECKLIST"
    AWAITING_CHECKLIST_CONFIRMATION = "AWAITING_CHECKLIST_CONFIRMATION"
    QUEUED = "QUEUED"
    MATCHING_EVIDENCE = "MATCHING_EVIDENCE"
    CHECKING = "CHECKING"
    AGGREGATING = "AGGREGATING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_ERRORS = "COMPLETED_WITH_ERRORS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    INTERRUPTED = "INTERRUPTED"


class VerificationTask(Base):
    __tablename__ = "verification_task"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, native_enum=False), default=TaskStatus.CREATED, nullable=False
    )
    stage: Mapped[str] = mapped_column(String(64), default=TaskStatus.CREATED.value, nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(16), default="1.0", nullable=False)
    warning_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
    files: Mapped[list["TaskFile"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )
    warnings: Mapped[list["ParseWarning"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )
    project_metadata: Mapped["ProjectMetadata | None"] = relationship(
        back_populates="task", cascade="all, delete-orphan", uselist=False
    )


from app.models.document import ParseWarning, ProjectMetadata, TaskFile  # noqa: E402
