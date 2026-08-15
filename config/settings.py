from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    github_token: str
    llm_api_key: str
    llm_model: str = "gpt-4o-mini"
    llm_base_url: str = "https://openrouter.ai/api/v1"
    database_path: Path = Path("./data/triage.db")
    poll_interval_seconds: int = 1800
    issue_discovery_window_minutes: int = 10080
    max_issue_comments: int = 3
    max_file_bytes: int = 20000
    api_host: str = "127.0.0.1"
    api_port: int = 8090
    min_repo_stars: int = 1000
    github_webhook_secret: str = ""
    search_per_page: int = 100
    search_max_pages: int = 3
    search_lookback_minutes: int = 10080


settings = Settings()
