import pytest
from agents import Runner
from app.agents.execution import RealEvidenceJudge
from app.core.config import Settings
from app.core.errors import AppError
from app.schemas.checklist import SourceCategory
from app.schemas.execution import (
    AgentExecutionInput,
    AgentJudgement,
    EvidenceCandidate,
    EvidenceRole,
    ReasonCode,
)


def request() -> AgentExecutionInput:
    return AgentExecutionInput(
        check_item_id="item",
        requirement="型号必须一致",
        candidates=[
            EvidenceCandidate(
                evidence_id="target",
                role=EvidenceRole.TARGET,
                source_category=SourceCategory.MANUAL,
                content="型号 X1",
            ),
            EvidenceCandidate(
                evidence_id="source",
                role=EvidenceRole.SOURCE,
                source_category=SourceCategory.PROJECT,
                content="model: X1",
            ),
        ],
    )


def judge(retries: int = 0) -> RealEvidenceJudge:
    return RealEvidenceJudge(
        Settings(
            _env_file=None,
            openai_api_key="test-key",
            openai_model="test-model",
            model_timeout_seconds=1,
            model_max_retries=retries,
        )
    )


@pytest.mark.asyncio
async def test_structured_output_error_retries_same_evidence_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    async def run(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        output = (
            AgentJudgement(
                conclusion="PASS",
                reason_code=ReasonCode.MATCH,
                reason="matched",
                target_evidence_ids=["target"],
                source_evidence_ids=["source"],
            )
            if calls == 2
            else {"conclusion": "PASS"}
        )
        return type("Result", (), {"final_output": output})()

    monkeypatch.setattr(Runner, "run", run)
    monkeypatch.setattr("app.agents.execution._retry_wait", lambda _state: 0)
    result = await judge(retries=1).judge(request())
    assert calls == 2
    assert result.metadata.attempts == 2
    assert result.judgement.evidence_ids == ["target", "source"]


@pytest.mark.asyncio
async def test_exhausted_timeout_maps_to_technical_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run(*_args, **_kwargs):
        raise TimeoutError

    monkeypatch.setattr(Runner, "run", run)
    monkeypatch.setattr("app.agents.execution._retry_wait", lambda _state: 0)
    with pytest.raises(AppError) as raised:
        await judge(retries=1).judge(request())
    assert raised.value.code == "MODEL_TIMEOUT"
