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
            conn.execute("""
                CREATE TABLE IF NOT EXISTS meta (
                    key    TEXT PRIMARY KEY,
                    value  TEXT NOT NULL
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

    def count_seen(self, id_prefix: str | None = None, exclude_prefix: str | None = None) -> int:
        sql, args = "SELECT COUNT(*) FROM announcements WHERE 1=1", []
        if id_prefix:
            sql += " AND id LIKE ? ESCAPE '\\'"
            args.append(id_prefix.replace("_", "\\_") + "%")
        if exclude_prefix:
            sql += " AND id NOT LIKE ? ESCAPE '\\'"
            args.append(exclude_prefix.replace("_", "\\_") + "%")
        with self._connect() as conn:
            return conn.execute(sql, args).fetchone()[0]

    def get_meta(self, key: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
            return row["value"] if row else None

    def set_meta(self, key: str, value: str):
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO meta (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
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
