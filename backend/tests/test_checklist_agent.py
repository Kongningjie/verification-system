import httpx2
import pytest
from agents import Runner
from app.agents.checklist import FakeChecklistGenerator, RealChecklistGenerator
from app.core.config import Settings
from app.core.errors import AppError
from app.schemas.checklist import CommentGenerationInput, Severity, SourceCategory
from openai import APIStatusError, AuthenticationError


def generation_input(
    comment_text: str = "检查型号；安全认证信息必须存在",
) -> CommentGenerationInput:
    return CommentGenerationInput(
        comment_id="7",
        comment_text=comment_text,
        selected_text="Model X1",
        heading_path=["产品信息"],
        context_before="before",
        context_after="after",
        available_source_categories=[SourceCategory.MANUAL, SourceCategory.PROJECT],
        common_rule_summaries=[
            {
                "rule_id": "common.model",
                "name": "型号一致性",
                "description": "型号必须一致",
            }
        ],
    )


@pytest.mark.asyncio
async def test_fake_agent_splits_maps_and_explains_critical_items() -> None:
    generator = FakeChecklistGenerator()

    result = await generator.generate(generation_input())

    assert len(result.output.items) == 2
    assert result.output.items[0].rule_mapping_id == "common.model"
    assert result.output.items[1].severity_suggestion == Severity.CRITICAL
    assert result.output.items[1].severity_reason
    assert generator.requests[0].comment_id == "7"


@pytest.mark.asyncio
async def test_fake_agent_never_skips_empty_comment() -> None:
    result = await FakeChecklistGenerator().generate(generation_input(""))

    assert len(result.output.items) == 1
    assert "UNCLEAR_REQUIREMENT" in result.output.items[0].generation_warnings
    assert result.output.items[0].severity_suggestion == Severity.NORMAL


def real_generator(*, retries: int = 0) -> RealChecklistGenerator:
    return RealChecklistGenerator(
        Settings(
            _env_file=None,
            openai_api_key="test-key",
            openai_model="test-model",
            model_timeout_seconds=1,
            model_max_retries=retries,
        )
    )


@pytest.mark.asyncio
async def test_real_agent_retries_temporary_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0
    expected = await FakeChecklistGenerator().generate(generation_input())

    async def run(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TimeoutError
        return type("Result", (), {"final_output": expected.output})()

    monkeypatch.setattr(Runner, "run", run)
    result = await real_generator(retries=1).generate(generation_input())

    assert calls == 2
    assert result.metadata.attempts == 2


@pytest.mark.asyncio
async def test_real_agent_retries_server_error(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0
    expected = await FakeChecklistGenerator().generate(generation_input())

    async def run(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            request = httpx2.Request("POST", "https://example.invalid")
            response = httpx2.Response(503, request=request)
            raise APIStatusError("unavailable", response=response, body=None)
        return type("Result", (), {"final_output": expected.output})()

    monkeypatch.setattr(Runner, "run", run)
    monkeypatch.setattr("app.agents.checklist._wait_for_retry", lambda _state: 0)
    result = await real_generator(retries=1).generate(generation_input())

    assert calls == 2
    assert result.metadata.attempts == 2


@pytest.mark.asyncio
async def test_real_agent_maps_authentication_error_without_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    async def run(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        request = httpx2.Request("POST", "https://example.invalid")
        response = httpx2.Response(401, request=request)
        raise AuthenticationError("invalid", response=response, body=None)

    monkeypatch.setattr(Runner, "run", run)
    with pytest.raises(AppError) as raised:
        await real_generator(retries=2).generate(generation_input())

    assert raised.value.code == "MODEL_AUTHENTICATION_FAILED"
    assert calls == 1


@pytest.mark.asyncio
async def test_real_agent_maps_invalid_structured_output(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run(*_args, **_kwargs):
        return type("Result", (), {"final_output": {"items": []}})()

    monkeypatch.setattr(Runner, "run", run)
    with pytest.raises(AppError) as raised:
        await real_generator().generate(generation_input())

    assert raised.value.code == "MODEL_OUTPUT_INVALID"


@pytest.mark.asyncio
async def test_real_agent_maps_exhausted_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run(*_args, **_kwargs):
        raise TimeoutError

    monkeypatch.setattr(Runner, "run", run)
    with pytest.raises(AppError) as raised:
        await real_generator().generate(generation_input())

    assert raised.value.code == "MODEL_TEMPORARY_FAILURE"
