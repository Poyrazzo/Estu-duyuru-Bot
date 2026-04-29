#!/usr/bin/env python3
"""
ESTÜ Canvas Duyuru Botu — Main Entry Point
"""

import json
import logging
import signal
import sys
import time
from pathlib import Path

from db import Database
from notifier import TelegramNotifier
from quiet_hours import is_quiet_now
from scraper import CanvasScraper, TokenExpiredError

CONFIG_PATH = Path(__file__).parent / "config.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("bot")


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def validate_config(cfg: dict):
    token = cfg["telegram"]["api_token"]
    chat_id = cfg["telegram"]["chat_id"]
    access_token = cfg["canvas"]["access_token"]

    if token == "YOUR_TELEGRAM_BOT_TOKEN":
        logger.error("Set your Telegram API token in config.json")
        sys.exit(1)
    if chat_id == "YOUR_CHAT_ID":
        logger.error("Set your Telegram chat_id in config.json")
        sys.exit(1)
    if access_token == "YOUR_CANVAS_ACCESS_TOKEN":
        logger.error("Set your Canvas access token in config.json")
        sys.exit(1)


class Bot:
    def __init__(self):
        self.cfg = load_config()
        validate_config(self.cfg)

        canvas_cfg = self.cfg["canvas"]
        tg_cfg = self.cfg["telegram"]
        db_cfg = self.cfg["database"]
        self.quiet_cfg = self.cfg.get("quiet_hours", {"enabled": False})

        self.db = Database(db_cfg["path"])
        self.notifier = TelegramNotifier(tg_cfg["api_token"], tg_cfg["chat_id"])
        self.scraper = CanvasScraper(
            base_url=canvas_cfg["base_url"],
            access_token=canvas_cfg["access_token"],
            timeout=canvas_cfg.get("request_timeout_seconds", 30),
        )
        self.course_ids: list = canvas_cfg.get("course_ids", [])
        self.interval: int = canvas_cfg.get("check_interval_seconds", 600)
        self._running = True

        signal.signal(signal.SIGINT, self._handle_stop)
        signal.signal(signal.SIGTERM, self._handle_stop)

    def _handle_stop(self, *_):
        logger.info("Shutdown signal received. Stopping...")
        self._running = False

    def _flush_queued(self):
        queued = self.db.flush_queue()
        for item in queued:
            self.notifier.send_announcement(
                subject=item["subject"],
                class_name=item["class_name"],
                link=item["link"],
            )
            logger.info("Sent queued announcement: %s", item["ann_id"])

    def _process_announcements(self):
        quiet_enabled = self.quiet_cfg.get("enabled", False)
        quiet_start = self.quiet_cfg.get("start", "23:00")
        quiet_end = self.quiet_cfg.get("end", "07:00")
        in_quiet = quiet_enabled and is_quiet_now(quiet_start, quiet_end)

        if not in_quiet and quiet_enabled:
            self._flush_queued()

        try:
            announcements = self.scraper.fetch_all_announcements(self.course_ids)
        except TokenExpiredError as exc:
            logger.error("%s", exc)
            self.notifier.send_token_expired_alert()
            return
        except Exception as exc:
            logger.error("Unexpected scraper error: %s", exc, exc_info=True)
            return

        new_count = 0
        for ann in announcements:
            if self.db.is_seen(ann.id):
                continue

            new_count += 1
            # Write to DB first — prevents duplicate sends on crash
            self.db.mark_seen(ann.id, ann.subject, ann.class_name, ann.link)

            if in_quiet:
                logger.info("Quiet hours — queuing: [%s] %s", ann.class_name, ann.subject)
                self.db.enqueue(ann.id, ann.subject, ann.class_name, ann.link)
            else:
                success = self.notifier.send_announcement(
                    subject=ann.subject,
                    class_name=ann.class_name,
                    link=ann.link,
                )
                if not success:
                    logger.warning("Notification failed for %s, queuing", ann.id)
                    self.db.enqueue(ann.id, ann.subject, ann.class_name, ann.link)

        if new_count == 0:
            logger.info("No new announcements.")
        else:
            logger.info("Processed %d new announcement(s).", new_count)

    def run(self):
        logger.info("=" * 60)
        logger.info("ESTÜ Canvas Announcement Bot starting up")
        logger.info("Interval: %ds | Courses: %s", self.interval, self.course_ids or "auto-discover")
        logger.info("=" * 60)

        self.notifier.send_startup_message()

        consecutive_errors = 0
        max_errors = 5

        while self._running:
            try:
                logger.info("--- Check cycle ---")
                self._process_announcements()
                consecutive_errors = 0
            except Exception as exc:
                consecutive_errors += 1
                logger.error("Unhandled error (%d/%d): %s", consecutive_errors, max_errors, exc, exc_info=True)
                if consecutive_errors >= max_errors:
                    msg = f"Bot stopped after {max_errors} consecutive errors: {exc}"
                    logger.critical(msg)
                    self.notifier.send_error_alert(msg)
                    sys.exit(1)

            for _ in range(self.interval):
                if not self._running:
                    break
                time.sleep(1)

        logger.info("Bot stopped cleanly.")


if __name__ == "__main__":
    Bot().run()
