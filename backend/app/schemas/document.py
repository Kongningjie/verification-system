from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.document import BlockType


class DocumentBlockSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    block_id: str
    block_type: BlockType
    text: str = ""
    heading_path: list[str] = Field(default_factory=list)
    order_index: int = Field(ge=0)
    locator: dict[str, Any] = Field(default_factory=dict)
    related_asset_ids: list[str] = Field(default_factory=list)


class TemplateCommentSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comment_id: str
    text: str = ""
    selected_text: str = ""
    heading_path: list[str] = Field(default_factory=list)
    anchor_block_id: str | None = None
    context_before: str | None = None
    context_after: str | None = None
    locator: dict[str, Any] = Field(default_factory=dict)
    warning_codes: list[str] = Field(default_factory=list)


class DocumentAssetSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: str
    media_type: str
    storage_path: str
    sha256: str
    width: int | None = None
    height: int | None = None
    relationship_id: str | None = None
    locator: dict[str, Any] = Field(default_factory=dict)


class ParseWarningSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    locator: dict[str, Any] = Field(default_factory=dict)


class DocumentGraph(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    document_id: str
    source_file_id: str
    kind: Literal["manual", "template", "evidence_pdf", "evidence_image"]
    blocks: list[DocumentBlockSchema] = Field(default_factory=list)
    comments: list[TemplateCommentSchema] = Field(default_factory=list)
    assets: list[DocumentAssetSchema] = Field(default_factory=list)
    parse_warnings: list[ParseWarningSchema] = Field(default_factory=list)
