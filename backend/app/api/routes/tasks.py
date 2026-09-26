import asyncio
import json
from collections.abc import Callable
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.agents.checklist import ChecklistGenerator, get_checklist_generator
from app.agents.execution import EvidenceJudge, get_evidence_judge
from app.core.config import Settings, get_settings
from app.core.errors import NotFoundError
from app.db.session import SessionLocal, get_db
from app.models.task import VerificationTask
from app.repositories.checklists import confirm_checklist, list_check_items, update_check_item
from app.repositories.results import get_result, list_results
from app.repositories.tasks import get_task_detail, list_tasks
from app.schemas.checklist import (
    CheckItemListResponse,
    CheckItemPatchRequest,
    CheckItemResponse,
    ChecklistVersionResponse,
    ConfirmChecklistRequest,
    ExecutorType,
    Severity,
)
from app.schemas.execution import CheckResultResponse, ResultConclusion, ResultListResponse
from app.schemas.task import TaskDetailResponse, TaskSummaryResponse
from app.services.execution import cancel_task, dispatch_with_new_session, ensure_retryable
from app.services.tasks import create_task
from app.workflow.events import event_bus

router = APIRouter(prefix="/tasks", tags=["tasks"])


def checklist_generator_dependency(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ChecklistGenerator:
    return get_checklist_generator(settings)


def evidence_judge_dependency(
    settings: Annotated[Settings, Depends(get_settings)],
) -> EvidenceJudge:
    return get_evidence_judge(settings)


def execution_session_factory_dependency() -> Callable[[], Session]:
    return SessionLocal


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
async def confirm_task_check_items(
    task_id: str,
    payload: ConfirmChecklistRequest,
    session: Annotated[Session, Depends(get_db)],
    evidence_judge: Annotated[EvidenceJudge, Depends(evidence_judge_dependency)],
    settings: Annotated[Settings, Depends(get_settings)],
    session_factory: Annotated[
        Callable[[], Session], Depends(execution_session_factory_dependency)
    ],
    background_tasks: BackgroundTasks,
) -> ChecklistVersionResponse:
    version = confirm_checklist(session, task_id, expected_revision=payload.expected_revision)
    background_tasks.add_task(
        dispatch_with_new_session,
        session_factory,
        task_id,
        evidence_judge,
        max_candidates_per_source=settings.max_evidence_candidates_per_source,
    )
    return version


@router.post("/{task_id}/cancel", response_model=TaskSummaryResponse)
def cancel_verification_task(
    task_id: str, session: Annotated[Session, Depends(get_db)]
) -> TaskSummaryResponse:
    return TaskSummaryResponse.model_validate(cancel_task(session, task_id))


@router.post("/{task_id}/retry-errors", response_model=TaskSummaryResponse)
async def retry_task_errors(
    task_id: str,
    session: Annotated[Session, Depends(get_db)],
    evidence_judge: Annotated[EvidenceJudge, Depends(evidence_judge_dependency)],
    settings: Annotated[Settings, Depends(get_settings)],
    session_factory: Annotated[
        Callable[[], Session], Depends(execution_session_factory_dependency)
    ],
    background_tasks: BackgroundTasks,
) -> TaskSummaryResponse:
    task = ensure_retryable(session, task_id)
    background_tasks.add_task(
        dispatch_with_new_session,
        session_factory,
        task_id,
        evidence_judge,
        retry_errors_only=True,
        max_candidates_per_source=settings.max_evidence_candidates_per_source,
    )
    return TaskSummaryResponse.model_validate(task)


@router.get("/{task_id}/results", response_model=ResultListResponse)
def get_task_results(
    task_id: str,
    session: Annotated[Session, Depends(get_db)],
    conclusion: Annotated[ResultConclusion | None, Query()] = None,
    executor_type: Annotated[ExecutorType | None, Query()] = None,
    severity: Annotated[Severity | None, Query()] = None,
) -> ResultListResponse:
    return list_results(
        session,
        task_id,
        conclusion=conclusion,
        executor_type=executor_type,
        severity=severity,
    )


@router.get("/{task_id}/results/{result_id}", response_model=CheckResultResponse)
def get_task_result(
    task_id: str,
    result_id: str,
    session: Annotated[Session, Depends(get_db)],
) -> CheckResultResponse:
    return get_result(session, task_id, result_id)


@router.get("/{task_id}/events")
async def task_events(
    task_id: str,
    request: Request,
    session: Annotated[Session, Depends(get_db)],
) -> StreamingResponse:
    if session.get(VerificationTask, task_id) is None:
        raise NotFoundError("TASK_NOT_FOUND", "The requested task does not exist.")
    queue = event_bus.subscribe(task_id)

    async def stream():
        try:
            while not await request.is_disconnected():
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                    payload = json.dumps(event.model_dump(mode="json"), ensure_ascii=False)
                    yield f"event: progress\ndata: {payload}\n\n"
                except TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            event_bus.unsubscribe(task_id, queue)

    return StreamingResponse(stream(), media_type="text/event-stream")
