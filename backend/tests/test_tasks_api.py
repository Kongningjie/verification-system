from pathlib import Path

from fastapi.testclient import TestClient
from tests.factories import (
    docx_bytes,
    image_bytes,
    project_json_bytes,
    scanned_pdf,
    text_pdf,
)

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def valid_files(tmp_path: Path, *, with_evidence: bool = True):
    files = [
        ("manual", ("manual.docx", docx_bytes(title="Manual", comment_text=None), DOCX_MIME)),
        ("template", ("template.docx", docx_bytes(include_image=True), DOCX_MIME)),
        ("project", ("project.json", project_json_bytes(), "application/json")),
    ]
    if with_evidence:
        pdf_path = tmp_path / "evidence.pdf"
        text_pdf(pdf_path)
        files.extend(
            [
                ("evidence_files", ("evidence.pdf", pdf_path.read_bytes(), "application/pdf")),
                (
                    "evidence_files",
                    ("identity.jpg", image_bytes(format_name="JPEG"), "image/jpeg"),
                ),
            ]
        )
    return files


def test_complete_upload_persists_and_restores_document_graph(
    api_client: TestClient, tmp_path: Path
) -> None:
    response = api_client.post(
        "/api/v1/tasks", data={"name": "Integration task"}, files=valid_files(tmp_path)
    )

    assert response.status_code == 201, response.text
    created = response.json()
    assert created["status"] == "GENERATING_CHECKLIST"
    assert created["progress"] == 60
    assert len(created["files"]) == 5
    assert len(created["documents"]) == 4
    assert created["project"]["project"]["product_name"] == "Phone X"
    template = next(item for item in created["documents"] if item["kind"] == "template")
    assert template["comments"][0]["selected_text"] == "Use battery A"

    restored = api_client.get(f"/api/v1/tasks/{created['id']}")
    assert restored.status_code == 200
    assert restored.json() == created
    listing = api_client.get("/api/v1/tasks")
    assert listing.status_code == 200
    assert [task["id"] for task in listing.json()] == [created["id"]]

    settings = api_client.test_settings  # type: ignore[attr-defined]
    task_root = settings.tasks_root / created["id"]
    assert {path.name for path in task_root.iterdir()} == {
        "uploads",
        "parsed",
        "extracted",
        "reports",
    }
    upload_names = [path.name for path in (task_root / "uploads").iterdir()]
    assert "manual.docx" not in upload_names
    assert all(len(Path(name).stem) == 36 for name in upload_names)


def test_invalid_required_file_marks_task_failed_and_removes_files(
    api_client: TestClient, tmp_path: Path
) -> None:
    files = valid_files(tmp_path, with_evidence=False)
    files[2] = ("project", ("project.json", b'{"bad": true}', "application/json"))

    response = api_client.post("/api/v1/tasks", data={"name": "Invalid task"}, files=files)

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "INVALID_PROJECT_SCHEMA"
    task_id = body["details"]["task_id"]
    failed = api_client.get(f"/api/v1/tasks/{task_id}").json()
    assert failed["status"] == "FAILED"
    assert failed["files"] == []
    settings = api_client.test_settings  # type: ignore[attr-defined]
    assert not (settings.tasks_root / task_id).exists()


def test_duplicate_file_in_same_task_is_rejected(api_client: TestClient) -> None:
    duplicate = docx_bytes(title="Same", comment_text=None)
    files = [
        ("manual", ("manual.docx", duplicate, DOCX_MIME)),
        ("template", ("template.docx", duplicate, DOCX_MIME)),
        ("project", ("project.json", project_json_bytes(), "application/json")),
    ]

    response = api_client.post("/api/v1/tasks", data={"name": "Duplicate task"}, files=files)

    assert response.status_code == 422
    assert response.json()["code"] == "DUPLICATE_FILE"


def test_extension_mime_and_signature_must_agree(api_client: TestClient) -> None:
    files = [
        ("manual", ("manual.docx", b"not a zip", DOCX_MIME)),
        ("template", ("template.docx", docx_bytes(), DOCX_MIME)),
        ("project", ("project.json", project_json_bytes(), "application/json")),
    ]

    response = api_client.post("/api/v1/tasks", data={"name": "Signature task"}, files=files)

    assert response.status_code == 422
    assert response.json()["code"] == "FILE_SIGNATURE_MISMATCH"


def test_upload_field_rejects_wrong_extension(api_client: TestClient) -> None:
    files = [
        ("manual", ("manual.pdf", docx_bytes(comment_text=None), DOCX_MIME)),
        ("template", ("template.docx", docx_bytes(), DOCX_MIME)),
        ("project", ("project.json", project_json_bytes(), "application/json")),
    ]

    response = api_client.post("/api/v1/tasks", data={"name": "Extension task"}, files=files)

    assert response.status_code == 422
    assert response.json()["code"] == "FILE_EXTENSION_MISMATCH"


def test_missing_required_multipart_field_uses_standard_error(api_client: TestClient) -> None:
    response = api_client.post("/api/v1/tasks", data={"name": "Missing"}, files=[])

    assert response.status_code == 422
    assert response.json()["code"] == "REQUEST_VALIDATION_ERROR"
    assert response.headers["X-Request-ID"] == response.json()["request_id"]


def test_declared_mime_mismatch_is_rejected(api_client: TestClient) -> None:
    files = [
        ("manual", ("manual.docx", docx_bytes(comment_text=None), "application/pdf")),
        ("template", ("template.docx", docx_bytes(), DOCX_MIME)),
        ("project", ("project.json", project_json_bytes(), "application/json")),
    ]

    response = api_client.post("/api/v1/tasks", data={"name": "MIME task"}, files=files)

    assert response.status_code == 422
    assert response.json()["code"] == "DECLARED_MIME_MISMATCH"


def test_file_size_limit_is_enforced(api_client: TestClient) -> None:
    settings = api_client.test_settings  # type: ignore[attr-defined]
    settings.max_file_size_bytes = 100
    files = [
        ("manual", ("manual.docx", docx_bytes(comment_text=None), DOCX_MIME)),
        ("template", ("template.docx", docx_bytes(), DOCX_MIME)),
        ("project", ("project.json", project_json_bytes(), "application/json")),
    ]

    response = api_client.post("/api/v1/tasks", data={"name": "Large task"}, files=files)

    assert response.status_code == 422
    assert response.json()["code"] == "FILE_TOO_LARGE"


def test_task_total_size_limit_is_enforced(api_client: TestClient) -> None:
    settings = api_client.test_settings  # type: ignore[attr-defined]
    settings.max_task_size_bytes = 1

    response = api_client.post(
        "/api/v1/tasks",
        data={"name": "Total size task"},
        files=[
            ("manual", ("manual.docx", docx_bytes(comment_text=None), DOCX_MIME)),
            ("template", ("template.docx", docx_bytes(), DOCX_MIME)),
            ("project", ("project.json", project_json_bytes(), "application/json")),
        ],
    )

    assert response.status_code == 422
    assert response.json()["code"] == "TASK_TOO_LARGE"


def test_task_file_count_limit_is_enforced(api_client: TestClient, tmp_path: Path) -> None:
    settings = api_client.test_settings  # type: ignore[attr-defined]
    settings.max_upload_files = 3

    response = api_client.post(
        "/api/v1/tasks",
        data={"name": "File count task"},
        files=valid_files(tmp_path, with_evidence=True),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "TOO_MANY_FILES"


def test_scanned_evidence_pdf_is_warned_and_ignored(api_client: TestClient, tmp_path: Path) -> None:
    scan_path = tmp_path / "scan.pdf"
    scanned_pdf(scan_path)
    files = valid_files(tmp_path, with_evidence=False)
    files.append(("evidence_files", ("scan.pdf", scan_path.read_bytes(), "application/pdf")))

    response = api_client.post("/api/v1/tasks", data={"name": "Scan task"}, files=files)

    assert response.status_code == 201, response.text
    body = response.json()
    pdf_file = next(item for item in body["files"] if item["category"] == "EVIDENCE_PDF")
    assert pdf_file["parse_status"] == "IGNORED"
    assert body["warning_count"] == 1
    assert body["warnings"][0]["code"] == "SCANNED_PDF_UNSUPPORTED"
    pdf_graph = next(item for item in body["documents"] if item["kind"] == "evidence_pdf")
    assert pdf_graph["blocks"] == []
    assert pdf_graph["assets"] == []


def test_client_path_is_not_used_as_stored_or_displayed_filename(
    api_client: TestClient,
) -> None:
    files = [
        (
            "manual",
            ("C:\\client\\manual.docx", docx_bytes(comment_text=None), DOCX_MIME),
        ),
        ("template", ("template.docx", docx_bytes(), DOCX_MIME)),
        ("project", ("project.json", project_json_bytes(), "application/json")),
    ]

    response = api_client.post("/api/v1/tasks", data={"name": "Filename task"}, files=files)

    assert response.status_code == 201, response.text
    manual = next(item for item in response.json()["files"] if item["category"] == "MANUAL_DOCX")
    assert manual["original_name"] == "manual.docx"


def test_cleanup_failure_remains_detectable(
    api_client: TestClient, tmp_path: Path, monkeypatch
) -> None:
    files = valid_files(tmp_path, with_evidence=False)
    files[2] = ("project", ("project.json", b'{"bad": true}', "application/json"))

    def fail_cleanup(_path):
        raise PermissionError("locked")

    monkeypatch.setattr("app.services.tasks.shutil.rmtree", fail_cleanup)
    response = api_client.post("/api/v1/tasks", data={"name": "Cleanup task"}, files=files)

    assert response.status_code == 500
    assert response.json()["code"] == "FILE_CLEANUP_FAILED"
    task_id = response.json()["details"]["task_id"]
    failed = api_client.get(f"/api/v1/tasks/{task_id}").json()
    assert failed["status"] == "FAILED"
    assert failed["error_code"] == "FILE_CLEANUP_FAILED"
    assert len(failed["files"]) == 3
    settings = api_client.test_settings  # type: ignore[attr-defined]
    assert (settings.tasks_root / task_id).exists()
