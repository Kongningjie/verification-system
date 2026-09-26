import logging
import shutil
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.core.request_context import current_request_id
from app.models.task import TaskStatus, VerificationTask
from app.services.storage import safe_path, task_directories

_NON_DELETABLE = {
    TaskStatus.VALIDATING,
    TaskStatus.PARSING,
    TaskStatus.GENERATING_CHECKLIST,
    TaskStatus.QUEUED,
    TaskStatus.MATCHING_EVIDENCE,
    TaskStatus.CHECKING,
    TaskStatus.AGGREGATING,
}
logger = logging.getLogger(__name__)


def delete_task(session: Session, settings: Settings, task_id: str) -> None:
    task = session.get(VerificationTask, task_id)
    root = task_directories(settings, task_id)["root"]
    staged = safe_path(settings.tasks_root, f".deleting-{task_id}")
    if task is None:
        if staged.exists():
            _remove_staged(staged, task_id, stage=None)
            return
        raise AppError("TASK_NOT_FOUND", "The requested task does not exist.", status_code=404)
    if task.status in _NON_DELETABLE:
        raise AppError(
            "TASK_NOT_DELETABLE",
            "Cancel or wait for the active task before deleting it.",
            status_code=409,
        )
    task_stage = task.stage
    if staged.exists():
        raise AppError(
            "TASK_DELETE_RETRY_REQUIRED",
            "A previous deletion attempt requires cleanup retry.",
            status_code=409,
        )
    moved = False
    try:
        if root.exists():
            root.replace(staged)
            moved = True
        session.delete(task)
        session.commit()
    except Exception as exc:
        session.rollback()
        if moved and staged.exists() and not root.exists():
            staged.replace(root)
        raise AppError(
            "TASK_DATABASE_DELETE_FAILED",
            "The task database records could not be deleted; files were restored.",
            status_code=500,
        ) from exc
    if moved:
        _remove_staged(staged, task_id, stage=task_stage)
    logger.info(
        "task deleted",
        extra={
            "task_id": task_id,
            "request_id": current_request_id(),
            "stage": task_stage,
            "operation": "delete_task",
            "error_code": None,
        },
    )


def _remove_staged(staged: Path, task_id: str, *, stage: str | None) -> None:
    try:
        shutil.rmtree(staged)
    except OSError as exc:
        logger.error(
            "task file cleanup failed",
            extra={
                "task_id": task_id,
                "request_id": current_request_id(),
                "stage": stage,
                "operation": "delete_task_files",
                "error_code": "TASK_FILE_CLEANUP_FAILED",
            },
        )
        raise AppError(
            "TASK_FILE_CLEANUP_FAILED",
            "Database records were deleted, but file cleanup failed. "
            "Retry deletion with the same task ID.",
            status_code=500,
            details={"task_id": task_id, "retryable": True},
        ) from exc
