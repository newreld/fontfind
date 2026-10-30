import unittest

from fontfind import crawl


class CrawlParsingTests(unittest.TestCase):
    def test_listing_finds_foundry_links(self):
        html = '<a href="/foundry/1/alias">Alias</a><a href="/in/1/topics/2/x">x</a><a href="/foundry/10/bitstream">Bitstream</a>'
        got = crawl.parse_listing(html)
        self.assertEqual(sorted(got.values()), ["Alias", "Bitstream"])
        self.assertIn("https://fontsinuse.com/foundry/1/alias", got)

    def test_official_site(self):
        html = '<a href="https://typo.social/@x">Mastodon</a><a href="http://alias.uk.com/">Official Site (offline)</a>'
        self.assertEqual(crawl.parse_foundry_page(html), "http://alias.uk.com/")
        self.assertIsNone(crawl.parse_foundry_page("<a href='/x'>x</a>"))

    def test_host(self):
        self.assertEqual(crawl.host_of("https://www.Example.com/a"), "example.com")

    def test_candidate(self):
        strong = {"auto": {"metric_scores": {"company_size": 10, "seats": 2}}}
        self.assertTrue(crawl.is_candidate(strong))
        self.assertFalse(crawl.is_candidate({"auto": {"metric_scores": {"company_size": 10, "seats": 8, "traffic": 6}}}))
        self.assertFalse(crawl.is_candidate({"auto": {"metric_scores": {"company_size": 2}}}))
        self.assertFalse(crawl.is_candidate(strong, "someuniversity.edu"))
        self.assertFalse(crawl.is_candidate({}))


if __name__ == "__main__":
    unittest.main()


class PeerLinkTests(unittest.TestCase):
    def test_external_links_skip_social_and_self(self):
        html = ('<a href="https://other-foundry.com/x">o</a><a href="https://instagram.com/a">i</a>'
                '<a href="/licensing">l</a><a href="https://www.me.com/y">me</a>')
        self.assertEqual(crawl.external_links(html, "https://me.com"), {"other-foundry.com": "https://other-foundry.com"})
