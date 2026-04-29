"""
Canvas LMS REST API scraper.
Uses Bearer token auth — no cookie/session needed.
Docs: https://canvas.instructure.com/doc/api/
"""

import logging
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


@dataclass
class Announcement:
    id: str
    subject: str
    class_name: str
    link: str


class TokenExpiredError(Exception):
    """Raised when Canvas returns 401 Unauthorized."""


class CanvasScraper:
    def __init__(self, base_url: str, access_token: str, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.session.headers["Authorization"] = f"Bearer {access_token}"

    def _get_json(self, path: str, params: dict | None = None) -> list | dict:
        url = f"{self.base_url}{path}"
        results = []
        while url:
            resp = self.session.get(url, params=params, timeout=self.timeout)

            if resp.status_code == 401:
                raise TokenExpiredError(
                    "Canvas returned 401 Unauthorized. Access token is invalid or expired."
                )
            resp.raise_for_status()

            data = resp.json()
            if isinstance(data, list):
                results.extend(data)
            else:
                return data

            # Canvas paginates via Link header
            url = self._next_page(resp)
            params = None  # params already in next URL

        return results

    @staticmethod
    def _next_page(resp: requests.Response) -> str | None:
        link_header = resp.headers.get("Link", "")
        for part in link_header.split(","):
            if 'rel="next"' in part:
                url = part.split(";")[0].strip().strip("<>")
                return url
        return None

    def get_active_courses(self) -> list[dict]:
        """Return all active enrolled courses."""
        logger.info("Fetching active course list from Canvas")
        courses = self._get_json(
            "/api/v1/courses",
            params={
                "enrollment_state": "active",
                "per_page": 100,
                "include[]": "term",
            },
        )
        logger.info("Found %d active courses", len(courses))
        return courses

    def fetch_course_announcements(self, course_id: int | str, course_name: str) -> list[Announcement]:
        """Fetch announcements for a single course via Canvas discussion_topics API."""
        logger.debug("Fetching announcements for course %s (%s)", course_id, course_name)
        try:
            topics = self._get_json(
                f"/api/v1/courses/{course_id}/discussion_topics",
                params={
                    "only_announcements": "true",
                    "per_page": 50,
                    "order_by": "recent_activity",
                },
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
            announcements.append(
                Announcement(id=ann_id, subject=subject, class_name=course_name, link=link)
            )

        return announcements

    def fetch_all_announcements(self, course_ids: list) -> list[Announcement]:
        """
        Aggregate announcements across all courses.
        If course_ids is empty, auto-discovers all active courses first.
        """
        if course_ids:
            # Use provided IDs; get names via API
            all_courses = []
            for cid in course_ids:
                try:
                    course = self._get_json(f"/api/v1/courses/{cid}")
                    all_courses.append({"id": cid, "name": course.get("name", str(cid))})
                except Exception as exc:
                    logger.warning("Could not fetch course %s info: %s", cid, exc)
                    all_courses.append({"id": cid, "name": str(cid)})
        else:
            raw = self.get_active_courses()
            all_courses = [{"id": c["id"], "name": c.get("name", str(c["id"]))} for c in raw]

        all_announcements: list[Announcement] = []
        for course in all_courses:
            try:
                anns = self.fetch_course_announcements(course["id"], course["name"])
                logger.info("  %s → %d announcement(s)", course["name"], len(anns))
                all_announcements.extend(anns)
            except TokenExpiredError:
                raise
            except Exception as exc:
                logger.warning("Failed for course %s: %s", course["name"], exc)

        # Deduplicate by ID
        seen: set[str] = set()
        unique = []
        for ann in all_announcements:
            if ann.id not in seen:
                seen.add(ann.id)
                unique.append(ann)

        logger.info("Total unique announcements fetched: %d", len(unique))
        return unique
