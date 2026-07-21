from config.settings import settings


def test_settings_load():
    assert settings.database_path is not None
    assert settings.github_token is not None
    assert settings.llm_api_key is not None
