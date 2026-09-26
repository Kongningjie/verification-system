from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models.checklist import ChecklistVersion
from app.models.execution import CheckResult, CheckRun, Evidence
from app.models.review import ReviewRecord
from app.models.task import VerificationTask
from app.schemas.checklist import ExecutorType, Severity
from app.schemas.execution import (
    CheckResultResponse,
    EvidenceResponse,
    ResultConclusion,
    ResultListResponse,
)


def list_results(
    session: Session,
    task_id: str,
    *,
    conclusion: ResultConclusion | None = None,
    executor_type: ExecutorType | None = None,
    severity: Severity | None = None,
    has_manual_override: bool | None = None,
    page: int = 1,
    page_size: int = 20,
) -> ResultListResponse:
    task = session.get(VerificationTask, task_id)
    if not task:
        raise NotFoundError("TASK_NOT_FOUND", "The requested task does not exist.")
    statement = select(CheckResult).where(CheckResult.task_id == task_id)
    if conclusion:
        statement = statement.where(CheckResult.final_conclusion == conclusion)
    if executor_type:
        statement = statement.where(CheckResult.executor_type == executor_type)
    if severity:
        statement = statement.where(CheckResult.severity == severity)
    if has_manual_override is not None:
        statement = statement.where(CheckResult.has_manual_override == has_manual_override)
    total = session.scalar(select(func.count()).select_from(statement.subquery())) or 0
    results = session.scalars(
        statement.order_by(CheckResult.created_at, CheckResult.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return ResultListResponse(
        task_id=task_id,
        task_status=task.status.value,
        total=total,
        page=page,
        page_size=page_size,
        items=[_serialize_result(session, result) for result in results],
    )


def get_result(session: Session, task_id: str, result_id: str) -> CheckResultResponse:
    result = session.scalar(
        select(CheckResult).where(CheckResult.id == result_id, CheckResult.task_id == task_id)
    )
    if not result:
        raise NotFoundError("CHECK_RESULT_NOT_FOUND", "The requested result does not exist.")
    return _serialize_result(session, result)


def _serialize_result(session: Session, result: CheckResult) -> CheckResultResponse:
    task = session.get(VerificationTask, result.task_id)
    checklist = (
        session.scalar(
            select(ChecklistVersion).where(
                ChecklistVersion.task_id == result.task_id,
                ChecklistVersion.version_number == task.confirmed_checklist_version,
            )
        )
        if task
        else None
    )
    requirement = next(
        (
            item.get("requirement", "")
            for item in (checklist.snapshot if checklist else [])
            if item.get("id") == result.check_item_id
        ),
        "",
    )
    evidence_by_id = {
        evidence.evidence_id: evidence
        for evidence in session.scalars(
            select(Evidence).where(
                Evidence.task_id == result.task_id,
                Evidence.evidence_id.in_(result.evidence_ids),
            )
        ).all()
    }
    runs = session.scalars(
        select(CheckRun).where(CheckRun.result_id == result.id).order_by(CheckRun.created_at)
    ).all()
    reviews = session.scalars(
        select(ReviewRecord)
        .where(ReviewRecord.result_id == result.id)
        .order_by(ReviewRecord.created_at, ReviewRecord.id)
    ).all()
    return CheckResultResponse(
        **CheckResultResponse.model_validate(result).model_dump(
            exclude={"evidences", "runs", "review_records", "requirement"}
        ),
        requirement=requirement,
        evidences=[
            EvidenceResponse.model_validate(evidence_by_id[evidence_id])
            for evidence_id in result.evidence_ids
            if evidence_id in evidence_by_id
        ],
        runs=runs,
        review_records=reviews,
    )
