import io
import json
import zipfile
from pathlib import Path

import pymupdf
from PIL import Image


def image_bytes(
    *, format_name: str = "PNG", size: tuple[int, int] = (8, 6), exif_orientation: int | None = None
) -> bytes:
    image = Image.new("RGB", size, color=(30, 120, 200))
    output = io.BytesIO()
    exif = Image.Exif()
    if exif_orientation is not None:
        exif[274] = exif_orientation
    image.save(output, format=format_name, exif=exif)
    return output.getvalue()


def docx_bytes(
    *,
    title: str = "Safety",
    selected_text: str = "Use battery A",
    comment_text: str | None = "Must match certification",
    include_table: bool = True,
    include_image: bool = False,
    missing_comment_end: bool = False,
    comment_in_table: bool = False,
    unknown_image_relationship: bool = False,
    second_heading: str | None = None,
    unsafe_document_xml: bytes | None = None,
    extra_entries: dict[str, bytes] | None = None,
) -> bytes:
    comment_start = '<w:commentRangeStart w:id="7"/>' if comment_text is not None else ""
    comment_end = (
        "" if comment_text is None or missing_comment_end else '<w:commentRangeEnd w:id="7"/>'
    )
    comment_reference = (
        '<w:r><w:commentReference w:id="7"/></w:r>' if comment_text is not None else ""
    )
    drawing_relation_id = "rIdMissing" if unknown_image_relationship else "rIdImage1"
    drawing = ""
    if include_image:
        drawing = f"""
        <w:r><w:drawing><a:graphic><a:graphicData>
          <a:blip r:embed="{drawing_relation_id}"/>
        </a:graphicData></a:graphic></w:drawing></w:r>
        """
    comment_paragraph = f"""
        <w:p>
          {comment_start}<w:r><w:t>{selected_text[:4]}</w:t></w:r>
          <w:r><w:t>{selected_text[4:]}</w:t></w:r>{comment_end}{comment_reference}{drawing}
        </w:p>
    """
    table = ""
    if include_table:
        table_content = (
            comment_paragraph
            if comment_in_table
            else """
          <w:p><w:r><w:t>Table value</w:t></w:r></w:p>
        """
        )
        table = f"""
        <w:tbl><w:tr><w:tc>{table_content}</w:tc></w:tr></w:tbl>
        """
    nested_heading = (
        f'<w:p><w:pPr><w:pStyle w:val="Heading2"/></w:pPr>'
        f"<w:r><w:t>{second_heading}</w:t></w:r></w:p>"
        if second_heading
        else ""
    )
    body_comment_paragraph = "" if comment_in_table else comment_paragraph
    document_xml = (
        unsafe_document_xml
        or f"""<?xml version="1.0" encoding="UTF-8"?>
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
      xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <w:body>
        <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>{title}</w:t></w:r></w:p>
        {nested_heading}
        {body_comment_paragraph}
        {table}
      </w:body>
    </w:document>""".encode()
    )
    comments_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
    <w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:comment w:id="7"><w:p><w:r><w:t>{comment_text or ""}</w:t></w:r></w:p></w:comment>
    </w:comments>""".encode()
    styles_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
    <w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:style w:type="paragraph" w:styleId="Heading1">
        <w:name w:val="heading 1"/><w:pPr><w:outlineLvl w:val="0"/></w:pPr>
      </w:style>
      <w:style w:type="paragraph" w:styleId="Heading2">
        <w:name w:val="heading 2"/><w:pPr><w:outlineLvl w:val="1"/></w:pPr>
      </w:style>
    </w:styles>"""
    relationships = """<?xml version="1.0" encoding="UTF-8"?>
    <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
    {image_relation}
    </Relationships>""".format(
        image_relation=(
            '<Relationship Id="rIdImage1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
            'Target="media/image1.png"/>'
            if include_image
            else ""
        )
    )
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", document_xml)
        archive.writestr("word/styles.xml", styles_xml)
        archive.writestr("word/_rels/document.xml.rels", relationships)
        if comment_text is not None:
            archive.writestr("word/comments.xml", comments_xml)
        if include_image:
            archive.writestr("word/media/image1.png", image_bytes())
        for name, content in (extra_entries or {}).items():
            archive.writestr(name, content)
    return output.getvalue()


def project_json_bytes(**overrides) -> bytes:
    payload = {
        "schema_version": "1.0",
        "project": {
            "product_name": "  Phone  X ",
            "model": "X1",
            "brand": None,
            "market": "EU",
            "language": [" zh-CN ", "en-US"],
        },
        "attributes": {" Battery  Type ": " A  1 "},
    }
    payload.update(overrides)
    return json.dumps(payload, ensure_ascii=False).encode()


def text_pdf(path: Path, text: str = "Certification evidence") -> None:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    document.save(path)
    document.close()


def scanned_pdf(path: Path) -> None:
    document = pymupdf.open()
    page = document.new_page(width=300, height=300)
    page.insert_image(page.rect, stream=image_bytes(size=(100, 100)))
    document.save(path)
    document.close()
