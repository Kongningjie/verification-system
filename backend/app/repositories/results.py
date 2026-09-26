from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models.execution import CheckResult, CheckRun, Evidence
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
) -> ResultListResponse:
    task = session.get(VerificationTask, task_id)
    if not task:
        raise NotFoundError("TASK_NOT_FOUND", "The requested task does not exist.")
    statement = select(CheckResult).where(CheckResult.task_id == task_id)
    if conclusion:
        statement = statement.where(CheckResult.system_conclusion == conclusion)
    if executor_type:
        statement = statement.where(CheckResult.executor_type == executor_type)
    if severity:
        statement = statement.where(CheckResult.severity == severity)
    results = session.scalars(statement.order_by(CheckResult.created_at, CheckResult.id)).all()
    return ResultListResponse(
        task_id=task_id,
        task_status=task.status.value,
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
    return CheckResultResponse(
        **CheckResultResponse.model_validate(result).model_dump(exclude={"evidences", "runs"}),
        evidences=[
            EvidenceResponse.model_validate(evidence_by_id[evidence_id])
            for evidence_id in result.evidence_ids
            if evidence_id in evidence_by_id
        ],
        runs=runs,
    )
