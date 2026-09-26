from pathlib import Path

import pytest
from app.core.errors import ValidationError
from app.models.document import FileCategory
from app.services.storage import category_for_evidence, safe_path


def test_safe_path_rejects_parent_traversal(tmp_path: Path) -> None:
    with pytest.raises(ValidationError) as exc_info:
        safe_path(tmp_path / "task", "..", "outside.txt")

    assert exc_info.value.code == "PATH_OUTSIDE_TASK"


@pytest.mark.parametrize(
    "filename,category",
    [
        ("evidence.pdf", FileCategory.EVIDENCE_PDF),
        ("photo.PNG", FileCategory.EVIDENCE_IMAGE),
        ("photo.jpeg", FileCategory.EVIDENCE_IMAGE),
    ],
)
def test_evidence_category_uses_supported_extension(filename: str, category: FileCategory) -> None:
    assert category_for_evidence(filename) == category


def test_unknown_evidence_extension_is_rejected() -> None:
    with pytest.raises(ValidationError) as exc_info:
        category_for_evidence("evidence.txt")

    assert exc_info.value.code == "UNSUPPORTED_EVIDENCE_EXTENSION"
