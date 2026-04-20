from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Turso only: libsql://... from the Turso dashboard (env: DATABASE_URL)
    database_url: str
    # Turso database auth token (env: TURSO_AUTH_TOKEN)
    turso_auth_token: str | None = None

    admin_token: str = "dev-admin-change-me"
    cors_dev: bool = True
    scheduled_scrape_enabled: bool = False
    scrape_interval_minutes: int = 360
    buddy4study_list_url: str = "https://www.buddy4study.com/scholarships"
    http_user_agent: str = "OmnimiseScholarshipBot/0.1 (+https://example.local)"
    scrape_request_delay_seconds: float = 0.25
    max_scrape_detail_pages: int = 12
    llm_api_base: str = "https://api.groq.com/openai/v1"
    llm_api_key: str | None = None
    llm_chat_model: str = "llama-3.3-70b-versatile"
    gemini_api_key: str | None = None
    gemini_embedding_model: str = "text-embedding-004"
    llm_embedding_model: str = "text-embedding-3-small"
    match_retrieval_k: int = 60
    match_llm_top_k: int = 20

    @field_validator("database_url")
    @classmethod
    def strip_database_url(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("DATABASE_URL is required")
        return v

    @model_validator(mode="after")
    def require_turso(self) -> "Settings":
        if not self.database_url.startswith("libsql://"):
            raise ValueError("DATABASE_URL must be a Turso libsql:// URL")
        token = (self.turso_auth_token or "").strip()
        if not token:
            raise ValueError("TURSO_AUTH_TOKEN is required for Turso")
        self.turso_auth_token = token
        return self

    def sqlalchemy_database_url(self) -> str:
        return f"sqlite+{self.database_url}?secure=true"

    def sqlalchemy_connect_args(self) -> dict:
        return {"auth_token": self.turso_auth_token}


settings = Settings()
