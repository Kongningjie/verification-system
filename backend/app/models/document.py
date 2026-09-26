import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import UTCDateTime


class FileCategory(StrEnum):
    MANUAL_DOCX = "MANUAL_DOCX"
    TEMPLATE_DOCX = "TEMPLATE_DOCX"
    PROJECT_JSON = "PROJECT_JSON"
    EVIDENCE_PDF = "EVIDENCE_PDF"
    EVIDENCE_IMAGE = "EVIDENCE_IMAGE"


class ParseStatus(StrEnum):
    PENDING = "PENDING"
    PARSED = "PARSED"
    IGNORED = "IGNORED"
    FAILED = "FAILED"


class BlockType(StrEnum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    TABLE_CELL = "table_cell"
    IMAGE = "image"
    PAGE_TEXT = "page_text"


class TaskFile(Base):
    __tablename__ = "task_file"
    __table_args__ = (UniqueConstraint("task_id", "sha256", name="uq_task_file_task_sha256"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id: Mapped[str] = mapped_column(
        ForeignKey("verification_task.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category: Mapped[FileCategory] = mapped_column(
        Enum(FileCategory, native_enum=False), nullable=False
    )
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    declared_mime: Mapped[str] = mapped_column(String(127), nullable=False)
    detected_mime: Mapped[str] = mapped_column(String(127), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    parse_status: Mapped[ParseStatus] = mapped_column(
        Enum(ParseStatus, native_enum=False), default=ParseStatus.PENDING, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=lambda: datetime.now(UTC), nullable=False
    )

    task: Mapped["VerificationTask"] = relationship(back_populates="files")
    blocks: Mapped[list["DocumentBlock"]] = relationship(
        back_populates="task_file", cascade="all, delete-orphan"
    )
    comments: Mapped[list["TemplateComment"]] = relationship(
        back_populates="task_file", cascade="all, delete-orphan"
    )
    assets: Mapped[list["DocumentAsset"]] = relationship(
        back_populates="task_file", cascade="all, delete-orphan"
    )
    warnings: Mapped[list["ParseWarning"]] = relationship(back_populates="task_file")


class DocumentBlock(Base):
    __tablename__ = "document_block"
    __table_args__ = (
        UniqueConstraint("task_file_id", "block_id", name="uq_document_block_file_block"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_file_id: Mapped[str] = mapped_column(
        ForeignKey("task_file.id", ondelete="CASCADE"), nullable=False, index=True
    )
    block_id: Mapped[str] = mapped_column(String(64), nullable=False)
    block_type: Mapped[BlockType] = mapped_column(
        Enum(BlockType, native_enum=False), nullable=False
    )
    text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    heading_path: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    locator: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    related_asset_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)

    task_file: Mapped[TaskFile] = relationship(back_populates="blocks")


class TemplateComment(Base):
    __tablename__ = "template_comment"
    __table_args__ = (
        UniqueConstraint("task_file_id", "comment_id", name="uq_template_comment_file_comment"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_file_id: Mapped[str] = mapped_column(
        ForeignKey("task_file.id", ondelete="CASCADE"), nullable=False, index=True
    )
    comment_id: Mapped[str] = mapped_column(String(64), nullable=False)
    text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    selected_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    heading_path: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    anchor_block_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    context_before: Mapped[str | None] = mapped_column(Text, nullable=True)
    context_after: Mapped[str | None] = mapped_column(Text, nullable=True)
    locator: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    warning_codes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)

    task_file: Mapped[TaskFile] = relationship(back_populates="comments")


class DocumentAsset(Base):
    __tablename__ = "document_asset"
    __table_args__ = (
        UniqueConstraint("task_file_id", "asset_id", name="uq_document_asset_file_asset"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_file_id: Mapped[str] = mapped_column(
        ForeignKey("task_file.id", ondelete="CASCADE"), nullable=False, index=True
    )
    asset_id: Mapped[str] = mapped_column(String(64), nullable=False)
    media_type: Mapped[str] = mapped_column(String(127), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    relationship_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    locator: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    task_file: Mapped[TaskFile] = relationship(back_populates="assets")


class ParseWarning(Base):
    __tablename__ = "parse_warning"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id: Mapped[str] = mapped_column(
        ForeignKey("verification_task.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_file_id: Mapped[str | None] = mapped_column(
        ForeignKey("task_file.id", ondelete="CASCADE"), nullable=True, index=True
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    locator: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    task: Mapped["VerificationTask"] = relationship(back_populates="warnings")
    task_file: Mapped[TaskFile | None] = relationship(back_populates="warnings")


class ProjectMetadata(Base):
    __tablename__ = "project_metadata"

    task_id: Mapped[str] = mapped_column(
        ForeignKey("verification_task.id", ondelete="CASCADE"), primary_key=True
    )
    raw_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    normalized_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    task: Mapped["VerificationTask"] = relationship(back_populates="project_metadata")


from app.models.task import VerificationTask  # noqa: E402
