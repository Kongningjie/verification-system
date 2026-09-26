import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Boolean, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import UTCDateTime
from app.schemas.checklist import CheckSourceType, CheckType, Severity

if TYPE_CHECKING:
    from app.models.task import VerificationTask


class CheckItem(Base):
    __tablename__ = "check_item"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id: Mapped[str] = mapped_column(
        ForeignKey("verification_task.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_type: Mapped[CheckSourceType] = mapped_column(
        Enum(CheckSourceType, native_enum=False), nullable=False
    )
    source_comment_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    rule_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    rule_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    requirement: Mapped[str] = mapped_column(Text, nullable=False)
    check_type: Mapped[CheckType] = mapped_column(
        Enum(CheckType, native_enum=False), nullable=False
    )
    severity: Mapped[Severity] = mapped_column(Enum(Severity, native_enum=False), nullable=False)
    required_source_categories: Mapped[list[str]] = mapped_column(
        JSON, default=list, nullable=False
    )
    target_hint: Mapped[str] = mapped_column(Text, default="", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    generation_warnings: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    source_comment_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_selected_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_heading_path: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    generation_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    task: Mapped["VerificationTask"] = relationship(back_populates="check_items")


class ChecklistVersion(Base):
    __tablename__ = "checklist_version"
    __table_args__ = (
        UniqueConstraint("task_id", "version_number", name="uq_checklist_version_task_number"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id: Mapped[str] = mapped_column(
        ForeignKey("verification_task.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    item_count: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    ruleset_version: Mapped[str] = mapped_column(String(32), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=lambda: datetime.now(UTC), nullable=False
    )

    task: Mapped["VerificationTask"] = relationship(back_populates="checklist_versions")
