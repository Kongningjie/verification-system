from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.document import FileCategory, ParseStatus
from app.models.task import TaskStatus
from app.schemas.document import DocumentGraph


class TaskFileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    category: FileCategory
    original_name: str
    declared_mime: str
    detected_mime: str
    size_bytes: int
    sha256: str
    parse_status: ParseStatus


class WarningResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    message: str
    locator: dict[str, Any] = Field(default_factory=dict)


class TaskSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    status: TaskStatus
    stage: str
    progress: int
    warning_count: int
    checklist_revision: int
    confirmed_checklist_version: int | None
    error_code: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    result_total: int = 0
    pass_count: int = 0
    fail_count: int = 0
    needs_review_count: int = 0
    error_count: int = 0
    manual_override_count: int = 0


class TaskDetailResponse(TaskSummaryResponse):
    files: list[TaskFileResponse]
    warnings: list[WarningResponse]
    project: dict[str, Any] | None = None
    documents: list[DocumentGraph] = Field(default_factory=list)


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any]
    request_id: str
