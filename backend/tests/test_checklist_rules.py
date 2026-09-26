import json
from pathlib import Path

import pytest
from app.models.checklist import CheckItem
from app.models.document import TemplateComment
from app.rules.registry import applicable_rules, load_common_rule_catalog
from app.schemas.checklist import CheckSourceType, CheckType, CommonRuleCatalog, Severity
from app.services.checklists import _mark_possible_duplicates
from pydantic import ValidationError


def test_common_rule_catalog_has_unique_required_rules() -> None:
    catalog = load_common_rule_catalog()

    assert catalog.schema_version == "1.0"
    assert len({rule.rule_id for rule in catalog.rules}) == len(catalog.rules)
    assert {
        "common.product_name",
        "common.model",
        "common.brand",
        "common.market",
        "common.language",
        "common.required_sections",
        "common.project_attributes",
    } <= {rule.rule_id for rule in catalog.rules}


def test_common_rule_catalog_rejects_duplicate_id_and_version() -> None:
    rule = load_common_rule_catalog().rules[0].model_dump(mode="json")

    with pytest.raises(ValidationError, match="unique"):
        CommonRuleCatalog.model_validate(
            {"schema_version": "1.0", "ruleset_version": "test", "rules": [rule, rule]}
        )


def test_registry_rejects_unknown_rule_fields(tmp_path: Path) -> None:
    payload = load_common_rule_catalog().model_dump(mode="json")
    payload["rules"][0]["unexpected"] = True
    path = tmp_path / "rules.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValidationError):
        load_common_rule_catalog(path)


def test_applicability_expands_each_project_attribute() -> None:
    rules = applicable_rules(
        load_common_rule_catalog(),
        {
            "project": {
                "product_name": "Phone",
                "model": None,
                "brand": None,
                "market": None,
                "language": [],
            },
            "attributes": {"battery": "A", "color": "blue"},
        },
    )

    identities = [(rule.rule_id, target) for rule, target in rules]
    assert ("common.product_name", "product_name") in identities
    assert ("common.model", "model") not in identities
    assert identities.count(("common.project_attributes", "battery")) == 1
    assert identities.count(("common.project_attributes", "color")) == 1


def test_duplicate_dynamic_requirements_are_warned_but_not_removed() -> None:
    first = CheckItem(
        task_id="task",
        source_type=CheckSourceType.TEMPLATE_COMMENT,
        name="认证要求",
        requirement="必须通过认证",
        check_type=CheckType.SEMANTIC,
        severity=Severity.CRITICAL,
    )
    second = CheckItem(
        task_id="task",
        source_type=CheckSourceType.TEMPLATE_COMMENT,
        name="认证要求",
        requirement="必须通过认证",
        check_type=CheckType.SEMANTIC,
        severity=Severity.CRITICAL,
    )
    groups = [
        (TemplateComment(comment_id="1", task_file_id="file"), [first]),
        (TemplateComment(comment_id="2", task_file_id="file"), [second]),
    ]

    _mark_possible_duplicates(groups)

    assert len(groups) == 2
    assert first.generation_warnings == ["POSSIBLE_DUPLICATE"]
    assert second.generation_warnings == ["POSSIBLE_DUPLICATE"]
