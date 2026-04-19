from __future__ import annotations

import logging
import time
import urllib.robotparser
from urllib.parse import urljoin, urlparse

import httpx

from app.config import settings

log = logging.getLogger(__name__)


class RobotsChecker:
    def __init__(self) -> None:
        self._cache: dict[str, urllib.robotparser.RobotFileParser] = {}

    def allowed(self, url: str, user_agent: str) -> bool:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return False
        base = f"{parsed.scheme}://{parsed.netloc}"
        robots_url = urljoin(base, "/robots.txt")
        if base not in self._cache:
            rp = urllib.robotparser.RobotFileParser()
            rp.set_url(robots_url)
            try:
                with httpx.Client(
                    headers={"User-Agent": user_agent},
                    timeout=15.0,
                    follow_redirects=True,
                ) as client:
                    r = client.get(robots_url)
                    if r.status_code == 200:
                        rp.parse(r.text.splitlines())
                    else:
                        rp.parse([])
            except Exception as exc:  # noqa: BLE001
                log.warning("robots fetch failed for %s: %s", robots_url, exc)
                rp.parse([])
            self._cache[base] = rp
        rp = self._cache[base]
        try:
            return rp.can_fetch(user_agent, url)
        except Exception:  # noqa: BLE001
            return True


def fetch_text(url: str, delay_seconds: float | None = None) -> str:
    ua = settings.http_user_agent
    delay = (
        settings.scrape_request_delay_seconds if delay_seconds is None else delay_seconds
    )
    time.sleep(delay)
    with httpx.Client(
        headers={"User-Agent": ua},
        timeout=30.0,
        follow_redirects=True,
    ) as client:
        r = client.get(url)
        r.raise_for_status()
        return r.text
