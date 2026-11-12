import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import fetch_logos  # noqa: E402
import import_logo  # noqa: E402


def _png_bytes(width=96, height=96):
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGBA", (width, height), (20, 120, 220, 255)).save(buffer, format="PNG")
    return buffer.getvalue()


class ImportLogoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        company_dir = self.root / "data" / "companies"
        company_dir.mkdir(parents=True)
        (company_dir / "demo.json").write_text(
            json.dumps({"id": "demo", "name": "示例", "contacts": {"website": "https://demo.example"}}),
            encoding="utf-8",
        )
        manifest = self.root / "data" / "views" / "assets" / "logos" / "manifest.json"
        manifest.parent.mkdir(parents=True)
        manifest.write_text(json.dumps({"schema_version": 1, "entries": [
            {"id": "demo", "status": "fetched", "path": "data/views/assets/logos/demo.png"}
        ]}), encoding="utf-8")
        self._original_fetch = fetch_logos.fetch_url
        fetch_logos.fetch_url = lambda url, timeout, max_bytes: (_png_bytes(), "image/png")

    def tearDown(self):
        fetch_logos.fetch_url = self._original_fetch
        self.tmp.cleanup()

    def test_import_overwrites_file_and_manifest(self):
        entry = import_logo.import_logo("demo", "https://demo.example/logo.png", "测试", root=self.root)
        self.assertEqual(entry["status"], "fetched")
        self.assertEqual(entry["method"], "manual_verified")
        self.assertEqual(entry["source_url"], "https://demo.example/logo.png")
        self.assertTrue((self.root / entry["path"]).exists())
        manifest = json.loads((self.root / "data/views/assets/logos/manifest.json").read_text())
        self.assertEqual(manifest["entries"][0]["source_url"], "https://demo.example/logo.png")

    def test_unknown_company_fails(self):
        with self.assertRaises(SystemExit):
            import_logo.import_logo("missing", "https://demo.example/logo.png", root=self.root)

    def test_non_image_payload_fails(self):
        fetch_logos.fetch_url = lambda url, timeout, max_bytes: (b"<html>nope</html>", "text/html")
        with self.assertRaises(SystemExit):
            import_logo.import_logo("demo", "https://demo.example/x", root=self.root)


if __name__ == "__main__":
    unittest.main()
