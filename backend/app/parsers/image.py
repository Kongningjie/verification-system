import hashlib
import uuid
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import Settings
from app.core.errors import ValidationError
from app.schemas.document import (
    DocumentAssetSchema,
    DocumentBlockSchema,
    DocumentGraph,
)


def parse_image(
    path: Path,
    *,
    source_file_id: str,
    extracted_dir: Path,
    relative_root: Path,
    settings: Settings,
) -> DocumentGraph:
    try:
        with Image.open(path) as source:
            if source.width * source.height > settings.max_image_pixels:
                raise ValidationError("IMAGE_TOO_LARGE", "Image pixel count exceeds the limit.")
            source.load()
            detected_format = (source.format or "").upper()
            expected_formats = {".png": {"PNG"}, ".jpg": {"JPEG"}, ".jpeg": {"JPEG"}}
            if detected_format not in expected_formats.get(path.suffix.lower(), set()):
                raise ValidationError(
                    "IMAGE_FORMAT_MISMATCH", "Decoded image format does not match its extension."
                )
            normalized = ImageOps.exif_transpose(source)
            normalized.thumbnail(
                (settings.max_model_image_edge, settings.max_model_image_edge),
                Image.Resampling.LANCZOS,
            )
            output_name = f"{uuid.uuid4()}.png"
            output_path = extracted_dir / output_name
            normalized.convert("RGBA" if "A" in normalized.getbands() else "RGB").save(
                output_path, format="PNG"
            )
            width, height = normalized.size
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValidationError("INVALID_IMAGE", "The image cannot be decoded safely.") from exc

    asset_id = "asset-0"
    sha256 = hashlib.sha256(output_path.read_bytes()).hexdigest()
    relative_path = output_path.relative_to(relative_root).as_posix()
    return DocumentGraph(
        document_id=f"document-{source_file_id}",
        source_file_id=source_file_id,
        kind="evidence_image",
        blocks=[
            DocumentBlockSchema(
                block_id="block-0",
                block_type="image",
                order_index=0,
                locator={"source": "uploaded_image"},
                related_asset_ids=[asset_id],
            )
        ],
        assets=[
            DocumentAssetSchema(
                asset_id=asset_id,
                media_type="image/png",
                storage_path=relative_path,
                sha256=sha256,
                width=width,
                height=height,
                locator={"source": "uploaded_image"},
            )
        ],
    )
