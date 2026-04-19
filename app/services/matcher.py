from datetime import date, datetime, timezone
import json
import math
import re
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
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


def _state_aliases() -> dict[str, str]:
    return {
        "andhra pradesh": "andhra pradesh",
        "ap": "andhra pradesh",
        "bihar": "bihar",
        "gujarat": "gujarat",
        "karnataka": "karnataka",
        "ka": "karnataka",
        "madhya pradesh": "madhya pradesh",
        "mp": "madhya pradesh",
        "maharashtra": "maharashtra",
        "mh": "maharashtra",
        "odisha": "odisha",
        "orissa": "odisha",
        "rajasthan": "rajasthan",
        "tamil nadu": "tamil nadu",
        "tn": "tamil nadu",
        "uttar pradesh": "uttar pradesh",
        "up": "uttar pradesh",
        "west bengal": "west bengal",
        "wb": "west bengal",
        "delhi": "delhi",
    }


def _extract_state_from_scholarship(s: Scholarship) -> str | None:
    text = " ".join(
        [
            s.title or "",
            s.summary or "",
            s.eligibility_text or "",
        ]
    ).lower()
    for key, canonical in _state_aliases().items():
        if key in text:
            return canonical
    return None


def _normalize_state(value: str | None) -> str | None:
    if not value:
        return None
    key = value.strip().lower()
    return _state_aliases().get(key, key)


def _passes_hard_filters(s: Scholarship, profile: dict[str, Any], today: date) -> tuple[bool, list[MatchReason]]:
    reasons: list[MatchReason] = []
    if _deadline_passed(s, today):
        reasons.append(MatchReason(type="filtered", detail="deadline_passed", weight=0.0))
        return False, reasons

    user_state = _normalize_state(str(profile.get("state") or ""))
    sch_state = _extract_state_from_scholarship(s)
    if user_state and sch_state and user_state != sch_state:
        reasons.append(
            MatchReason(
                type="filtered",
                detail=f"state_mismatch:user={user_state};scholarship={sch_state}",
                weight=0.0,
            )
        )
        return False, reasons

    return True, reasons


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _normalize_similarity(score: float) -> float:
    # cosine in [-1, 1] -> [0, 1]
    return max(0.0, min(1.0, (score + 1.0) / 2.0))


def _deadline_urgency_score(s: Scholarship, today: date) -> float:
    if s.deadline is None:
        return 0.35
    days = (s.deadline - today).days
    if days < 0:
        return 0.0
    if days <= 14:
        return 1.0
    if days <= 30:
        return 0.85
    if days <= 60:
        return 0.65
    if days <= 120:
        return 0.45
    return 0.25


def _user_behavior_score(_user: User) -> float:
    # Placeholder until interaction telemetry is available.
    return 0.5


def _build_llm_prompt(user: User, profile: dict[str, Any], candidates: list[tuple[Scholarship, float]]) -> str:
    profile_json = json.dumps(profile, ensure_ascii=True)
    resume_json = json.dumps(user.resume_extracted or {}, ensure_ascii=True)
    candidate_rows: list[dict[str, Any]] = []
    for s, sim in candidates:
        candidate_rows.append(
            {
                "id": s.id,
                "title": s.title,
                "summary": s.summary,
                "eligibility_text": s.eligibility_text,
                "amount": s.amount,
                "deadline": s.deadline.isoformat() if s.deadline else None,
                "tags": s.tags,
                "semantic_similarity": round(sim, 6),
            }
        )
    candidates_json = json.dumps(candidate_rows, ensure_ascii=True)
    return (
        "You are a strict scholarship ranking assistant.\n"
        "Task: For each candidate scholarship, score two dimensions in [0,1]:\n"
        "1) eligibility_score: how likely user is eligible from explicit evidence only.\n"
        "2) field_fit_score: how well scholarship aligns with user academics/interests.\n"
        "Rules:\n"
        "- Be conservative. If evidence is missing, lower score.\n"
        "- If clearly ineligible, set eligibility_score <= 0.2 and rejected=true.\n"
        "- Provide 1-3 concise reasons grounded in the candidate text.\n"
        "- Output strict JSON only, matching schema.\n\n"
        f"USER_PROFILE_JSON={profile_json}\n"
        f"USER_RESUME_JSON={resume_json}\n"
        f"CANDIDATES_JSON={candidates_json}\n"
    )


def _gemini_model_path(model_id: str) -> str:
    mid = model_id.strip()
    if mid.startswith("models/"):
        return mid
    return f"models/{mid}"


def _call_gemini_embeddings(texts: list[str]) -> list[list[float]] | None:
    if not settings.gemini_api_key or not texts:
        return None
    model_path = _gemini_model_path(settings.gemini_embedding_model)
    url = (
        "https://generativelanguage.googleapis.com/v1beta/"
        f"{model_path}:batchEmbedContents?key={settings.gemini_api_key}"
    )
    chunk_size = 64
    all_vectors: list[list[float]] = []
    try:
        with httpx.Client(timeout=90.0) as client:
            for i in range(0, len(texts), chunk_size):
                chunk = texts[i : i + chunk_size]
                requests_body = [
                    {
                        "model": model_path,
                        "content": {"parts": [{"text": t[:8000]}]},
                    }
                    for t in chunk
                ]
                res = client.post(url, json={"requests": requests_body})
                res.raise_for_status()
                data = res.json()
                embs = data.get("embeddings") or []
                if len(embs) != len(chunk):
                    return None
                for emb in embs:
                    vec = emb.get("values")
                    if not isinstance(vec, list):
                        return None
                    all_vectors.append(vec)
        if len(all_vectors) != len(texts):
            return None
        return all_vectors
    except Exception:
        return None


def _call_openai_compatible_embeddings(texts: list[str]) -> list[list[float]] | None:
    if not settings.llm_api_key or not texts:
        return None
    base = settings.llm_api_base.rstrip("/")
    url = f"{base}/embeddings"
    headers = {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.llm_embedding_model,
        "input": texts,
    }
    try:
        with httpx.Client(timeout=45.0) as client:
            res = client.post(url, headers=headers, json=payload)
            res.raise_for_status()
            data = res.json()
        rows = data.get("data") or []
        vectors = [row.get("embedding") for row in rows if isinstance(row.get("embedding"), list)]
        if len(vectors) != len(texts):
            return None
        return vectors
    except Exception:
        return None


def _call_embeddings(texts: list[str]) -> list[list[float]] | None:
    if not texts:
        return None
    if settings.gemini_api_key:
        return _call_gemini_embeddings(texts)
    return _call_openai_compatible_embeddings(texts)


def _call_llm_rerank(user: User, profile: dict[str, Any], candidates: list[tuple[Scholarship, float]]) -> dict[str, Any] | None:
    if not settings.llm_api_key or not candidates:
        return None
    base = settings.llm_api_base.rstrip("/")
    url = f"{base}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
    }
    prompt = _build_llm_prompt(user, profile, candidates)
    schema = {
        "name": "scholarship_rerank",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "eligibility_score": {"type": "number"},
                            "field_fit_score": {"type": "number"},
                            "rejected": {"type": "boolean"},
                            "reasons": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                        "required": ["id", "eligibility_score", "field_fit_score", "rejected", "reasons"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["items"],
            "additionalProperties": False,
        },
    }
    base_l = settings.llm_api_base.lower()
    use_groq = "groq.com" in base_l
    system_msg = (
        "Return only a single JSON object with key \"items\" (array). "
        "Each element must have: id, eligibility_score, field_fit_score, rejected, reasons. "
        "No markdown, no prose."
    )
    if use_groq:
        response_format: dict[str, Any] = {"type": "json_object"}
    else:
        response_format = {"type": "json_schema", "json_schema": schema}
    payload: dict[str, Any] = {
        "model": settings.llm_chat_model,
        "temperature": 0.1,
        "response_format": response_format,
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": prompt},
        ],
    }
    try:
        with httpx.Client(timeout=60.0) as client:
            res = client.post(url, headers=headers, json=payload)
            res.raise_for_status()
            data = res.json()
        content = data["choices"][0]["message"]["content"]
        if not isinstance(content, str):
            return None
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            return None
        return parsed
    except Exception:
        return None


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

    filtered_pool: list[Scholarship] = []
    for s in scholarships:
        ok, _ = _passes_hard_filters(s, profile, today)
        if ok:
            filtered_pool.append(s)

    # Stage 1: embeddings-based retrieval (fallback to lexical overlap if embeddings unavailable).
    retrieval_k = max(limit, settings.match_retrieval_k)
    retrieved: list[tuple[Scholarship, float]] = []
    user_embedding: list[float] | None = None

    scholarship_blobs = [_scholarship_blob(s) for s in filtered_pool]
    vectors = _call_embeddings([user_text, *scholarship_blobs]) if filtered_pool else None
    if vectors and len(vectors) == len(filtered_pool) + 1:
        user_embedding = vectors[0]
        for s, vec in zip(filtered_pool, vectors[1:]):
            sim = _normalize_similarity(_cosine_similarity(user_embedding, vec))
            retrieved.append((s, sim))
    else:
        for s in filtered_pool:
            blob = _scholarship_blob(s)
            overlap = user_tokens & _tokens(blob)
            approx = min(1.0, len(overlap) / 25.0)
            retrieved.append((s, approx))
    retrieved.sort(key=lambda x: x[1], reverse=True)
    retrieved = retrieved[:retrieval_k]

    # Stage 2: LLM rerank on top-K with strict JSON.
    llm_top_k = min(len(retrieved), max(limit, settings.match_llm_top_k))
    rerank_input = retrieved[:llm_top_k]
    llm_result = _call_llm_rerank(user, profile, rerank_input)
    by_id: dict[str, dict[str, Any]] = {}
    if isinstance(llm_result, dict):
        items = llm_result.get("items")
        if isinstance(items, list):
            for row in items:
                if isinstance(row, dict) and isinstance(row.get("id"), str):
                    by_id[row["id"]] = row

    behavior_score = _user_behavior_score(user)
    results: list[ScholarshipMatch] = []
    for s, semantic_similarity in retrieved:
        blob_l = _scholarship_blob(s).lower()
        item = by_id.get(s.id, {})
        eligibility = float(item.get("eligibility_score", 0.0)) if isinstance(item, dict) else 0.0
        field_fit = float(item.get("field_fit_score", 0.0)) if isinstance(item, dict) else 0.0
        rejected = bool(item.get("rejected")) if isinstance(item, dict) else False
        deadline_urgency = _deadline_urgency_score(s, today)

        if not by_id:
            # Fallback calibration if LLM is unavailable.
            if fos and fos in blob_l:
                field_fit = max(field_fit, 0.8)
            kw_hits = sum(1 for kw in explicit_keywords if kw and kw in blob_l)
            eligibility = max(eligibility, min(1.0, 0.3 + (0.15 * kw_hits)))
        eligibility = max(0.0, min(1.0, eligibility))
        field_fit = max(0.0, min(1.0, field_fit))
        semantic_similarity = max(0.0, min(1.0, semantic_similarity))

        final_score = (
            (0.35 * eligibility)
            + (0.30 * field_fit)
            + (0.20 * semantic_similarity)
            + (0.10 * deadline_urgency)
            + (0.05 * behavior_score)
        )
        if rejected:
            final_score *= 0.5

        reason_rows: list[MatchReason] = [
            MatchReason(type="component", detail="eligibility", weight=round(eligibility, 4)),
            MatchReason(type="component", detail="field_fit", weight=round(field_fit, 4)),
            MatchReason(type="component", detail="semantic_similarity", weight=round(semantic_similarity, 4)),
            MatchReason(type="component", detail="deadline_urgency", weight=round(deadline_urgency, 4)),
            MatchReason(type="component", detail="user_behavior", weight=round(behavior_score, 4)),
        ]
        if rejected:
            reason_rows.append(MatchReason(type="penalty", detail="llm_rejected", weight=0.5))
        if isinstance(item, dict):
            rr = item.get("reasons")
            if isinstance(rr, list):
                for txt in rr[:3]:
                    if isinstance(txt, str) and txt.strip():
                        reason_rows.append(MatchReason(type="llm_reason", detail=txt[:240], weight=1.0))

        so = ScholarshipOut.model_validate(s)
        results.append(ScholarshipMatch(scholarship=so, score=round(final_score * 100.0, 4), reasons=reason_rows))

    results.sort(key=lambda m: m.score, reverse=True)
    return user.id, results[:limit]


def normalize_user_profile_input(profile: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in profile.items():
        if v is None or v == "":
            continue
        out[k] = v
    return out
