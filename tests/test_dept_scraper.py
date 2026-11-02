import unittest
from pathlib import Path
from unittest import mock

from bs4 import BeautifulSoup

from scraper import DeptScraper, LayoutChangedError

FIXTURES = Path(__file__).parent / "fixtures"


def _soup(name: str) -> BeautifulSoup:
    return BeautifulSoup((FIXTURES / name).read_text(encoding="utf-8"), "lxml")


class DeptListTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(DeptScraper, "_get_soup", return_value=_soup("dept_list.html"))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.items = DeptScraper().list_announcements()

    def test_parses_all_items_on_page(self):
        self.assertGreaterEqual(len(self.items), 8)

    def test_first_item_fields(self):
        first = self.items[0]
        self.assertEqual(first.id, "ceng_about-midterm-exams-of-bim437-and-bim444")
        self.assertEqual(first.subject, "About Midterm Exams of BIM437 and BIM444")
        self.assertTrue(first.link.startswith("https://ceng.eskisehir.edu.tr/tr/Duyuru/Detay/"))
        self.assertTrue(first.posted_at.startswith("30 Eki 2026"))
        self.assertIn("summary sheet", first.content)  # excerpt is the fallback body

    def test_ids_are_unique(self):
        ids = [a.id for a in self.items]
        self.assertEqual(len(ids), len(set(ids)))


class DeptDetailTest(unittest.TestCase):
    def test_detail_gives_full_text_and_time(self):
        with mock.patch.object(DeptScraper, "_get_soup", return_value=_soup("dept_detail.html")):
            content, posted_at = DeptScraper()._fetch_detail("https://x/tr/Duyuru/Detay/y")
        self.assertIn("Özdemir Bayraktar", content)
        self.assertEqual(posted_at, "27 Eki 2026, 13:46")


class LayoutChangeTest(unittest.TestCase):
    def test_unrecognised_page_raises_instead_of_returning_empty(self):
        html = BeautifulSoup("<html><body><h1>Yeni tasarım</h1></body></html>", "lxml")
        with mock.patch.object(DeptScraper, "_get_soup", return_value=html):
            with self.assertRaises(LayoutChangedError):
                DeptScraper().list_announcements()


if __name__ == "__main__":
    unittest.main()
