from functools import lru_cache
from pathlib import Path
from typing import Any

from app.schemas.checklist import CommonRuleCatalog, CommonRuleDefinition


@lru_cache
def load_common_rule_catalog(path: Path | None = None) -> CommonRuleCatalog:
    source = path or Path(__file__).with_name("common_rules.json")
    return CommonRuleCatalog.model_validate_json(source.read_text(encoding="utf-8"))


def applicable_rules(
    catalog: CommonRuleCatalog, project_data: dict[str, Any]
) -> list[tuple[CommonRuleDefinition, str]]:
    project = project_data.get("project", {})
    attributes = project_data.get("attributes", {})
    result: list[tuple[CommonRuleDefinition, str]] = []
    for rule in catalog.rules:
        if rule.applicability == "always":
            result.append((rule, ""))
        elif rule.applicability == "attributes.non_empty":
            for key in sorted(attributes):
                result.append((rule, key))
        elif rule.applicability.startswith("project.") and rule.applicability.endswith("_present"):
            field = rule.applicability.removeprefix("project.").removesuffix("_present")
            value = project.get(field)
            if value not in (None, "", []):
                result.append((rule, field))
    return result


def rule_summaries(catalog: CommonRuleCatalog) -> list[dict[str, str]]:
    return [
        {"rule_id": rule.rule_id, "name": rule.name, "description": rule.description}
        for rule in catalog.rules
    ]
