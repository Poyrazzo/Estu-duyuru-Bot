#!/usr/bin/env python3
"""Single-shot check — used by GitHub Actions.

    python run_once.py            # check Canvas + department site, notify about new items
    python run_once.py --check    # health check only: verify tokens/sites, send nothing
"""

import json
import logging
import sys
import time
from pathlib import Path

from db import Database
from notifier import TelegramNotifier
from pipeline import process
from scraper import CanvasScraper, DeptScraper, LayoutChangedError, TokenExpiredError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("run_once")

CONFIG_PATH = Path(__file__).parent / "config.json"
ALERT_COOLDOWN_SECONDS = 12 * 3600  # a broken source is re-announced at most twice a day


def _alert_once(db: Database, key: str, send) -> bool:
    """Send an alert unless the same one went out recently (runs are every 15 min).

    Returns True when a fresh alert went out.
    """
    last = float(db.get_meta(f"alert:{key}") or 0)
    if time.time() - last < ALERT_COOLDOWN_SECONDS:
        logger.info("Alert '%s' suppressed (sent recently).", key)
        return False
    if send():
        db.set_meta(f"alert:{key}", str(time.time()))
        return True
    return False


def _clear_alert(db: Database, key: str) -> None:
    if db.get_meta(f"alert:{key}"):
        db.set_meta(f"alert:{key}", "0")


def check_health(cfg: dict) -> int:
    """Verify each external dependency without sending anything. Returns number of failures."""
    import requests

    failures = 0
    tg = cfg["telegram"]
    try:
        r = requests.get(f"https://api.telegram.org/bot{tg['api_token']}/getMe", timeout=20)
        ok = r.ok and r.json().get("ok")
        print(f"[{'OK' if ok else 'FAIL'}] Telegram bot: "
              f"{r.json().get('result', {}).get('username') if ok else 'HTTP ' + str(r.status_code)}")
        failures += not ok
    except Exception as exc:
        print(f"[FAIL] Telegram: {type(exc).__name__}")
        failures += 1

    cv = cfg["canvas"]
    try:
        canvas = CanvasScraper(cv["base_url"], cv["access_token"], cv.get("request_timeout_seconds", 30))
        me = canvas._get_json("/api/v1/users/self")
        courses = canvas.get_active_courses()
        print(f"[OK] Canvas: {me.get('name')} — {len(courses)} aktif ders")
    except TokenExpiredError:
        print("[FAIL] Canvas: token geçersiz/süresi dolmuş (401)")
        failures += 1
    except Exception as exc:
        print(f"[FAIL] Canvas: {type(exc).__name__}: {exc}")
        failures += 1

    try:
        items = DeptScraper().list_announcements()
        print(f"[OK] Bölüm sitesi: {len(items)} duyuru ayrıştırıldı (en yeni: {items[0].subject[:50]})")
    except Exception as exc:
        print(f"[FAIL] Bölüm sitesi: {exc}")
        failures += 1
    return failures


def main() -> int:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)

    if "--check" in sys.argv:
        return 1 if check_health(cfg) else 0

    db = Database(cfg["database"]["path"])
    notifier = TelegramNotifier(cfg["telegram"]["api_token"], cfg["telegram"]["chat_id"])
    timeout = cfg["canvas"].get("request_timeout_seconds", 30)
    canvas = CanvasScraper(
        base_url=cfg["canvas"]["base_url"],
        access_token=cfg["canvas"]["access_token"],
        timeout=timeout,
    )
    dept = DeptScraper(timeout=timeout)
    course_ids = cfg["canvas"].get("course_ids", [])

    sent = failed = 0
    fresh_alerts = 0

    logger.info("--- Canvas check ---")
    try:
        stats = process("canvas", canvas.fetch_all_announcements(course_ids), db, notifier)
        sent, failed = sent + stats.sent, failed + stats.failed
        _clear_alert(db, "canvas")
    except TokenExpiredError as exc:
        logger.error("%s", exc)
        fresh_alerts += _alert_once(db, "canvas", notifier.send_token_expired_alert)
    except Exception as exc:
        logger.error("Canvas error: %s", exc, exc_info=True)
        fresh_alerts += _alert_once(db, "canvas", lambda: notifier.send_error_alert(f"Canvas hatası: {exc}"))

    logger.info("--- Dept site check ---")
    try:
        stats = process("dept", dept.list_announcements(), db, notifier, enrich=dept.enrich)
        sent, failed = sent + stats.sent, failed + stats.failed
        _clear_alert(db, "dept")
    except (LayoutChangedError, Exception) as exc:
        logger.error("Dept scraper error: %s", exc, exc_info=not isinstance(exc, LayoutChangedError))
        fresh_alerts += _alert_once(db, "dept", lambda: notifier.send_error_alert(f"Bölüm sitesi hatası: {exc}"))

    if sent == 0 and failed == 0:
        logger.info("No new announcements.")
    else:
        logger.info("Sent: %d, failed to send: %d", sent, failed)

    # Non-zero exit turns the Actions run red (GitHub then emails you) instead of silently "succeeding".
    # Only on a fresh alert or a failed send, so a long outage is ~2 emails a day, not one per run.
    return 1 if (fresh_alerts or failed) else 0


if __name__ == "__main__":
    sys.exit(main())
