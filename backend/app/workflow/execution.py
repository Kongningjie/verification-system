import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any

from app.agents.execution import EvidenceJudge
from app.core.errors import AppError
from app.evidence.matcher import normalize_text
from app.models.task import VerificationTask
from app.schemas.checklist import CheckType, ExecutorType, Severity, SourceCategory
from app.schemas.execution import (
    AgentExecutionInput,
    EvidenceCandidate,
    EvidenceRole,
    PersistedJudgement,
    ReasonCode,
    ResultConclusion,
    RunType,
)


@dataclass
class RunRecord:
    run_type: RunType
    executor_type: ExecutorType
    input_hash: str
    conclusion: ResultConclusion | None
    reason: str | None
    evidence_ids: list[str]
    reason_code: ReasonCode | None = None
    differences: list[str] | None = None
    missing_information: list[str] | None = None
    model_name: str | None = None
    prompt_version: str = "rules-1.0"
    duration_ms: int = 0
    retry_count: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    error_type: str | None = None


@dataclass
class ItemExecution:
    item: dict[str, Any]
    executor_type: ExecutorType
    candidates: list[EvidenceCandidate]
    judgement: PersistedJudgement
    runs: list[RunRecord]


def executor_for(item: dict[str, Any]) -> ExecutorType:
    check_type = CheckType(item["check_type"])
    if check_type == CheckType.FIELD:
        return ExecutorType.FIELD_RULE
    if check_type in {CheckType.STRUCTURE, CheckType.CUSTOM_STRUCTURE}:
        return ExecutorType.STRUCTURE_RULE
    if check_type in {CheckType.VISUAL, CheckType.CUSTOM_VISUAL}:
        return ExecutorType.VISION_AGENT
    return ExecutorType.SEMANTIC_AGENT


def input_hash(item: dict[str, Any], candidates: list[EvidenceCandidate]) -> str:
    payload = {
        "item": item,
        "candidate_ids": [candidate.evidence_id for candidate in candidates],
        "candidate_content": [candidate.content for candidate in candidates],
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode()
    ).hexdigest()


def _missing_data(
    item: dict[str, Any], candidates: list[EvidenceCandidate]
) -> PersistedJudgement | None:
    targets = [candidate for candidate in candidates if candidate.role == EvidenceRole.TARGET]
    if not targets:
        return PersistedJudgement(
            conclusion=ResultConclusion.NEEDS_REVIEW,
            reason_code=ReasonCode.MISSING_TARGET_CONTENT,
            reason="未在说明书中找到可核对的目标内容。",
        )
    required = {SourceCategory(value) for value in item.get("required_source_categories", [])}
    required.discard(SourceCategory.MANUAL)
    available = {
        candidate.source_category
        for candidate in candidates
        if candidate.role == EvidenceRole.SOURCE
    }
    missing = sorted(category.value for category in required - available)
    if missing:
        return PersistedJudgement(
            conclusion=ResultConclusion.NEEDS_REVIEW,
            reason_code=ReasonCode.MISSING_SOURCE_DATA,
            reason=f"缺少核对所需依据：{', '.join(missing)}。",
        )
    conflict = detect_source_conflict(candidates)
    if conflict:
        return PersistedJudgement(
            conclusion=ResultConclusion.NEEDS_REVIEW,
            reason_code=ReasonCode.SOURCE_CONFLICT,
            reason=f"同一事实的依据值互相冲突：{conflict}。",
            evidence_ids=[
                candidate.evidence_id
                for candidate in candidates
                if candidate.role == EvidenceRole.SOURCE
            ][:4],
        )
    return None


def detect_source_conflict(candidates: list[EvidenceCandidate]) -> str | None:
    facts: dict[str, set[str]] = {}
    for candidate in candidates:
        if candidate.role != EvidenceRole.SOURCE:
            continue
        key = candidate.locator.get("fact_key") or candidate.locator.get("field")
        if not key:
            continue
        value = normalize_text(candidate.content.split(":", 1)[-1])
        if value:
            facts.setdefault(str(key), set()).add(value)
    for key, values in facts.items():
        if len(values) > 1:
            return key
    return None


def _field_name(rule_id: str | None) -> str | None:
    return {
        "common.product_name": "product_name",
        "common.model": "model",
        "common.brand": "brand",
        "common.market": "market",
    }.get(rule_id or "")


def execute_field_rule(
    item: dict[str, Any], candidates: list[EvidenceCandidate]
) -> PersistedJudgement:
    missing = _missing_data(item, candidates)
    if missing:
        return missing
    targets = [candidate for candidate in candidates if candidate.role == EvidenceRole.TARGET]
    sources = [candidate for candidate in candidates if candidate.role == EvidenceRole.SOURCE]
    field = _field_name(item.get("rule_id"))
    if field:
        sources = [candidate for candidate in sources if candidate.locator.get("field") == field]
    elif item.get("rule_id") == "common.project_attributes":
        sources = [
            candidate for candidate in sources if candidate.locator.get("section") == "attributes"
        ]
    if not sources:
        return PersistedJudgement(
            conclusion=ResultConclusion.NEEDS_REVIEW,
            reason_code=ReasonCode.MISSING_SOURCE_DATA,
            reason="没有找到可用于字段规则的权威项目字段。",
        )
    target_text = normalize_text(" ".join(candidate.content for candidate in targets))
    matched = [
        candidate
        for candidate in sources
        if normalize_text(candidate.content.split(":", 1)[-1]) in target_text
    ]
    evidence = [targets[0].evidence_id, *[candidate.evidence_id for candidate in sources]]
    if len(matched) == len(sources):
        return PersistedJudgement(
            conclusion=ResultConclusion.PASS,
            reason_code=ReasonCode.MATCH,
            reason="说明书目标内容与项目字段一致。",
            evidence_ids=evidence,
        )
    return PersistedJudgement(
        conclusion=ResultConclusion.FAIL,
        reason_code=ReasonCode.MISMATCH,
        reason="说明书目标内容未包含项目字段的规范化值。",
        evidence_ids=evidence,
    )


def execute_structure_rule(
    item: dict[str, Any], candidates: list[EvidenceCandidate]
) -> PersistedJudgement:
    missing = _missing_data(item, candidates)
    if missing:
        return missing
    targets = [candidate for candidate in candidates if candidate.role == EvidenceRole.TARGET]
    combined = normalize_text(" ".join(candidate.content for candidate in targets))
    rule_id = item.get("rule_id")
    if rule_id == "common.language":
        sources = [
            candidate for candidate in candidates if candidate.locator.get("field") == "language"
        ]
        if not sources:
            return PersistedJudgement(
                conclusion=ResultConclusion.NEEDS_REVIEW,
                reason_code=ReasonCode.MISSING_SOURCE_DATA,
                reason="项目资料未声明目标语言。",
            )
        expected = [
            token.strip()
            for token in sources[0].content.split(":", 1)[-1].split(",")
            if token.strip()
        ]
        passed = all(normalize_text(token) in combined for token in expected)
        ids = [targets[0].evidence_id, sources[0].evidence_id]
    elif rule_id == "common.required_sections":
        headings = normalize_text(
            " ".join(
                " ".join(map(str, candidate.locator.get("heading_path", [])))
                for candidate in targets
            )
        )
        expected_groups = (("安全", "safety"), ("使用", "operation", "usage"))
        passed = all(any(term in headings for term in group) for group in expected_groups)
        ids = [candidate.evidence_id for candidate in targets[:3]]
    else:
        hint = normalize_text(item.get("target_hint") or item.get("requirement") or "")
        passed = bool(hint and hint in combined)
        ids = [targets[0].evidence_id]
    return PersistedJudgement(
        conclusion=ResultConclusion.PASS if passed else ResultConclusion.FAIL,
        reason_code=ReasonCode.MATCH if passed else ReasonCode.MISMATCH,
        reason="说明书结构满足核对要求。" if passed else "说明书结构未满足核对要求。",
        evidence_ids=ids,
    )


async def execute_model(
    item: dict[str, Any],
    candidates: list[EvidenceCandidate],
    judge: EvidenceJudge,
    *,
    independent: bool,
) -> tuple[PersistedJudgement, RunRecord]:
    missing = _missing_data(item, candidates)
    run_type = RunType.INDEPENDENT_REVIEW if independent else RunType.PRIMARY
    digest = input_hash(item, candidates)
    if missing:
        return missing, RunRecord(
            run_type=run_type,
            executor_type=executor_for(item),
            input_hash=digest,
            conclusion=missing.conclusion,
            reason=missing.reason,
            evidence_ids=missing.evidence_ids,
            reason_code=missing.reason_code,
        )
    request = AgentExecutionInput(
        check_item_id=item["id"],
        requirement=item["requirement"],
        candidates=candidates,
        independent_review=independent,
    )
    try:
        output = await judge.judge(request)
    except AppError as exc:
        reason_by_error = {
            "MODEL_OUTPUT_INVALID": ReasonCode.STRUCTURED_OUTPUT_ERROR,
            "MODEL_AUTHENTICATION_FAILED": ReasonCode.MODEL_AUTH_ERROR,
            "MODEL_TIMEOUT": ReasonCode.MODEL_TIMEOUT,
            "MODEL_RATE_LIMIT_EXHAUSTED": ReasonCode.MODEL_RATE_LIMIT_EXHAUSTED,
        }
        judgement = PersistedJudgement(
            conclusion=ResultConclusion.ERROR,
            reason_code=reason_by_error.get(exc.code, ReasonCode.INTERNAL_ERROR),
            reason=exc.message,
        )
        return judgement, RunRecord(
            run_type=run_type,
            executor_type=executor_for(item),
            input_hash=digest,
            conclusion=ResultConclusion.ERROR,
            reason=exc.message,
            evidence_ids=[],
            reason_code=judgement.reason_code,
            model_name=judge.model_name,
            prompt_version="evidence-judgement-1.0",
            error_type=exc.code,
        )
    judgement = PersistedJudgement(
        conclusion=ResultConclusion(output.judgement.conclusion),
        reason_code=output.judgement.reason_code,
        reason=output.judgement.reason,
        evidence_ids=output.judgement.evidence_ids,
    )
    metadata = output.metadata
    return judgement, RunRecord(
        run_type=run_type,
        executor_type=executor_for(item),
        input_hash=digest,
        conclusion=judgement.conclusion,
        reason=judgement.reason,
        evidence_ids=judgement.evidence_ids,
        reason_code=judgement.reason_code,
        differences=output.judgement.differences,
        missing_information=output.judgement.missing_information,
        model_name=metadata.model,
        prompt_version=metadata.prompt_version,
        duration_ms=metadata.duration_ms,
        retry_count=metadata.attempts - 1,
        input_tokens=metadata.input_tokens,
        output_tokens=metadata.output_tokens,
    )


async def execute_item(
    task: VerificationTask,
    item: dict[str, Any],
    candidates: list[EvidenceCandidate],
    judge: EvidenceJudge,
) -> ItemExecution:
    executor = executor_for(item)
    digest = input_hash(item, candidates)
    if item.get("generation_metadata", {}).get("applicable") is False:
        judgement = PersistedJudgement(
            conclusion=ResultConclusion.NOT_APPLICABLE,
            reason_code=ReasonCode.NOT_APPLICABLE_BY_RULE,
            reason="确认后的规则适用条件表明本项不适用。",
        )
        return ItemExecution(
            item=item,
            executor_type=executor,
            candidates=candidates,
            judgement=judgement,
            runs=[
                RunRecord(
                    RunType.PRIMARY,
                    executor,
                    digest,
                    judgement.conclusion,
                    judgement.reason,
                    [],
                )
            ],
        )
    if executor == ExecutorType.FIELD_RULE:
        started = time.perf_counter()
        try:
            judgement = execute_field_rule(item, candidates)
            error = None
        except Exception:
            judgement = PersistedJudgement(
                conclusion=ResultConclusion.ERROR,
                reason_code=ReasonCode.INTERNAL_ERROR,
                reason="字段规则执行失败。",
            )
            error = "RULE_EXECUTION_ERROR"
        runs = [
            RunRecord(
                RunType.PRIMARY,
                executor,
                digest,
                judgement.conclusion,
                judgement.reason,
                judgement.evidence_ids,
                duration_ms=int((time.perf_counter() - started) * 1000),
                error_type=error,
            )
        ]
    elif executor == ExecutorType.STRUCTURE_RULE:
        started = time.perf_counter()
        try:
            judgement = execute_structure_rule(item, candidates)
            error = None
        except Exception:
            judgement = PersistedJudgement(
                conclusion=ResultConclusion.ERROR,
                reason_code=ReasonCode.INTERNAL_ERROR,
                reason="结构规则执行失败。",
            )
            error = "RULE_EXECUTION_ERROR"
        runs = [
            RunRecord(
                RunType.PRIMARY,
                executor,
                digest,
                judgement.conclusion,
                judgement.reason,
                judgement.evidence_ids,
                duration_ms=int((time.perf_counter() - started) * 1000),
                error_type=error,
            )
        ]
    else:
        judgement, primary = await execute_model(item, candidates, judge, independent=False)
        runs = [primary]
        needs_second = item["severity"] == Severity.CRITICAL.value or (
            item["severity"] == Severity.NORMAL.value
            and judgement.conclusion == ResultConclusion.FAIL
        )
        if needs_second and judgement.conclusion != ResultConclusion.ERROR:
            second, second_run = await execute_model(item, candidates, judge, independent=True)
            runs.append(second_run)
            if second.conclusion == ResultConclusion.ERROR:
                judgement = second
            elif second.conclusion != judgement.conclusion:
                judgement = PersistedJudgement(
                    conclusion=ResultConclusion.NEEDS_REVIEW,
                    reason_code=ReasonCode.MODEL_DISAGREEMENT,
                    reason="两次相互隔离的模型判断不一致，需要人工复核。",
                    evidence_ids=list(dict.fromkeys(judgement.evidence_ids + second.evidence_ids)),
                )
    return ItemExecution(
        item=item, executor_type=executor, candidates=candidates, judgement=judgement, runs=runs
    )
