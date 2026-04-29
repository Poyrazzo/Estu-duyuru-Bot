#!/usr/bin/env python3
"""
Single-shot check — used by GitHub Actions.
Runs exactly one scrape cycle then exits.
"""

import json
import logging
import sys
from pathlib import Path

from db import Database
from notifier import TelegramNotifier
from scraper import CanvasScraper, TokenExpiredError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("run_once")

CONFIG_PATH = Path(__file__).parent / "config.json"


def main():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)

    db = Database(cfg["database"]["path"])
    notifier = TelegramNotifier(cfg["telegram"]["api_token"], cfg["telegram"]["chat_id"])
    scraper = CanvasScraper(
        base_url=cfg["canvas"]["base_url"],
        access_token=cfg["canvas"]["access_token"],
        timeout=cfg["canvas"].get("request_timeout_seconds", 30),
    )
    course_ids = cfg["canvas"].get("course_ids", [])

    logger.info("Starting one-shot check (course_ids=%s)", course_ids or "auto")

    try:
        announcements = scraper.fetch_all_announcements(course_ids)
    except TokenExpiredError as exc:
        logger.error("%s", exc)
        notifier.send_token_expired_alert()
        sys.exit(1)
    except Exception as exc:
        logger.error("Scraper error: %s", exc, exc_info=True)
        notifier.send_error_alert(str(exc))
        sys.exit(1)

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
        )
        logger.info("Sent: [%s] %s", ann.class_name, ann.subject)

    if new_count == 0:
        logger.info("No new announcements.")
    else:
        logger.info("Sent %d new notification(s).", new_count)


if __name__ == "__main__":
    main()
