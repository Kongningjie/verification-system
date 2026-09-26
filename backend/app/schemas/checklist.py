from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CheckSourceType(StrEnum):
    COMMON_RULE = "COMMON_RULE"
    TEMPLATE_COMMENT = "TEMPLATE_COMMENT"


class BaseCheckType(StrEnum):
    FIELD = "FIELD"
    SEMANTIC = "SEMANTIC"
    VISUAL = "VISUAL"
    STRUCTURE = "STRUCTURE"


class CheckType(StrEnum):
    FIELD = "FIELD"
    SEMANTIC = "SEMANTIC"
    VISUAL = "VISUAL"
    STRUCTURE = "STRUCTURE"
    CUSTOM_SEMANTIC = "CUSTOM_SEMANTIC"
    CUSTOM_VISUAL = "CUSTOM_VISUAL"
    CUSTOM_STRUCTURE = "CUSTOM_STRUCTURE"


class Severity(StrEnum):
    CRITICAL = "CRITICAL"
    NORMAL = "NORMAL"


class SourceCategory(StrEnum):
    MANUAL = "MANUAL"
    PROJECT = "PROJECT"
    EVIDENCE_PDF = "EVIDENCE_PDF"
    EVIDENCE_IMAGE = "EVIDENCE_IMAGE"


class ExecutorType(StrEnum):
    FIELD_RULE = "FIELD_RULE"
    STRUCTURE_RULE = "STRUCTURE_RULE"
    SEMANTIC_AGENT = "SEMANTIC_AGENT"
    VISION_AGENT = "VISION_AGENT"


class CommonRuleDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_id: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=4000)
    check_type: BaseCheckType
    default_severity: Severity
    required_sources: list[SourceCategory]
    applicability: str = Field(min_length=1, max_length=255)
    executor: ExecutorType


class CommonRuleCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    ruleset_version: str
    rules: list[CommonRuleDefinition]

    @model_validator(mode="after")
    def validate_unique_rules(self) -> "CommonRuleCatalog":
        identities = [(rule.rule_id, rule.version) for rule in self.rules]
        if len(identities) != len(set(identities)):
            raise ValueError("Common rule IDs and versions must be unique.")
        return self


class GeneratedCheckItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_comment_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    requirement: str = Field(min_length=1, max_length=4000)
    check_type: BaseCheckType
    severity_suggestion: Severity
    severity_reason: str = Field(max_length=1000)
    required_source_categories: list[SourceCategory]
    target_hint: str = Field(default="", max_length=1000)
    rule_mapping_id: str | None = Field(default=None, max_length=100)
    generation_warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def critical_requires_reason(self) -> "GeneratedCheckItem":
        if self.severity_suggestion == Severity.CRITICAL and not self.severity_reason.strip():
            raise ValueError("CRITICAL suggestions must include a severity reason.")
        return self


class GeneratedCheckItems(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: Annotated[list[GeneratedCheckItem], Field(min_length=1)]


class CommentGenerationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comment_id: str
    comment_text: str
    selected_text: str
    heading_path: list[str]
    context_before: str | None
    context_after: str | None
    available_source_categories: list[SourceCategory]
    common_rule_summaries: list[dict[str, str]]


class AgentRunMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str
    prompt_version: str
    duration_ms: int = Field(ge=0)
    attempts: int = Field(ge=1)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)


class CommentGenerationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    output: GeneratedCheckItems
    metadata: AgentRunMetadata


class CheckItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_type: CheckSourceType
    source_comment_id: str | None
    rule_id: str | None
    rule_version: str | None
    name: str
    requirement: str
    check_type: CheckType
    severity: Severity
    required_source_categories: list[SourceCategory]
    target_hint: str
    enabled: bool
    generation_warnings: list[str]
    source_comment_text: str | None
    source_selected_text: str | None
    source_heading_path: list[str]
    version: int
    created_at: datetime
    updated_at: datetime


class CheckItemListResponse(BaseModel):
    schema_version: str = "1.0"
    task_id: str
    task_status: str
    checklist_revision: int
    confirmed_version: int | None
    items: list[CheckItemResponse]


class CheckItemPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    requirement: str | None = Field(default=None, min_length=1, max_length=4000)
    check_type: CheckType | None = None
    severity: Severity | None = None
    required_source_categories: list[SourceCategory] | None = None
    target_hint: str | None = Field(default=None, max_length=1000)
    enabled: bool | None = None


class ConfirmChecklistRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)


class ChecklistVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    schema_version: str = "1.0"
    id: str
    task_id: str
    version_number: int
    item_count: int
    snapshot: list[CheckItemResponse]
    ruleset_version: str
    prompt_version: str
    model_name: str
    created_at: datetime
