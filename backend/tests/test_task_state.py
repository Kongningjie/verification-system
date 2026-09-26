from app.core.errors import AppError
from app.db.base import Base
from app.models.task import TaskStatus, VerificationTask
from app.workflow.task_state import interrupt_active_tasks, transition_task
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def test_invalid_state_transition_is_rejected() -> None:
    task = VerificationTask(name="State task")

    try:
        transition_task(task, TaskStatus.PARSING, progress=30)
    except AppError as exc:
        assert exc.code == "INVALID_TASK_STATE_TRANSITION"
    else:
        raise AssertionError("Invalid transition was accepted")


def test_restart_interrupts_active_tasks_but_not_confirmation_wait() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        active_tasks = [
            VerificationTask(name=status.value, status=status, stage=status.value)
            for status in (
                TaskStatus.PARSING,
                TaskStatus.QUEUED,
                TaskStatus.MATCHING_EVIDENCE,
                TaskStatus.CHECKING,
                TaskStatus.AGGREGATING,
            )
        ]
        waiting = VerificationTask(
            name="Waiting",
            status=TaskStatus.AWAITING_CHECKLIST_CONFIRMATION,
            stage=TaskStatus.AWAITING_CHECKLIST_CONFIRMATION.value,
        )
        session.add_all([*active_tasks, waiting])
        session.commit()

        assert interrupt_active_tasks(session) == len(active_tasks)
        for active in active_tasks:
            session.refresh(active)
            assert active.status == TaskStatus.INTERRUPTED
        session.refresh(waiting)

        assert waiting.status == TaskStatus.AWAITING_CHECKLIST_CONFIRMATION
