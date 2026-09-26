import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Boolean,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import UTCDateTime
from app.schemas.checklist import ExecutorType, Severity, SourceCategory
from app.schemas.execution import EvidenceRole, ReasonCode, ResultConclusion, RunType

if TYPE_CHECKING:
    from app.models.task import VerificationTask


class Evidence(Base):
    __tablename__ = "evidence"
    __table_args__ = (UniqueConstraint("task_id", "evidence_id", name="uq_evidence_task_stable"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id: Mapped[str] = mapped_column(
        ForeignKey("verification_task.id", ondelete="CASCADE"), index=True
    )
    check_item_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    evidence_id: Mapped[str] = mapped_column(String(80), nullable=False)
    file_id: Mapped[str | None] = mapped_column(
        ForeignKey("task_file.id", ondelete="CASCADE"), nullable=True
    )
    role: Mapped[EvidenceRole] = mapped_column(
        Enum(EvidenceRole, native_enum=False), nullable=False
    )
    source_category: Mapped[SourceCategory] = mapped_column(
        Enum(SourceCategory, native_enum=False), nullable=False
    )
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(String(31), default="text", nullable=False)
    locator: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    score: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    asset_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)


class CheckRun(Base):
    __tablename__ = "check_run"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id: Mapped[str] = mapped_column(
        ForeignKey("verification_task.id", ondelete="CASCADE"), index=True
    )
    check_item_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    result_id: Mapped[str | None] = mapped_column(
        ForeignKey("check_result.id", ondelete="SET NULL"), nullable=True
    )
    run_type: Mapped[RunType] = mapped_column(Enum(RunType, native_enum=False), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    executor_type: Mapped[ExecutorType] = mapped_column(
        Enum(ExecutorType, native_enum=False), nullable=False
    )
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    conclusion: Mapped[ResultConclusion | None] = mapped_column(
        Enum(ResultConclusion, native_enum=False), nullable=True
    )
    reason_code: Mapped[ReasonCode | None] = mapped_column(
        Enum(ReasonCode, native_enum=False), nullable=True
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    differences: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    missing_information: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    model_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=lambda: datetime.now(UTC), nullable=False
    )


class CheckResult(Base):
    __tablename__ = "check_result"
    __table_args__ = (UniqueConstraint("task_id", "check_item_id", name="uq_result_task_item"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id: Mapped[str] = mapped_column(
        ForeignKey("verification_task.id", ondelete="CASCADE"), index=True
    )
    check_item_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    check_name: Mapped[str] = mapped_column(String(255), nullable=False)
    check_type: Mapped[str] = mapped_column(String(31), nullable=False)
    executor_type: Mapped[ExecutorType] = mapped_column(
        Enum(ExecutorType, native_enum=False), nullable=False
    )
    severity: Mapped[Severity] = mapped_column(Enum(Severity, native_enum=False), nullable=False)
    system_conclusion: Mapped[ResultConclusion] = mapped_column(
        Enum(ResultConclusion, native_enum=False), nullable=False
    )
    final_conclusion: Mapped[ResultConclusion] = mapped_column(
        Enum(ResultConclusion, native_enum=False), nullable=False
    )
    reason_code: Mapped[ReasonCode] = mapped_column(
        Enum(ReasonCode, native_enum=False), nullable=False
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    has_manual_override: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    task: Mapped["VerificationTask"] = relationship(back_populates="results")
