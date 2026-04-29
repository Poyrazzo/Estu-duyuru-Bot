#!/usr/bin/env python3
"""Single-shot check — used by GitHub Actions."""

import json
import logging
import sys
from pathlib import Path

from db import Database
from notifier import TelegramNotifier
from scraper import CanvasScraper, DeptScraper, TokenExpiredError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("run_once")

CONFIG_PATH = Path(__file__).parent / "config.json"


def _process(announcements, db, notifier):
    new_count = 0
    for ann in announcements:
        if db.is_seen(ann.id):
            continue
        new_count += 1
        db.mark_seen(ann.id, ann.subject, ann.class_name, ann.link)
        notifier.send_announcement(
            subject=ann.subject,
            class_name=ann.class_name,
            link=ann.link,
            content=ann.content,
            posted_at=ann.posted_at,
        )
        logger.info("Sent: [%s] %s", ann.class_name, ann.subject)
    return new_count


def main():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)

    db = Database(cfg["database"]["path"])
    notifier = TelegramNotifier(cfg["telegram"]["api_token"], cfg["telegram"]["chat_id"])
    canvas = CanvasScraper(
        base_url=cfg["canvas"]["base_url"],
        access_token=cfg["canvas"]["access_token"],
        timeout=cfg["canvas"].get("request_timeout_seconds", 30),
    )
    dept = DeptScraper(timeout=cfg["canvas"].get("request_timeout_seconds", 30))
    course_ids = cfg["canvas"].get("course_ids", [])

    total_new = 0

    # Canvas
    logger.info("--- Canvas check ---")
    try:
        total_new += _process(canvas.fetch_all_announcements(course_ids), db, notifier)
    except TokenExpiredError as exc:
        logger.error("%s", exc)
        notifier.send_token_expired_alert()

    # Department site
    logger.info("--- Dept site check ---")
    try:
        total_new += _process(dept.fetch_announcements(), db, notifier)
    except Exception as exc:
        logger.error("Dept scraper error: %s", exc, exc_info=True)
        notifier.send_error_alert(f"Bölüm sitesi hatası: {exc}")

    if total_new == 0:
        logger.info("No new announcements.")
    else:
        logger.info("Total new notifications sent: %d", total_new)


if __name__ == "__main__":
    main()
