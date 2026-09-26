from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict


class ReportFormat(StrEnum):
    EXCEL = "EXCEL"
    JSON = "JSON"


class ReportStatus(StrEnum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ReportCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: ReportFormat


class ReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    schema_version: Literal["1.0"] = "1.0"
    id: str
    task_id: str
    format: ReportFormat
    status: ReportStatus
    sha256: str | None
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None
