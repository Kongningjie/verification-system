from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test_alembic_upgrade_and_downgrade_from_empty_database(tmp_path: Path) -> None:
    database_path = tmp_path / "migration.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    config = Config("alembic.ini")
    config.attributes["database_url"] = database_url

    command.upgrade(config, "head")

    engine = create_engine(database_url)
    tables = set(inspect(engine).get_table_names())
    assert {
        "verification_task",
        "task_file",
        "document_block",
        "template_comment",
        "document_asset",
        "parse_warning",
        "project_metadata",
    } <= tables
    task_columns = {column["name"] for column in inspect(engine).get_columns("verification_task")}
    assert {"schema_version", "warning_count", "error_code", "error_message"} <= task_columns
    engine.dispose()

    command.downgrade(config, "base")

    engine = create_engine(database_url)
    assert set(inspect(engine).get_table_names()) == {"alembic_version"}
    engine.dispose()
