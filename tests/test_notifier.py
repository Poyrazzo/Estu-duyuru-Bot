import unittest

from notifier import MAX_MESSAGE_CHARS, TelegramNotifier


class BuildAnnouncementTest(unittest.TestCase):
    def setUp(self):
        self.n = TelegramNotifier("t", "1")

    def test_long_content_stays_under_telegram_limit(self):
        text = self.n._build_announcement("Konu", "Ders", "http://x/1", content="a & b < c " * 2000)
        self.assertLessEqual(len(text), MAX_MESSAGE_CHARS)
        self.assertIn("Konu", text)
        self.assertIn("http://x/1", text)

    def test_link_with_quotes_cannot_break_out_of_href(self):
        text = self.n._build_announcement("K", "D", 'http://x/?a="1"&b=2')
        self.assertIn('href="http://x/?a=&quot;1&quot;&amp;b=2"', text)


if __name__ == "__main__":
    unittest.main()
