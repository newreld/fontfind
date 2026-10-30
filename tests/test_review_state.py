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


class GateTests(unittest.TestCase):
    PAGES = {"https://x.test/eula": "Prices depend on the number of employees in the company, logos are allowed. Broadcast needs an extra license."}
    VERDICT = {"qualifies": "yes", "web": "yes", "evidence": [
        {"claim": "a", "quote": "Prices depend on the number of employees in the company"},
        {"claim": "b", "quote": "logos are allowed. Broadcast needs"}]}

    def run_gate(self, extra):
        f = {"name": "X"}
        review.apply(f, dict(self.VERDICT), self.PAGES, extra)
        return f

    def test_yes_needs_browser_look_and_clean_second_check(self):
        extra = {"observation": {"checked": True}, "check": {"objections": [], "still_yes": True}}
        self.assertEqual(self.run_gate(extra)["qualifies"], "yes")

    def test_no_browser_look_caps_at_likely(self):
        extra = {"observation": {"checked": False, "reason": "no font page found"}, "check": {"still_yes": True}}
        f = self.run_gate(extra)
        self.assertEqual(f["qualifies"], "likely")
        self.assertIn("could not be inspected", f["todo"])

    def test_verified_objection_downgrades(self):
        extra = {"observation": {"checked": True}, "check": {"still_yes": False, "downgrade_to": "partial", "objections": [
            {"point": "broadcast is extra", "quote": "Broadcast needs an extra license."}]}}
        f = self.run_gate(extra)
        self.assertEqual(f["qualifies"], "partial")
        self.assertIn("second check", f["todo"])

    def test_invented_objection_does_not_downgrade(self):
        extra = {"observation": {"checked": True}, "check": {"still_yes": False, "downgrade_to": "partial", "objections": [
            {"point": "made up", "quote": "Everything costs ten times more than listed here."}]}}
        self.assertEqual(self.run_gate(extra)["qualifies"], "yes")


if __name__ == "__main__":
    unittest.main()
