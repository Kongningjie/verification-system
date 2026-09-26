import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.checklist import ExecutorType, Severity, SourceCategory


class ResultConclusion(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    ERROR = "ERROR"


class ReasonCode(StrEnum):
    MATCH = "MATCH"
    MISMATCH = "MISMATCH"
    SOURCE_CONFLICT = "SOURCE_CONFLICT"
    MISSING_TARGET_CONTENT = "MISSING_TARGET_CONTENT"
    MISSING_SOURCE_DATA = "MISSING_SOURCE_DATA"
    MODEL_DISAGREEMENT = "MODEL_DISAGREEMENT"
    AMBIGUOUS_REQUIREMENT = "AMBIGUOUS_REQUIREMENT"
    NOT_APPLICABLE_BY_RULE = "NOT_APPLICABLE_BY_RULE"
    PARSER_ERROR = "PARSER_ERROR"
    MODEL_TIMEOUT = "MODEL_TIMEOUT"
    MODEL_AUTH_ERROR = "MODEL_AUTH_ERROR"
    MODEL_RATE_LIMIT_EXHAUSTED = "MODEL_RATE_LIMIT_EXHAUSTED"
    STRUCTURED_OUTPUT_ERROR = "STRUCTURED_OUTPUT_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class EvidenceRole(StrEnum):
    TARGET = "TARGET"
    SOURCE = "SOURCE"


class RunType(StrEnum):
    PRIMARY = "PRIMARY"
    INDEPENDENT_REVIEW = "INDEPENDENT_REVIEW"
    RETRY = "RETRY"


class EvidenceCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    source_file_id: str | None = None
    role: EvidenceRole
    source_category: SourceCategory
    content: str = Field(max_length=4000)
    locator: dict[str, Any] = Field(default_factory=dict)
    score: float = 0
    asset_path: str | None = None


class AgentJudgement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conclusion: Literal["PASS", "FAIL", "NEEDS_REVIEW"]
    reason_code: ReasonCode
    reason: str = Field(min_length=1, max_length=4000)
    target_evidence_ids: list[str] = Field(default_factory=list)
    source_evidence_ids: list[str] = Field(default_factory=list)
    differences: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_evidence(self) -> "AgentJudgement":
        if not self.target_evidence_ids and not self.source_evidence_ids:
            raise ValueError("Agent judgements must cite at least one candidate evidence ID.")
        allowed = {
            "PASS": {ReasonCode.MATCH},
            "FAIL": {ReasonCode.MISMATCH},
            "NEEDS_REVIEW": {
                ReasonCode.SOURCE_CONFLICT,
                ReasonCode.AMBIGUOUS_REQUIREMENT,
                ReasonCode.MISSING_TARGET_CONTENT,
                ReasonCode.MISSING_SOURCE_DATA,
            },
        }
        if self.reason_code not in allowed[self.conclusion]:
            raise ValueError("The model reason code is inconsistent with its conclusion.")
        return self

    @property
    def evidence_ids(self) -> list[str]:
        return list(dict.fromkeys(self.target_evidence_ids + self.source_evidence_ids))


class AgentExecutionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    check_item_id: str
    requirement: str
    candidates: list[EvidenceCandidate]
    independent_review: bool = False


class ExecutionMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str
    prompt_version: str
    duration_ms: int = Field(ge=0)
    attempts: int = Field(ge=1)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)


class AgentExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    judgement: AgentJudgement
    metadata: ExecutionMetadata


class EvidenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    evidence_id: str
    file_id: str | None
    role: EvidenceRole
    source_category: SourceCategory
    excerpt: str
    content_type: str
    locator: dict[str, Any]
    score: float


class CheckRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    run_type: RunType
    attempt_number: int
    executor_type: ExecutorType
    conclusion: ResultConclusion | None
    reason_code: ReasonCode | None
    reason: str | None
    evidence_ids: list[str]
    differences: list[str]
    missing_information: list[str]
    model_name: str | None
    prompt_version: str
    duration_ms: int
    retry_count: int
    input_tokens: int | None
    output_tokens: int | None
    error_type: str | None
    created_at: datetime


class ReviewRecordSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    reviewer_name: str
    previous_conclusion: ResultConclusion
    new_conclusion: ResultConclusion
    comment: str
    created_at: datetime


class CheckResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    schema_version: Literal["1.0"] = "1.0"
    id: str
    task_id: str
    check_item_id: str
    check_name: str
    requirement: str = ""
    check_type: str
    severity: Severity
    system_conclusion: ResultConclusion
    final_conclusion: ResultConclusion
    reason_code: ReasonCode
    reason: str
    evidence_ids: list[str]
    has_manual_override: bool
    evidences: list[EvidenceResponse] = Field(default_factory=list)
    runs: list[CheckRunResponse] = Field(default_factory=list)
    review_records: list[ReviewRecordSummary] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ResultListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    task_id: str
    task_status: str
    total: int
    page: int
    page_size: int
    items: list[CheckResultResponse]


class ProgressEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str
    type: str
    status: str
    stage: str
    progress: int = Field(ge=0, le=100)
    message: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ResultFilter(BaseModel):
    conclusion: ResultConclusion | None = None
    executor_type: ExecutorType | None = None
    severity: Severity | None = None
    has_manual_override: bool | None = None


class PersistedJudgement(BaseModel):
    conclusion: ResultConclusion
    reason_code: ReasonCode
    reason: str
    evidence_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_evidence_for_decisions(self) -> "PersistedJudgement":
        if (
            self.conclusion in {ResultConclusion.PASS, ResultConclusion.FAIL}
            and not self.evidence_ids
        ):
            raise ValueError("PASS and FAIL conclusions require evidence.")
        return self
