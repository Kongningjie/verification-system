from sqlalchemy import inspect

from app.core.config import get_settings
from app.db.session import SessionLocal, engine
from app.workflow.task_state import interrupt_active_tasks


def initialize_runtime() -> None:
    """创建本地运行目录；数据库结构由 Alembic 管理。"""
    settings = get_settings()
    settings.data_root.mkdir(parents=True, exist_ok=True)
    settings.tasks_root.mkdir(parents=True, exist_ok=True)
    if inspect(engine).has_table("verification_task"):
        with SessionLocal() as session:
            interrupt_active_tasks(session)
