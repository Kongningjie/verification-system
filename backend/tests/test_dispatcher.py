import asyncio

import pytest
from app.agents.execution import FakeEvidenceJudge
from app.services.execution import LocalTaskDispatcher


@pytest.mark.asyncio
async def test_dispatcher_serializes_tasks(monkeypatch: pytest.MonkeyPatch) -> None:
    active = 0
    maximum = 0
    order: list[str] = []

    async def fake_execute(_session, task_id, _judge, **_kwargs):
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        order.append(f"start:{task_id}")
        await asyncio.sleep(0.01)
        order.append(f"end:{task_id}")
        active -= 1

    monkeypatch.setattr("app.services.execution.execute_task", fake_execute)
    dispatcher = LocalTaskDispatcher()
    await asyncio.gather(
        dispatcher.dispatch(object(), "one", FakeEvidenceJudge()),  # type: ignore[arg-type]
        dispatcher.dispatch(object(), "two", FakeEvidenceJudge()),  # type: ignore[arg-type]
    )
    assert maximum == 1
    assert order in (
        ["start:one", "end:one", "start:two", "end:two"],
        ["start:two", "end:two", "start:one", "end:one"],
    )


@pytest.mark.asyncio
async def test_dispatcher_exposes_cancel_signal(monkeypatch: pytest.MonkeyPatch) -> None:
    started = asyncio.Event()
    observed = asyncio.Event()

    async def fake_execute(_session, _task_id, _judge, **kwargs):
        started.set()
        while not kwargs["is_cancelled"]():
            await asyncio.sleep(0)
        observed.set()

    monkeypatch.setattr("app.services.execution.execute_task", fake_execute)
    dispatcher = LocalTaskDispatcher()
    running = asyncio.create_task(
        dispatcher.dispatch(object(), "cancel-me", FakeEvidenceJudge())  # type: ignore[arg-type]
    )
    await started.wait()
    dispatcher.cancel("cancel-me")
    await running
    assert observed.is_set()
