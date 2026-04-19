import json
from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class UserCreate(BaseModel):
    """Arbitrary profile fields (education_level, field_of_study, keywords, etc.)."""

    profile: dict[str, Any] = Field(default_factory=dict)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    profile: dict[str, Any]
    resume_extracted: dict[str, Any] | None
    resume_original_name: str | None
    created_at: datetime
    updated_at: datetime


class ScholarshipOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source: str
    source_url: str
    title: str
    summary: str | None
    eligibility_text: str | None
    amount: str | None
    deadline: date | None
    tags: list[Any] | dict[str, Any] | None
    last_seen_at: datetime
    is_active: bool

    @field_validator("tags", mode="before")
    @classmethod
    def coerce_tags(cls, v: Any) -> list[Any] | dict[str, Any] | None:
        if v is None:
            return None
        if isinstance(v, (list, dict)):
            return v
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
            except json.JSONDecodeError:
                return None
            if isinstance(parsed, (list, dict)):
                return parsed
        return None


class ScholarshipList(BaseModel):
    items: list[ScholarshipOut]
    total: int
    skip: int
    limit: int


class MatchReason(BaseModel):
    type: str
    detail: str
    weight: float


class ScholarshipMatch(BaseModel):
    scholarship: ScholarshipOut
    score: float
    reasons: list[MatchReason]


class MatchListOut(BaseModel):
    user_id: UUID
    items: list[ScholarshipMatch]


class ScrapeRunResult(BaseModel):
    inserted: int
    updated: int
    fetched_urls: int
    errors: list[str]


class ImportScholarshipItem(BaseModel):
    source: str = "import"
    source_url: str
    title: str
    summary: str | None = None
    eligibility_text: str | None = None
    amount: str | None = None
    deadline: date | None = None
    tags: list[str] | dict[str, Any] | None = None


class ImportScholarshipsIn(BaseModel):
    items: list[ImportScholarshipItem]


class ImportScholarshipsResult(BaseModel):
    upserted: int
