import json
from pathlib import Path

import pytest
from app.core.errors import ValidationError
from app.parsers.project_json import parse_project_json
from tests.factories import project_json_bytes


def test_project_json_preserves_raw_and_normalizes_values(tmp_path: Path) -> None:
    path = tmp_path / "project.json"
    path.write_bytes(project_json_bytes())

    parsed = parse_project_json(path)

    assert parsed.raw["project"]["product_name"] == "  Phone  X "
    assert parsed.normalized["project"]["product_name"] == "Phone X"
    assert parsed.normalized["attributes"] == {"Battery Type": "A 1"}


@pytest.mark.parametrize(
    "payload,code",
    [
        ({"schema_version": "2.0", "project": {}, "attributes": {}}, "INVALID_PROJECT_SCHEMA"),
        (
            {
                "schema_version": "1.0",
                "project": {"language": []},
                "attributes": {"nested": {"bad": True}},
            },
            "INVALID_PROJECT_SCHEMA",
        ),
    ],
)
def test_invalid_project_json_is_rejected(tmp_path: Path, payload: dict, code: str) -> None:
    path = tmp_path / "project.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValidationError) as exc_info:
        parse_project_json(path)

    assert exc_info.value.code == code


def test_normalized_duplicate_attribute_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "project.json"
    path.write_bytes(project_json_bytes(attributes={"Model  Name": "A", "Model Name": "B"}))

    with pytest.raises(ValidationError) as exc_info:
        parse_project_json(path)

    assert exc_info.value.code == "DUPLICATE_NORMALIZED_ATTRIBUTE"
