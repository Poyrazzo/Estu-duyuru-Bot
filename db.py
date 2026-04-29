import sqlite3
import logging
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_schema()

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self):
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS announcements (
                    id          TEXT PRIMARY KEY,
                    subject     TEXT NOT NULL,
                    class_name  TEXT NOT NULL,
                    link        TEXT NOT NULL,
                    date_found  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS queued_notifications (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    ann_id      TEXT NOT NULL,
                    subject     TEXT NOT NULL,
                    class_name  TEXT NOT NULL,
                    link        TEXT NOT NULL,
                    created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
                )
            """)
        logger.debug("Database schema initialized at %s", self.db_path)

    def is_seen(self, ann_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM announcements WHERE id = ?", (ann_id,)
            ).fetchone()
            return row is not None

    def mark_seen(self, ann_id: str, subject: str, class_name: str, link: str):
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO announcements (id, subject, class_name, link) VALUES (?, ?, ?, ?)",
                (ann_id, subject, class_name, link),
            )

    def enqueue(self, ann_id: str, subject: str, class_name: str, link: str):
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO queued_notifications (ann_id, subject, class_name, link) VALUES (?, ?, ?, ?)",
                (ann_id, subject, class_name, link),
            )

    def flush_queue(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, ann_id, subject, class_name, link FROM queued_notifications ORDER BY id"
            ).fetchall()
            if rows:
                ids = [r["id"] for r in rows]
                conn.execute(
                    f"DELETE FROM queued_notifications WHERE id IN ({','.join('?' * len(ids))})",
                    ids,
                )
            return [dict(r) for r in rows]
