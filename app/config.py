from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite:///./data/app.db"
    data_dir: Path = Path("data")
    resume_dir: Path = Path("data/resumes")
    admin_token: str = "dev-admin-change-me"
    cors_dev: bool = True
    # Periodic scrapes are off by default so the API starts immediately and nothing runs in the background.
    scheduled_scrape_enabled: bool = False
    scrape_interval_minutes: int = 360
    buddy4study_list_url: str = "https://www.buddy4study.com/scholarships"
    http_user_agent: str = "OmnimiseScholarshipBot/0.1 (+https://example.local)"
    # Lower = faster scrapes (be polite on shared/public networks).
    scrape_request_delay_seconds: float = 0.25
    max_scrape_detail_pages: int = 12


settings = Settings()
