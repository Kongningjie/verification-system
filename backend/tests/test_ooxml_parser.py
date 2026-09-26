from pathlib import Path

import pytest
from app.core.config import Settings
from app.core.errors import ValidationError
from app.parsers.ooxml import parse_docx
from tests.factories import docx_bytes


def parse_fixture(tmp_path: Path, content: bytes, **setting_overrides):
    source = tmp_path / "source.docx"
    source.write_bytes(content)
    extracted = tmp_path / "extracted"
    extracted.mkdir()
    settings = Settings(_env_file=None, data_root=tmp_path, **setting_overrides)
    return parse_docx(
        source,
        source_file_id="file-1",
        kind="template",
        extracted_dir=extracted,
        relative_root=tmp_path,
        settings=settings,
    )


def test_docx_parses_heading_cross_run_comment_table_and_nearby_image(tmp_path: Path) -> None:
    graph = parse_fixture(
        tmp_path,
        docx_bytes(include_image=True, second_heading="Battery", selected_text="Use battery A"),
    )

    assert [block.block_type.value for block in graph.blocks] == [
        "heading",
        "heading",
        "paragraph",
        "image",
        "table_cell",
    ]
    assert graph.blocks[2].heading_path == ["Safety", "Battery"]
    assert graph.comments[0].selected_text == "Use battery A"
    assert graph.comments[0].anchor_block_id == graph.blocks[2].block_id
    assert graph.comments[0].context_before == "Battery"
    assert graph.comments[0].context_after == "Table value"
    assert graph.comments[0].locator["nearby_asset_ids"] == ["asset-0"]
    assert graph.assets[0].relationship_id == "rIdImage1"


def test_comment_inside_table_is_anchored_to_table_cell(tmp_path: Path) -> None:
    graph = parse_fixture(tmp_path, docx_bytes(comment_in_table=True))

    assert graph.comments[0].selected_text == "Use battery A"
    assert graph.comments[0].locator["block_type"] == "table_cell"
    assert graph.comments[0].locator["block_index"] == 1


def test_incomplete_comment_range_produces_explicit_warning(tmp_path: Path) -> None:
    graph = parse_fixture(tmp_path, docx_bytes(missing_comment_end=True))

    assert "COMMENT_RANGE_END_MISSING" in graph.comments[0].warning_codes
    assert {warning.code for warning in graph.parse_warnings} >= {"COMMENT_RANGE_END_MISSING"}


def test_unknown_image_relationship_produces_warning(tmp_path: Path) -> None:
    graph = parse_fixture(tmp_path, docx_bytes(include_image=True, unknown_image_relationship=True))

    assert "UNKNOWN_IMAGE_RELATIONSHIP" in {warning.code for warning in graph.parse_warnings}


@pytest.mark.parametrize(
    "content,settings,code",
    [
        (docx_bytes(extra_entries={"../outside.txt": b"bad"}), {}, "ZIP_SLIP"),
        (
            docx_bytes(extra_entries={"word/media/bomb.bin": b"A" * 20_000}),
            {"max_docx_compression_ratio": 10},
            "DOCX_COMPRESSION_RATIO_EXCEEDED",
        ),
        (docx_bytes(), {"max_xml_nodes": 3}, "XML_NODE_LIMIT_EXCEEDED"),
        (b"not-a-zip", {}, "INVALID_DOCX"),
    ],
)
def test_unsafe_or_damaged_docx_is_rejected(
    tmp_path: Path, content: bytes, settings: dict, code: str
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        parse_fixture(tmp_path, content, **settings)

    assert exc_info.value.code == code


def test_external_entity_declaration_is_rejected(tmp_path: Path) -> None:
    unsafe_xml = b"""<?xml version="1.0"?>
    <!DOCTYPE w:document [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body><w:p><w:r><w:t>&xxe;</w:t></w:r></w:p></w:body>
    </w:document>"""

    with pytest.raises(ValidationError) as exc_info:
        parse_fixture(tmp_path, docx_bytes(unsafe_document_xml=unsafe_xml))

    assert exc_info.value.code == "UNSAFE_XML"
