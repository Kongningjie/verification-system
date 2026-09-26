import hashlib
import io
import posixpath
import re
import uuid
import zipfile
from collections.abc import Iterable
from pathlib import Path, PurePosixPath
from typing import Any

from lxml import etree
from PIL import Image, UnidentifiedImageError

from app.core.config import Settings
from app.core.errors import ValidationError
from app.schemas.document import (
    DocumentAssetSchema,
    DocumentBlockSchema,
    DocumentGraph,
    ParseWarningSchema,
    TemplateCommentSchema,
)

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"w": W_NS, "r": R_NS, "a": A_NS, "pr": PKG_REL_NS}


def _tag(namespace: str, local: str) -> str:
    return f"{{{namespace}}}{local}"


def _safe_xml(content: bytes, settings: Settings, *, part_name: str) -> etree._Element:
    upper = content[:4096].upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise ValidationError(
            "UNSAFE_XML",
            "OOXML parts containing DTD or entity declarations are not supported.",
            details={"part": part_name},
        )
    parser = etree.XMLParser(
        resolve_entities=False,
        load_dtd=False,
        no_network=True,
        huge_tree=False,
        recover=False,
    )
    try:
        root = etree.fromstring(content, parser=parser)
    except etree.XMLSyntaxError as exc:
        raise ValidationError(
            "INVALID_OOXML_XML", "An OOXML XML part is invalid.", details={"part": part_name}
        ) from exc
    if sum(1 for _ in root.iter()) > settings.max_xml_nodes:
        raise ValidationError(
            "XML_NODE_LIMIT_EXCEEDED",
            "An OOXML XML part exceeds the configured node limit.",
            details={"part": part_name},
        )
    return root


def _validate_archive(archive: zipfile.ZipFile, settings: Settings) -> set[str]:
    infos = archive.infolist()
    if len(infos) > settings.max_docx_entries:
        raise ValidationError("DOCX_TOO_MANY_ENTRIES", "The DOCX contains too many ZIP entries.")
    total_size = 0
    names: set[str] = set()
    for info in infos:
        normalized_name = info.filename.replace("\\", "/")
        pure_name = PurePosixPath(normalized_name)
        if pure_name.is_absolute() or ".." in pure_name.parts:
            raise ValidationError("ZIP_SLIP", "The DOCX contains an unsafe ZIP entry path.")
        if info.flag_bits & 0x1:
            raise ValidationError("ENCRYPTED_DOCX", "Encrypted DOCX entries are not supported.")
        total_size += info.file_size
        if total_size > settings.max_docx_uncompressed_bytes:
            raise ValidationError(
                "DOCX_UNCOMPRESSED_LIMIT_EXCEEDED",
                "The DOCX uncompressed size exceeds the configured limit.",
            )
        if (
            info.file_size
            and info.file_size / max(info.compress_size, 1) > settings.max_docx_compression_ratio
        ):
            raise ValidationError(
                "DOCX_COMPRESSION_RATIO_EXCEEDED",
                "The DOCX contains a suspiciously compressed ZIP entry.",
            )
        names.add(normalized_name)
    if "word/document.xml" not in names or "[Content_Types].xml" not in names:
        raise ValidationError("INVALID_DOCX", "The ZIP file is not a valid Word DOCX document.")
    return names


def _read_part(
    archive: zipfile.ZipFile, names: set[str], name: str, settings: Settings
) -> etree._Element | None:
    if name not in names:
        return None
    return _safe_xml(archive.read(name), settings, part_name=name)


def _heading_styles(
    archive: zipfile.ZipFile, names: set[str], settings: Settings
) -> dict[str, int]:
    root = _read_part(archive, names, "word/styles.xml", settings)
    result: dict[str, int] = {}
    if root is None:
        return result
    for style in root.xpath("//w:style[@w:type='paragraph']", namespaces=NS):
        style_id = style.get(_tag(W_NS, "styleId"))
        name_node = style.find("w:name", namespaces=NS)
        outline_node = style.find("w:pPr/w:outlineLvl", namespaces=NS)
        if not style_id:
            continue
        level: int | None = None
        if outline_node is not None:
            value = outline_node.get(_tag(W_NS, "val"))
            if value is not None and value.isdigit():
                level = int(value) + 1
        if level is None and name_node is not None:
            style_name = name_node.get(_tag(W_NS, "val"), "")
            match = re.search(r"(?:heading|标题)\s*([1-9])", style_name, re.IGNORECASE)
            if match:
                level = int(match.group(1))
        if level is None:
            match = re.fullmatch(r"Heading([1-9])", style_id, re.IGNORECASE)
            if match:
                level = int(match.group(1))
        if level is not None:
            result[style_id] = level
    return result


def _relationships(archive: zipfile.ZipFile, names: set[str], settings: Settings) -> dict[str, str]:
    root = _read_part(archive, names, "word/_rels/document.xml.rels", settings)
    if root is None:
        return {}
    relationships: dict[str, str] = {}
    for relation in root.xpath("//pr:Relationship", namespaces=NS):
        relation_id = relation.get("Id")
        target = relation.get("Target")
        if not relation_id or not target or relation.get("TargetMode") == "External":
            continue
        resolved = posixpath.normpath(posixpath.join("word", target)).replace("\\", "/")
        if not resolved.startswith("word/") or ".." in PurePosixPath(resolved).parts:
            raise ValidationError("ZIP_SLIP", "A DOCX relationship leaves the word directory.")
        relationships[relation_id] = resolved
    return relationships


def _comment_texts(archive: zipfile.ZipFile, names: set[str], settings: Settings) -> dict[str, str]:
    root = _read_part(archive, names, "word/comments.xml", settings)
    if root is None:
        return {}
    comments: dict[str, str] = {}
    for comment in root.xpath("//w:comment", namespaces=NS):
        comment_id = comment.get(_tag(W_NS, "id"))
        if comment_id is not None:
            comments[comment_id] = "".join(comment.itertext()).strip()
    return comments


def _paragraphs_in_table(table: etree._Element) -> Iterable[tuple[etree._Element, dict[str, int]]]:
    for row_index, row in enumerate(table.findall("w:tr", namespaces=NS)):
        for column_index, cell in enumerate(row.findall("w:tc", namespaces=NS)):
            for paragraph in cell.xpath(
                ".//w:p[not(ancestor::w:tc/ancestor::w:tc)]", namespaces=NS
            ):
                yield paragraph, {"row": row_index, "column": column_index}


def parse_docx(
    path: Path,
    *,
    source_file_id: str,
    kind: str,
    extracted_dir: Path,
    relative_root: Path,
    settings: Settings,
) -> DocumentGraph:
    try:
        archive = zipfile.ZipFile(path)
    except zipfile.BadZipFile as exc:
        raise ValidationError("INVALID_DOCX", "The DOCX ZIP container is invalid.") from exc

    try:
        names = _validate_archive(archive, settings)
        document_root = _read_part(archive, names, "word/document.xml", settings)
        if document_root is None:
            raise ValidationError("INVALID_DOCX", "The DOCX has no document.xml part.")
        style_levels = _heading_styles(archive, names, settings)
        relationships = _relationships(archive, names, settings)
        comment_texts = _comment_texts(archive, names, settings)

        blocks: list[DocumentBlockSchema] = []
        assets: list[DocumentAssetSchema] = []
        warnings: list[ParseWarningSchema] = []
        heading_stack: list[str] = []
        active_comments: dict[str, list[str]] = {}
        comment_state: dict[str, dict[str, Any]] = {
            comment_id: {
                "selected": [],
                "anchor": None,
                "heading_path": [],
                "start": False,
                "end": False,
                "reference": False,
            }
            for comment_id in comment_texts
        }
        extracted_assets: dict[str, str] = {}

        def warning(code: str, message: str, locator: dict[str, Any] | None = None) -> None:
            warnings.append(ParseWarningSchema(code=code, message=message, locator=locator or {}))

        def ensure_comment(comment_id: str) -> dict[str, Any]:
            if comment_id not in comment_state:
                comment_state[comment_id] = {
                    "selected": [],
                    "anchor": None,
                    "heading_path": [],
                    "start": False,
                    "end": False,
                    "reference": False,
                }
                warning(
                    "COMMENT_DEFINITION_MISSING",
                    "A comment range references an ID absent from comments.xml.",
                    {"comment_id": comment_id},
                )
            return comment_state[comment_id]

        def extract_asset(relation_id: str, locator: dict[str, Any]) -> str | None:
            if relation_id in extracted_assets:
                return extracted_assets[relation_id]
            part_name = relationships.get(relation_id)
            if not part_name or part_name not in names:
                warning(
                    "UNKNOWN_IMAGE_RELATIONSHIP",
                    "An image relationship could not be resolved.",
                    {**locator, "relationship_id": relation_id},
                )
                return None
            if not part_name.startswith("word/media/"):
                warning(
                    "UNSUPPORTED_IMAGE_RELATIONSHIP",
                    "A drawing points to a non-media OOXML part.",
                    {**locator, "relationship_id": relation_id},
                )
                return None
            content = archive.read(part_name)
            try:
                with Image.open(io.BytesIO(content)) as image:
                    width, height = image.size
                    if width * height > settings.max_image_pixels:
                        raise ValidationError(
                            "IMAGE_TOO_LARGE", "An embedded DOCX image exceeds the pixel limit."
                        )
                    image.load()
                    media_type = Image.MIME.get(image.format or "", "application/octet-stream")
            except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
                raise ValidationError(
                    "INVALID_EMBEDDED_IMAGE", "An embedded DOCX image cannot be decoded safely."
                ) from exc
            suffix = Path(part_name).suffix.lower() or ".bin"
            output_path = extracted_dir / f"{uuid.uuid4()}{suffix}"
            output_path.write_bytes(content)
            asset_id = f"asset-{len(assets)}"
            assets.append(
                DocumentAssetSchema(
                    asset_id=asset_id,
                    media_type=media_type,
                    storage_path=output_path.relative_to(relative_root).as_posix(),
                    sha256=hashlib.sha256(content).hexdigest(),
                    width=width,
                    height=height,
                    relationship_id=relation_id,
                    locator=locator,
                )
            )
            extracted_assets[relation_id] = asset_id
            return asset_id

        def consume_paragraph(
            paragraph: etree._Element,
            *,
            table_locator: dict[str, int] | None = None,
            table_index: int | None = None,
        ) -> None:
            nonlocal heading_stack
            block_id = f"block-{len(blocks)}"
            text_parts: list[str] = []
            has_comment_marker = False
            paragraph_comment_ids: set[str] = set(active_comments)

            for element in paragraph.iter():
                if element.tag == _tag(W_NS, "commentRangeStart"):
                    comment_id = element.get(_tag(W_NS, "id"))
                    if comment_id is not None:
                        state = ensure_comment(comment_id)
                        state["start"] = True
                        if state["anchor"] is None:
                            state["anchor"] = block_id
                            state["heading_path"] = list(heading_stack)
                        active_comments[comment_id] = state["selected"]
                        paragraph_comment_ids.add(comment_id)
                        has_comment_marker = True
                elif element.tag == _tag(W_NS, "t"):
                    text = element.text or ""
                    text_parts.append(text)
                    for selected in active_comments.values():
                        selected.append(text)
                elif element.tag == _tag(W_NS, "tab"):
                    text_parts.append("\t")
                    for selected in active_comments.values():
                        selected.append("\t")
                elif element.tag in {_tag(W_NS, "br"), _tag(W_NS, "cr")}:
                    text_parts.append("\n")
                    for selected in active_comments.values():
                        selected.append("\n")
                elif element.tag == _tag(W_NS, "commentRangeEnd"):
                    comment_id = element.get(_tag(W_NS, "id"))
                    if comment_id is not None:
                        state = ensure_comment(comment_id)
                        state["end"] = True
                        active_comments.pop(comment_id, None)
                        paragraph_comment_ids.add(comment_id)
                        has_comment_marker = True
                elif element.tag == _tag(W_NS, "commentReference"):
                    comment_id = element.get(_tag(W_NS, "id"))
                    if comment_id is not None:
                        ensure_comment(comment_id)["reference"] = True
                        paragraph_comment_ids.add(comment_id)
                        has_comment_marker = True

            text = "".join(text_parts).strip()
            style_node = paragraph.find("w:pPr/w:pStyle", namespaces=NS)
            style_id = style_node.get(_tag(W_NS, "val")) if style_node is not None else None
            heading_level = style_levels.get(style_id or "")
            block_type = "table_cell" if table_locator is not None else "paragraph"
            if heading_level is not None and text:
                heading_stack = heading_stack[: heading_level - 1]
                while len(heading_stack) < heading_level - 1:
                    heading_stack.append("")
                heading_stack.append(text)
                block_type = "heading"

            relation_ids = [
                element.get(_tag(R_NS, "embed"))
                for element in paragraph.xpath(".//a:blip", namespaces=NS)
                if element.get(_tag(R_NS, "embed"))
            ]
            locator: dict[str, Any] = {"block_index": len(blocks)}
            if table_locator is not None:
                locator.update({"table": table_index, **table_locator})
            asset_pairs: list[tuple[str, str]] = []
            for relation_id in relation_ids:
                asset_id = extract_asset(
                    relation_id,
                    {**locator, "relationship_id": relation_id},
                )
                if asset_id:
                    asset_pairs.append((relation_id, asset_id))
            related_assets = [asset_id for _, asset_id in asset_pairs]

            if text or has_comment_marker or not related_assets:
                blocks.append(
                    DocumentBlockSchema(
                        block_id=block_id,
                        block_type=block_type,
                        text=text,
                        heading_path=list(heading_stack),
                        order_index=len(blocks),
                        locator=locator,
                        related_asset_ids=related_assets,
                    )
                )
            for relation_id, asset_id in asset_pairs:
                blocks.append(
                    DocumentBlockSchema(
                        block_id=f"block-{len(blocks)}",
                        block_type="image",
                        heading_path=list(heading_stack),
                        order_index=len(blocks),
                        locator={**locator, "relationship_id": relation_id},
                        related_asset_ids=[asset_id],
                    )
                )
            for comment_id in paragraph_comment_ids:
                state = ensure_comment(comment_id)
                if state["anchor"] is None:
                    state["anchor"] = block_id
                    state["heading_path"] = list(heading_stack)

        body = document_root.find("w:body", namespaces=NS)
        if body is None:
            raise ValidationError("INVALID_DOCX", "The DOCX body is missing.")
        table_index = 0
        for child in body:
            if child.tag == _tag(W_NS, "p"):
                consume_paragraph(child)
            elif child.tag == _tag(W_NS, "tbl"):
                for paragraph, cell_locator in _paragraphs_in_table(child):
                    consume_paragraph(
                        paragraph, table_locator=cell_locator, table_index=table_index
                    )
                table_index += 1

        comments: list[TemplateCommentSchema] = []
        block_positions = {block.block_id: index for index, block in enumerate(blocks)}
        for comment_id, state in comment_state.items():
            warning_codes: list[str] = []
            if not state["start"]:
                warning_codes.append("COMMENT_RANGE_START_MISSING")
            if not state["end"]:
                warning_codes.append("COMMENT_RANGE_END_MISSING")
            if not state["reference"]:
                warning_codes.append("COMMENT_REFERENCE_MISSING")
            for code in warning_codes:
                warning(
                    code,
                    "A template comment uses an unsupported or incomplete range shape.",
                    {"comment_id": comment_id},
                )
            anchor = state["anchor"]
            position = block_positions.get(anchor, -1)
            before = next(
                (block.text for block in reversed(blocks[:position]) if block.text), None
            )
            after = next(
                (block.text for block in blocks[position + 1 :] if block.text), None
            ) if position >= 0 else None
            nearby_assets: list[str] = []
            if position >= 0:
                for block in blocks[max(0, position - 1) : position + 2]:
                    nearby_assets.extend(block.related_asset_ids)
            comments.append(
                TemplateCommentSchema(
                    comment_id=comment_id,
                    text=comment_texts.get(comment_id, ""),
                    selected_text="".join(state["selected"]).strip(),
                    heading_path=state["heading_path"],
                    anchor_block_id=anchor,
                    context_before=before,
                    context_after=after,
                    locator={
                        "heading_path": state["heading_path"],
                        "block_type": blocks[position].block_type.value if position >= 0 else None,
                        "block_index": position if position >= 0 else None,
                        "comment_id": comment_id,
                        "quote": "".join(state["selected"]).strip()[:300],
                        "nearby_asset_ids": list(dict.fromkeys(nearby_assets)),
                    },
                    warning_codes=warning_codes,
                )
            )

        return DocumentGraph(
            document_id=f"document-{source_file_id}",
            source_file_id=source_file_id,
            kind=kind,
            blocks=blocks,
            comments=comments,
            assets=assets,
            parse_warnings=warnings,
        )
    except ValidationError:
        raise
    except (KeyError, OSError, zipfile.BadZipFile) as exc:
        raise ValidationError("INVALID_DOCX", "The DOCX could not be parsed safely.") from exc
    finally:
        archive.close()
