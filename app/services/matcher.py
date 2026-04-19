from datetime import date, datetime, timezone
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.scholarship import Scholarship
from app.models.user import User
from app.schemas import MatchReason, ScholarshipMatch, ScholarshipOut


def _profile_to_dict(profile: dict[str, Any]) -> dict[str, Any]:
    return profile


def _tokens(text: str) -> set[str]:
    text = text.lower()
    return set(re.findall(r"[a-z0-9]{3,}", text))


def _scholarship_blob(s: Scholarship) -> str:
    parts = [s.title or "", s.summary or "", s.eligibility_text or ""]
    if isinstance(s.tags, list):
        parts.append(" ".join(str(x) for x in s.tags))
    elif isinstance(s.tags, dict):
        parts.append(" ".join(f"{k}:{v}" for k, v in s.tags.items()))
    return "\n".join(parts)


def _user_blob(user: User) -> tuple[str, dict[str, Any]]:
    profile = _profile_to_dict(user.profile or {})
    resume = user.resume_extracted or {}
    kw = resume.get("keywords") or []
    if isinstance(kw, str):
        kw = [kw]
    parts = [
        str(profile.get("education_level") or ""),
        str(profile.get("field_of_study") or ""),
        str(profile.get("state") or ""),
        str(profile.get("gender") or ""),
        str(profile.get("category") or ""),
        str(profile.get("annual_income_band") or ""),
        " ".join(str(k) for k in profile.get("keywords") or []),
        " ".join(str(k) for k in kw),
    ]
    return "\n".join(parts), profile


def _deadline_passed(s: Scholarship, today: date) -> bool:
    if s.deadline is None:
        return False
    return s.deadline < today


def match_scholarships_for_user(
    db: Session,
    user_id: str,
    limit: int = 50,
) -> tuple[str, list[ScholarshipMatch]]:
    user = db.get(User, user_id)
    if user is None:
        raise KeyError("user not found")

    today = datetime.now(timezone.utc).date()
    stmt = select(Scholarship).where(Scholarship.is_active.is_(True))
    scholarships = list(db.scalars(stmt).all())

    user_text, profile = _user_blob(user)
    user_tokens = _tokens(user_text)
    fos = (profile.get("field_of_study") or "").lower()
    explicit_keywords = [str(k).lower() for k in (profile.get("keywords") or [])]

    results: list[ScholarshipMatch] = []
    for s in scholarships:
        reasons: list[MatchReason] = []
        if _deadline_passed(s, today):
            reasons.append(
                MatchReason(type="filtered", detail="deadline_passed", weight=0.0)
            )
            continue

        blob = _scholarship_blob(s)
        blob_l = blob.lower()
        sch_tokens = _tokens(blob)
        overlap = user_tokens & sch_tokens
        score = float(len(overlap)) * 3.0
        for t in overlap:
            reasons.append(MatchReason(type="keyword", detail=t, weight=3.0))

        if fos and fos in blob_l:
            score += 12.0
            reasons.append(MatchReason(type="field", detail="field_of_study", weight=12.0))

        for kw in explicit_keywords:
            if kw and kw in blob_l:
                score += 8.0
                reasons.append(MatchReason(type="keyword", detail=f"profile:{kw}", weight=8.0))

        if isinstance(s.tags, list):
            for tag in s.tags:
                tl = str(tag).lower()
                if tl in user_tokens or tl in fos:
                    score += 5.0
                    reasons.append(MatchReason(type="tag", detail=str(tag), weight=5.0))

        if score <= 0 and not reasons:
            reasons.append(MatchReason(type="baseline", detail="listed", weight=0.5))
            score = 0.5

        so = ScholarshipOut.model_validate(s)
        results.append(ScholarshipMatch(scholarship=so, score=score, reasons=reasons))

    results.sort(key=lambda m: m.score, reverse=True)
    return user.id, results[:limit]


def normalize_user_profile_input(profile: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in profile.items():
        if v is None or v == "":
            continue
        out[k] = v
    return out
