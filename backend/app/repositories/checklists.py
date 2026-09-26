from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, selectinload

from app.core.errors import AppError, NotFoundError
from app.models.checklist import CheckItem, ChecklistVersion
from app.models.task import TaskStatus, VerificationTask
from app.rules.registry import load_common_rule_catalog
from app.schemas.checklist import (
    CheckItemListResponse,
    CheckItemPatchRequest,
    CheckItemResponse,
    ChecklistVersionResponse,
)
from app.workflow.task_state import transition_task


def list_check_items(session: Session, task_id: str) -> CheckItemListResponse:
    task = session.get(VerificationTask, task_id)
    if task is None:
        raise NotFoundError("TASK_NOT_FOUND", "The requested task does not exist.")
    items = session.scalars(
        select(CheckItem)
        .where(CheckItem.task_id == task_id)
        .order_by(CheckItem.created_at, CheckItem.id)
    ).all()
    return CheckItemListResponse(
        task_id=task.id,
        task_status=task.status.value,
        checklist_revision=task.checklist_revision,
        confirmed_version=task.confirmed_checklist_version,
        items=[CheckItemResponse.model_validate(item) for item in items],
    )


def update_check_item(
    session: Session,
    task_id: str,
    item_id: str,
    patch: CheckItemPatchRequest,
) -> CheckItemResponse:
    task = session.get(VerificationTask, task_id)
    if task is None:
        raise NotFoundError("TASK_NOT_FOUND", "The requested task does not exist.")
    if task.status != TaskStatus.AWAITING_CHECKLIST_CONFIRMATION:
        raise AppError(
            "CHECKLIST_NOT_EDITABLE",
            "Only an unconfirmed checklist awaiting confirmation can be edited.",
            status_code=409,
        )
    values = patch.model_dump(exclude={"expected_version"}, exclude_none=True, mode="json")
    if not values:
        item = session.scalar(
            select(CheckItem).where(CheckItem.id == item_id, CheckItem.task_id == task_id)
        )
        if item is None:
            raise NotFoundError("CHECK_ITEM_NOT_FOUND", "The requested check item does not exist.")
        if item.version != patch.expected_version:
            raise AppError(
                "CHECK_ITEM_VERSION_CONFLICT",
                "The check item was changed by another request.",
                status_code=409,
                details={"current_version": item.version},
            )
        return CheckItemResponse.model_validate(item)
    values["version"] = CheckItem.version + 1
    result = session.execute(
        update(CheckItem)
        .where(
            CheckItem.id == item_id,
            CheckItem.task_id == task_id,
            CheckItem.version == patch.expected_version,
        )
        .values(**values)
    )
    if not result.rowcount:
        existing = session.scalar(
            select(CheckItem).where(CheckItem.id == item_id, CheckItem.task_id == task_id)
        )
        if existing is None:
            raise NotFoundError("CHECK_ITEM_NOT_FOUND", "The requested check item does not exist.")
        raise AppError(
            "CHECK_ITEM_VERSION_CONFLICT",
            "The check item was changed by another request.",
            status_code=409,
            details={"current_version": existing.version},
        )
    session.execute(
        update(VerificationTask)
        .where(VerificationTask.id == task_id)
        .values(checklist_revision=VerificationTask.checklist_revision + 1)
    )
    session.commit()
    item = session.scalar(select(CheckItem).where(CheckItem.id == item_id))
    return CheckItemResponse.model_validate(item)


def confirm_checklist(
    session: Session, task_id: str, *, expected_revision: int
) -> ChecklistVersionResponse:
    task = session.scalar(
        select(VerificationTask)
        .where(VerificationTask.id == task_id)
        .options(selectinload(VerificationTask.check_items))
    )
    if task is None:
        raise NotFoundError("TASK_NOT_FOUND", "The requested task does not exist.")
    if task.status != TaskStatus.AWAITING_CHECKLIST_CONFIRMATION:
        raise AppError(
            "CHECKLIST_NOT_CONFIRMABLE",
            "Only a checklist awaiting confirmation can be confirmed.",
            status_code=409,
        )
    if task.checklist_revision != expected_revision:
        raise AppError(
            "CHECKLIST_VERSION_CONFLICT",
            "The checklist changed after it was loaded.",
            status_code=409,
            details={"current_revision": task.checklist_revision},
        )
    enabled_items = sorted(
        (item for item in task.check_items if item.enabled),
        key=lambda item: (item.created_at, item.id),
    )
    if not enabled_items:
        raise AppError(
            "EMPTY_CHECKLIST",
            "At least one enabled check item is required before confirmation.",
            status_code=422,
        )
    next_version = (
        session.scalar(
            select(func.coalesce(func.max(ChecklistVersion.version_number), 0)).where(
                ChecklistVersion.task_id == task_id
            )
        )
        or 0
    ) + 1
    catalog = load_common_rule_catalog()
    model_names = {
        item.generation_metadata.get("model")
        for item in task.check_items
        if item.generation_metadata.get("model")
    }
    prompt_versions = {
        item.generation_metadata.get("prompt_version")
        for item in task.check_items
        if item.generation_metadata.get("prompt_version")
    }
    snapshot = [
        CheckItemResponse.model_validate(item).model_dump(mode="json") for item in enabled_items
    ]
    version = ChecklistVersion(
        task_id=task_id,
        version_number=next_version,
        item_count=len(snapshot),
        snapshot=snapshot,
        ruleset_version=catalog.ruleset_version,
        prompt_version=",".join(sorted(prompt_versions)) or "none",
        model_name=",".join(sorted(model_names)) or "rules-only",
    )
    session.add(version)
    task.confirmed_checklist_version = next_version
    transition_task(task, TaskStatus.QUEUED, progress=70)
    session.commit()
    session.refresh(version)
    return ChecklistVersionResponse.model_validate(version)
