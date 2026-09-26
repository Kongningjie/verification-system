from pathlib import Path

from app.core.errors import AppError
from app.schemas.checklist import (
    BaseCheckType,
    GeneratedCheckItem,
    GeneratedCheckItems,
    Severity,
    SourceCategory,
)
from fastapi.testclient import TestClient
from tests.factories import docx_bytes
from tests.test_tasks_api import DOCX_MIME, valid_files


def create_task(api_client: TestClient, tmp_path: Path) -> dict:
    response = api_client.post(
        "/api/v1/tasks", data={"name": "Checklist task"}, files=valid_files(tmp_path)
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_generated_checklist_covers_common_rules_and_every_comment(
    api_client: TestClient, tmp_path: Path
) -> None:
    task = create_task(api_client, tmp_path)

    response = api_client.get(f"/api/v1/tasks/{task['id']}/check-items")

    assert response.status_code == 200
    body = response.json()
    assert body["task_status"] == "AWAITING_CHECKLIST_CONFIRMATION"
    assert body["checklist_revision"] == 1
    assert {item["rule_id"] for item in body["items"]} >= {
        "common.product_name",
        "common.model",
        "common.market",
        "common.language",
        "common.required_sections",
        "common.project_attributes",
    }
    comments = [item for item in body["items"] if item["source_type"] == "TEMPLATE_COMMENT"]
    assert {item["source_comment_id"] for item in comments} == {"7"}
    assert comments[0]["source_comment_text"] == "Must match certification"
    assert comments[0]["source_selected_text"] == "Use battery A"


def test_edit_uses_optimistic_lock_and_confirmation_is_immutable(
    api_client: TestClient, tmp_path: Path
) -> None:
    task = create_task(api_client, tmp_path)
    listing = api_client.get(f"/api/v1/tasks/{task['id']}/check-items").json()
    item = next(entry for entry in listing["items"] if entry["source_type"] == "TEMPLATE_COMMENT")

    edited = api_client.patch(
        f"/api/v1/tasks/{task['id']}/check-items/{item['id']}",
        json={
            "expected_version": item["version"],
            "name": "认证资料一致性",
            "severity": "CRITICAL",
            "enabled": True,
        },
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["version"] == 2
    assert edited.json()["severity"] == "CRITICAL"

    stale = api_client.patch(
        f"/api/v1/tasks/{task['id']}/check-items/{item['id']}",
        json={"expected_version": 1, "name": "stale"},
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "CHECK_ITEM_VERSION_CONFLICT"

    current = api_client.get(f"/api/v1/tasks/{task['id']}/check-items").json()
    confirmed = api_client.post(
        f"/api/v1/tasks/{task['id']}/check-items/confirm",
        json={"expected_revision": current["checklist_revision"]},
    )
    assert confirmed.status_code == 200, confirmed.text
    snapshot = confirmed.json()
    assert snapshot["version_number"] == 1
    assert any(entry["name"] == "认证资料一致性" for entry in snapshot["snapshot"])
    assert api_client.get(f"/api/v1/tasks/{task['id']}").json()["status"] == "QUEUED"

    after_confirm = api_client.patch(
        f"/api/v1/tasks/{task['id']}/check-items/{item['id']}",
        json={"expected_version": 2, "name": "must not change"},
    )
    assert after_confirm.status_code == 409
    assert after_confirm.json()["code"] == "CHECKLIST_NOT_EDITABLE"
    second_confirm = api_client.post(
        f"/api/v1/tasks/{task['id']}/check-items/confirm",
        json={"expected_revision": current["checklist_revision"]},
    )
    assert second_confirm.status_code == 409


def test_confirmation_rejects_stale_revision_and_empty_enabled_list(
    api_client: TestClient, tmp_path: Path
) -> None:
    task = create_task(api_client, tmp_path)
    listing = api_client.get(f"/api/v1/tasks/{task['id']}/check-items").json()

    stale = api_client.post(
        f"/api/v1/tasks/{task['id']}/check-items/confirm",
        json={"expected_revision": listing["checklist_revision"] + 1},
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "CHECKLIST_VERSION_CONFLICT"

    revision = listing["checklist_revision"]
    for item in listing["items"]:
        response = api_client.patch(
            f"/api/v1/tasks/{task['id']}/check-items/{item['id']}",
            json={"expected_version": item["version"], "enabled": False},
        )
        assert response.status_code == 200
        revision += 1
    empty = api_client.post(
        f"/api/v1/tasks/{task['id']}/check-items/confirm",
        json={"expected_revision": revision},
    )
    assert empty.status_code == 422
    assert empty.json()["code"] == "EMPTY_CHECKLIST"


def test_generation_failure_is_visible_and_keeps_parsed_materials(
    api_client: TestClient, tmp_path: Path
) -> None:
    generator = api_client.fake_checklist_generator  # type: ignore[attr-defined]

    def fail(_request):
        raise AppError("MODEL_OUTPUT_INVALID", "Invalid structured output.", status_code=502)

    generator._responder = fail
    response = api_client.post(
        "/api/v1/tasks", data={"name": "Failed checklist"}, files=valid_files(tmp_path)
    )

    assert response.status_code == 502
    assert response.json()["code"] == "MODEL_OUTPUT_INVALID"
    task_id = response.json()["details"]["task_id"]
    failed = api_client.get(f"/api/v1/tasks/{task_id}").json()
    assert failed["status"] == "FAILED"
    assert failed["error_code"] == "MODEL_OUTPUT_INVALID"
    assert len(failed["files"]) == 5
    settings = api_client.test_settings  # type: ignore[attr-defined]
    assert (settings.tasks_root / task_id / "uploads").exists()


def test_unjustified_critical_suggestion_is_downgraded_with_warning(
    api_client: TestClient, tmp_path: Path
) -> None:
    generator = api_client.fake_checklist_generator  # type: ignore[attr-defined]

    def suggest_critical(request):
        return GeneratedCheckItems(
            items=[
                GeneratedCheckItem(
                    source_comment_id=request.comment_id,
                    name="普通格式",
                    requirement="检查普通格式",
                    check_type=BaseCheckType.SEMANTIC,
                    severity_suggestion=Severity.CRITICAL,
                    severity_reason="模型主观认为重要",
                    required_source_categories=[
                        SourceCategory.MANUAL,
                        SourceCategory.EVIDENCE_PDF,
                    ],
                    target_hint=request.selected_text,
                )
            ]
        )

    generator._responder = suggest_critical
    files = valid_files(tmp_path)
    files[1] = (
        "template",
        ("template.docx", docx_bytes(comment_text="Check formatting"), DOCX_MIME),
    )
    response = api_client.post(
        "/api/v1/tasks", data={"name": "Severity task"}, files=files
    )
    assert response.status_code == 201, response.text
    task = response.json()
    listing = api_client.get(f"/api/v1/tasks/{task['id']}/check-items").json()
    item = next(entry for entry in listing["items"] if entry["source_type"] == "TEMPLATE_COMMENT")

    assert item["severity"] == "NORMAL"
    assert "CRITICAL_SUGGESTION_DOWNGRADED" in item["generation_warnings"]
