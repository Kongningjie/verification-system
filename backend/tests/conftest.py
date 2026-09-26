from collections.abc import Generator
from pathlib import Path

import pytest
from app.agents.checklist import FakeChecklistGenerator
from app.agents.execution import FakeEvidenceJudge
from app.api.routes.tasks import (
    checklist_generator_dependency,
    evidence_judge_dependency,
    execution_session_factory_dependency,
)
from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker


@pytest.fixture
def api_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Generator[TestClient, None, None]:
    database_path = tmp_path / "app.db"
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{database_path.as_posix()}",
        data_root=tmp_path / "data",
        max_file_size_bytes=2 * 1024 * 1024,
        max_task_size_bytes=8 * 1024 * 1024,
    )
    engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    testing_session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)

    def override_db() -> Generator[Session, None, None]:
        with testing_session() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_settings] = lambda: settings
    fake_generator = FakeChecklistGenerator()
    app.dependency_overrides[checklist_generator_dependency] = lambda: fake_generator
    fake_judge = FakeEvidenceJudge()
    app.dependency_overrides[evidence_judge_dependency] = lambda: fake_judge
    app.dependency_overrides[execution_session_factory_dependency] = lambda: testing_session
    monkeypatch.setattr("app.main.initialize_runtime", lambda: None)
    with TestClient(app) as client:
        client.test_settings = settings  # type: ignore[attr-defined]
        client.fake_checklist_generator = fake_generator  # type: ignore[attr-defined]
        client.fake_evidence_judge = fake_judge  # type: ignore[attr-defined]
        yield client
    app.dependency_overrides.clear()
    engine.dispose()
