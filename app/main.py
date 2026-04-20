from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.logging_config import setup_logging
from app.routers import admin, scholarships, users

setup_logging()
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler: BackgroundScheduler | None = None
    if settings.scheduled_scrape_enabled:
        scheduler = BackgroundScheduler()

        def scheduled_scrape() -> None:
            from app.db import SessionLocal
            from app.services.scrape_service import run_scrape_job

            db = SessionLocal()
            try:
                run_scrape_job(db)
                db.commit()
            except Exception:
                db.rollback()
                log.exception("Scheduled scrape failed")
            finally:
                db.close()

        interval = max(settings.scrape_interval_minutes, 5)
        scheduler.add_job(
            scheduled_scrape,
            "interval",
            minutes=interval,
            id="scholarship_scrape",
            replace_existing=True,
        )
        scheduler.start()
        log.info("APScheduler started: scrape every %s minutes", interval)
    else:
        log.info("APScheduler disabled (set SCHEDULED_SCRAPE_ENABLED=true to enable)")
    yield
    if scheduler is not None:
        scheduler.shutdown(wait=False)
        log.info("APScheduler stopped")


app = FastAPI(title="Scholarship Agent API", lifespan=lifespan)

allow_origins = set(settings.cors_origin_list())
allow_origin_regex: str | None = None
if settings.cors_dev:
    allow_origins.update(
        {
            "http://localhost",
            "http://127.0.0.1",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        }
    )
    allow_origin_regex = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"

if allow_origins or allow_origin_regex:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=sorted(allow_origins),
        allow_origin_regex=allow_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(users.router)
app.include_router(scholarships.router)
app.include_router(admin.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
