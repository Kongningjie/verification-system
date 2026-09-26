from pathlib import Path

from app.core.errors import AppError
from fastapi.testclient import TestClient
from tests.test_checklist_api import create_task


def confirm(api_client: TestClient, task_id: str) -> None:
    listing = api_client.get(f"/api/v1/tasks/{task_id}/check-items").json()
    response = api_client.post(
        f"/api/v1/tasks/{task_id}/check-items/confirm",
        json={"expected_revision": listing["checklist_revision"]},
    )
    assert response.status_code == 200, response.text


def test_confirmed_task_executes_to_traceable_results(
    api_client: TestClient, tmp_path: Path
) -> None:
    task = create_task(api_client, tmp_path)
    confirm(api_client, task["id"])

    detail = api_client.get(f"/api/v1/tasks/{task['id']}").json()
    assert detail["status"] == "COMPLETED"
    assert detail["progress"] == 100
    response = api_client.get(f"/api/v1/tasks/{task['id']}/results")
    assert response.status_code == 200, response.text
    results = response.json()["items"]
    checklist = api_client.get(f"/api/v1/tasks/{task['id']}/check-items").json()["items"]
    assert len(results) == len([item for item in checklist if item["enabled"]])
    for result in results:
        if result["system_conclusion"] in {"PASS", "FAIL"}:
            assert result["evidence_ids"]
            assert {item["evidence_id"] for item in result["evidences"]} == set(
                result["evidence_ids"]
            )
    critical_model = next(
        result
        for result in results
        if result["severity"] == "CRITICAL"
        and result["check_type"] in {"SEMANTIC", "CUSTOM_SEMANTIC", "VISUAL", "CUSTOM_VISUAL"}
    )
    assert [run["run_type"] for run in critical_model["runs"]] == [
        "PRIMARY",
        "INDEPENDENT_REVIEW",
    ]

    filtered = api_client.get(
        f"/api/v1/tasks/{task['id']}/results", params={"severity": "CRITICAL"}
    )
    assert filtered.status_code == 200
    assert all(item["severity"] == "CRITICAL" for item in filtered.json()["items"])
    single = api_client.get(f"/api/v1/tasks/{task['id']}/results/{results[0]['id']}")
    assert single.status_code == 200


def test_technical_model_errors_are_retryable_without_becoming_review(
    api_client: TestClient, tmp_path: Path
) -> None:
    judge = api_client.fake_evidence_judge  # type: ignore[attr-defined]

    def fail(_request):
        raise AppError("MODEL_TEMPORARY_FAILURE", "temporary", status_code=502)

    judge._responder = fail
    task = create_task(api_client, tmp_path)
    confirm(api_client, task["id"])
    detail = api_client.get(f"/api/v1/tasks/{task['id']}").json()
    assert detail["status"] == "COMPLETED_WITH_ERRORS"
    before = api_client.get(
        f"/api/v1/tasks/{task['id']}/results", params={"conclusion": "ERROR"}
    ).json()["items"]
    assert before
    assert all(item["reason_code"] == "INTERNAL_ERROR" for item in before)

    judge._responder = None
    retried = api_client.post(f"/api/v1/tasks/{task['id']}/retry-errors")
    assert retried.status_code == 200, retried.text
    assert api_client.get(f"/api/v1/tasks/{task['id']}").json()["status"] == "COMPLETED"
    after = api_client.get(
        f"/api/v1/tasks/{task['id']}/results", params={"conclusion": "ERROR"}
    ).json()["items"]
    assert after == []


def test_cancel_rejects_finished_task(api_client: TestClient, tmp_path: Path) -> None:
    task = create_task(api_client, tmp_path)
    confirm(api_client, task["id"])
    response = api_client.post(f"/api/v1/tasks/{task['id']}/cancel")
    assert response.status_code == 409
    assert response.json()["code"] == "TASK_NOT_CANCELLABLE"


def test_sse_rejects_unknown_task(api_client: TestClient) -> None:
    response = api_client.get("/api/v1/tasks/missing/events")
    assert response.status_code == 404
    assert response.json()["code"] == "TASK_NOT_FOUND"
