from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # PostgreSQL URL from Neon, Render Postgres, etc. (env: DATABASE_URL)
    # Use postgresql://... or postgres://... — psycopg is selected automatically.
    database_url: str

    admin_token: str = "dev-admin-change-me"
    cors_dev: bool = True
    cors_origins: str = ""
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
    def require_postgres_url(self) -> "Settings":
        head = self.database_url.split("://", 1)[0].lower()
        allowed = {"postgresql", "postgres", "postgresql+psycopg", "postgresql+psycopg2"}
        if head not in allowed:
            raise ValueError(
                "DATABASE_URL must be a PostgreSQL URL (e.g. Neon: postgresql://user:pass@host/db?sslmode=require)",
            )
        return self

    def sqlalchemy_database_url(self) -> str:
        u = self.database_url
        if u.startswith("postgresql+psycopg://") or u.startswith("postgresql+psycopg2://"):
            return u
        if u.startswith("postgresql://"):
            return "postgresql+psycopg://" + u[len("postgresql://") :]
        if u.startswith("postgres://"):
            return "postgresql+psycopg://" + u[len("postgres://") :]
        return u

    def sqlalchemy_connect_args(self) -> dict:
        return {}

    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
