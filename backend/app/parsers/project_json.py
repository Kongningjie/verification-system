import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from pydantic import ValidationError as PydanticValidationError

from app.core.errors import ValidationError
from app.schemas.project import ParsedProject, ProjectInput


def parse_project_json(path: Path) -> ParsedProject:
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError("INVALID_PROJECT_JSON", "The project JSON is invalid.") from exc
    if not isinstance(raw, dict):
        raise ValidationError("INVALID_PROJECT_JSON", "The project JSON root must be an object.")

    try:
        validated = ProjectInput.model_validate(raw)
    except PydanticValidationError as exc:
        raise ValidationError(
            "INVALID_PROJECT_SCHEMA",
            "The project JSON does not conform to schema_version 1.0.",
            details={"errors": exc.errors(include_input=False, include_url=False)},
        ) from exc

    project = {
        key: _normalize_value(value) for key, value in validated.project.model_dump().items()
    }
    attributes: dict[str, Any] = {}
    for raw_key, value in validated.attributes.items():
        normalized_key = _normalize_text(raw_key)
        if normalized_key in attributes:
            raise ValidationError(
                "DUPLICATE_NORMALIZED_ATTRIBUTE",
                "Two attribute keys become identical after normalization.",
                details={"key": normalized_key},
            )
        attributes[normalized_key] = _normalize_value(value)

    return ParsedProject(
        raw=raw,
        normalized={
            "schema_version": "1.0",
            "project": project,
            "attributes": attributes,
        },
    )


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value)).strip()


def _normalize_value(value: Any) -> Any:
    if isinstance(value, str):
        return _normalize_text(value)
    if isinstance(value, list):
        return [_normalize_text(item) for item in value]
    return value
