import unittest

from fontfind.classify import classify
from fontfind.discover import license_links

ALL_IN = """
Our fonts are licensed by company size: the total number of employees, including freelancers.
One licence covers all media: print, web, app, social media and video.
Logos and wordmarks are included at no extra cost.
"""

LOGO_ADDON = """
Pricing is based on company size. Choose the tier up to 25 employees or up to 100 employees.
The only exception is logos/wordmarks, which are available as an optional add-on at checkout.
"""

SEATS = """
Desktop licenses are based on the number of computers the fonts are installed on.
Web licenses are priced by monthly unique visitors. App licenses by monthly active users.
"""

RESTRICTED = """
Licenses are priced by number of employees in your company.
You may not use the fonts in your logo or trademark.
"""


class ClassifyTest(unittest.TestCase):
    def test_all_in_one_with_logo(self):
        r = classify(ALL_IN)
        self.assertEqual(r.metric(), "company_size")
        self.assertEqual(r.logo(), "included")
        self.assertEqual(r.suggestion(), "likely")

    def test_logo_addon(self):
        r = classify(LOGO_ADDON)
        self.assertEqual(r.metric(), "company_size")
        self.assertEqual(r.logo(), "separate")
        self.assertEqual(r.suggestion(), "partial")

    def test_seat_based(self):
        r = classify(SEATS)
        self.assertIn(r.metric(), ("seats", "traffic"))
        self.assertEqual(r.suggestion(), "no")

    def test_restricted_logo(self):
        r = classify(RESTRICTED)
        self.assertEqual(r.logo(), "restricted")

    def test_evidence_is_kept(self):
        d = classify(ALL_IN).as_dict()
        self.assertTrue(any("Logos" in s for s in d["evidence"]["logo:included"]))

    def test_no_extra_fee_for_logo(self):
        r = classify("Priced by company size. There are no extra fees for logo use.")
        self.assertEqual(r.logo(), "included")

    def test_empty(self):
        self.assertEqual(classify("").suggestion(), "unknown")


class DiscoverTest(unittest.TestCase):
    def test_license_links(self):
        html = """
        <a href="/licensing">Licensing</a>
        <a href="/faq">FAQ</a>
        <a href="/fonts/foo">Foo</a>
        <a href="https://other.com/eula">EULA elsewhere</a>
        <a href="/legal/eula.pdf">End user license agreement</a>
        """
        links = license_links(html, "https://www.example.com/")
        self.assertEqual(links[0], "https://www.example.com/licensing")
        self.assertIn("https://www.example.com/legal/eula.pdf", links)
        self.assertIn("https://www.example.com/faq", links)
        self.assertNotIn("https://other.com/eula", links)
        self.assertNotIn("https://www.example.com/fonts/foo", links)


if __name__ == "__main__":
    unittest.main()
