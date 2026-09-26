from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.task import TaskStatus, VerificationTask

_ALLOWED_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.CREATED: {TaskStatus.VALIDATING, TaskStatus.FAILED, TaskStatus.CANCELLED},
    TaskStatus.VALIDATING: {TaskStatus.PARSING, TaskStatus.FAILED, TaskStatus.CANCELLED},
    TaskStatus.PARSING: {
        TaskStatus.GENERATING_CHECKLIST,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    },
    TaskStatus.GENERATING_CHECKLIST: {
        TaskStatus.AWAITING_CHECKLIST_CONFIRMATION,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
        TaskStatus.INTERRUPTED,
    },
}

_ACTIVE_STATUSES = {
    TaskStatus.VALIDATING,
    TaskStatus.PARSING,
    TaskStatus.GENERATING_CHECKLIST,
    TaskStatus.QUEUED,
    TaskStatus.MATCHING_EVIDENCE,
    TaskStatus.CHECKING,
    TaskStatus.AGGREGATING,
}


def transition_task(
    task: VerificationTask,
    target: TaskStatus,
    *,
    progress: int,
) -> None:
    current = task.status or TaskStatus.CREATED
    if target not in _ALLOWED_TRANSITIONS.get(current, set()):
        raise AppError(
            "INVALID_TASK_STATE_TRANSITION",
            f"Cannot transition task from {current.value} to {target.value}.",
            status_code=409,
        )
    task.status = target
    task.stage = target.value
    task.progress = progress


def fail_task(task: VerificationTask, *, code: str, message: str) -> None:
    task.status = TaskStatus.FAILED
    task.stage = TaskStatus.FAILED.value
    task.error_code = code
    task.error_message = message


def interrupt_active_tasks(session: Session) -> int:
    result = session.execute(
        update(VerificationTask)
        .where(VerificationTask.status.in_(_ACTIVE_STATUSES))
        .values(
            status=TaskStatus.INTERRUPTED,
            stage=TaskStatus.INTERRUPTED.value,
        )
    )
    session.commit()
    return result.rowcount or 0
