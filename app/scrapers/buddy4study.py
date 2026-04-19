from __future__ import annotations

import json
import logging
import re
from datetime import date
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup
from dateutil import parser as date_parser

from app.config import settings
from app.scrapers.dto import ScholarshipIn
from app.scrapers.http_util import RobotsChecker, fetch_text

log = logging.getLogger(__name__)

MAX_LIST_URLS = 20


def _absolute_url(base: str, href: str) -> str:
    return urljoin(base, href).split("#")[0].rstrip("/")


def _same_site(url: str, candidate: str) -> bool:
    try:
        a = urlparse(url).netloc.lower()
        b = urlparse(candidate).netloc.lower()
        return bool(a and a == b)
    except Exception:  # noqa: BLE001
        return False


def discover_listing_urls(list_html: str, list_url: str) -> list[str]:
    soup = BeautifulSoup(list_html, "html.parser")
    found: list[str] = []
    for a in soup.find_all("a", href=True):
        full = _absolute_url(list_url, a["href"])
        if not _same_site(list_url, full):
            continue
        low = full.lower()
        if "scholarship" not in low:
            continue
        path = urlparse(full).path.rstrip("/").lower()
        if path.endswith("/scholarships") or path == "/scholarships":
            continue
        if any(x in low for x in (".pdf", ".jpg", ".png", ".jpeg", "/login", "/register")):
            continue
        found.append(full)
    seen: set[str] = set()
    out: list[str] = []
    for u in found:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def discover_listing_card_urls(list_html: str, list_url: str) -> list[str]:
    soup = BeautifulSoup(list_html, "html.parser")
    found: list[str] = []
    for a in soup.find_all("a", href=True):
        classes = " ".join(a.get("class", []))
        if "Listing_categoriesBox" not in classes:
            continue
        full = _absolute_url(list_url, a["href"])
        if not _same_site(list_url, full):
            continue
        low = full.lower()
        if any(x in low for x in (".pdf", ".jpg", ".png", ".jpeg", "/login", "/register")):
            continue
        found.append(full)
    return list(dict.fromkeys(found))


def _is_acceptable_detail_url(full: str) -> bool:
    try:
        parsed = urlparse(full)
    except Exception:  # noqa: BLE001
        return False
    host = (parsed.netloc or "").lower()
    if "buddy4study.com" not in host:
        return False
    path = (parsed.path or "").rstrip("/").lower()
    if not path or path == "/":
        return False
    low = full.lower()
    if any(x in low for x in (".pdf", ".jpg", ".png", ".jpeg", "/login", "/register")):
        return False
    segments = [s for s in path.split("/") if s]
    if not segments:
        return False
    if segments in (["scholarships"], ["scholarship"]):
        return False
    if path.startswith("/scholarships/"):
        return False
    if len(segments) == 2 and segments[-1] == "scholarships":
        return False
    return True


def _normalize_candidate_url(raw: str, list_url: str) -> str | None:
    u = raw.strip().strip('"').strip("'").rstrip(",;\\")
    if not u or len(u) > 2048:
        return None
    if u.startswith("//"):
        u = "https:" + u
    elif u.startswith("/"):
        u = urljoin(list_url, u)
    elif not u.startswith("http"):
        return None
    parsed = urlparse(u)
    clean = urlunparse(
        (parsed.scheme, parsed.netloc, parsed.path, "", parsed.query, "")
    ).rstrip("/")
    return clean or None


def _walk_json_for_url_strings(obj: Any, sink: set[str]) -> None:
    if isinstance(obj, str):
        if "buddy4study" not in obj.lower() and "/scholarship" not in obj.lower():
            return
        for m in re.finditer(r"https?://[^\s\"'<>\\]+", obj):
            sink.add(m.group(0).rstrip(",;)}]\\"))
        for m in re.finditer(r"(/scholarships?/[\w\-./%]+)", obj, re.I):
            sink.add(m.group(1))
    elif isinstance(obj, dict):
        for v in obj.values():
            _walk_json_for_url_strings(v, sink)
    elif isinstance(obj, list):
        for v in obj:
            _walk_json_for_url_strings(v, sink)


def _urls_from_next_data(html: str) -> set[str]:
    found: set[str] = set()
    m = re.search(
        r'<script[^>]*\bid=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
        html,
        re.I | re.DOTALL,
    )
    if not m:
        return found
    raw = m.group(1).strip()
    if not raw:
        return found
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        log.debug("__NEXT_DATA__ JSON parse failed")
        return found
    _walk_json_for_url_strings(data, found)
    return found


def _urls_from_raw_html_strings(html: str) -> set[str]:
    found: set[str] = set()
    for m in re.finditer(r'["\'](/scholarships/[^"\'>\s]+)["\']', html, re.I):
        found.add(m.group(1))
    for m in re.finditer(
        r'https?://(?:www\.)?buddy4study\.com/(?:scholarship|page)/[a-zA-Z0-9][a-zA-Z0-9\-._~/%#?=&]*',
        html,
        re.I,
    ):
        found.add(m.group(0))
    for m in re.finditer(r'["\'](/scholarships?/[^"\'>\s]+)["\']', html, re.I):
        found.add(m.group(1))
    for m in re.finditer(r'["\'](/page/[^"\'>\s]*scholarship[^"\'>\s]*)["\']', html, re.I):
        found.add(m.group(1))
    return found


def _urls_from_json_script_tags(html: str) -> set[str]:
    found: set[str] = set()
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all("script"):
        t = (tag.get("type") or "").lower()
        if "json" not in t and tag.get("id") != "__NEXT_DATA__":
            continue
        raw = tag.string or tag.get_text() or ""
        if "scholarship" not in raw.lower() and "buddy4study" not in raw.lower():
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        _walk_json_for_url_strings(data, found)
    return found


def collect_scholarship_detail_urls(html: str, list_url: str) -> list[str]:
    """Collect detail page URLs from anchors, Next.js __NEXT_DATA__, and raw HTML strings."""
    cap = max(1, settings.max_scrape_detail_pages)
    candidates: set[str] = set()

    for u in discover_listing_urls(html, list_url):
        nu = _normalize_candidate_url(u, list_url)
        if nu:
            candidates.add(nu)

    for u in discover_listing_card_urls(html, list_url):
        nu = _normalize_candidate_url(u, list_url)
        if nu:
            candidates.add(nu)

    for raw in (
        _urls_from_next_data(html)
        | _urls_from_raw_html_strings(html)
        | _urls_from_json_script_tags(html)
    ):
        nu = _normalize_candidate_url(raw, list_url)
        if nu:
            candidates.add(nu)

    ordered: list[str] = []
    seen: set[str] = set()
    for u in sorted(candidates):
        if u in seen:
            continue
        if not _is_acceptable_detail_url(u):
            continue
        seen.add(u)
        ordered.append(u)
    return ordered[:cap]


def collect_listing_urls(html: str, list_url: str) -> list[str]:
    candidates: set[str] = set()
    for u in discover_listing_urls(html, list_url):
        nu = _normalize_candidate_url(u, list_url)
        if nu:
            candidates.add(nu)
    for raw in (
        _urls_from_next_data(html)
        | _urls_from_raw_html_strings(html)
        | _urls_from_json_script_tags(html)
    ):
        nu = _normalize_candidate_url(raw, list_url)
        if nu:
            candidates.add(nu)

    out: list[str] = []
    for u in sorted(candidates):
        path = urlparse(u).path.lower().rstrip("/")
        if not path.startswith("/scholarships/"):
            continue
        if u not in out:
            out.append(u)
    return out


def _urls_from_sitemap_xml(xml_text: str) -> list[str]:
    soup = BeautifulSoup(xml_text, "xml")
    out: list[str] = []
    for loc in soup.find_all("loc"):
        text = (loc.get_text() or "").strip()
        if text:
            out.append(text)
    return out


def collect_detail_urls_from_sitemaps(robots: RobotsChecker, ua: str) -> list[str]:
    cap = max(1, settings.max_scrape_detail_pages)
    sitemap_index_url = "https://www.buddy4study.com/sitemap.xml"
    if not robots.allowed(sitemap_index_url, ua):
        return []

    try:
        index_xml = fetch_text(sitemap_index_url)
    except Exception as exc:  # noqa: BLE001
        log.warning("sitemap index fetch failed %s: %s", sitemap_index_url, exc)
        return []

    sitemap_urls = _urls_from_sitemap_xml(index_xml)
    if not sitemap_urls:
        return []

    collected: list[str] = []
    seen: set[str] = set()
    for sm_url in sitemap_urls:
        if len(collected) >= cap:
            break
        if not _same_site(sitemap_index_url, sm_url):
            continue
        if not robots.allowed(sm_url, ua):
            continue
        try:
            sm_xml = fetch_text(sm_url)
        except Exception as exc:  # noqa: BLE001
            log.warning("sitemap fetch failed %s: %s", sm_url, exc)
            continue

        for raw in _urls_from_sitemap_xml(sm_xml):
            if len(collected) >= cap:
                break
            nu = _normalize_candidate_url(raw, sitemap_index_url)
            if not nu or nu in seen:
                continue
            path = urlparse(nu).path.lower()
            if not (path.startswith("/scholarship/") or path.startswith("/page/")):
                continue
            seen.add(nu)
            collected.append(nu)
    return collected


def _text_one(soup: BeautifulSoup, selector: str) -> str | None:
    el = soup.select_one(selector)
    if el and el.get_text(strip=True):
        return el.get_text(" ", strip=True)
    return None


def _meta(soup: BeautifulSoup, prop: str | None = None, name: str | None = None) -> str | None:
    if prop:
        tag = soup.find("meta", attrs={"property": prop})
    else:
        tag = soup.find("meta", attrs={"name": name})
    if tag and tag.get("content"):
        return str(tag["content"]).strip()
    return None


def _parse_deadline_from_text(text: str) -> date | None:
    if not text:
        return None
    m = re.search(
        r"(20\d{2}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]20\d{2})",
        text,
    )
    if not m:
        return None
    try:
        return date_parser.parse(m.group(1), dayfirst=False).date()
    except (ValueError, TypeError, OverflowError):
        return None


def parse_detail(html: str, url: str) -> ScholarshipIn:
    soup = BeautifulSoup(html, "html.parser")
    title = (
        _text_one(soup, "h1")
        or _meta(soup, prop="og:title")
        or _meta(soup, name="twitter:title")
        or "Scholarship"
    )
    summary = _meta(soup, name="description") or _meta(soup, prop="og:description")
    body = soup.find("main") or soup.find("article") or soup.body
    eligibility_text = None
    if body:
        eligibility_text = body.get_text(" ", strip=True)[:8000]
    amount = None
    amt_m = re.search(
        r"(₹|Rs\.?|INR)\s*[\d,]+(?:\s*-\s*[\d,]+)?",
        eligibility_text or "",
        flags=re.I,
    )
    if amt_m:
        amount = amt_m.group(0)
    deadline = _parse_deadline_from_text(
        " ".join(
            filter(
                None,
                [summary or "", eligibility_text or "", title],
            )
        )
    )
    raw: dict[str, Any] = {"url": url, "title_len": len(title)}
    tags: list[str] = []
    low = (title + " " + (summary or "")).lower()
    for label in ("engineering", "medical", "mba", "phd", "school", "girl", "women", "sc", "st", "obc"):
        if label in low:
            tags.append(label)
    return ScholarshipIn(
        source="buddy4study",
        source_url=url,
        title=title.strip()[:512],
        summary=(summary or "")[:4000] if summary else None,
        eligibility_text=eligibility_text,
        amount=amount,
        deadline=deadline,
        tags=tags or None,
        raw_payload=raw,
    )


def run_buddy4study_scrape(robots: RobotsChecker) -> list[ScholarshipIn]:
    ua = settings.http_user_agent
    list_url = settings.buddy4study_list_url
    if not robots.allowed(list_url, ua):
        log.warning("robots.txt disallows list fetch: %s", list_url)
        return []

    items: list[ScholarshipIn] = []
    visited_lists: set[str] = set()
    queue: list[str] = [list_url]

    while queue and len(visited_lists) < MAX_LIST_URLS:
        current = queue.pop(0)
        if current in visited_lists:
            continue
        visited_lists.add(current)
        if not robots.allowed(current, ua):
            log.warning("robots.txt disallows: %s", current)
            continue
        try:
            html = fetch_text(current)
        except Exception as exc:  # noqa: BLE001
            log.warning("list fetch failed %s: %s", current, exc)
            continue
        for lurl in collect_listing_urls(html, current):
            if lurl not in visited_lists and lurl not in queue:
                queue.append(lurl)
        # Listing pages are category hubs under /scholarships/*.
        # Detail pages are usually /scholarship/*, /page/*, or card URLs.
        detail_urls: list[str] = []
        for u in collect_scholarship_detail_urls(html, current):
            if urlparse(u).path.lower().startswith("/scholarships/"):
                if u not in visited_lists and u not in queue:
                    queue.append(u)
                continue
            detail_urls.append(u)

        if not detail_urls:
            log.warning(
                "No scholarship detail URLs found in HTML from %s "
                "(try BUDDY4STUDY_LIST_URL or admin JSON import if the site is JS-only).",
                current,
            )
        for durl in detail_urls:
            if not robots.allowed(durl, ua):
                continue
            try:
                dhtml = fetch_text(durl)
                items.append(parse_detail(dhtml, durl))
            except Exception as exc:  # noqa: BLE001
                log.warning("detail fetch failed %s: %s", durl, exc)
        # enqueue a few more listing pages if pagination links exist
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            label = (a.get_text() or "").strip().lower()
            href = a["href"]
            full = _absolute_url(current, href)
            if not _same_site(list_url, full):
                continue
            if any(x in label for x in ("next", "more", "view all")) or re.search(
                r"/scholarships(?:/|$)", full.lower()
            ):
                if full not in visited_lists and full not in queue:
                    queue.append(full)
    # de-dupe by URL
    by_url: dict[str, ScholarshipIn] = {}
    for it in items:
        by_url[it.source_url] = it
    deduped = list(by_url.values())

    if deduped:
        return deduped

    # Fallback for JS-rendered listing pages: use sitemap detail URLs.
    for durl in collect_detail_urls_from_sitemaps(robots, ua):
        if not robots.allowed(durl, ua):
            continue
        try:
            dhtml = fetch_text(durl)
            deduped.append(parse_detail(dhtml, durl))
        except Exception as exc:  # noqa: BLE001
            log.warning("detail fetch failed %s: %s", durl, exc)
    return deduped
