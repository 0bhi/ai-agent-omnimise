from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass
class ScholarshipIn:
    source: str
    source_url: str
    title: str
    summary: str | None
    eligibility_text: str | None
    amount: str | None
    deadline: date | None
    tags: list[str] | dict[str, Any] | None
    raw_payload: dict[str, Any] | None
