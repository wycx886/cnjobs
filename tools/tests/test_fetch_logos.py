"""Unit tests for the official-site logo fetcher; no live network calls."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import fetch_logos

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
HTML = b"""<!doctype html><html><head>
<meta property="og:image" content="/static/brand.png">
<link rel="apple-touch-icon" href="touch.png">
<link rel="icon" href="favicon-32.png">
</head><body><img class="site-logo" src="logo.svg" alt="Logo"></body></html>"""


def fake_fetcher(*page_urls):
    calls = []
    pages = set(page_urls)

    def fetch(url, timeout, max_bytes):
        calls.append((url, timeout, max_bytes))
        if url in pages:
            return HTML, "text/html"
        if url.endswith((".png", ".svg", ".ico")):
            return (b"<svg xmlns='http://www.w3.org/2000/svg'></svg>" if url.endswith(".svg") else PNG), \
                ("image/svg+xml" if url.endswith(".svg") else "image/png")
        raise ValueError("not an image")

    return fetch, calls


def record(company_id="alpha", website="https://alpha.example/", player_group="new_entrant",
           organization_type="operating_organization"):
    return {
        "id": company_id,
        "name": "阿尔法",
        "organization_type": organization_type,
        "targeting": {"player_group": player_group},
        "contacts": {"website": website},
        "channels": [],
    }


class CandidateTests(unittest.TestCase):
    def test_candidates_prefer_icons_then_brand_images_and_resolve_relative_urls(self):
        urls = fetch_logos.candidate_urls(HTML.decode("utf-8"), "https://alpha.example/about/")
        self.assertEqual(urls[0], "https://alpha.example/about/touch.png")
        self.assertIn("https://alpha.example/static/brand.png", urls)
        self.assertIn("https://alpha.example/about/logo.svg", urls)
        self.assertEqual(urls[-1], "https://alpha.example/favicon.ico")
        self.assertEqual(len(urls), len(set(urls)))

    def test_image_extension_sniffs_magic_and_svg(self):
        self.assertEqual(fetch_logos.image_extension(PNG, ""), "png")
        self.assertEqual(fetch_logos.image_extension(PNG, "image/x-icon"), "png")
        self.assertEqual(fetch_logos.image_extension(b"<svg></svg>", "application/octet-stream"), "svg")
        self.assertIsNone(fetch_logos.image_extension(b"<html>404</html>", "text/html"))


class FetchLogoTests(unittest.TestCase):
    def test_rejects_wide_banners_unless_url_is_a_declared_icon(self):
        import struct as _struct
        wide = b"\x89PNG\r\n\x1a\n" + _struct.pack(">I", 13) + b"IHDR" + _struct.pack(">II", 1200, 630)
        self.assertTrue(fetch_logos.looks_like_banner(wide, "png", "https://alpha.example/og.png"))
        self.assertFalse(fetch_logos.looks_like_banner(wide, "png", "https://alpha.example/apple-icon.png"))

    def test_fetches_first_usable_official_image_without_third_party_cdn(self):
        with tempfile.TemporaryDirectory() as tmp:
            fetch, calls = fake_fetcher("https://alpha.example/about/")
            result = fetch_logos.fetch_logo(record(website="https://alpha.example/about/"), root=Path(tmp), fetcher=fetch)
            self.assertEqual(result["status"], "fetched")
            self.assertEqual(result["source_url"], "https://alpha.example/about/touch.png")
            self.assertTrue(result["path"].startswith("data/views/assets/logos/alpha."))
            self.assertTrue((Path(tmp) / result["path"]).exists())
            self.assertNotIn("clearbit", result["source_url"].lower())
            self.assertEqual(calls[0][2], fetch_logos.MAX_HTML_BYTES)

    def test_skips_without_website_or_usable_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            fetch, _ = fake_fetcher()
            result = fetch_logos.fetch_logo(record(website=None), root=Path(tmp), fetcher=fetch)
            self.assertEqual(result["status"], "skipped")
            self.assertEqual(result["reason"], "no_website")

            def only_html(url, timeout, max_bytes):
                return b"<html><head><title>no logo</title></head></html>", "text/html"

            result = fetch_logos.fetch_logo(record(), root=Path(tmp), fetcher=only_html)
            self.assertEqual(result["status"], "skipped")
            self.assertEqual(result["reason"], "no_usable_image")

    def test_is_idempotent_when_a_logo_file_already_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            fetch, calls = fake_fetcher("https://alpha.example/")
            first = fetch_logos.fetch_logo(record(), root=Path(tmp), fetcher=fetch)
            self.assertEqual(first["status"], "fetched")
            count = len(calls)
            second = fetch_logos.fetch_logo(record(), root=Path(tmp), fetcher=fetch)
            self.assertEqual(second["status"], "fetched")
            self.assertEqual(second["reason"], "already_fetched")
            self.assertEqual(len(calls), count)

    def test_fetch_all_targets_startups_and_investment_firms_with_websites(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            companies = root / "data/companies"
            companies.mkdir(parents=True)
            (companies / "alpha.json").write_text(json.dumps(record(), ensure_ascii=False))
            (companies / "beta.json").write_text(json.dumps(record("beta", player_group="incumbent"), ensure_ascii=False))
            (companies / "gamma.json").write_text(json.dumps(
                record("gamma", website="https://gamma.example/", organization_type="investment_firm"), ensure_ascii=False))
            (companies / "delta.json").write_text(json.dumps(
                record("delta", website=None, organization_type="investment_firm"), ensure_ascii=False))
            fetch, _ = fake_fetcher("https://alpha.example/", "https://gamma.example/")
            results = fetch_logos.fetch_all(root=root, workers=1, fetcher=fetch)
            self.assertEqual([item["id"] for item in results], ["alpha", "gamma"])
            manifest = json.loads((root / fetch_logos.MANIFEST).read_text())
            self.assertEqual([item["id"] for item in manifest["entries"]], ["alpha", "gamma"])
            self.assertTrue(all(item["status"] == "fetched" for item in manifest["entries"]))

    def test_id_filter_includes_investment_firms_even_without_a_website(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            companies = root / "data/companies"
            companies.mkdir(parents=True)
            (companies / "alpha.json").write_text(json.dumps(record(), ensure_ascii=False))
            (companies / "gamma.json").write_text(json.dumps(
                record("gamma", website="https://gamma.example/", organization_type="investment_firm"), ensure_ascii=False))
            (companies / "delta.json").write_text(json.dumps(
                record("delta", website=None, organization_type="investment_firm"), ensure_ascii=False))
            fetch, _ = fake_fetcher("https://gamma.example/")
            results = fetch_logos.fetch_all(root=root, ids=["gamma"], workers=1, fetcher=fetch)
            self.assertEqual([item["id"] for item in results], ["gamma"])
            self.assertEqual(results[0]["status"], "fetched")

            results = fetch_logos.fetch_all(root=root, ids=["delta"], workers=1, fetcher=fetch)
            self.assertEqual(results[0]["status"], "skipped")
            self.assertEqual(results[0]["reason"], "no_website")


if __name__ == "__main__":
    unittest.main()
