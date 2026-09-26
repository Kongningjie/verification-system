import logging

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.errors import AppError, NotFoundError, ValidationError
from app.core.request_context import current_request_id
from app.models.execution import CheckResult
from app.models.review import ReviewRecord
from app.models.task import TaskStatus, VerificationTask
from app.schemas.checklist import Severity
from app.schemas.execution import ResultConclusion
from app.schemas.review import ReviewRecordResponse, ReviewRequest

_REVIEWABLE_STATES = {TaskStatus.COMPLETED, TaskStatus.COMPLETED_WITH_ERRORS}
_COMMENT_REQUIRED_TO_PASS = {
    ResultConclusion.FAIL,
    ResultConclusion.ERROR,
    ResultConclusion.NEEDS_REVIEW,
}
logger = logging.getLogger(__name__)


def review_result(
    session: Session,
    task_id: str,
    result_id: str,
    payload: ReviewRequest,
    *,
    reviewer_name: str,
) -> ReviewRecordResponse:
    task = session.get(VerificationTask, task_id)
    if task is None:
        raise NotFoundError("TASK_NOT_FOUND", "The requested task does not exist.")
    if task.status not in _REVIEWABLE_STATES:
        raise AppError(
            "RESULT_NOT_REVIEWABLE",
            "Results can only be reviewed after task execution completes.",
            status_code=409,
        )
    result = session.scalar(
        select(CheckResult).where(CheckResult.id == result_id, CheckResult.task_id == task_id)
    )
    if result is None:
        raise NotFoundError("CHECK_RESULT_NOT_FOUND", "The requested result does not exist.")
    previous = result.final_conclusion
    if payload.final_conclusion == previous:
        raise ValidationError(
            "REVIEW_CONCLUSION_UNCHANGED",
            "The reviewed conclusion must differ from the current final conclusion.",
        )
    comment = payload.comment.strip()
    requires_comment = result.severity == Severity.CRITICAL or (
        previous in _COMMENT_REQUIRED_TO_PASS and payload.final_conclusion == ResultConclusion.PASS
    )
    if requires_comment and not comment:
        raise ValidationError(
            "REVIEW_COMMENT_REQUIRED",
            "A review comment is required for this conclusion change.",
        )
    has_override = payload.final_conclusion != result.system_conclusion
    updated = session.execute(
        update(CheckResult)
        .where(
            CheckResult.id == result_id,
            CheckResult.task_id == task_id,
            CheckResult.final_conclusion == previous,
        )
        .values(
            final_conclusion=payload.final_conclusion,
            has_manual_override=has_override,
        )
    )
    if not updated.rowcount:
        session.rollback()
        raise AppError(
            "REVIEW_CONFLICT",
            "The result changed after it was loaded. Refresh and review again.",
            status_code=409,
        )
    record = ReviewRecord(
        task_id=task_id,
        result_id=result_id,
        reviewer_name=reviewer_name,
        previous_conclusion=previous,
        new_conclusion=payload.final_conclusion,
        comment=comment,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    logger.info(
        "review recorded",
        extra={
            "task_id": task_id,
            "request_id": current_request_id(),
            "stage": task.stage,
            "operation": "review_result",
            "error_code": None,
        },
    )
    return ReviewRecordResponse.model_validate(record)
