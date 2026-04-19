from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import require_admin
from app.scrapers.dto import ScholarshipIn
from app.schemas import (
    ImportScholarshipsIn,
    ImportScholarshipsResult,
    ScrapeRunResult,
)
from app.services.scrape_service import import_scholarships, run_scrape_job

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/scrape/run", response_model=ScrapeRunResult, dependencies=[Depends(require_admin)])
def trigger_scrape(db: Session = Depends(get_db)) -> ScrapeRunResult:
    result = run_scrape_job(db)
    db.commit()
    return ScrapeRunResult(**result)


@router.post(
    "/scholarships/import",
    response_model=ImportScholarshipsResult,
    dependencies=[Depends(require_admin)],
)
def import_json(payload: ImportScholarshipsIn, db: Session = Depends(get_db)) -> ImportScholarshipsResult:
    items = [
        ScholarshipIn(
            source=i.source,
            source_url=i.source_url,
            title=i.title,
            summary=i.summary,
            eligibility_text=i.eligibility_text,
            amount=i.amount,
            deadline=i.deadline,
            tags=i.tags,
            raw_payload={"import": True},
        )
        for i in payload.items
    ]
    n = import_scholarships(db, items)
    db.commit()
    return ImportScholarshipsResult(upserted=n)
