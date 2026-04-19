from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.scholarship import Scholarship
from app.scrapers.buddy4study import run_buddy4study_scrape
from app.scrapers.dto import ScholarshipIn
from app.scrapers.http_util import RobotsChecker

log = logging.getLogger(__name__)


def _normalize_source_url(url: str) -> str:
    return url.split("#", 1)[0].rstrip("/")


def upsert_scholarships(db: Session, items: list[ScholarshipIn]) -> tuple[int, int]:
    now = datetime.now(timezone.utc)
    inserted = 0
    updated = 0
    for item in items:
        norm_url = _normalize_source_url(item.source_url)
        existing = db.scalar(select(Scholarship).where(Scholarship.source_url == norm_url))
        if existing is None:
            db.add(
                Scholarship(
                    source=item.source,
                    source_url=norm_url,
                    title=item.title,
                    summary=item.summary,
                    eligibility_text=item.eligibility_text,
                    amount=item.amount,
                    deadline=item.deadline,
                    tags=item.tags,
                    raw_payload=item.raw_payload,
                    last_seen_at=now,
                    is_active=True,
                    created_at=now,
                    updated_at=now,
                )
            )
            inserted += 1
        else:
            existing.title = item.title
            existing.summary = item.summary
            existing.eligibility_text = item.eligibility_text
            existing.amount = item.amount
            existing.deadline = item.deadline
            existing.tags = item.tags
            existing.raw_payload = item.raw_payload
            existing.last_seen_at = now
            existing.is_active = True
            existing.updated_at = now
            updated += 1
    return inserted, updated


def run_scrape_job(db: Session) -> dict:
    robots = RobotsChecker()
    errors: list[str] = []
    try:
        items = run_buddy4study_scrape(robots)
    except Exception as exc:  # noqa: BLE001
        log.exception("scrape job failed")
        errors.append(str(exc))
        items = []
    inserted, updated = upsert_scholarships(db, items)
    db.flush()
    log.info(
        "scrape job finished: scraped_items=%s inserted=%s updated=%s errors=%s",
        len(items),
        inserted,
        updated,
        errors,
    )
    return {
        "inserted": inserted,
        "updated": updated,
        "fetched_urls": len(items),
        "errors": errors,
    }


def import_scholarships(db: Session, items: list[ScholarshipIn]) -> int:
    inserted, updated = upsert_scholarships(db, items)
    return inserted + updated
