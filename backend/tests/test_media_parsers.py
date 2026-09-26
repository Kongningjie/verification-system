from pathlib import Path

import pytest
from app.core.config import Settings
from app.core.errors import ValidationError
from app.parsers.image import parse_image
from app.parsers.pdf import parse_pdf
from tests.factories import image_bytes, scanned_pdf, text_pdf


def test_text_pdf_has_page_coordinates(tmp_path: Path) -> None:
    source = tmp_path / "evidence.pdf"
    extracted = tmp_path / "extracted"
    extracted.mkdir()
    text_pdf(source)

    graph, is_scanned = parse_pdf(
        source,
        source_file_id="pdf-1",
        extracted_dir=extracted,
        relative_root=tmp_path,
        settings=Settings(_env_file=None, data_root=tmp_path),
    )

    assert not is_scanned
    assert graph.blocks[0].locator["page"] == 1
    assert len(graph.blocks[0].locator["bbox"]) == 4


def test_scanned_pdf_is_identified_and_warned(tmp_path: Path) -> None:
    source = tmp_path / "scan.pdf"
    extracted = tmp_path / "extracted"
    extracted.mkdir()
    scanned_pdf(source)

    graph, is_scanned = parse_pdf(
        source,
        source_file_id="pdf-1",
        extracted_dir=extracted,
        relative_root=tmp_path,
        settings=Settings(_env_file=None, data_root=tmp_path),
    )

    assert is_scanned
    assert [warning.code for warning in graph.parse_warnings] == ["SCANNED_PDF_UNSUPPORTED"]


def test_damaged_pdf_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "broken.pdf"
    source.write_bytes(b"%PDF-1.7\nbroken")
    extracted = tmp_path / "extracted"
    extracted.mkdir()

    with pytest.raises(ValidationError) as exc_info:
        parse_pdf(
            source,
            source_file_id="pdf-1",
            extracted_dir=extracted,
            relative_root=tmp_path,
            settings=Settings(_env_file=None, data_root=tmp_path),
        )

    assert exc_info.value.code == "INVALID_PDF"


def test_image_exif_orientation_is_applied(tmp_path: Path) -> None:
    source = tmp_path / "photo.jpg"
    source.write_bytes(image_bytes(format_name="JPEG", size=(10, 20), exif_orientation=6))
    extracted = tmp_path / "extracted"
    extracted.mkdir()

    graph = parse_image(
        source,
        source_file_id="image-1",
        extracted_dir=extracted,
        relative_root=tmp_path,
        settings=Settings(_env_file=None, data_root=tmp_path),
    )

    assert (graph.assets[0].width, graph.assets[0].height) == (20, 10)
    assert Path(tmp_path, graph.assets[0].storage_path).exists()


@pytest.mark.parametrize(
    "content,max_pixels,code",
    [
        (b"broken", 40_000_000, "INVALID_IMAGE"),
        (image_bytes(size=(30, 30)), 100, "IMAGE_TOO_LARGE"),
    ],
)
def test_damaged_or_oversized_image_is_rejected(
    tmp_path: Path, content: bytes, max_pixels: int, code: str
) -> None:
    source = tmp_path / "image.png"
    source.write_bytes(content)
    extracted = tmp_path / "extracted"
    extracted.mkdir()

    with pytest.raises(ValidationError) as exc_info:
        parse_image(
            source,
            source_file_id="image-1",
            extracted_dir=extracted,
            relative_root=tmp_path,
            settings=Settings(_env_file=None, data_root=tmp_path, max_image_pixels=max_pixels),
        )

    assert exc_info.value.code == code


def test_decoded_image_format_must_match_extension(tmp_path: Path) -> None:
    source = tmp_path / "image.png"
    source.write_bytes(image_bytes(format_name="JPEG"))
    extracted = tmp_path / "extracted"
    extracted.mkdir()

    with pytest.raises(ValidationError) as exc_info:
        parse_image(
            source,
            source_file_id="image-1",
            extracted_dir=extracted,
            relative_root=tmp_path,
            settings=Settings(_env_file=None, data_root=tmp_path),
        )

    assert exc_info.value.code == "IMAGE_FORMAT_MISMATCH"
