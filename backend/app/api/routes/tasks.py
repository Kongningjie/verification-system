from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy.orm import Session

from app.agents.checklist import ChecklistGenerator, get_checklist_generator
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.repositories.checklists import confirm_checklist, list_check_items, update_check_item
from app.repositories.tasks import get_task_detail, list_tasks
from app.schemas.checklist import (
    CheckItemListResponse,
    CheckItemPatchRequest,
    CheckItemResponse,
    ChecklistVersionResponse,
    ConfirmChecklistRequest,
)
from app.schemas.task import TaskDetailResponse, TaskSummaryResponse
from app.services.tasks import create_task

router = APIRouter(prefix="/tasks", tags=["tasks"])


def checklist_generator_dependency(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ChecklistGenerator:
    return get_checklist_generator(settings)


@router.post("", response_model=TaskDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_verification_task(
    name: Annotated[str, Form()],
    manual: Annotated[UploadFile, File()],
    template: Annotated[UploadFile, File()],
    project: Annotated[UploadFile, File()],
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    checklist_generator: Annotated[ChecklistGenerator, Depends(checklist_generator_dependency)],
    evidence_files: Annotated[list[UploadFile] | None, File()] = None,
) -> TaskDetailResponse:
    return await create_task(
        session,
        settings,
        name=name,
        manual=manual,
        template=template,
        project=project,
        evidence_files=evidence_files or [],
        checklist_generator=checklist_generator,
    )


@router.get("", response_model=list[TaskSummaryResponse])
def get_tasks(session: Annotated[Session, Depends(get_db)]) -> list[TaskSummaryResponse]:
    return list_tasks(session)


@router.get("/{task_id}", response_model=TaskDetailResponse)
def get_verification_task(
    task_id: str, session: Annotated[Session, Depends(get_db)]
) -> TaskDetailResponse:
    return get_task_detail(session, task_id)


@router.get("/{task_id}/check-items", response_model=CheckItemListResponse)
def get_task_check_items(
    task_id: str, session: Annotated[Session, Depends(get_db)]
) -> CheckItemListResponse:
    return list_check_items(session, task_id)


@router.patch("/{task_id}/check-items/{item_id}", response_model=CheckItemResponse)
def patch_task_check_item(
    task_id: str,
    item_id: str,
    payload: CheckItemPatchRequest,
    session: Annotated[Session, Depends(get_db)],
) -> CheckItemResponse:
    return update_check_item(session, task_id, item_id, payload)


@router.post("/{task_id}/check-items/confirm", response_model=ChecklistVersionResponse)
def confirm_task_check_items(
    task_id: str,
    payload: ConfirmChecklistRequest,
    session: Annotated[Session, Depends(get_db)],
) -> ChecklistVersionResponse:
    return confirm_checklist(session, task_id, expected_revision=payload.expected_revision)
