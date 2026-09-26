from app.core.config import get_settings


def initialize_runtime() -> None:
    """创建本地运行目录；数据库结构由 Alembic 管理。"""
    settings = get_settings()
    settings.data_root.mkdir(parents=True, exist_ok=True)
    settings.tasks_root.mkdir(parents=True, exist_ok=True)
