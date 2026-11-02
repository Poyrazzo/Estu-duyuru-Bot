"""Shared "which announcements are new, notify, remember" logic (used by run_once and bot)."""

import logging
from dataclasses import dataclass
from typing import Callable, Iterable

from db import Database
from scraper import Announcement

logger = logging.getLogger(__name__)

# Dept IDs are "ceng_<slug>"; every other ID is a Canvas topic ID.
DEPT_PREFIX = "ceng_"


@dataclass
class Stats:
    sent: int = 0
    failed: int = 0
    seeded: int = 0


def _is_seeded(source: str, db: Database) -> bool:
    """A source counts as seeded once it has run before — explicit flag, or rows from an older DB."""
    if db.get_meta(f"seeded:{source}"):
        return True
    if source == "dept":
        return db.count_seen(id_prefix=DEPT_PREFIX) > 0
    return db.count_seen(exclude_prefix=DEPT_PREFIX) > 0


def process(
    source: str,
    announcements: Iterable[Announcement],
    db: Database,
    notifier,
    enrich: Callable[[Announcement], None] | None = None,
) -> Stats:
    """Send unseen announcements; an announcement is remembered only after Telegram accepted it.

    The first run of a source (empty history, e.g. fresh install or lost cache) just records
    what is already published instead of flooding the chat with old announcements.
    """
    stats = Stats()
    announcements = list(announcements)

    if not _is_seeded(source, db):
        for ann in announcements:
            db.mark_seen(ann.id, ann.subject, ann.class_name, ann.link)
        db.set_meta(f"seeded:{source}", "1")
        stats.seeded = len(announcements)
        logger.info("%s: ilk çalıştırma — %d mevcut duyuru bildirim göndermeden kaydedildi.",
                    source, stats.seeded)
        return stats

    for ann in announcements:
        if db.is_seen(ann.id):
            continue
        if enrich:
            enrich(ann)
        if notifier.send_announcement(
            subject=ann.subject,
            class_name=ann.class_name,
            link=ann.link,
            content=ann.content,
            posted_at=ann.posted_at,
        ):
            db.mark_seen(ann.id, ann.subject, ann.class_name, ann.link)
            stats.sent += 1
            logger.info("Sent: [%s] %s", ann.class_name, ann.subject)
        else:
            stats.failed += 1
            logger.error("Send failed, will retry next run: [%s] %s", ann.class_name, ann.subject)
    return stats
