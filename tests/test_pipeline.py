import os
import tempfile
import unittest
from unittest import mock

import requests

from db import Database
from pipeline import process
from scraper import Announcement, CanvasScraper, TokenExpiredError


class FakeNotifier:
    def __init__(self, fail_ids=()):
        self.sent = []
        self.fail_ids = set(fail_ids)

    def send_announcement(self, subject, class_name, link, content="", posted_at=""):
        if subject in self.fail_ids:
            return False
        self.sent.append(subject)
        return True


def ann(i, source="Canvas Ders", prefix=""):
    return Announcement(id=f"{prefix}{i}", subject=f"S{i}", class_name=source, link=f"http://x/{i}")


class PipelineTest(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.addCleanup(os.unlink, self.path)
        self.db = Database(self.path)

    def seeded_db(self):
        """A source whose first (seeding) run already happened."""
        process("canvas", [], self.db, FakeNotifier())

    def test_first_run_seeds_without_sending(self):
        n = FakeNotifier()
        stats = process("canvas", [ann(1), ann(2)], self.db, n)
        self.assertEqual(n.sent, [])
        self.assertEqual(stats.seeded, 2)
        self.assertTrue(self.db.is_seen("1"))

    def test_second_run_sends_only_new(self):
        process("canvas", [ann(1)], self.db, FakeNotifier())
        n = FakeNotifier()
        stats = process("canvas", [ann(1), ann(2)], self.db, n)
        self.assertEqual(n.sent, ["S2"])
        self.assertEqual(stats.sent, 1)

    def test_failed_send_is_not_marked_seen_and_is_retried(self):
        self.seeded_db()
        flaky = FakeNotifier(fail_ids={"S5"})
        stats = process("canvas", [ann(5)], self.db, flaky)
        self.assertEqual(stats.failed, 1)
        self.assertFalse(self.db.is_seen("5"))

        healthy = FakeNotifier()
        process("canvas", [ann(5)], self.db, healthy)
        self.assertEqual(healthy.sent, ["S5"])

    def test_existing_db_rows_count_as_seeded(self):
        # A DB created by the old version has rows but no 'seeded' flag.
        self.db.mark_seen("7", "old", "Canvas Ders", "http://x/7")
        n = FakeNotifier()
        process("canvas", [ann(7), ann(8)], self.db, n)
        self.assertEqual(n.sent, ["S8"])

    def test_sources_seed_independently(self):
        process("canvas", [ann(1)], self.db, FakeNotifier())
        n = FakeNotifier()
        # dept has never run: must seed, not flood, even though canvas rows exist.
        stats = process("dept", [ann("a", prefix="ceng_")], self.db, n)
        self.assertEqual(n.sent, [])
        self.assertEqual(stats.seeded, 1)

    def test_enrich_is_only_called_for_unseen(self):
        self.seeded_db()
        self.db.mark_seen("1", "S1", "Canvas Ders", "http://x/1")
        calls = []
        process("canvas", [ann(1), ann(2)], self.db, FakeNotifier(), enrich=calls.append)
        self.assertEqual([a.id for a in calls], ["2"])


class CanvasErrorHandlingTest(unittest.TestCase):
    def _scraper(self, status):
        s = CanvasScraper("https://canvas.example", "tok")
        resp = requests.Response()
        resp.status_code = status
        resp._content = b'{"errors":[]}'
        s.session = mock.Mock()
        s.session.get.return_value = resp
        return s

    def test_403_on_one_course_is_skipped_not_treated_as_dead_token(self):
        out = self._scraper(403).fetch_course_announcements(1, "Kısıtlı Ders")
        self.assertEqual(out, [])

    def test_401_still_means_dead_token(self):
        with self.assertRaises(TokenExpiredError):
            self._scraper(401).fetch_course_announcements(1, "Ders")


if __name__ == "__main__":
    unittest.main()
