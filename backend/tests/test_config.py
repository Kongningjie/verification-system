from app.core.config import Settings


def test_default_settings_have_safe_local_values() -> None:
    settings = Settings(_env_file=None)
    assert settings.database_url.startswith("sqlite")
    assert settings.model_max_concurrency == 3
    assert settings.openai_api_key is None
