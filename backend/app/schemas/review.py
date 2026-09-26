from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.execution import ResultConclusion


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    final_conclusion: ResultConclusion
    comment: str = Field(default="", max_length=4000)


class ReviewRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    schema_version: Literal["1.0"] = "1.0"
    id: str
    task_id: str
    result_id: str
    reviewer_name: str
    previous_conclusion: ResultConclusion
    new_conclusion: ResultConclusion
    comment: str
    created_at: datetime
