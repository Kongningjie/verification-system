import asyncio
import hashlib
from collections.abc import Callable

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.agents.execution import EvidenceJudge
from app.core.errors import AppError, NotFoundError
from app.evidence.matcher import EvidenceMatcher, MatchRequest
from app.models.checklist import ChecklistVersion
from app.models.document import TaskFile
from app.models.execution import CheckResult, CheckRun, Evidence
from app.models.task import TaskStatus, VerificationTask
from app.schemas.execution import ProgressEvent, ResultConclusion
from app.workflow.events import event_bus
from app.workflow.execution import ItemExecution, execute_item
from app.workflow.task_state import fail_task, transition_task


class LocalTaskDispatcher:
    """A process-local single execution slot; work inside one task may run concurrently."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._cancelled: set[str] = set()

    async def dispatch(
        self,
        session: Session,
        task_id: str,
        judge: EvidenceJudge,
        *,
        retry_errors_only: bool = False,
        max_candidates_per_source: int = 8,
    ) -> None:
        async with self._lock:
            try:
                await execute_task(
                    session,
                    task_id,
                    judge,
                    retry_errors_only=retry_errors_only,
                    max_candidates_per_source=max_candidates_per_source,
                    is_cancelled=lambda: task_id in self._cancelled,
                )
            finally:
                self._cancelled.discard(task_id)

    def cancel(self, task_id: str) -> None:
        self._cancelled.add(task_id)


dispatcher = LocalTaskDispatcher()


def ensure_retryable(session: Session, task_id: str) -> VerificationTask:
    task = session.get(VerificationTask, task_id)
    if not task:
        raise NotFoundError("TASK_NOT_FOUND", "The requested task does not exist.")
    if task.status != TaskStatus.COMPLETED_WITH_ERRORS:
        raise AppError(
            "TASK_NOT_RETRYABLE",
            "Only a task completed with technical errors can be retried.",
            status_code=409,
        )
    has_error = session.scalar(
        select(CheckResult.id)
        .where(
            CheckResult.task_id == task_id,
            CheckResult.system_conclusion == ResultConclusion.ERROR,
        )
        .limit(1)
    )
    if not has_error:
        raise AppError("NO_ERROR_RESULTS", "There are no ERROR results to retry.", status_code=409)
    transition_task(task, TaskStatus.QUEUED, progress=70)
    session.commit()
    return task


async def dispatch_with_new_session(
    session_factory: Callable[[], Session],
    task_id: str,
    judge: EvidenceJudge,
    *,
    retry_errors_only: bool = False,
    max_candidates_per_source: int = 8,
) -> None:
    with session_factory() as session:
        try:
            await dispatcher.dispatch(
                session,
                task_id,
                judge,
                retry_errors_only=retry_errors_only,
                max_candidates_per_source=max_candidates_per_source,
            )
        except Exception:
            session.rollback()
            task = session.get(VerificationTask, task_id)
            if task and task.status not in {TaskStatus.CANCELLED, TaskStatus.INTERRUPTED}:
                fail_task(
                    task,
                    code="INTERNAL_ERROR",
                    message="The task workflow stopped because of an internal execution error.",
                )
                session.commit()
                await _publish(task, "任务执行发生内部错误")


async def _publish(task: VerificationTask, message: str) -> None:
    event_type = {
        TaskStatus.COMPLETED: "task.completed",
        TaskStatus.COMPLETED_WITH_ERRORS: "task.completed_with_errors",
        TaskStatus.FAILED: "task.failed",
        TaskStatus.CANCELLED: "task.cancelled",
    }.get(task.status, "task.stage_changed")
    await event_bus.publish(
        ProgressEvent(
            task_id=task.id,
            type=event_type,
            status=task.status.value,
            stage=task.stage,
            progress=task.progress,
            message=message,
        )
    )


def _load_task(session: Session, task_id: str) -> VerificationTask:
    task = session.scalar(
        select(VerificationTask)
        .where(VerificationTask.id == task_id)
        .options(
            selectinload(VerificationTask.files).selectinload(TaskFile.blocks),
            selectinload(VerificationTask.files).selectinload(TaskFile.assets),
            selectinload(VerificationTask.project_metadata),
            selectinload(VerificationTask.results),
        )
    )
    if not task:
        raise NotFoundError("TASK_NOT_FOUND", "The requested task does not exist.")
    return task


async def execute_task(
    session: Session,
    task_id: str,
    judge: EvidenceJudge,
    *,
    retry_errors_only: bool = False,
    max_candidates_per_source: int = 8,
    is_cancelled: Callable[[], bool] = lambda: False,
) -> None:
    task = _load_task(session, task_id)
    allowed = {TaskStatus.QUEUED}
    if retry_errors_only:
        allowed.add(TaskStatus.COMPLETED_WITH_ERRORS)
    if task.status not in allowed:
        raise AppError(
            "TASK_NOT_EXECUTABLE", "The task is not queued for execution.", status_code=409
        )
    version = session.scalar(
        select(ChecklistVersion).where(
            ChecklistVersion.task_id == task_id,
            ChecklistVersion.version_number == task.confirmed_checklist_version,
        )
    )
    if not version:
        raise AppError(
            "CONFIRMED_CHECKLIST_MISSING",
            "The confirmed checklist snapshot is missing.",
            status_code=409,
        )
    items = list(version.snapshot)
    if retry_errors_only:
        error_ids = {
            result.check_item_id
            for result in task.results
            if result.system_conclusion == ResultConclusion.ERROR
        }
        items = [item for item in items if item["id"] in error_ids]
        if not items:
            raise AppError(
                "NO_ERROR_RESULTS", "There are no ERROR results to retry.", status_code=409
            )
        session.execute(
            delete(CheckRun).where(
                CheckRun.task_id == task_id, CheckRun.check_item_id.in_(error_ids)
            )
        )
        session.execute(
            delete(CheckResult).where(
                CheckResult.task_id == task_id, CheckResult.check_item_id.in_(error_ids)
            )
        )
        session.commit()
        if task.status != TaskStatus.QUEUED:
            transition_task(task, TaskStatus.QUEUED, progress=70)
    transition_task(task, TaskStatus.MATCHING_EVIDENCE, progress=75)
    session.commit()
    await _publish(task, "正在匹配候选证据")
    matcher = EvidenceMatcher(max_candidates_per_source)
    matched = [
        (
            item,
            matcher.match(
                task,
                MatchRequest(
                    check_item_id=item["id"],
                    requirement=item["requirement"],
                    target_hint=item.get("target_hint", ""),
                    required_sources=list(item.get("required_source_categories", [])),
                    heading_path=list(item.get("source_heading_path", [])),
                ),
            ),
        )
        for item in items
    ]
    if is_cancelled():
        await _cancel(session, task)
        return
    transition_task(task, TaskStatus.CHECKING, progress=82)
    session.commit()
    await _publish(task, "正在执行规则与模型核对")
    executions = await asyncio.gather(
        *(execute_item(task, item, candidates, judge) for item, candidates in matched)
    )
    if is_cancelled():
        await _cancel(session, task)
        return
    transition_task(task, TaskStatus.AGGREGATING, progress=94)
    session.commit()
    await _publish(task, "正在汇总结论")
    for execution in executions:
        _persist_execution(session, task_id, execution)
    session.commit()
    has_errors = session.scalar(
        select(CheckResult.id)
        .where(
            CheckResult.task_id == task_id,
            CheckResult.system_conclusion == ResultConclusion.ERROR,
        )
        .limit(1)
    )
    transition_task(
        task,
        TaskStatus.COMPLETED_WITH_ERRORS if has_errors else TaskStatus.COMPLETED,
        progress=100,
    )
    session.commit()
    await _publish(task, "核对完成")


def _persist_execution(session: Session, task_id: str, execution: ItemExecution) -> None:
    unique_candidates = {candidate.evidence_id: candidate for candidate in execution.candidates}
    for candidate in unique_candidates.values():
        evidence = session.scalar(
            select(Evidence).where(
                Evidence.task_id == task_id,
                Evidence.evidence_id == candidate.evidence_id,
            )
        )
        if evidence is None:
            evidence = Evidence(
                task_id=task_id,
                check_item_id=execution.item["id"],
                evidence_id=candidate.evidence_id,
            )
            session.add(evidence)
        evidence.role = candidate.role
        evidence.file_id = candidate.source_file_id
        evidence.source_category = candidate.source_category
        evidence.excerpt = candidate.content
        evidence.locator = candidate.locator
        evidence.score = candidate.score
        evidence.asset_path = candidate.asset_path
        evidence.content_type = "image" if candidate.asset_path else "text"
        evidence.sha256 = hashlib.sha256(candidate.content.encode()).hexdigest()
    judgement = execution.judgement
    result = CheckResult(
        task_id=task_id,
        check_item_id=execution.item["id"],
        check_name=execution.item["name"],
        check_type=execution.item["check_type"],
        executor_type=execution.executor_type,
        severity=execution.item["severity"],
        system_conclusion=judgement.conclusion,
        final_conclusion=judgement.conclusion,
        reason_code=judgement.reason_code,
        reason=judgement.reason,
        evidence_ids=judgement.evidence_ids,
        has_manual_override=False,
    )
    session.add(result)
    session.flush()
    for run in execution.runs:
        session.add(
            CheckRun(
                task_id=task_id,
                check_item_id=execution.item["id"],
                result_id=result.id,
                run_type=run.run_type,
                attempt_number=1,
                executor_type=run.executor_type,
                input_hash=run.input_hash,
                conclusion=run.conclusion,
                reason_code=run.reason_code or judgement.reason_code,
                reason=run.reason,
                evidence_ids=run.evidence_ids,
                differences=run.differences or [],
                missing_information=run.missing_information or [],
                model_name=run.model_name,
                prompt_version=run.prompt_version,
                duration_ms=run.duration_ms,
                retry_count=run.retry_count,
                input_tokens=run.input_tokens,
                output_tokens=run.output_tokens,
                error_type=run.error_type,
            )
        )


async def _cancel(session: Session, task: VerificationTask) -> None:
    transition_task(task, TaskStatus.CANCELLED, progress=task.progress)
    session.commit()
    await _publish(task, "任务已取消")


def cancel_task(session: Session, task_id: str) -> VerificationTask:
    task = session.get(VerificationTask, task_id)
    if not task:
        raise NotFoundError("TASK_NOT_FOUND", "The requested task does not exist.")
    if task.status not in {
        TaskStatus.QUEUED,
        TaskStatus.MATCHING_EVIDENCE,
        TaskStatus.CHECKING,
        TaskStatus.AGGREGATING,
    }:
        raise AppError("TASK_NOT_CANCELLABLE", "The task is not active or queued.", status_code=409)
    dispatcher.cancel(task_id)
    if task.status == TaskStatus.QUEUED:
        transition_task(task, TaskStatus.CANCELLED, progress=task.progress)
        session.commit()
    return task
