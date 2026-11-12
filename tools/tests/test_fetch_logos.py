"""Unit tests for the official-site logo fetcher; no live network calls."""
import gzip
import json
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import fetch_logos


def make_png(width=180, height=180, color=(120, 80, 200, 255)):
    """Build a real, decodable RGBA PNG without depending on Pillow."""
    raw = b"".join(b"\x00" + bytes(color) * width for _ in range(height))

    def chunk(kind, payload):
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(
            ">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9))
            + chunk(b"IEND", b""))


PNG = make_png()
HTML = b"""<!doctype html><html><head>
<meta property="og:image" content="/static/brand.png">
<link rel="apple-touch-icon" href="touch.png">
<link rel="icon" href="favicon-32.png">
</head><body><img class="site-logo" src="logo.svg" alt="Logo"></body></html>"""
SVG = b"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 120 40'><rect width='120' height='40'/></svg>"


def fake_fetcher(*page_urls, images=None):
    calls = []
    pages = set(page_urls)
    images = images or {}

    def fetch(url, timeout, max_bytes):
        calls.append((url, timeout, max_bytes))
        if url in pages:
            return HTML, "text/html"
        if url in images:
            return images[url]
        if url.endswith((".png", ".svg", ".ico")):
            return (SVG if url.endswith(".svg") else PNG), \
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

    def test_candidates_follow_logo_ancestors_and_lazy_data_src(self):
        html = """<div class="site-header"><div class="logo"><img data-src="/img/brand.png"></div></div>
        <div class="u-logo lazyload"><img data-src="/img/lazy.webp" src="/img/blank.gif"></div>"""
        urls = fetch_logos.candidate_urls(html, "https://alpha.example/")
        self.assertIn("https://alpha.example/img/brand.png", urls)
        self.assertIn("https://alpha.example/img/lazy.webp", urls)

    def test_image_extension_sniffs_magic_and_svg(self):
        self.assertEqual(fetch_logos.image_extension(PNG, ""), "png")
        self.assertEqual(fetch_logos.image_extension(PNG, "image/x-icon"), "png")
        self.assertEqual(fetch_logos.image_extension(b"<svg></svg>", "application/octet-stream"), "svg")
        self.assertIsNone(fetch_logos.image_extension(b"<html>404</html>", "text/html"))

    def test_image_extension_and_dimensions_handle_gzip_mislabelled_ico(self):
        compressed = gzip.compress(PNG)
        self.assertEqual(fetch_logos.image_extension(compressed, "image/x-icon"), "png")
        self.assertEqual(fetch_logos.image_dimensions(compressed, "png"), (180, 180))


class FetchLogoTests(unittest.TestCase):
    def test_rejects_wide_banners_unless_url_is_a_declared_icon(self):
        wide = b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", 1200, 630)
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
            self.assertGreaterEqual(result["width"], 1)
            self.assertGreaterEqual(result["height"], 1)

    def test_fetches_gzip_mislabelled_favicon_and_saves_png(self):
        with tempfile.TemporaryDirectory() as tmp:
            fetch, _ = fake_fetcher(
                "https://alpha.example/",
                images={"https://alpha.example/touch.png": (gzip.compress(PNG), "image/x-icon")},
            )
            result = fetch_logos.fetch_logo(record(), root=Path(tmp), fetcher=fetch)
            self.assertEqual(result["status"], "fetched")
            self.assertTrue(result["path"].endswith(".png"))
            self.assertEqual(result["content_type"], "image/png")

    def test_square_icon_is_composed_on_canvas_with_margin(self):
        if not fetch_logos.HAS_PIL:
            self.skipTest("Pillow not installed")
        with tempfile.TemporaryDirectory() as tmp:
            fetch, _ = fake_fetcher("https://alpha.example/")
            result = fetch_logos.fetch_logo(record(), root=Path(tmp), fetcher=fetch)
            path = Path(tmp) / result["path"]
            image = fetch_logos.Image.open(path)
            self.assertEqual(image.size, (fetch_logos.CANVAS_SIZE, fetch_logos.CANVAS_SIZE))
            self.assertEqual(image.getpixel((0, 0))[3], 0)
            self.assertEqual(image.getpixel((128, 128))[3], 255)

    def test_wide_wordmark_keeps_natural_aspect_ratio(self):
        wide = make_png(640, 160)
        with tempfile.TemporaryDirectory() as tmp:
            def fetch(url, timeout, max_bytes):
                if url == "https://alpha.example/":
                    return b'<html><body><img class="brand-logo" src="/wide.png"></body></html>', "text/html"
                if url == "https://alpha.example/wide.png":
                    return wide, "image/png"
                raise ValueError("not found")

            result = fetch_logos.fetch_logo(record(), root=Path(tmp), fetcher=fetch)
            self.assertEqual(result["status"], "fetched")
            self.assertEqual(result["width"] / result["height"], 4.0)
            self.assertGreaterEqual(result["width"], fetch_logos.MIN_LONG_SIDE)
            saved = fetch_logos.Image.open(Path(tmp) / result["path"]) if fetch_logos.HAS_PIL else None
            if saved:
                self.assertEqual(saved.size, (result["width"], result["height"]))

    def test_prefers_better_square_apple_touch_icon_over_very_wide_mark(self):
        wide = make_png(1020, 240)
        square = make_png(180, 180)
        with tempfile.TemporaryDirectory() as tmp:
            def fetch(url, timeout, max_bytes):
                if url == "https://alpha.example/":
                    return (b'<html><head><link rel="apple-touch-icon" href="/touch.png"></head>'
                            b'<body><img class="logo" src="/wide.png"></body></html>'), "text/html"
                if url.endswith("/touch.png"):
                    return square, "image/png"
                if url.endswith("/wide.png"):
                    return wide, "image/png"
                raise ValueError("not found")

            result = fetch_logos.fetch_logo(record(), root=Path(tmp), fetcher=fetch)
            self.assertEqual(result["status"], "fetched")
            self.assertEqual(result["source_url"], "https://alpha.example/touch.png")

    def test_tiny_favicon_does_not_beat_a_legible_wordmark(self):
        wide = make_png(800, 200)
        tiny = make_png(32, 32)
        with tempfile.TemporaryDirectory() as tmp:
            def fetch(url, timeout, max_bytes):
                if url == "https://alpha.example/":
                    return (b'<html><head><link rel="icon" href="/favicon-32.png"></head>'
                            b'<body><img class="logo" src="/wide.png"></body></html>'), "text/html"
                if url.endswith("/favicon-32.png"):
                    return tiny, "image/png"
                if url.endswith("/wide.png"):
                    return wide, "image/png"
                raise ValueError("not found")

            result = fetch_logos.fetch_logo(record(), root=Path(tmp), fetcher=fetch)
            self.assertEqual(result["status"], "fetched")
            self.assertEqual(result["source_url"], "https://alpha.example/wide.png")
            self.assertGreater(result["width"], result["height"])

    def test_clean_svg_source_is_kept_as_svg(self):
        with tempfile.TemporaryDirectory() as tmp:
            def fetch(url, timeout, max_bytes):
                if url == "https://alpha.example/":
                    return b'<html><body><img class="logo" src="/logo.svg"></body></html>', "text/html"
                if url.endswith("/logo.svg"):
                    return SVG, "image/svg+xml"
                raise ValueError("not found")

            result = fetch_logos.fetch_logo(record(), root=Path(tmp), fetcher=fetch)
            self.assertEqual(result["path"], "data/views/assets/logos/alpha.svg")
            self.assertEqual((result["width"], result["height"]), (120, 40))

    def test_keeps_existing_asset_when_a_forced_refetch_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            fetch, _ = fake_fetcher("https://alpha.example/")
            first = fetch_logos.fetch_logo(record(), root=Path(tmp), fetcher=fetch)
            self.assertEqual(first["status"], "fetched")
            path = Path(tmp) / first["path"]

            def broken(url, timeout, max_bytes):
                raise ValueError("offline")

            result = fetch_logos.fetch_logo(record(), root=Path(tmp), fetcher=broken, force=True)
            self.assertEqual(result["status"], "kept")
            self.assertEqual(result["reason"], "homepage_failed")
            self.assertTrue(path.exists())

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
            self.assertTrue(all(item.get("width") and item.get("height") for item in manifest["entries"]))

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

    def test_normalize_assets_preserves_natural_aspect_and_updates_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            logo_dir = root / fetch_logos.LOGO_DIR
            logo_dir.mkdir(parents=True)
            (logo_dir / "alpha.png").write_bytes(make_png(80, 40))
            (root / "data/companies").mkdir(parents=True)
            (root / "data/companies/alpha.json").write_text(json.dumps(record(), ensure_ascii=False))
            fetch_logos.save_manifest([{
                "id": "alpha", "status": "fetched", "path": "data/views/assets/logos/alpha.png",
                "width": 80, "height": 40, "fetched_at": "2026-01-01T00:00:00+00:00",
            }], root=root)
            results = fetch_logos.normalize_assets(root=root)
            self.assertEqual(results[0]["status"], "fetched")
            self.assertGreaterEqual(results[0]["width"], fetch_logos.MIN_LONG_SIDE)
            self.assertEqual(results[0]["width"] / results[0]["height"], 2.0)
            manifest = json.loads((root / fetch_logos.MANIFEST).read_text())
            self.assertEqual(manifest["entries"][0]["fetched_at"], "2026-01-01T00:00:00+00:00")
            self.assertEqual(manifest["entries"][0]["width"], results[0]["width"])

    def test_normalize_assets_handles_extension_change_and_missing_manifest_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            logo_dir = root / fetch_logos.LOGO_DIR
            logo_dir.mkdir(parents=True)
            # A PNG payload stored with a legacy .ico suffix exercises the
            # delete-then-rename path that used to crash while reading mtime.
            (logo_dir / "alpha.ico").write_bytes(make_png(64, 64))
            (root / "data/companies").mkdir(parents=True)
            (root / "data/companies/alpha.json").write_text(json.dumps(record(), ensure_ascii=False))
            results = fetch_logos.normalize_assets(root=root)
            self.assertEqual(results[0]["status"], "fetched")
            self.assertTrue(results[0]["path"].endswith(".png"))
            self.assertFalse((logo_dir / "alpha.ico").exists())
            self.assertTrue((root / results[0]["path"]).exists())
            manifest = json.loads((root / fetch_logos.MANIFEST).read_text())
            self.assertEqual(manifest["entries"][0]["path"], results[0]["path"])


if __name__ == "__main__":
    unittest.main()
