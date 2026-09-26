import logging
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings
from app.core.errors import AppError, NotFoundError
from app.core.request_context import current_request_id
from app.models.checklist import ChecklistVersion
from app.models.execution import CheckResult, CheckRun, Evidence
from app.models.report import Report
from app.models.review import ReviewRecord
from app.models.task import TaskStatus, VerificationTask
from app.reports.generator import generated_at, write_excel_report, write_json_report
from app.schemas.report import ReportCreateRequest, ReportFormat, ReportResponse, ReportStatus
from app.services.storage import safe_path

_REPORTABLE_STATES = {TaskStatus.COMPLETED, TaskStatus.COMPLETED_WITH_ERRORS}
logger = logging.getLogger(__name__)


def create_report(
    session: Session,
    settings: Settings,
    task_id: str,
    payload: ReportCreateRequest,
) -> ReportResponse:
    task = session.scalar(
        select(VerificationTask)
        .where(VerificationTask.id == task_id)
        .options(selectinload(VerificationTask.files))
    )
    if task is None:
        raise NotFoundError("TASK_NOT_FOUND", "The requested task does not exist.")
    if task.status not in _REPORTABLE_STATES:
        raise AppError(
            "TASK_NOT_REPORTABLE",
            "Reports can only be generated after task execution completes.",
            status_code=409,
        )
    report = Report(task_id=task_id, format=payload.format, status=ReportStatus.PENDING)
    session.add(report)
    session.commit()
    session.refresh(report)
    report_id = report.id
    extension = ".xlsx" if payload.format == ReportFormat.EXCEL else ".json"
    relative_path = f"tasks/{task_id}/reports/{report_id}{extension}"
    final_path = safe_path(settings.data_root, relative_path)
    temporary_path = safe_path(final_path.parent, f".{report_id}{extension}.part")
    final_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        snapshot = build_report_snapshot(session, task)
        sha256 = (
            write_excel_report(temporary_path, snapshot)
            if payload.format == ReportFormat.EXCEL
            else write_json_report(temporary_path, snapshot)
        )
        temporary_path.replace(final_path)
        report.relative_path = relative_path
        report.sha256 = sha256
        report.status = ReportStatus.COMPLETED
        report.completed_at = datetime.now(UTC)
        session.commit()
        logger.info(
            "report generated",
            extra={
                "task_id": task_id,
                "request_id": current_request_id(),
                "stage": task.stage,
                "operation": "create_report",
                "error_code": None,
            },
        )
    except Exception as exc:
        session.rollback()
        temporary_path.unlink(missing_ok=True)
        final_path.unlink(missing_ok=True)
        report = session.get(Report, report_id)
        if report is None:
            raise AppError(
                "REPORT_GENERATION_FAILED",
                "The report could not be generated; the task result was unchanged.",
                status_code=500,
            ) from exc
        report.status = ReportStatus.FAILED
        report.error_message = "Report generation failed."
        session.commit()
        logger.error(
            "report generation failed",
            extra={
                "task_id": task_id,
                "request_id": current_request_id(),
                "stage": task.stage,
                "operation": "create_report",
                "error_code": "REPORT_GENERATION_FAILED",
            },
        )
        raise AppError(
            "REPORT_GENERATION_FAILED",
            "The report could not be generated; the task result was unchanged.",
            status_code=500,
            details={"report_id": report_id},
        ) from exc
    return ReportResponse.model_validate(report)


def build_report_snapshot(session: Session, task: VerificationTask) -> dict:
    results = session.scalars(
        select(CheckResult).where(CheckResult.task_id == task.id).order_by(CheckResult.created_at)
    ).all()
    evidence = session.scalars(
        select(Evidence).where(Evidence.task_id == task.id).order_by(Evidence.evidence_id)
    ).all()
    reviews = session.scalars(
        select(ReviewRecord)
        .where(ReviewRecord.task_id == task.id)
        .order_by(ReviewRecord.created_at)
    ).all()
    runs = session.scalars(select(CheckRun).where(CheckRun.task_id == task.id)).all()
    checklist = session.scalar(
        select(ChecklistVersion).where(
            ChecklistVersion.task_id == task.id,
            ChecklistVersion.version_number == task.confirmed_checklist_version,
        )
    )
    file_names = {item.id: item.original_name for item in task.files}
    checklist_items = {item.get("id"): item for item in (checklist.snapshot if checklist else [])}
    return {
        "schema_version": "1.0",
        "generated_at": generated_at(),
        "task": {
            "id": task.id,
            "name": task.name,
            "status": task.status.value,
            "created_at": task.created_at.isoformat(),
            "updated_at": task.updated_at.isoformat(),
        },
        "files": [
            {
                "id": item.id,
                "category": item.category.value,
                "original_name": item.original_name,
                "size_bytes": item.size_bytes,
                "sha256": item.sha256,
            }
            for item in task.files
        ],
        "checklist_snapshot": checklist.snapshot if checklist else [],
        "results": [
            {
                "id": item.id,
                "check_item_id": item.check_item_id,
                "check_name": item.check_name,
                "requirement": checklist_items.get(item.check_item_id, {}).get("requirement", ""),
                "check_type": item.check_type,
                "severity": item.severity.value,
                "system_conclusion": item.system_conclusion.value,
                "final_conclusion": item.final_conclusion.value,
                "reason_code": item.reason_code.value,
                "reason": item.reason,
                "evidence_ids": item.evidence_ids,
                "has_manual_override": item.has_manual_override,
            }
            for item in results
        ],
        "evidence": [
            {
                "evidence_id": item.evidence_id,
                "check_item_id": item.check_item_id,
                "role": item.role.value,
                "source_category": item.source_category.value,
                "source_file_name": file_names.get(item.file_id, "project.json"),
                "content_type": item.content_type,
                "excerpt": item.excerpt,
                "locator": item.locator,
                "sha256": item.sha256,
            }
            for item in evidence
        ],
        "review_records": [
            {
                "id": item.id,
                "result_id": item.result_id,
                "reviewer_name": item.reviewer_name,
                "previous_conclusion": item.previous_conclusion.value,
                "new_conclusion": item.new_conclusion.value,
                "comment": item.comment,
                "created_at": item.created_at.isoformat(),
            }
            for item in reviews
        ],
        "execution_metadata": {
            "checklist_version": task.confirmed_checklist_version,
            "ruleset_version": checklist.ruleset_version if checklist else "unknown",
            "prompt_versions": sorted({item.prompt_version for item in runs}),
            "models": sorted({item.model_name for item in runs if item.model_name}),
            "run_count": len(runs),
            "input_tokens": sum(item.input_tokens or 0 for item in runs),
            "output_tokens": sum(item.output_tokens or 0 for item in runs),
        },
    }


def resolve_report_download(
    session: Session, settings: Settings, task_id: str, report_id: str
) -> tuple[Path, str, str]:
    report = session.scalar(select(Report).where(Report.id == report_id, Report.task_id == task_id))
    if report is None:
        raise NotFoundError("REPORT_NOT_FOUND", "The requested report does not exist.")
    if report.status != ReportStatus.COMPLETED or not report.relative_path:
        raise AppError(
            "REPORT_NOT_READY", "The report is not available for download.", status_code=409
        )
    path = safe_path(settings.data_root, report.relative_path)
    if not path.is_file():
        raise AppError("REPORT_FILE_MISSING", "The report file is missing.", status_code=410)
    media_type = (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if report.format == ReportFormat.EXCEL
        else "application/json"
    )
    return path, f"verification-report-{report.id}{path.suffix}", media_type
