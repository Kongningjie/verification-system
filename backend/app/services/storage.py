import hashlib
import uuid
from pathlib import Path, PurePosixPath

from fastapi import UploadFile

from app.core.config import Settings
from app.core.errors import ValidationError
from app.models.document import FileCategory

_EXTENSIONS: dict[FileCategory, set[str]] = {
    FileCategory.MANUAL_DOCX: {".docx"},
    FileCategory.TEMPLATE_DOCX: {".docx"},
    FileCategory.PROJECT_JSON: {".json"},
    FileCategory.EVIDENCE_PDF: {".pdf"},
    FileCategory.EVIDENCE_IMAGE: {".png", ".jpg", ".jpeg"},
}

_MIME_TYPES: dict[FileCategory, set[str]] = {
    FileCategory.MANUAL_DOCX: {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    },
    FileCategory.TEMPLATE_DOCX: {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    },
    FileCategory.PROJECT_JSON: {"application/json", "text/json"},
    FileCategory.EVIDENCE_PDF: {"application/pdf"},
    FileCategory.EVIDENCE_IMAGE: {"image/png", "image/jpeg"},
}

_DETECTED_MIME: dict[str, str] = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".json": "application/json",
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


def safe_path(root: Path, *parts: str) -> Path:
    resolved_root = root.resolve()
    candidate = resolved_root.joinpath(*parts).resolve()
    if not candidate.is_relative_to(resolved_root):
        raise ValidationError("PATH_OUTSIDE_TASK", "The resolved path leaves the task directory.")
    return candidate


def task_directories(settings: Settings, task_id: str) -> dict[str, Path]:
    task_root = safe_path(settings.tasks_root, task_id)
    return {
        "root": task_root,
        "uploads": safe_path(task_root, "uploads"),
        "parsed": safe_path(task_root, "parsed"),
        "extracted": safe_path(task_root, "extracted"),
        "reports": safe_path(task_root, "reports"),
    }


def create_task_directories(settings: Settings, task_id: str) -> dict[str, Path]:
    directories = task_directories(settings, task_id)
    for directory in directories.values():
        directory.mkdir(parents=True, exist_ok=True)
    return directories


def category_for_evidence(filename: str | None) -> FileCategory:
    extension = Path(filename or "").suffix.lower()
    if extension == ".pdf":
        return FileCategory.EVIDENCE_PDF
    if extension in {".png", ".jpg", ".jpeg"}:
        return FileCategory.EVIDENCE_IMAGE
    raise ValidationError(
        "UNSUPPORTED_EVIDENCE_EXTENSION",
        "Evidence files must be PDF, PNG, JPG, or JPEG.",
        details={"extension": extension},
    )


async def save_upload(
    upload: UploadFile,
    category: FileCategory,
    uploads_dir: Path,
    settings: Settings,
) -> tuple[Path, str, int, str, str, str]:
    original_name = upload.filename or ""
    if not original_name or "\x00" in original_name or len(original_name) > 255:
        raise ValidationError("INVALID_FILENAME", "The uploaded filename is invalid.")

    metadata_name = PurePosixPath(original_name.replace("\\", "/")).name
    extension = Path(metadata_name).suffix.lower()
    if extension not in _EXTENSIONS[category]:
        raise ValidationError(
            "FILE_EXTENSION_MISMATCH",
            "The file extension does not match its upload field.",
            details={"filename": original_name, "category": category.value},
        )

    declared_mime = (upload.content_type or "").lower()
    if declared_mime not in _MIME_TYPES[category]:
        raise ValidationError(
            "DECLARED_MIME_MISMATCH",
            "The declared MIME type does not match the file category.",
            details={"filename": original_name, "declared_mime": declared_mime},
        )

    stored_name = f"{uuid.uuid4()}{extension}"
    final_path = safe_path(uploads_dir, stored_name)
    temporary_path = safe_path(uploads_dir, f".{stored_name}.part")
    digest = hashlib.sha256()
    size = 0
    header = bytearray()

    try:
        with temporary_path.open("xb") as destination:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > settings.max_file_size_bytes:
                    raise ValidationError(
                        "FILE_TOO_LARGE",
                        "An uploaded file exceeds the configured size limit.",
                        details={"filename": original_name},
                    )
                if len(header) < 16:
                    header.extend(chunk[: 16 - len(header)])
                digest.update(chunk)
                destination.write(chunk)
        _validate_signature(category, extension, bytes(header), original_name)
        temporary_path.replace(final_path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        final_path.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()

    return (
        final_path,
        digest.hexdigest(),
        size,
        declared_mime,
        _DETECTED_MIME[extension],
        metadata_name,
    )


def _validate_signature(
    category: FileCategory, extension: str, header: bytes, original_name: str
) -> None:
    valid = False
    if category in {FileCategory.MANUAL_DOCX, FileCategory.TEMPLATE_DOCX}:
        valid = header.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"))
    elif category == FileCategory.PROJECT_JSON:
        content = header.lstrip(b"\xef\xbb\xbf \t\r\n")
        valid = content.startswith(b"{")
    elif category == FileCategory.EVIDENCE_PDF:
        valid = header.startswith(b"%PDF-")
    elif category == FileCategory.EVIDENCE_IMAGE:
        if extension == ".png":
            valid = header.startswith(b"\x89PNG\r\n\x1a\n")
        else:
            valid = header.startswith(b"\xff\xd8\xff")

    if not valid:
        raise ValidationError(
            "FILE_SIGNATURE_MISMATCH",
            "The file signature does not match its extension and MIME type.",
            details={"filename": original_name},
        )
