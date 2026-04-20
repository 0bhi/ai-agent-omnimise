import tempfile
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.user import User
from app.schemas import UserCreate, UserOut
from app.services.matcher import match_scholarships_for_user, normalize_user_profile_input
from app.services.resume_parser import build_resume_extracted
from app.schemas import MatchListOut

router = APIRouter(prefix="/users", tags=["users"])


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, db: Session = Depends(get_db)) -> User:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    profile = normalize_user_profile_input(payload.profile)
    user = User(profile=profile, created_at=now, updated_at=now)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/{user_id}/resume", response_model=UserOut)
async def upload_resume(
    user_id: UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> User:
    from datetime import datetime, timezone

    user = db.get(User, str(user_id))
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    suffix = (file.filename or "").rsplit(".", 1)[-1].lower()
    if suffix not in {"pdf", "docx"}:
        raise HTTPException(status_code=400, detail="Only PDF or DOCX files are supported")

    data = await file.read()
    with tempfile.NamedTemporaryFile(delete=False, suffix=f".{suffix}") as tmp:
        tmp.write(data)
        tmp_path = tmp.name
    path = Path(tmp_path)
    try:
        extracted, preview = build_resume_extracted(path)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Could not parse resume: {exc}") from exc
    finally:
        path.unlink(missing_ok=True)

    now = datetime.now(timezone.utc)
    user.resume_path = None
    user.resume_original_name = file.filename
    user.resume_extracted = extracted
    user.resume_text_preview = preview
    user.updated_at = now
    db.commit()
    db.refresh(user)
    return user


@router.get("/{user_id}/matches", response_model=MatchListOut)
def get_matches(user_id: UUID, limit: int = 50, db: Session = Depends(get_db)) -> MatchListOut:
    try:
        uid, items = match_scholarships_for_user(db, str(user_id), limit=limit)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="User not found") from exc
    return MatchListOut(user_id=UUID(uid), items=items)
