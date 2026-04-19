import uuid
from datetime import datetime

from sqlalchemy import DateTime, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    profile: Mapped[dict] = mapped_column(JSON, default=dict)
    resume_extracted: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    resume_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    resume_original_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    resume_text_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
