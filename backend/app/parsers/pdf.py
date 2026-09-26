import hashlib
import re
import uuid
from pathlib import Path

import pymupdf

from app.core.config import Settings
from app.core.errors import ValidationError
from app.schemas.document import (
    DocumentAssetSchema,
    DocumentBlockSchema,
    DocumentGraph,
    ParseWarningSchema,
)


def parse_pdf(
    path: Path,
    *,
    source_file_id: str,
    extracted_dir: Path,
    relative_root: Path,
    settings: Settings,
) -> tuple[DocumentGraph, bool]:
    try:
        document = pymupdf.open(path)
    except Exception as exc:
        raise ValidationError("INVALID_PDF", "The PDF cannot be opened.") from exc

    blocks: list[DocumentBlockSchema] = []
    assets: list[DocumentAssetSchema] = []
    scanned_pages = 0
    page_count = document.page_count
    if document.needs_pass:
        document.close()
        raise ValidationError("ENCRYPTED_PDF", "Encrypted PDFs are not supported.")
    try:
        if document.page_count == 0:
            raise ValidationError("INVALID_PDF", "The PDF has no pages.")
        for page_index, page in enumerate(document):
            page_text = page.get_text("text").strip()
            images = page.get_images(full=True)
            page_area = max(page.rect.width * page.rect.height, 1)
            max_image_ratio = 0.0
            for image_info in images:
                xref = image_info[0]
                for rect in page.get_image_rects(xref):
                    max_image_ratio = max(max_image_ratio, (rect.width * rect.height) / page_area)
            if len(page_text) < settings.scanned_pdf_text_threshold and max_image_ratio >= 0.7:
                scanned_pages += 1

            for raw_block in page.get_text("blocks"):
                x0, y0, x1, y1, text, *_ = raw_block
                normalized_text = text.strip()
                if not normalized_text:
                    continue
                block_id = f"block-{len(blocks)}"
                blocks.append(
                    DocumentBlockSchema(
                        block_id=block_id,
                        block_type="page_text",
                        text=normalized_text,
                        order_index=len(blocks),
                        locator={
                            "page": page_index + 1,
                            "bbox": [x0, y0, x1, y1],
                            "quote": normalized_text[:300],
                        },
                    )
                )

            seen_xrefs: set[int] = set()
            for image_info in images:
                xref = image_info[0]
                if xref in seen_xrefs:
                    continue
                seen_xrefs.add(xref)
                extracted = document.extract_image(xref)
                extension = extracted.get("ext", "bin")
                content = extracted["image"]
                width = extracted.get("width")
                height = extracted.get("height")
                if width and height and width * height > settings.max_image_pixels:
                    raise ValidationError(
                        "IMAGE_TOO_LARGE", "An embedded PDF image exceeds the pixel limit."
                    )
                if not re.fullmatch(r"[a-zA-Z0-9]{1,10}", extension):
                    extension = "bin"
                output_name = f"{uuid.uuid4()}.{extension}"
                output_path = extracted_dir / output_name
                output_path.write_bytes(content)
                asset_id = f"asset-{len(assets)}"
                assets.append(
                    DocumentAssetSchema(
                        asset_id=asset_id,
                        media_type=f"image/{extension}",
                        storage_path=output_path.relative_to(relative_root).as_posix(),
                        sha256=hashlib.sha256(content).hexdigest(),
                        width=width,
                        height=height,
                        locator={"page": page_index + 1, "xref": xref},
                    )
                )
    except ValidationError:
        raise
    except Exception as exc:
        raise ValidationError("INVALID_PDF", "The PDF could not be parsed safely.") from exc
    finally:
        document.close()

    is_scanned = scanned_pages == page_count
    warnings = []
    if is_scanned:
        for asset in assets:
            (relative_root / asset.storage_path).unlink(missing_ok=True)
        assets.clear()
        blocks.clear()
        warnings.append(
            ParseWarningSchema(
                code="SCANNED_PDF_UNSUPPORTED",
                message=(
                    "The PDF appears to be scanned and was ignored because OCR is out of scope."
                ),
            )
        )
    return (
        DocumentGraph(
            document_id=f"document-{source_file_id}",
            source_file_id=source_file_id,
            kind="evidence_pdf",
            blocks=blocks,
            assets=assets,
            parse_warnings=warnings,
        ),
        is_scanned,
    )
