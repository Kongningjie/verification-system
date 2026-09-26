from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.repositories.tasks import get_task_detail, list_tasks
from app.schemas.task import TaskDetailResponse, TaskSummaryResponse
from app.services.tasks import create_task

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("", response_model=TaskDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_verification_task(
    name: Annotated[str, Form()],
    manual: Annotated[UploadFile, File()],
    template: Annotated[UploadFile, File()],
    project: Annotated[UploadFile, File()],
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
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
    )


@router.get("", response_model=list[TaskSummaryResponse])
def get_tasks(session: Annotated[Session, Depends(get_db)]) -> list[TaskSummaryResponse]:
    return list_tasks(session)


@router.get("/{task_id}", response_model=TaskDetailResponse)
def get_verification_task(
    task_id: str, session: Annotated[Session, Depends(get_db)]
) -> TaskDetailResponse:
    return get_task_detail(session, task_id)
