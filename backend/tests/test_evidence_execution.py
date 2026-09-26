import asyncio
from types import SimpleNamespace

import pytest
from app.agents.execution import FakeEvidenceJudge, model_call_slot
from app.core.errors import AppError
from app.evidence.matcher import (
    EvidenceMatcher,
    MatchRequest,
    lexical_score,
    search_terms,
    stable_evidence_id,
)
from app.models.document import BlockType, FileCategory
from app.schemas.checklist import ExecutorType, Severity, SourceCategory
from app.schemas.execution import (
    AgentExecutionInput,
    AgentJudgement,
    EvidenceCandidate,
    EvidenceRole,
    ReasonCode,
    ResultConclusion,
)
from app.workflow.execution import (
    detect_source_conflict,
    execute_field_rule,
    execute_item,
    executor_for,
)


def candidate(
    evidence_id: str,
    role: EvidenceRole,
    content: str,
    *,
    category: SourceCategory = SourceCategory.MANUAL,
    locator: dict | None = None,
) -> EvidenceCandidate:
    return EvidenceCandidate(
        evidence_id=evidence_id,
        role=role,
        source_category=category,
        content=content,
        locator=locator or {},
    )


def item(**overrides) -> dict:
    value = {
        "id": "item-1",
        "name": "市场一致性",
        "requirement": "市场内容应与项目资料一致",
        "check_type": "SEMANTIC",
        "severity": "CRITICAL",
        "required_source_categories": ["MANUAL", "PROJECT"],
        "target_hint": "EU",
        "rule_id": "common.market",
        "generation_metadata": {},
    }
    value.update(overrides)
    return value


def test_search_terms_and_ranking_support_chinese_ngrams_and_english_tokens() -> None:
    assert "安全" in search_terms("安全说明 Model-X")
    assert "model-x" in search_terms("安全说明 Model-X")
    assert lexical_score("电池 safety", "电池安全说明") > lexical_score("电池 safety", "售后服务")
    assert stable_evidence_id("a", "b") == stable_evidence_id("a", "b")


def test_matcher_ranks_and_caps_each_source_category() -> None:
    blocks = [
        SimpleNamespace(
            block_id=f"b{index}",
            block_type=BlockType.PARAGRAPH,
            text=("目标型号 X1" if index == 5 else f"无关内容 {index}"),
            heading_path=["产品信息"],
            order_index=index,
            locator={"block_index": index},
            related_asset_ids=[],
        )
        for index in range(10)
    ]
    manual = SimpleNamespace(
        id="manual-file",
        category=FileCategory.MANUAL_DOCX,
        blocks=blocks,
        assets=[],
    )
    task = SimpleNamespace(files=[manual], project_metadata=None)
    matched = EvidenceMatcher(max_candidates_per_source=3).match(
        task,
        MatchRequest(
            check_item_id="item",
            requirement="核对型号 X1",
            target_hint="X1",
            required_sources=[SourceCategory.MANUAL],
            heading_path=["产品信息"],
        ),
    )
    assert len(matched) == 3
    assert matched[0].locator["block_id"] == "b5"


def test_field_rule_requires_sources_and_never_passes_without_evidence() -> None:
    check = item(check_type="FIELD", rule_id="common.model")
    missing = execute_field_rule(check, [])
    assert missing.conclusion == ResultConclusion.NEEDS_REVIEW
    assert missing.reason_code == ReasonCode.MISSING_TARGET_CONTENT

    values = [
        candidate("target", EvidenceRole.TARGET, "产品型号 X1"),
        candidate(
            "source",
            EvidenceRole.SOURCE,
            "model: X1",
            category=SourceCategory.PROJECT,
            locator={"field": "model"},
        ),
    ]
    passed = execute_field_rule(check, values)
    assert passed.conclusion == ResultConclusion.PASS
    assert passed.evidence_ids == ["target", "source"]


def test_all_check_types_route_to_their_fixed_channels() -> None:
    assert executor_for(item(check_type="FIELD")) == ExecutorType.FIELD_RULE
    assert executor_for(item(check_type="STRUCTURE")) == ExecutorType.STRUCTURE_RULE
    assert executor_for(item(check_type="CUSTOM_STRUCTURE")) == ExecutorType.STRUCTURE_RULE
    assert executor_for(item(check_type="SEMANTIC")) == ExecutorType.SEMANTIC_AGENT
    assert executor_for(item(check_type="CUSTOM_SEMANTIC")) == ExecutorType.SEMANTIC_AGENT
    assert executor_for(item(check_type="VISUAL")) == ExecutorType.VISION_AGENT
    assert executor_for(item(check_type="CUSTOM_VISUAL")) == ExecutorType.VISION_AGENT


def test_same_fact_conflict_is_program_controlled() -> None:
    values = [
        candidate(
            "one",
            EvidenceRole.SOURCE,
            "model: X1",
            category=SourceCategory.PROJECT,
            locator={"fact_key": "model"},
        ),
        candidate(
            "two",
            EvidenceRole.SOURCE,
            "model: X2",
            category=SourceCategory.EVIDENCE_PDF,
            locator={"fact_key": "model"},
        ),
    ]
    assert detect_source_conflict(values) == "model"


@pytest.mark.asyncio
async def test_fake_judge_rejects_unknown_evidence_id() -> None:
    judge = FakeEvidenceJudge(
        lambda _request: AgentJudgement(
            conclusion="PASS",
            reason_code=ReasonCode.MATCH,
            reason="invalid",
            target_evidence_ids=["invented"],
        )
    )
    request = AgentExecutionInput(
        check_item_id="item",
        requirement="check",
        candidates=[candidate("known", EvidenceRole.TARGET, "content")],
    )
    with pytest.raises(AppError, match="unknown evidence") as error:
        await judge.judge(request)
    assert error.value.code == "MODEL_OUTPUT_INVALID"


@pytest.mark.asyncio
async def test_critical_model_item_runs_isolated_second_judgement() -> None:
    calls = 0

    def disagree(request: AgentExecutionInput) -> AgentJudgement:
        nonlocal calls
        calls += 1
        conclusion = "PASS" if calls == 1 else "FAIL"
        return AgentJudgement(
            conclusion=conclusion,
            reason_code=(ReasonCode.MATCH if conclusion == "PASS" else ReasonCode.MISMATCH),
            reason=f"run {calls}",
            target_evidence_ids=[request.candidates[0].evidence_id],
        )

    judge = FakeEvidenceJudge(disagree)
    values = [
        candidate("target", EvidenceRole.TARGET, "EU manual"),
        candidate(
            "source",
            EvidenceRole.SOURCE,
            "market: EU",
            category=SourceCategory.PROJECT,
            locator={"field": "market"},
        ),
    ]
    execution = await execute_item(None, item(), values, judge)  # type: ignore[arg-type]
    assert execution.executor_type == ExecutorType.SEMANTIC_AGENT
    assert execution.judgement.conclusion == ResultConclusion.NEEDS_REVIEW
    assert execution.judgement.reason_code == ReasonCode.MODEL_DISAGREEMENT
    assert len(execution.runs) == 2
    assert judge.requests[0].independent_review is False
    assert judge.requests[1].independent_review is True
    assert "conclusion" not in judge.requests[1].model_dump_json()


@pytest.mark.asyncio
async def test_not_applicable_is_program_controlled_without_model_call() -> None:
    judge = FakeEvidenceJudge()
    execution = await execute_item(
        None,
        item(
            severity=Severity.NORMAL.value,
            generation_metadata={"applicable": False},
        ),
        [],
        judge,
    )  # type: ignore[arg-type]
    assert execution.judgement.conclusion == ResultConclusion.NOT_APPLICABLE
    assert not judge.requests


@pytest.mark.asyncio
async def test_normal_fail_also_runs_independent_review() -> None:
    judge = FakeEvidenceJudge(
        lambda request: AgentJudgement(
            conclusion="FAIL",
            reason_code=ReasonCode.MISMATCH,
            reason="not matched",
            target_evidence_ids=[request.candidates[0].evidence_id],
        )
    )
    values = [candidate("target", EvidenceRole.TARGET, "manual content")]
    execution = await execute_item(
        None,
        item(
            severity=Severity.NORMAL.value,
            required_source_categories=["MANUAL"],
        ),
        values,
        judge,
    )  # type: ignore[arg-type]
    assert execution.judgement.conclusion == ResultConclusion.FAIL
    assert len(execution.runs) == 2


@pytest.mark.asyncio
async def test_process_model_semaphore_caps_concurrency() -> None:
    active = 0
    maximum = 0

    async def work() -> None:
        nonlocal active, maximum
        async with model_call_slot(2):
            active += 1
            maximum = max(maximum, active)
            await asyncio.sleep(0.01)
            active -= 1

    await asyncio.gather(*(work() for _ in range(7)))
    assert maximum == 2
