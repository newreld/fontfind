import datetime as dt
import unittest

from fontfind import review


def entry(method, days_ago=0):
    date = (dt.date.today() - dt.timedelta(days=days_ago)).isoformat()
    return {"verified": {"method": method, "date": date}}


class PendingTests(unittest.TestCase):
    def test_not_reviewed_is_pending(self):
        self.assertTrue(review.needs_review(entry("auto-screened, not reviewed")))
        self.assertTrue(review.needs_review(entry("search-snippet")))

    def test_hand_and_auto_reviewed_are_not_pending(self):
        self.assertFalse(review.needs_review(entry("browser-reviewed")))
        self.assertFalse(review.needs_review(entry(review.METHOD)))

    def test_failed_waits_a_week_then_retries(self):
        failed = f"{review.FAILED} (license pages unreadable)"
        self.assertFalse(review.needs_review(entry(failed, 1)))
        self.assertTrue(review.needs_review(entry(failed, 8)))

    def test_mark_unreadable_records_reason(self):
        f = {"name": "X"}
        reason = review.mark_unreadable(f, ["https://x.test/licensing: HTTP 429"])
        self.assertIn("HTTP 429", reason)
        self.assertTrue(f["verified"]["method"].startswith(review.FAILED))
        self.assertIn("could not be read", f["todo"])


if __name__ == "__main__":
    unittest.main()
