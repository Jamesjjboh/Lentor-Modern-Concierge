"""Unit tests for the Telegram markdown sanitizer."""

import unittest

from src.formatting import clean_markdown_for_telegram


class TestFormatting(unittest.TestCase):
    def test_bullets_and_bold_normalised(self):
        raw = "* **24/7 Security:** `+65 6054 3379` *(Available 24 hours)*"
        out = clean_markdown_for_telegram(raw)
        self.assertTrue(out.startswith("• *24/7 Security:*"))
        self.assertNotIn("**", out)

    def test_double_asterisk_bold_converted(self):
        out = clean_markdown_for_telegram("log tickets via the **Novade app** today")
        self.assertEqual(out, "log tickets via the *Novade app* today")

    def test_unclosed_leading_asterisk_removed(self):
        out = clean_markdown_for_telegram("*Note: please log tickets via the *Novade app* now")
        self.assertEqual(out.count("*") % 2, 0)

    def test_unbalanced_backtick_removed(self):
        out = clean_markdown_for_telegram("call `+65 6054 3379 now")
        self.assertNotIn("`", out)

    def test_plain_text_untouched(self):
        self.assertEqual(clean_markdown_for_telegram("Hello neighbour"), "Hello neighbour")
        self.assertEqual(clean_markdown_for_telegram(""), "")


if __name__ == "__main__":
    unittest.main()
