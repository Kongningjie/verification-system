import re
from collections import Counter

from sqlalchemy.orm import Session

from app.agents.checklist import ChecklistGenerator
from app.core.errors import AppError
from app.models.checklist import CheckItem
from app.models.document import FileCategory, ParseStatus, TemplateComment
from app.models.task import TaskStatus, VerificationTask
from app.rules.registry import applicable_rules, load_common_rule_catalog, rule_summaries
from app.schemas.checklist import (
    BaseCheckType,
    CheckSourceType,
    CheckType,
    CommentGenerationInput,
    Severity,
    SourceCategory,
)
from app.workflow.task_state import transition_task

_CRITICAL_TERMS = (
    "法规",
    "认证",
    "安全",
    "强制",
    "禁止",
    "不可缺失",
    "必须",
    "regulation",
    "certification",
    "safety",
    "mandatory",
    "prohibited",
    "must",
    "required",
    "shall",
)


async def generate_checklist(
    session: Session,
    task: VerificationTask,
    generator: ChecklistGenerator,
) -> None:
    if task.status != TaskStatus.GENERATING_CHECKLIST:
        raise AppError(
            "INVALID_CHECKLIST_GENERATION_STATE",
            "The task is not ready for checklist generation.",
            status_code=409,
        )
    catalog = load_common_rule_catalog()
    project_data = task.project_metadata.normalized_data if task.project_metadata else {}
    pending: list[CheckItem] = []
    for rule, target_field in applicable_rules(catalog, project_data):
        requirement = rule.description
        name = rule.name
        if rule.rule_id == "common.project_attributes" and target_field:
            name = f"扩展属性：{target_field}"
            requirement = f"说明书中与“{target_field}”相关的内容必须与项目资料一致。"
        pending.append(
            CheckItem(
                task_id=task.id,
                source_type=CheckSourceType.COMMON_RULE,
                rule_id=rule.rule_id,
                rule_version=rule.version,
                name=name,
                requirement=requirement,
                check_type=CheckType(rule.check_type.value),
                severity=rule.default_severity,
                required_source_categories=[source.value for source in rule.required_sources],
                target_hint=target_field,
                generation_warnings=[],
                source_heading_path=[],
                generation_metadata={
                    "ruleset_version": catalog.ruleset_version,
                    "executor": rule.executor.value,
                },
            )
        )

    template_file = next(
        (item for item in task.files if item.category == FileCategory.TEMPLATE_DOCX), None
    )
    comments = (
        sorted(template_file.comments, key=lambda item: item.comment_id) if template_file else []
    )
    available_sources = _available_sources(task)
    summaries = rule_summaries(catalog)
    generated_groups: list[tuple[TemplateComment, list[CheckItem]]] = []
    for comment in comments:
        request = CommentGenerationInput(
            comment_id=comment.comment_id,
            comment_text=comment.text,
            selected_text=comment.selected_text,
            heading_path=comment.heading_path,
            context_before=(comment.context_before or "")[:1500] or None,
            context_after=(comment.context_after or "")[:1500] or None,
            available_source_categories=available_sources,
            common_rule_summaries=summaries,
        )
        result = await generator.generate(request)
        if not result.output.items:
            raise AppError(
                "COMMENT_GENERATION_EMPTY",
                "A template comment produced no checklist item.",
                status_code=502,
                details={"comment_id": comment.comment_id},
            )
        group: list[CheckItem] = []
        for generated in result.output.items:
            if generated.source_comment_id != comment.comment_id:
                raise AppError(
                    "MODEL_OUTPUT_SOURCE_MISMATCH",
                    "The checklist model changed the source comment identifier.",
                    status_code=502,
                    details={"comment_id": comment.comment_id},
                )
            warnings = list(dict.fromkeys([*comment.warning_codes, *generated.generation_warnings]))
            severity = generated.severity_suggestion
            if severity == Severity.CRITICAL and not any(
                term in comment.text.casefold() for term in _CRITICAL_TERMS
            ):
                severity = Severity.NORMAL
                warnings.append("CRITICAL_SUGGESTION_DOWNGRADED")
            valid_rule_ids = {rule.rule_id for rule in catalog.rules}
            mapping = generated.rule_mapping_id
            if mapping and mapping not in valid_rule_ids:
                mapping = None
                warnings.append("UNKNOWN_RULE_MAPPING")
            if any(
                source not in available_sources
                for source in generated.required_source_categories
            ):
                warnings.append("REQUIRED_SOURCE_UNAVAILABLE")
            mapped_rule = next(
                (rule for rule in catalog.rules if rule.rule_id == mapping), None
            )
            if mapped_rule is not None:
                final_check_type = CheckType(mapped_rule.check_type.value)
            elif generated.check_type == BaseCheckType.VISUAL:
                final_check_type = CheckType.CUSTOM_VISUAL
            elif generated.check_type == BaseCheckType.STRUCTURE:
                final_check_type = CheckType.CUSTOM_STRUCTURE
            else:
                final_check_type = CheckType.CUSTOM_SEMANTIC
            group.append(
                CheckItem(
                    task_id=task.id,
                    source_type=CheckSourceType.TEMPLATE_COMMENT,
                    source_comment_id=comment.comment_id,
                    rule_id=mapping,
                    name=generated.name,
                    requirement=generated.requirement,
                    check_type=final_check_type,
                    severity=severity,
                    required_source_categories=[
                        source.value for source in generated.required_source_categories
                    ],
                    target_hint=generated.target_hint,
                    generation_warnings=list(dict.fromkeys(warnings)),
                    source_comment_text=comment.text,
                    source_selected_text=comment.selected_text,
                    source_heading_path=comment.heading_path,
                    generation_metadata=result.metadata.model_dump(mode="json"),
                )
            )
        generated_groups.append((comment, group))

    _mark_possible_duplicates(generated_groups)
    for _, group in generated_groups:
        pending.extend(group)
    session.add_all(pending)
    task.checklist_revision = 1
    transition_task(task, TaskStatus.AWAITING_CHECKLIST_CONFIRMATION, progress=65)
    session.commit()


def _available_sources(task: VerificationTask) -> list[SourceCategory]:
    result = [SourceCategory.MANUAL, SourceCategory.PROJECT]
    if any(
        item.category == FileCategory.EVIDENCE_PDF and item.parse_status == ParseStatus.PARSED
        for item in task.files
    ):
        result.append(SourceCategory.EVIDENCE_PDF)
    if any(
        item.category == FileCategory.EVIDENCE_IMAGE and item.parse_status == ParseStatus.PARSED
        for item in task.files
    ):
        result.append(SourceCategory.EVIDENCE_IMAGE)
    return result


def _mark_possible_duplicates(groups: list[tuple[TemplateComment, list[CheckItem]]]) -> None:
    normalized = [
        re.sub(r"\W+", "", f"{item.name}{item.requirement}").casefold()
        for _, group in groups
        for item in group
    ]
    counts = Counter(value for value in normalized if value)
    position = 0
    for _, group in groups:
        for item in group:
            if normalized[position] and counts[normalized[position]] > 1:
                item.generation_warnings = list(
                    dict.fromkeys([*(item.generation_warnings or []), "POSSIBLE_DUPLICATE"])
                )
            position += 1
