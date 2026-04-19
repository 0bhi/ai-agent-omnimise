from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite:///./data/app.db"
    # Required for remote Turso when DATABASE_URL is libsql://...
    turso_auth_token: str | None = None
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
    # Chat (OpenAI-compatible): default Groq. Set LLM_API_KEY to your Groq key.
    llm_api_base: str = "https://api.groq.com/openai/v1"
    llm_api_key: str | None = None
    llm_chat_model: str = "llama-3.3-70b-versatile"
    # Embeddings: use Gemini when GEMINI_API_KEY is set; otherwise optional OpenAI-style embeddings.
    gemini_api_key: str | None = None
    gemini_embedding_model: str = "text-embedding-004"
    llm_embedding_model: str = "text-embedding-3-small"
    match_retrieval_k: int = 60
    match_llm_top_k: int = 20

    def sqlalchemy_database_url(self) -> str:
        """SQLAlchemy URL (Turso libsql:// becomes sqlite+libsql:// per Turso docs)."""
        if self.database_url.startswith("libsql://"):
            return f"sqlite+{self.database_url}?secure=true"
        return self.database_url

    def sqlalchemy_connect_args(self) -> dict:
        if self.database_url.startswith("libsql://"):
            args: dict = {}
            if self.turso_auth_token:
                args["auth_token"] = self.turso_auth_token
            return args
        if self.database_url.startswith("sqlite"):
            return {"check_same_thread": False}
        return {}


settings = Settings()
