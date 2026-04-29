"""
Scrapers:
  - CanvasScraper   : Canvas LMS REST API (Bearer token)
  - DeptScraper     : ceng.eskisehir.edu.tr/tr/Duyuru (HTML scraping)
"""

import logging
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8",
}


@dataclass
class Announcement:
    id: str
    subject: str
    class_name: str
    link: str
    content: str = field(default="")
    posted_at: str = field(default="")  # human-readable, e.g. "28 Nis 2026, 13:25"


class TokenExpiredError(Exception):
    """Canvas returned 401 — token invalid or expired."""


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

_TR_MONTHS = {
    "Jan": "Oca", "Feb": "Şub", "Mar": "Mar", "Apr": "Nis",
    "May": "May", "Jun": "Haz", "Jul": "Tem", "Aug": "Ağu",
    "Sep": "Eyl", "Oct": "Eki", "Nov": "Kas", "Dec": "Ara",
}

def _format_canvas_date(iso: str) -> str:
    """Convert '2026-04-28T10:25:27Z' → '28 Nis 2026, 13:25' (UTC+3)."""
    if not iso:
        return ""
    try:
        from datetime import datetime, timezone, timedelta
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        dt = dt.astimezone(timezone(timedelta(hours=3)))
        month_en = dt.strftime("%b")
        month_tr = _TR_MONTHS.get(month_en, month_en)
        return dt.strftime(f"%d {month_tr} %Y, %H:%M")
    except Exception:
        return iso


def _format_dept_date(raw: str) -> str:
    """Convert '28.04.2026 14:46:12' → '28 Nis 2026, 14:46'."""
    if not raw:
        return ""
    try:
        from datetime import datetime
        dt = datetime.strptime(raw.strip(), "%d.%m.%Y %H:%M:%S")
        month_tr = _TR_MONTHS.get(dt.strftime("%b"), dt.strftime("%b"))
        return dt.strftime(f"%d {month_tr} %Y, %H:%M")
    except Exception:
        return raw


def _html_to_text(html: str, max_chars: int = 900) -> str:
    """Strip HTML tags and collapse whitespace."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")
    # Replace <br>/<p> with newlines before stripping
    for tag in soup.find_all(["br", "p", "li"]):
        tag.insert_before("\n")
    text = soup.get_text(separator=" ")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text).strip()
    if len(text) > max_chars:
        text = text[:max_chars].rstrip() + "…"
    return text


# ─────────────────────────────────────────────────────────────
# Canvas scraper
# ─────────────────────────────────────────────────────────────

class CanvasScraper:
    def __init__(self, base_url: str, access_token: str, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.session.headers["Authorization"] = f"Bearer {access_token}"
        self.session.headers["Accept"] = "application/json"

    def _get_json(self, path: str, params: dict | None = None) -> list | dict:
        url = f"{self.base_url}{path}"
        results = []
        while url:
            resp = self.session.get(url, params=params, timeout=self.timeout)
            if resp.status_code == 401:
                raise TokenExpiredError(
                    "Canvas 401 Unauthorized — access token is invalid or expired."
                )
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list):
                results.extend(data)
            else:
                return data
            url = self._next_page(resp)
            params = None
        return results

    @staticmethod
    def _next_page(resp: requests.Response) -> str | None:
        for part in resp.headers.get("Link", "").split(","):
            if 'rel="next"' in part:
                return part.split(";")[0].strip().strip("<>")
        return None

    def get_active_courses(self) -> list[dict]:
        logger.info("Fetching active Canvas courses")
        return self._get_json("/api/v1/courses", params={
            "enrollment_state": "active", "per_page": 100
        })

    def fetch_course_announcements(self, course_id: int | str, course_name: str) -> list[Announcement]:
        logger.debug("Canvas: fetching announcements for %s", course_name)
        try:
            topics = self._get_json(
                f"/api/v1/courses/{course_id}/discussion_topics",
                params={"only_announcements": "true", "per_page": 50, "order_by": "recent_activity"},
            )
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code in (401, 403):
                raise TokenExpiredError(str(exc)) from exc
            logger.warning("HTTP error for course %s: %s", course_id, exc)
            return []

        announcements = []
        for topic in topics:
            ann_id = str(topic.get("id", ""))
            if not ann_id:
                continue
            subject = topic.get("title") or "No subject"
            link = topic.get("html_url") or f"{self.base_url}/courses/{course_id}/discussion_topics/{ann_id}"
            content = _html_to_text(topic.get("message", ""))
            posted_at = _format_canvas_date(topic.get("posted_at") or topic.get("created_at", ""))
            announcements.append(Announcement(
                id=ann_id,
                subject=subject,
                class_name=course_name,
                link=link,
                content=content,
                posted_at=posted_at,
            ))
        return announcements

    def fetch_all_announcements(self, course_ids: list) -> list[Announcement]:
        if course_ids:
            all_courses = []
            for cid in course_ids:
                try:
                    c = self._get_json(f"/api/v1/courses/{cid}")
                    all_courses.append({"id": cid, "name": c.get("name", str(cid))})
                except Exception as exc:
                    logger.warning("Could not fetch course %s: %s", cid, exc)
                    all_courses.append({"id": cid, "name": str(cid)})
        else:
            raw = self.get_active_courses()
            all_courses = [{"id": c["id"], "name": c.get("name", str(c["id"]))} for c in raw]

        all_announcements: list[Announcement] = []
        for course in all_courses:
            try:
                anns = self.fetch_course_announcements(course["id"], course["name"])
                logger.info("  Canvas %s → %d", course["name"], len(anns))
                all_announcements.extend(anns)
            except TokenExpiredError:
                raise
            except Exception as exc:
                logger.warning("Canvas course %s failed: %s", course["name"], exc)

        seen: set[str] = set()
        unique = []
        for ann in all_announcements:
            if ann.id not in seen:
                seen.add(ann.id)
                unique.append(ann)

        logger.info("Canvas total unique: %d", len(unique))
        return unique


# ─────────────────────────────────────────────────────────────
# Department website scraper
# ─────────────────────────────────────────────────────────────

DEPT_BASE = "https://ceng.eskisehir.edu.tr"
DEPT_LIST = f"{DEPT_BASE}/tr/Duyuru"
SOURCE_NAME = "CENG Bölüm Sitesi"


class DeptScraper:
    def __init__(self, timeout: int = 20):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def _get_soup(self, url: str) -> BeautifulSoup:
        resp = self.session.get(url, timeout=self.timeout)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "lxml")

    def _fetch_detail(self, detail_url: str) -> tuple[str, str]:
        """Return (content_text, posted_at) from a detail page."""
        try:
            soup = self._get_soup(detail_url)
            content = ""
            content_div = soup.select_one(".gdlr-core-blog-content")
            if content_div:
                content = _html_to_text(str(content_div), max_chars=900)
            date_el = soup.select_one("span.gdlr-core-blog-info")
            posted_at = _format_dept_date(date_el.get_text(strip=True)) if date_el else ""
            return content, posted_at
        except Exception as exc:
            logger.warning("Dept detail fetch failed (%s): %s", detail_url, exc)
        return "", ""

    def fetch_announcements(self) -> list[Announcement]:
        logger.info("Dept: fetching %s", DEPT_LIST)
        try:
            soup = self._get_soup(DEPT_LIST)
        except Exception as exc:
            logger.warning("Dept list page failed: %s", exc)
            return []

        announcements = []
        # Each announcement has 3 <a> tags with the same href (thumbnail, title, "Devamı").
        # Only the one inside h3.gdlr-core-blog-title carries the real title.
        links = soup.select('h3.gdlr-core-blog-title a[href*="/tr/Duyuru/Detay/"]')

        seen_hrefs: set[str] = set()
        for a in links:
            href = a.get("href", "")
            if not href or href in seen_hrefs:
                continue
            seen_hrefs.add(href)

            title = a.get_text(strip=True)
            if not title:
                continue

            # Use the URL slug as stable unique ID, prefixed to avoid collision with Canvas IDs
            slug = href.rstrip("/").split("/")[-1]
            ann_id = f"ceng_{slug}"
            full_url = urljoin(DEPT_BASE, href)

            content, posted_at = self._fetch_detail(full_url)

            announcements.append(Announcement(
                id=ann_id,
                subject=title,
                class_name=SOURCE_NAME,
                link=full_url,
                content=content,
                posted_at=posted_at,
            ))

        logger.info("Dept total: %d", len(announcements))
        return announcements
