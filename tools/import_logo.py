"""Import a single, human-verified logo from an explicit URL.

``fetch_logos.py`` guesses the logo from a homepage, which can pick a customer
case image, a QR code or a partner wall instead of the brand mark.  When a
researcher has opened the official page and identified the real logo asset,
this tool stores exactly that asset, normalizes it for the dashboard and
records the source in the logo manifest.

Only official sources belong here: the company's own website, or its own
official account/announcement page.  Third-party logo CDNs are not allowed.

Usage::

    python3 tools/import_logo.py --id 4paradigm \
        --url https://www.4paradigm.com/images/logo.png \
        --note "官网页头 logo（人工核对）"
"""
import argparse
import json
import ssl
import sys
from datetime import datetime, timezone
from pathlib import Path

import fetch_logos as logos


def import_logo(company_id, url, note=None, root=Path(logos.ROOT), referer=None, insecure=False,
                invert=False):
    record_path = Path(root) / "data" / "companies" / f"{company_id}.json"
    if not record_path.exists():
        raise SystemExit(f"unknown company id: {company_id}")
    record = json.loads(record_path.read_text(encoding="utf-8"))

    # CDNs behind the official site often require the site as Referer, and some
    # newer brand domains ship an incomplete certificate chain.
    logos._FETCH_CONTEXT.referer = referer or logos.website_for(record)
    original_context = ssl.create_default_context
    if insecure:
        ssl.create_default_context = lambda *a, **k: ssl._create_unverified_context()
    try:
        data, content_type = logos.fetch_url(url, logos.DEFAULT_TIMEOUT, logos.MAX_IMAGE_BYTES)
    finally:
        if insecure:
            ssl.create_default_context = original_context
    extension = logos.image_extension(data, content_type)
    if not extension:
        raise SystemExit(f"not a recognized image: {url} ({content_type})")

    if extension == "svg":
        if invert:
            data = logos._invert_white_svg(data)
        normalized = logos.normalize_svg(data)
        if normalized:
            payload, (width, height) = normalized
        else:
            payload = data
            dimensions = logos.image_dimensions(data, "svg") or (0, 0)
            width, height = int(dimensions[0]), int(dimensions[1])
        extension, content_type = "svg", "image/svg+xml"
    else:
        decoded = logos._decode_image(data, content_type)
        if not decoded:
            raise SystemExit(f"cannot decode image: {url}")
        image = decoded.get("image")
        if image is None:  # Pillow missing: store the source bytes untouched.
            payload, extension, content_type = data, decoded["ext"], content_type
            width, height = decoded["width"], decoded["height"]
        else:
            payload, (width, height) = logos.normalize_raster(
                image, invert_white=invert or decoded.get("white_like", False))
            extension, content_type = "png", "image/png"

    path = logos._store_asset(root, company_id, payload, extension)
    manifest = logos.load_manifest(root)
    entries = {entry["id"]: entry for entry in manifest.get("entries", [])}
    entries[company_id] = {
        "id": company_id,
        "status": "fetched",
        "source_url": url,
        "website": logos.website_for(record),
        "fetched_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "content_type": content_type,
        "bytes": len(payload),
        "width": width,
        "height": height,
        "path": path,
        "method": "manual_verified",
        "note": note,
    }
    logos.save_manifest(list(entries.values()), root)
    return entries[company_id]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--id", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--note", default=None)
    parser.add_argument("--referer", default=None, help="Referer header; defaults to the company website")
    parser.add_argument("--insecure", action="store_true", help="skip TLS verification for a broken chain")
    parser.add_argument("--invert", action="store_true", help="invert a white/light brand mark for light backgrounds")
    args = parser.parse_args(argv)
    entry = import_logo(args.id, args.url, args.note, referer=args.referer, insecure=args.insecure,
                        invert=args.invert)
    print(json.dumps(entry, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
