import shutil
import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError, ValidationError
from app.models.document import FileCategory, ParseStatus, ParseWarning, TaskFile
from app.models.task import TaskStatus, VerificationTask
from app.parsers.image import parse_image
from app.parsers.ooxml import parse_docx
from app.parsers.pdf import parse_pdf
from app.parsers.project_json import parse_project_json
from app.repositories.tasks import add_graph, get_task_detail, set_project_metadata
from app.schemas.task import TaskDetailResponse
from app.services.storage import (
    category_for_evidence,
    create_task_directories,
    safe_path,
    save_upload,
    task_directories,
)
from app.workflow.task_state import fail_task, transition_task


async def create_task(
    session: Session,
    settings: Settings,
    *,
    name: str,
    manual: UploadFile,
    template: UploadFile,
    project: UploadFile,
    evidence_files: list[UploadFile],
) -> TaskDetailResponse:
    clean_name = name.strip()
    if not clean_name or len(clean_name) > 255:
        raise ValidationError("INVALID_TASK_NAME", "Task name must contain 1 to 255 characters.")
    if len(evidence_files) + 3 > settings.max_upload_files:
        raise ValidationError("TOO_MANY_FILES", "The task contains too many uploaded files.")

    task = VerificationTask(id=str(uuid.uuid4()), name=clean_name)
    session.add(task)
    session.commit()
    session.refresh(task)
    directories: dict[str, Path] | None = None

    try:
        transition_task(task, TaskStatus.VALIDATING, progress=5)
        session.commit()
        directories = create_task_directories(settings, task.id)
        uploads = [
            (manual, FileCategory.MANUAL_DOCX),
            (template, FileCategory.TEMPLATE_DOCX),
            (project, FileCategory.PROJECT_JSON),
            *((upload, category_for_evidence(upload.filename)) for upload in evidence_files),
        ]
        total_size = 0
        hashes: set[str] = set()
        task_files: list[TaskFile] = []
        for upload, category in uploads:
            (
                path,
                sha256,
                size,
                declared_mime,
                detected_mime,
                original_name,
            ) = await save_upload(upload, category, directories["uploads"], settings)
            total_size += size
            if total_size > settings.max_task_size_bytes:
                raise ValidationError(
                    "TASK_TOO_LARGE", "Uploaded task materials exceed the total size limit."
                )
            if sha256 in hashes:
                path.unlink(missing_ok=True)
                raise ValidationError(
                    "DUPLICATE_FILE", "The same file cannot be uploaded twice in one task."
                )
            hashes.add(sha256)
            task_file = TaskFile(
                task_id=task.id,
                category=category,
                original_name=original_name,
                storage_path=path.relative_to(settings.data_root.resolve()).as_posix(),
                declared_mime=declared_mime,
                detected_mime=detected_mime,
                size_bytes=size,
                sha256=sha256,
                parse_status=ParseStatus.PENDING,
            )
            session.add(task_file)
            task_files.append(task_file)
        session.flush()
        transition_task(task, TaskStatus.PARSING, progress=35)
        session.commit()

        for task_file in task_files:
            source_path = safe_path(settings.data_root, task_file.storage_path)
            if task_file.category == FileCategory.PROJECT_JSON:
                parsed_project = parse_project_json(source_path)
                set_project_metadata(
                    session,
                    task,
                    raw_data=parsed_project.raw,
                    normalized_data=parsed_project.normalized,
                )
                task_file.parse_status = ParseStatus.PARSED
                continue
            if task_file.category in {
                FileCategory.MANUAL_DOCX,
                FileCategory.TEMPLATE_DOCX,
            }:
                graph = parse_docx(
                    source_path,
                    source_file_id=task_file.id,
                    kind=(
                        "manual" if task_file.category == FileCategory.MANUAL_DOCX else "template"
                    ),
                    extracted_dir=directories["extracted"],
                    relative_root=settings.data_root.resolve(),
                    settings=settings,
                )
                add_graph(session, task, task_file, graph)
                task_file.parse_status = ParseStatus.PARSED
                continue
            if task_file.category == FileCategory.EVIDENCE_PDF:
                graph, is_scanned = parse_pdf(
                    source_path,
                    source_file_id=task_file.id,
                    extracted_dir=directories["extracted"],
                    relative_root=settings.data_root.resolve(),
                    settings=settings,
                )
                add_graph(session, task, task_file, graph)
                task_file.parse_status = ParseStatus.IGNORED if is_scanned else ParseStatus.PARSED
                continue
            graph = parse_image(
                source_path,
                source_file_id=task_file.id,
                extracted_dir=directories["extracted"],
                relative_root=settings.data_root.resolve(),
                settings=settings,
            )
            add_graph(session, task, task_file, graph)
            task_file.parse_status = ParseStatus.PARSED

        session.flush()
        task.warning_count = (
            session.scalar(
                select(func.count(ParseWarning.id)).where(ParseWarning.task_id == task.id)
            )
            or 0
        )
        transition_task(task, TaskStatus.GENERATING_CHECKLIST, progress=60)
        session.commit()
        return get_task_detail(session, task.id)
    except Exception as exc:
        session.rollback()
        for upload in [manual, template, project, *evidence_files]:
            await upload.close()
        if directories is None:
            directories = task_directories(settings, task.id)
        task_root = directories["root"]
        verified_root = safe_path(settings.tasks_root, task.id)
        cleanup_failed = False
        if task_root == verified_root and task_root.exists():
            try:
                shutil.rmtree(task_root)
            except OSError:
                cleanup_failed = True

        persisted_task = session.get(VerificationTask, task.id)
        if persisted_task is not None:
            if not cleanup_failed:
                for task_file in list(persisted_task.files):
                    session.delete(task_file)
            fail_task(
                persisted_task,
                code=(
                    "FILE_CLEANUP_FAILED"
                    if cleanup_failed
                    else exc.code
                    if isinstance(exc, AppError)
                    else "TASK_PROCESSING_FAILED"
                ),
                message=(
                    "Task processing failed and residual files require manual cleanup."
                    if cleanup_failed
                    else exc.message
                    if isinstance(exc, AppError)
                    else "The task could not be processed."
                ),
            )
            session.commit()
        if cleanup_failed:
            raise AppError(
                "FILE_CLEANUP_FAILED",
                "Task processing failed and residual files require manual cleanup.",
                status_code=500,
                details={"task_id": task.id},
            ) from exc
        if isinstance(exc, AppError):
            exc.details.setdefault("task_id", task.id)
            raise
        raise AppError(
            "TASK_PROCESSING_FAILED",
            "The task could not be processed.",
            status_code=500,
            details={"task_id": task.id},
        ) from exc
