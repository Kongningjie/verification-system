from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import NotFoundError
from app.models.document import (
    DocumentAsset,
    DocumentBlock,
    ParseWarning,
    ProjectMetadata,
    TaskFile,
    TemplateComment,
)
from app.models.execution import CheckResult
from app.models.task import VerificationTask
from app.schemas.document import DocumentGraph
from app.schemas.execution import ResultConclusion
from app.schemas.task import (
    TaskDetailResponse,
    TaskFileResponse,
    TaskSummaryResponse,
    WarningResponse,
)


def add_graph(
    session: Session, task: VerificationTask, task_file: TaskFile, graph: DocumentGraph
) -> None:
    for block in graph.blocks:
        session.add(
            DocumentBlock(
                task_file_id=task_file.id,
                block_id=block.block_id,
                block_type=block.block_type,
                text=block.text,
                heading_path=block.heading_path,
                order_index=block.order_index,
                locator=block.locator,
                related_asset_ids=block.related_asset_ids,
            )
        )
    for comment in graph.comments:
        session.add(
            TemplateComment(
                task_file_id=task_file.id,
                comment_id=comment.comment_id,
                text=comment.text,
                selected_text=comment.selected_text,
                heading_path=comment.heading_path,
                anchor_block_id=comment.anchor_block_id,
                context_before=comment.context_before,
                context_after=comment.context_after,
                locator=comment.locator,
                warning_codes=comment.warning_codes,
            )
        )
    for asset in graph.assets:
        session.add(
            DocumentAsset(
                task_file_id=task_file.id,
                asset_id=asset.asset_id,
                media_type=asset.media_type,
                storage_path=asset.storage_path,
                sha256=asset.sha256,
                width=asset.width,
                height=asset.height,
                relationship_id=asset.relationship_id,
                locator=asset.locator,
            )
        )
    for item in graph.parse_warnings:
        session.add(
            ParseWarning(
                task_id=task.id,
                task_file_id=task_file.id,
                code=item.code,
                message=item.message,
                locator=item.locator,
            )
        )


def set_project_metadata(
    session: Session,
    task: VerificationTask,
    *,
    raw_data: dict,
    normalized_data: dict,
) -> None:
    session.add(
        ProjectMetadata(
            task_id=task.id,
            raw_data=raw_data,
            normalized_data=normalized_data,
        )
    )


def list_tasks(session: Session) -> list[TaskSummaryResponse]:
    tasks = session.scalars(
        select(VerificationTask).order_by(VerificationTask.created_at.desc())
    ).all()
    counts = session.execute(
        select(
            CheckResult.task_id,
            CheckResult.final_conclusion,
            CheckResult.has_manual_override,
        )
    ).all()
    by_task: dict[str, list[tuple[ResultConclusion, bool]]] = {}
    for task_id, conclusion, overridden in counts:
        by_task.setdefault(task_id, []).append((conclusion, overridden))
    responses: list[TaskSummaryResponse] = []
    for task in tasks:
        values = by_task.get(task.id, [])
        responses.append(
            TaskSummaryResponse(
                **TaskSummaryResponse.model_validate(task).model_dump(
                    exclude={
                        "result_total",
                        "pass_count",
                        "fail_count",
                        "needs_review_count",
                        "error_count",
                        "manual_override_count",
                    }
                ),
                result_total=len(values),
                pass_count=sum(value == ResultConclusion.PASS for value, _ in values),
                fail_count=sum(value == ResultConclusion.FAIL for value, _ in values),
                needs_review_count=sum(
                    value == ResultConclusion.NEEDS_REVIEW for value, _ in values
                ),
                error_count=sum(value == ResultConclusion.ERROR for value, _ in values),
                manual_override_count=sum(overridden for _, overridden in values),
            )
        )
    return responses


def get_task_model(session: Session, task_id: str) -> VerificationTask:
    statement = (
        select(VerificationTask)
        .where(VerificationTask.id == task_id)
        .options(
            selectinload(VerificationTask.files).selectinload(TaskFile.blocks),
            selectinload(VerificationTask.files).selectinload(TaskFile.comments),
            selectinload(VerificationTask.files).selectinload(TaskFile.assets),
            selectinload(VerificationTask.warnings),
            selectinload(VerificationTask.project_metadata),
            selectinload(VerificationTask.check_items),
            selectinload(VerificationTask.checklist_versions),
        )
    )
    task = session.scalar(statement)
    if task is None:
        raise NotFoundError("TASK_NOT_FOUND", "The requested task does not exist.")
    return task


def get_task_detail(session: Session, task_id: str) -> TaskDetailResponse:
    task = get_task_model(session, task_id)
    files = sorted(task.files, key=lambda item: (item.category.value, item.original_name))
    documents: list[DocumentGraph] = []
    kind_by_category = {
        "MANUAL_DOCX": "manual",
        "TEMPLATE_DOCX": "template",
        "EVIDENCE_PDF": "evidence_pdf",
        "EVIDENCE_IMAGE": "evidence_image",
    }
    for task_file in files:
        kind = kind_by_category.get(task_file.category.value)
        if kind is None:
            continue
        documents.append(
            DocumentGraph(
                document_id=f"document-{task_file.id}",
                source_file_id=task_file.id,
                kind=kind,
                blocks=[
                    {
                        "block_id": block.block_id,
                        "block_type": block.block_type,
                        "text": block.text,
                        "heading_path": block.heading_path,
                        "order_index": block.order_index,
                        "locator": block.locator,
                        "related_asset_ids": block.related_asset_ids,
                    }
                    for block in sorted(task_file.blocks, key=lambda item: item.order_index)
                ],
                comments=[
                    {
                        "comment_id": comment.comment_id,
                        "text": comment.text,
                        "selected_text": comment.selected_text,
                        "heading_path": comment.heading_path,
                        "anchor_block_id": comment.anchor_block_id,
                        "context_before": comment.context_before,
                        "context_after": comment.context_after,
                        "locator": comment.locator,
                        "warning_codes": comment.warning_codes,
                    }
                    for comment in sorted(task_file.comments, key=lambda item: item.comment_id)
                ],
                assets=[
                    {
                        "asset_id": asset.asset_id,
                        "media_type": asset.media_type,
                        "storage_path": asset.storage_path,
                        "sha256": asset.sha256,
                        "width": asset.width,
                        "height": asset.height,
                        "relationship_id": asset.relationship_id,
                        "locator": asset.locator,
                    }
                    for asset in sorted(task_file.assets, key=lambda item: item.asset_id)
                ],
                parse_warnings=[
                    {
                        "code": warning.code,
                        "message": warning.message,
                        "locator": warning.locator,
                    }
                    for warning in task.warnings
                    if warning.task_file_id == task_file.id
                ],
            )
        )
    return TaskDetailResponse(
        **TaskSummaryResponse.model_validate(task).model_dump(),
        files=[TaskFileResponse.model_validate(task_file) for task_file in files],
        warnings=[WarningResponse.model_validate(warning) for warning in task.warnings],
        project=(task.project_metadata.normalized_data if task.project_metadata else None),
        documents=documents,
    )
