import tempfile
import unittest
from pathlib import Path

from confluence_api import absolute_url, build_base_url, get_host
from fix_confluence_links import ConfluenceLinkFixer


class UrlTests(unittest.TestCase):
    def test_build_base_url(self):
        cases = {
            "https://jun-test.atlassian.net/wiki/spaces/test/overview": "https://jun-test.atlassian.net/wiki",
            "jun-test.atlassian.net": "https://jun-test.atlassian.net/wiki",
            "jun-test": "https://jun-test.atlassian.net/wiki",
            "confluence.example.com": "https://confluence.example.com",
            "example.com/confluence/": "https://example.com/confluence",
            "https://confluence.example.com/display/KEY/Page": "https://confluence.example.com",
        }
        for site, expected in cases.items():
            with self.subTest(site=site):
                self.assertEqual(build_base_url(site), expected)
        self.assertEqual(get_host("https://x.atlassian.net/wiki/x"), "x.atlassian.net")

    def test_absolute_url_cloud(self):
        site = "x.atlassian.net"
        self.assertEqual(
            absolute_url(site, "/wiki/download/attachments/1/a.png"),
            "https://x.atlassian.net/wiki/download/attachments/1/a.png",
        )
        self.assertEqual(
            absolute_url(site, "/download/attachments/1/a.png"),
            "https://x.atlassian.net/wiki/download/attachments/1/a.png",
        )
        self.assertEqual(
            absolute_url(site, "https://o.com/a.png"), "https://o.com/a.png"
        )

    def test_absolute_url_server(self):
        self.assertEqual(
            absolute_url("c.example.com", "/download/a.png"),
            "https://c.example.com/download/a.png",
        )


class LinkFixerTests(unittest.TestCase):
    def _write(self, path: Path, page_id: str, body: str):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f'<html><head><meta name="ConfluencePageID" content="{page_id}">'
            f"</head><body>{body}</body></html>",
            encoding="utf-8",
        )

    def test_fixes_cloud_and_server_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            body = (
                '<a class="x" href="https://s.atlassian.net/wiki/spaces/T/pages/2/Child">a</a>'
                '<a href="/wiki/spaces/T/pages/2">b</a>'
                '<a href="/pages/viewpage.action?pageId=2">c</a>'
                '<a href="/spaces/T/pages/999/Missing">d</a>'
            )
            self._write(root / "Home.html", "1", body)
            self._write(root / "2-Child" / "Child.html", "2", "")

            dry = ConfluenceLinkFixer(str(root), dry_run=True)
            dry.scan_files()
            dry.process_all_files()
            self.assertEqual(dry.stats["html_links_fixed"], 3)
            self.assertIn("pages/2/Child", (root / "Home.html").read_text())

            fixer = ConfluenceLinkFixer(str(root))
            fixer.scan_files()
            fixer.process_all_files()
            html = (root / "Home.html").read_text()
            self.assertEqual(html.count('href="2-Child/Child.html"'), 3)
            self.assertIn('class="x"', html)
            self.assertIn("/pages/999/Missing", html)
            self.assertEqual(fixer.stats["broken_links"], 1)


if __name__ == "__main__":
    unittest.main()
