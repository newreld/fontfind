import unittest

from fontfind import review


class VerifyTests(unittest.TestCase):
    PAGES = {"https://x.test/eula": "Fees are calculated based on the number of employees\nwithin the company."}

    def test_keeps_verbatim_quote_ignoring_whitespace_and_case(self):
        ev = [{"claim": "headcount", "quote": "fees are calculated based on the number of employees within the company.", "source": "z"}]
        got = review.verified_evidence(ev, self.PAGES)
        self.assertEqual(got[0]["source"], "https://x.test/eula")

    def test_drops_invented_quote(self):
        ev = [{"claim": "web", "quote": "Web use is included for unlimited domains at no extra cost", "source": "z"}]
        self.assertEqual(review.verified_evidence(ev, self.PAGES), [])

    def test_drops_too_short_quote(self):
        self.assertEqual(review.verified_evidence([{"claim": "x", "quote": "employees"}], self.PAGES), [])


if __name__ == "__main__":
    unittest.main()
