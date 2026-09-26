from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

ProjectScalar = str | int | float | bool | list[str] | None


class ProjectCore(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    product_name: str | None = None
    model: str | None = None
    brand: str | None = None
    market: str | None = None
    language: list[str]


class ProjectInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: str
    project: ProjectCore
    attributes: dict[str, ProjectScalar]

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, value: str) -> str:
        if value != "1.0":
            raise ValueError("Only schema_version 1.0 is supported")
        return value

    @field_validator("attributes")
    @classmethod
    def validate_attributes(cls, value: dict[str, ProjectScalar]) -> dict[str, ProjectScalar]:
        for key, item in value.items():
            if not key.strip():
                raise ValueError("Attribute keys cannot be blank")
            if isinstance(item, list) and not all(isinstance(part, str) for part in item):
                raise ValueError("Attribute arrays may contain strings only")
        return value


class ParsedProject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    raw: dict[str, Any]
    normalized: dict[str, Any]
