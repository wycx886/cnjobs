"""Fetch public organization logos from official websites into generated view assets.

Targets startup operating companies and investment firms with an official website.
"""
import argparse
import json
import re
import socket
import struct
import ssl
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
LOGO_DIR = Path("data/views/assets/logos")
MANIFEST = LOGO_DIR / "manifest.json"
MAX_IMAGE_BYTES = 512 * 1024
MAX_HTML_BYTES = 2 * 1024 * 1024
DEFAULT_TIMEOUT = 15
USER_AGENT = "cnjobs research logo fetcher (public official sites; contact via repository)"
IMAGE_EXTENSIONS = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/gif": "gif",
    "image/webp": "webp",
    "image/svg+xml": "svg",
    "image/x-icon": "ico",
    "image/vnd.microsoft.icon": "ico",
    "image/ico": "ico",
}
MAGIC = (
    (b"\x89PNG\r\n\x1a\n", "png", "image/png"),
    (b"\xff\xd8\xff", "jpg", "image/jpeg"),
    (b"GIF87a", "gif", "image/gif"),
    (b"GIF89a", "gif", "image/gif"),
    (b"\x00\x00\x01\x00", "ico", "image/x-icon"),
)


class _AssetParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.candidates = []
        self._rank = {}

    def _add(self, url, rank):
        if not url:
            return
        self.candidates.append((rank, url))

    def handle_starttag(self, tag, attrs):
        values = {key.lower(): (value or "") for key, value in attrs}
        if tag == "link":
            rel = values.get("rel", "").lower()
            if "apple-touch-icon" in rel:
                self._add(values.get("href"), 10)
            elif "icon" in rel:
                self._add(values.get("href"), 20)
            return
        if tag == "img":
            haystack = " ".join(values.get(key, "") for key in ("src", "class", "id", "alt")).lower()
            if "logo" in haystack or "brand" in haystack:
                self._add(values.get("src"), 30)
            return
        if tag == "meta":
            key = (values.get("property") or values.get("name") or "").lower()
            if key in {"og:image", "og:image:url"}:
                self._add(values.get("content"), 40)
            elif key in {"twitter:image", "twitter:image:src"}:
                self._add(values.get("content"), 45)
            return


def candidate_urls(html, base_url):
    parser = _AssetParser()
    try:
        parser.feed(html or "")
    except Exception:
        pass
    seen = set()
    ordered = []
    for rank, raw in sorted(parser.candidates, key=lambda item: item[0]):
        value = raw.strip()
        if not value or value.startswith(("data:", "javascript:", "#")):
            continue
        absolute = urljoin(base_url, value)
        if not absolute.lower().startswith(("http://", "https://")):
            continue
        if absolute in seen:
            continue
        seen.add(absolute)
        ordered.append(absolute)
    fallback = urljoin(base_url, "/favicon.ico")
    if fallback not in seen:
        ordered.append(fallback)
    return ordered


def website_for(record):
    contacts = record.get("contacts") or {}
    if contacts.get("website"):
        return contacts["website"]
    for channel in record.get("channels") or []:
        if channel.get("platform") == "website" and channel.get("url"):
            return channel["url"]
    return None


def _is_private_host(hostname):
    host = (hostname or "").lower()
    if host in {"localhost", "0.0.0.0", "::1"}:
        return True
    if re.fullmatch(r"127(?:\.\d{1,3}){3}", host):
        return True
    if re.fullmatch(r"10(?:\.\d{1,3}){3}", host):
        return True
    if re.fullmatch(r"192\.168(?:\.\d{1,3}){2}", host):
        return True
    if re.fullmatch(r"172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2}", host):
        return True
    return False


def fetch_url(url, timeout=DEFAULT_TIMEOUT, max_bytes=MAX_IMAGE_BYTES):
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or _is_private_host(parsed.hostname):
        raise ValueError("unsupported public URL")
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "image/*,text/html;q=0.8,*/*;q=0.5"})
    context = ssl.create_default_context()
    with build_opener().open(request, timeout=timeout) as response:
        content_type = (response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        data = response.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError("file too large")
    return data, content_type


def image_extension(data, content_type):
    content_type = (content_type or "").lower()
    for magic, extension, _ in MAGIC:
        if data.startswith(magic):
            return extension
    head = data[:512].lstrip().lower()
    if head.startswith(b"<svg") or (head.startswith(b"<?xml") and b"<svg" in head):
        return "svg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if content_type in IMAGE_EXTENSIONS:
        return IMAGE_EXTENSIONS[content_type]
    return None


def image_dimensions(data, extension):
    try:
        if extension == "png" and data[12:16] == b"IHDR":
            return struct.unpack(">II", data[16:24])
        if extension == "gif":
            return struct.unpack("<HH", data[6:10])
        if extension == "ico":
            count = struct.unpack("<H", data[4:6])[0]
            if count:
                width = data[6] or 256
                height = data[7] or 256
                return width, height
        if extension == "webp" and data[12:16] == b"VP8X":
            return (int.from_bytes(data[24:27], "little") + 1,
                    int.from_bytes(data[27:30], "little") + 1)
        if extension == "svg":
            match = re.search(rb'viewBox=["\']\s*[-\d.]+\s+[-\d.]+\s+([\d.]+)\s+([\d.]+)', data[:2000])
            if match:
                return float(match.group(1)), float(match.group(2))
        if extension in {"jpg", "jpeg"}:
            index = 2
            while index < len(data) - 9:
                if data[index] != 0xFF:
                    index += 1
                    continue
                marker = data[index + 1]
                length = struct.unpack(">H", data[index + 2:index + 4])[0]
                if marker in {0xC0, 0xC1, 0xC2, 0xC3}:
                    height, width = struct.unpack(">HH", data[index + 5:index + 9])
                    return width, height
                index += 2 + length
    except (IndexError, struct.error, ValueError):
        return None
    return None


def looks_like_banner(data, extension, source_url):
    lowered = source_url.lower()
    if any(token in lowered for token in ("icon", "favicon", "logo")):
        return False
    dimensions = image_dimensions(data, extension)
    if not dimensions:
        return False
    width, height = dimensions
    if not width or not height:
        return False
    ratio = max(width, height) / min(width, height)
    return max(width, height) >= 500 and ratio >= 1.8


def existing_logo(root, company_id):
    directory = Path(root) / LOGO_DIR
    for path in sorted(directory.glob(company_id + ".*")):
        if path.suffix.lower().lstrip(".") in set(IMAGE_EXTENSIONS.values()):
            return path
    return None


def fetch_logo(record, root=ROOT, fetcher=fetch_url, timeout=DEFAULT_TIMEOUT, force=False):
    company_id = record["id"]
    existing = existing_logo(root, company_id)
    if existing and not force:
        return {
            "id": company_id,
            "status": "fetched",
            "reason": "already_fetched",
            "path": (LOGO_DIR / existing.name).as_posix(),
        }
    website = website_for(record)
    if not website:
        return {"id": company_id, "status": "skipped", "reason": "no_website"}
    try:
        html_bytes, content_type = fetcher(website, timeout, MAX_HTML_BYTES)
    except (HTTPError, URLError, socket.timeout, TimeoutError, ssl.SSLError, ValueError, OSError) as error:
        return {"id": company_id, "status": "skipped", "reason": "homepage_failed", "website": website,
                "detail": type(error).__name__}
    html = html_bytes.decode("utf-8", errors="ignore")
    candidates = candidate_urls(html, website)
    if not candidates:
        return {"id": company_id, "status": "skipped", "reason": "no_candidates", "website": website}
    for candidate in candidates:
        try:
            data, image_type = fetcher(candidate, timeout, MAX_IMAGE_BYTES)
        except (HTTPError, URLError, socket.timeout, TimeoutError, ssl.SSLError, ValueError, OSError) as error:
            continue
        extension = image_extension(data, image_type)
        if not extension or looks_like_banner(data, extension, candidate):
            continue
        directory = Path(root) / LOGO_DIR
        directory.mkdir(parents=True, exist_ok=True)
        filename = company_id + "." + extension
        for old in directory.glob(company_id + ".*"):
            if old.suffix.lower().lstrip(".") in set(IMAGE_EXTENSIONS.values()) and old.name != filename:
                old.unlink()
        (directory / filename).write_bytes(data)
        return {
            "id": company_id,
            "status": "fetched",
            "source_url": candidate,
            "website": website,
            "fetched_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "content_type": image_type or None,
            "bytes": len(data),
            "path": (LOGO_DIR / filename).as_posix(),
        }
    return {"id": company_id, "status": "skipped", "reason": "no_usable_image", "website": website}


def logo_records(root=ROOT, ids=None):
    """Select startups plus investment firms, keeping --id usable for either type."""
    directory = Path(root) / "data/companies"
    wanted = set(ids) if ids else None
    records = []
    for path in sorted(directory.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        organization_type = record.get("organization_type")
        is_startup = organization_type == "operating_organization" and \
            (record.get("targeting") or {}).get("player_group") == "new_entrant"
        is_investment_firm = organization_type == "investment_firm"
        if not (is_startup or is_investment_firm):
            continue
        if wanted is not None:
            if record["id"] not in wanted:
                continue
        elif is_investment_firm and not website_for(record):
            # Default sweep only considers firms with an official site; --id can still report no_website.
            continue
        records.append(record)
    return records


def load_manifest(root=ROOT):
    path = Path(root) / MANIFEST
    if not path.exists():
        return {"schema_version": 1, "entries": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {"schema_version": 1, "entries": []}
    data.setdefault("entries", [])
    return data


def save_manifest(entries, root=ROOT):
    path = Path(root) / MANIFEST
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema_version": 1, "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
               "entries": sorted(entries, key=lambda item: item["id"])}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def fetch_all(root=ROOT, ids=None, timeout=DEFAULT_TIMEOUT, workers=8, fetcher=fetch_url, force=False):
    records = logo_records(root, ids=ids)
    previous = {entry["id"]: entry for entry in load_manifest(root)["entries"]}
    results = []

    def run(record):
        result = fetch_logo(record, root=root, fetcher=fetcher, timeout=timeout, force=force)
        merged = dict(previous.get(record["id"], {}))
        merged.update({key: value for key, value in result.items() if value is not None})
        return merged

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        results.extend(pool.map(run, records))
    merged_entries = dict(previous)
    merged_entries.update({entry["id"]: entry for entry in results})
    keep = {Path(entry["path"]).name for entry in merged_entries.values()
            if entry.get("status") == "fetched" and entry.get("path")}
    directory = Path(root) / LOGO_DIR
    if directory.exists():
        for path in directory.iterdir():
            if path.is_file() and path.suffix.lower().lstrip(".") in set(IMAGE_EXTENSIONS.values()) and path.name not in keep:
                path.unlink()
    save_manifest(list(merged_entries.values()), root=root)
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--id", action="append", dest="ids", help="fetch only one company id (repeatable)")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--force", action="store_true", help="re-fetch even when a logo file exists")
    args = parser.parse_args(argv)
    results = fetch_all(root=args.root, ids=args.ids, timeout=args.timeout, workers=args.workers, force=args.force)
    fetched = sum(1 for item in results if item.get("status") == "fetched")
    skipped = len(results) - fetched
    print("Logos fetched %d, skipped %d. Manifest: %s" % (fetched, skipped, (Path(args.root) / MANIFEST)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
