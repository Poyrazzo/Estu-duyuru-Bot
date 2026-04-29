#!/usr/bin/env python3
"""ESTÜ Canvas + Bölüm Sitesi Duyuru Botu — Main Entry Point"""

import json
import logging
import signal
import sys
import time
from pathlib import Path

from db import Database
from notifier import TelegramNotifier
from quiet_hours import is_quiet_now
from scraper import CanvasScraper, DeptScraper, TokenExpiredError

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
    if cfg["telegram"]["api_token"] == "YOUR_TELEGRAM_BOT_TOKEN":
        logger.error("Set Telegram token in config.json"); sys.exit(1)
    if cfg["telegram"]["chat_id"] == "YOUR_CHAT_ID":
        logger.error("Set Telegram chat_id in config.json"); sys.exit(1)
    if cfg["canvas"]["access_token"] == "YOUR_CANVAS_ACCESS_TOKEN":
        logger.error("Set Canvas access token in config.json"); sys.exit(1)


class Bot:
    def __init__(self):
        self.cfg = load_config()
        validate_config(self.cfg)

        canvas_cfg = self.cfg["canvas"]
        tg_cfg = self.cfg["telegram"]
        self.quiet_cfg = self.cfg.get("quiet_hours", {"enabled": False})

        self.db = Database(self.cfg["database"]["path"])
        self.notifier = TelegramNotifier(tg_cfg["api_token"], tg_cfg["chat_id"])
        self.canvas = CanvasScraper(
            base_url=canvas_cfg["base_url"],
            access_token=canvas_cfg["access_token"],
            timeout=canvas_cfg.get("request_timeout_seconds", 30),
        )
        self.dept = DeptScraper(timeout=canvas_cfg.get("request_timeout_seconds", 30))
        self.course_ids: list = canvas_cfg.get("course_ids", [])
        self.interval: int = canvas_cfg.get("check_interval_seconds", 600)
        self._running = True

        signal.signal(signal.SIGINT, self._handle_stop)
        signal.signal(signal.SIGTERM, self._handle_stop)

    def _handle_stop(self, *_):
        logger.info("Shutdown signal received.")
        self._running = False

    def _flush_queued(self):
        for item in self.db.flush_queue():
            self.notifier.send_announcement(
                subject=item["subject"],
                class_name=item["class_name"],
                link=item["link"],
                content=item.get("content", ""),
            )

    def _process(self, announcements, in_quiet: bool):
        new = 0
        for ann in announcements:
            if self.db.is_seen(ann.id):
                continue
            new += 1
            self.db.mark_seen(ann.id, ann.subject, ann.class_name, ann.link)
            if in_quiet:
                self.db.enqueue(ann.id, ann.subject, ann.class_name, ann.link)
                logger.info("Queued (quiet hours): [%s] %s", ann.class_name, ann.subject)
            else:
                ok = self.notifier.send_announcement(
                    subject=ann.subject,
                    class_name=ann.class_name,
                    link=ann.link,
                    content=ann.content,
                    posted_at=ann.posted_at,
                )
                if not ok:
                    self.db.enqueue(ann.id, ann.subject, ann.class_name, ann.link)
        return new

    def _check_cycle(self):
        quiet_enabled = self.quiet_cfg.get("enabled", False)
        in_quiet = quiet_enabled and is_quiet_now(
            self.quiet_cfg.get("start", "23:00"),
            self.quiet_cfg.get("end", "07:00"),
        )

        if not in_quiet and quiet_enabled:
            self._flush_queued()

        total_new = 0

        # Canvas
        try:
            anns = self.canvas.fetch_all_announcements(self.course_ids)
            total_new += self._process(anns, in_quiet)
        except TokenExpiredError as exc:
            logger.error("%s", exc)
            self.notifier.send_token_expired_alert()

        # Department site
        try:
            anns = self.dept.fetch_announcements()
            total_new += self._process(anns, in_quiet)
        except Exception as exc:
            logger.warning("Dept scraper error: %s", exc)

        if total_new == 0:
            logger.info("No new announcements.")
        else:
            logger.info("Sent %d new notification(s).", total_new)

    def run(self):
        logger.info("=" * 60)
        logger.info("ESTÜ Duyuru Bot starting (Canvas + Bölüm Sitesi)")
        logger.info("Interval: %ds | Courses: %s", self.interval, self.course_ids or "auto")
        logger.info("=" * 60)

        self.notifier.send_startup_message()

        consecutive_errors = 0
        while self._running:
            try:
                logger.info("--- Check cycle ---")
                self._check_cycle()
                consecutive_errors = 0
            except Exception as exc:
                consecutive_errors += 1
                logger.error("Unhandled error (%d/5): %s", consecutive_errors, exc, exc_info=True)
                if consecutive_errors >= 5:
                    self.notifier.send_error_alert(f"Bot stopped: {exc}")
                    sys.exit(1)

            for _ in range(self.interval):
                if not self._running:
                    break
                time.sleep(1)

        logger.info("Bot stopped.")


if __name__ == "__main__":
    Bot().run()
