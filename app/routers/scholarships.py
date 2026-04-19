from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.scholarship import Scholarship
from app.schemas import ScholarshipList, ScholarshipOut

router = APIRouter(prefix="/scholarships", tags=["scholarships"])


@router.get("", response_model=ScholarshipList)
def list_scholarships(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    tag: str | None = None,
    db: Session = Depends(get_db),
) -> ScholarshipList:
    base = select(Scholarship).where(Scholarship.is_active.is_(True))
    count_stmt = select(func.count()).select_from(Scholarship).where(Scholarship.is_active.is_(True))
    if tag:
        like = f"%{tag}%"
        base = base.where(
            or_(
                Scholarship.title.ilike(like),
                Scholarship.summary.ilike(like),
                Scholarship.eligibility_text.ilike(like),
            )
        )
        count_stmt = select(func.count()).select_from(Scholarship).where(
            Scholarship.is_active.is_(True),
            or_(
                Scholarship.title.ilike(like),
                Scholarship.summary.ilike(like),
                Scholarship.eligibility_text.ilike(like),
            ),
        )
    total = int(db.scalar(count_stmt) or 0)
    rows = db.scalars(base.order_by(Scholarship.last_seen_at.desc()).offset(skip).limit(limit)).all()
    items = [ScholarshipOut.model_validate(r) for r in rows]
    return ScholarshipList(items=items, total=total, skip=skip, limit=limit)
