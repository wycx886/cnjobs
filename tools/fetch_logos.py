"""Fetch and normalize public organization logos from official websites.

Targets startup operating companies and investment firms with an official
website.  Candidates are parsed from the official homepage (apple-touch-icon,
declared icons, brand images, og:image, /favicon.ico), fetched in bounded
batches and scored by decodability, dimensions and aspect ratio.

Raster assets are normalized for the dashboard:

* square-ish (0.7 <= width / height <= 1.6): trimmed, upscaled and composed on
  a transparent 256x256 canvas with an even margin;
* wide or tall marks: trimmed, upscaled to at least 320px on the long side and
  saved at their natural aspect ratio so CSS/JS can widen the display frame;
* clean SVG sources are kept as SVG (vector, resolution independent).
"""
import argparse
import gzip
import io
import json
import re
import socket
import ssl
import struct
import sys
import threading
import time
import zlib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, unquote, urljoin, urlparse
from urllib.request import HTTPSHandler, Request, build_opener

try:  # Pillow is optional: without it the fetcher still stores the source bytes.
    from PIL import Image, ImageChops

    Image.MAX_IMAGE_PIXELS = 80_000_000
    HAS_PIL = True
except Exception:  # pragma: no cover - exercised only in minimal environments
    Image = None
    ImageChops = None
    HAS_PIL = False

ROOT = Path(__file__).resolve().parents[1]
LOGO_DIR = Path("data/views/assets/logos")
MANIFEST = LOGO_DIR / "manifest.json"
MAX_IMAGE_BYTES = 2 * 1024 * 1024
MAX_DECOMPRESSED_BYTES = 24 * 1024 * 1024
MAX_HTML_BYTES = 2 * 1024 * 1024
MAX_CANDIDATES = 8
DEFAULT_TIMEOUT = 12
CANVAS_SIZE = 256
CANVAS_MARGIN = 16
SQUARE_ASPECT_MIN = 0.7
SQUARE_ASPECT_MAX = 1.6
MIN_LONG_SIDE = 320
MAX_LONG_SIDE = 1600
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 cnjobs-research"
)
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
ASSET_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp", "svg", "ico"}
MAGIC = (
    (b"\x89PNG\r\n\x1a\n", "png", "image/png"),
    (b"\xff\xd8\xff", "jpg", "image/jpeg"),
    (b"GIF87a", "gif", "image/gif"),
    (b"GIF89a", "gif", "image/gif"),
    (b"\x00\x00\x01\x00", "ico", "image/x-icon"),
)
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param",
             "source", "track", "wbr"}
RETRY_STATUS = {429, 500, 502, 503, 504}

_THROTTLE_LOCK = threading.Lock()
_HOST_LAST_REQUEST = {}
_FETCH_CONTEXT = threading.local()


class _AssetParser(HTMLParser):
    """Collect logo-ish asset URLs, remembering logo-class ancestors for lazy imgs."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.candidates = []
        self._stack = []

    def _add(self, url, rank):
        if url:
            self.candidates.append((rank, url))

    def _context_tokens(self):
        tokens = set()
        for _, context in self._stack[-4:]:
            tokens.update(context.split())
        return tokens

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        values = {key.lower(): (value or "") for key, value in attrs}
        if tag == "link":
            rel = values.get("rel", "").lower()
            if "apple-touch-icon" in rel:
                self._add(values.get("href"), 10)
            elif "icon" in rel:
                self._add(values.get("href"), 15)
            elif "mask-icon" in rel:
                self._add(values.get("href"), 18)
            elif "preload" in rel and values.get("as", "").lower() == "image":
                # Next.js and similar frameworks expose the header logo only as a preload.
                source = values.get("imagesrcset") or values.get("srcset") or values.get("href") or ""
                if _logo_marker(source):
                    url = _largest_srcset_url(values.get("imagesrcset") or values.get("srcset") or "")
                    self._add(url or values.get("href"), 25)
            return
        if tag == "meta":
            key = (values.get("property") or values.get("name") or "").lower()
            if key in {"og:image", "og:image:url", "og:image:secure_url"}:
                self._add(values.get("content"), 40)
            elif key in {"twitter:image", "twitter:image:src"}:
                self._add(values.get("content"), 45)
            return
        if tag == "img":
            own = _class_tokens(values.get("class"), values.get("id"))
            context = self._context_tokens()
            excluded = bool((own | context) & EXCLUDE_CLASS_TOKENS)
            src = values.get("data-src") or values.get("data-original") or values.get("data-lazy-src") \
                or values.get("src") or ""
            alt = values.get("alt") or ""
            srcset = values.get("data-srcset") or values.get("srcset") or ""
            marked = _logo_marker(src) or _logo_marker(alt) or _has_logo_token(own) \
                or _has_logo_token(context) or _logo_marker(srcset)
            if marked and not excluded:
                for key in ("data-src", "data-original", "data-lazy-src", "src"):
                    self._add(values.get(key), 30)
                if srcset:
                    self._add(_largest_srcset_url(srcset), 30)
            return
        if tag not in VOID_TAGS:
            context = " ".join(sorted(_class_tokens(values.get("class"), values.get("id"))))
            self._stack.append((tag, context))
            if len(self._stack) > 12:
                self._stack.pop(0)

    def handle_endtag(self, tag):
        tag = tag.lower()
        for index in range(len(self._stack) - 1, -1, -1):
            if self._stack[index][0] == tag:
                del self._stack[index:]
                break


LOGO_CLASS_TOKENS = {
    "logo", "brand", "navbar-brand", "site-logo", "header-logo", "footer-logo",
    "logo-wrap", "logo-wrapper", "logo-container", "logocontainer", "logo-box",
    "logo-area", "logo-img", "logo-image", "logo-pic", "logo-top", "logo-link",
    "brand-logo", "main-logo", "nav-logo",
}
EXCLUDE_CLASS_TOKENS = {
    "banner", "banner-logo", "hero", "hero-logo", "slider", "carousel", "swiper",
    "cover", "partner", "partners", "client", "clients", "friend", "friends",
    "case", "cases", "product", "products", "news", "logo-cloud", "logo-wall",
    "brand-wall", "brand-cloud",
}


def _class_tokens(*values):
    tokens = set()
    for value in values:
        for token in re.split(r"\s+", (value or "").lower().replace("_", "-")):
            if token:
                tokens.add(token)
    return tokens


def _logo_marker(value):
    lowered = (value or "").lower()
    return "logo" in lowered or "brand" in lowered


def _has_logo_token(tokens):
    """u-logo, footer-logo, logo-wrap etc. mark a logo container; ring-brand does not."""
    for token in tokens:
        if token in LOGO_CLASS_TOKENS:
            return True
        if "logo" in re.split(r"[-/]", token):
            return True
    return False


def _unwrap_query_url(url):
    """Next.js image endpoints carry the original asset in the url= query param."""
    parsed = urlparse(url)
    if not parsed.query:
        return url
    inner = parse_qs(parsed.query).get("url", [None])[0]
    if inner and re.search(r"\.(?:png|jpe?g|webp|svg|gif|ico)(?:\?|$)", inner, re.IGNORECASE):
        return unquote(inner)
    return url


def _largest_srcset_url(srcset):
    best_url, best_score = "", -1.0
    for part in (srcset or "").split(","):
        pieces = part.strip().split()
        if not pieces:
            continue
        url = _unwrap_query_url(pieces[0])
        score = 0.0
        if len(pieces) > 1:
            descriptor = pieces[1].lower()
            match = re.match(r"([\d.]+)(w|x)$", descriptor)
            if match:
                score = float(match.group(1))
        if url and score > best_score:
            best_url, best_score = url, score
    return best_url


def _candidate_entries(html, base_url, with_fallback=True):
    parser = _AssetParser()
    try:
        parser.feed(html or "")
    except Exception:
        pass
    seen = set()
    ordered = []
    for rank, raw in sorted(parser.candidates, key=lambda item: item[0]):
        value = (raw or "").strip()
        if not value or value.startswith(("data:", "javascript:", "#", "blob:")):
            continue
        absolute = urljoin(base_url, value)
        if not absolute.lower().startswith(("http://", "https://")):
            continue
        if absolute in seen:
            continue
        seen.add(absolute)
        ordered.append((absolute, rank))
    if with_fallback:
        fallback = urljoin(base_url, "/favicon.ico")
        if fallback not in seen:
            ordered.append((fallback, 50))
    return ordered


def candidate_urls(html, base_url):
    return [url for url, _ in _candidate_entries(html, base_url)]


def _fallback_candidates(website):
    """Standard locations worth trying when the homepage itself is unreachable."""
    return [
        (urljoin(website, "/apple-touch-icon.png"), 55),
        (urljoin(website, "/apple-touch-icon-precomposed.png"), 55),
        (urljoin(website, "/favicon.ico"), 50),
    ]


def _meta_refresh_url(html, base_url):
    for tag in re.findall(r"<meta\b[^>]*>", html or "", re.IGNORECASE):
        if not re.search(r"http-equiv\s*=\s*[\"']?refresh", tag, re.IGNORECASE):
            continue
        content = re.search(r"content\s*=\s*[\"']([^\"']+)[\"']", tag, re.IGNORECASE)
        if not content:
            continue
        target = re.search(r"url\s*=\s*([^;]+)", content.group(1), re.IGNORECASE)
        if target:
            value = target.group(1).strip().strip("\"'")
            if value:
                return urljoin(base_url, value)
    return None


def website_for(record):
    contacts = record.get("contacts") or {}
    if contacts.get("website"):
        return contacts["website"]
    for channel in record.get("channels") or []:
        if channel.get("platform") == "website" and channel.get("url"):
            return channel["url"]
    return None


def _normalized_website(website):
    website = (website or "").strip()
    if not website:
        return None
    if not website.lower().startswith(("http://", "https://")):
        website = "https://" + website
    return website


def _is_private_host(hostname):
    host = (hostname or "").lower()
    if host in {"localhost", "0.0.0.0", "::1", "[::1]"}:
        return True
    if re.fullmatch(r"127(?:\.\d{1,3}){3}", host):
        return True
    if re.fullmatch(r"10(?:\.\d{1,3}){3}", host):
        return True
    if re.fullmatch(r"192\.168(?:\.\d{1,3}){2}", host):
        return True
    if re.fullmatch(r"172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2}", host):
        return True
    if re.fullmatch(r"169\.254(?:\.\d{1,3}){2}", host):
        return True
    return False


def _throttle(host, interval=0.2):
    """Keep per-host requests polite even when several workers run."""
    with _THROTTLE_LOCK:
        last = _HOST_LAST_REQUEST.get(host, 0.0)
        wait = interval - (time.monotonic() - last)
        if wait > 0:
            time.sleep(wait)
        _HOST_LAST_REQUEST[host] = time.monotonic()


def fetch_url(url, timeout=DEFAULT_TIMEOUT, max_bytes=MAX_IMAGE_BYTES):
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or _is_private_host(parsed.hostname):
        raise ValueError("unsupported public URL")
    _throttle(parsed.hostname)
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "image/avif,image/webp,image/png,image/svg+xml,image/*,text/html;q=0.8,*/*;q=0.5",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    referer = getattr(_FETCH_CONTEXT, "referer", None)
    if referer:
        headers["Referer"] = referer
    request = Request(url, headers=headers)
    context = ssl.create_default_context()
    last_error = None
    for attempt in range(2):
        try:
            with build_opener(HTTPSHandler(context=context)).open(request, timeout=timeout) as response:
                final = urlparse(response.geturl())
                if final.hostname and _is_private_host(final.hostname):
                    raise ValueError("unsupported public URL")
                content_type = (response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
                content_encoding = (response.headers.get("Content-Encoding") or "").lower()
                data = response.read(max_bytes + 1)
            if any(token in content_encoding for token in ("gzip", "x-gzip")) or data.startswith(b"\x1f\x8b"):
                data = _gunzip(data)
            if len(data) > max_bytes:
                raise ValueError("file too large")
            return data, content_type
        except HTTPError as error:
            last_error = error
            if error.code in RETRY_STATUS and attempt == 0:
                time.sleep(1.5)
                continue
            raise
        except (socket.timeout, TimeoutError) as error:
            last_error = error
            if attempt == 0:
                time.sleep(0.5)
                continue
            raise
    raise last_error  # pragma: no cover


def _gunzip(data):
    if not data.startswith(b"\x1f\x8b"):
        return data
    try:
        return zlib.decompressobj(16 + zlib.MAX_WBITS).decompress(data, MAX_DECOMPRESSED_BYTES)
    except zlib.error:
        return data


def image_extension(data, content_type):
    data = _gunzip(data or b"")
    content_type = (content_type or "").lower()
    for magic, extension, _ in MAGIC:
        if data.startswith(magic):
            return extension
    head = data[:512].lstrip().lower()
    if head.startswith(b"<svg") or (head.startswith(b"<?xml") and b"<svg" in head[:1024]):
        return "svg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if content_type in IMAGE_EXTENSIONS:
        return IMAGE_EXTENSIONS[content_type]
    return None


def image_dimensions(data, extension):
    data = _gunzip(data or b"")
    try:
        if extension == "png" and data[12:16] == b"IHDR":
            return struct.unpack(">II", data[16:24])
        if extension == "gif":
            return struct.unpack("<HH", data[6:10])
        if extension == "ico":
            count = struct.unpack("<H", data[4:6])[0]
            best = None
            for index in range(count):
                offset = 6 + index * 16
                width = data[offset] or 256
                height = data[offset + 1] or 256
                if best is None or width * height > best[0] * best[1]:
                    best = (width, height)
            if best:
                return best
        if extension == "webp":
            if data[12:16] == b"VP8X":
                return (int.from_bytes(data[24:27], "little") + 1,
                        int.from_bytes(data[27:30], "little") + 1)
            if data[12:16] == b"VP8 " and data[23:26] == b"\x9d\x01\x2a":
                width = struct.unpack("<H", data[26:28])[0] & 0x3FFF
                height = struct.unpack("<H", data[28:30])[0] & 0x3FFF
                return width, height
            if data[12:16] == b"VP8L" and data[20:21] == b"\x2f":
                bits = int.from_bytes(data[21:25], "little")
                return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
        if extension == "svg":
            text = data[:6000].decode("utf-8", errors="ignore")
            viewbox = re.search(r'viewBox=["\']\s*[-\d.]+\s+[-\d.]+\s+([\d.]+)\s+([\d.]+)', text)
            if viewbox:
                width, height = float(viewbox.group(1)), float(viewbox.group(2))
                if width > 0 and height > 0:
                    return width, height
            width_match = re.search(r'\bwidth=["\']\s*([\d.]+)', text)
            height_match = re.search(r'\bheight=["\']\s*([\d.]+)', text)
            if width_match and height_match:
                return float(width_match.group(1)), float(height_match.group(1))
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
        pass
    if HAS_PIL:
        try:
            with Image.open(io.BytesIO(data)) as image:
                return image.size
        except Exception:
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


def _decode_image(data, content_type):
    """Return a decoded candidate description, or None when it is not a usable image."""
    raw = _gunzip(data or b"")
    extension = image_extension(raw, content_type)
    if not extension:
        return None
    if extension == "svg":
        text = raw[:MAX_IMAGE_BYTES].decode("utf-8", errors="ignore")
        lowered = text.lower()
        if "<svg" not in lowered:
            return None
        if "<script" in lowered or "javascript:" in lowered or "<foreignobject" in lowered:
            return None
        dimensions = image_dimensions(raw, "svg")
        if not dimensions:
            return None
        width, height = int(round(dimensions[0])), int(round(dimensions[1]))
        if width < 1 or height < 1:
            return None
        return {"kind": "svg", "ext": "svg", "data": raw, "width": width, "height": height,
                "empty": False, "white_like": _svg_white_like(raw)}
    if not HAS_PIL:
        dimensions = image_dimensions(raw, extension)
        if not dimensions:
            return None
        width, height = int(round(dimensions[0])), int(round(dimensions[1]))
        if width < 1 or height < 1:
            return None
        return {"kind": "raster", "ext": extension, "data": raw, "width": width, "height": height,
                "image": None, "empty": False, "white_like": False}
    try:
        image = Image.open(io.BytesIO(raw))
        if image.format == "ICO" and getattr(image, "ico", None):
            sizes = list(image.ico.sizes())
            if sizes:
                best = max(sizes, key=lambda size: size[0] * size[1])
                image.size = best
        image.load()
        width, height = image.size
    except Exception:
        return None
    if width < 1 or height < 1:
        return None
    flags = _white_like_image(image)
    return {"kind": "raster", "ext": extension, "data": raw, "width": width, "height": height,
            "image": image, "empty": flags["empty"], "white_like": flags["white_like"]}


def _rank_bonus(rank):
    return {10: 12, 15: 10, 18: 8, 30: 10, 35: 4, 40: 2, 45: 0, 50: 0, 55: 6}.get(rank, 0)


def score_candidate(info, rank):
    """Prefer decodable, large, square-ish official icons over banners/wordmarks."""
    width, height = info["width"], info["height"]
    aspect = width / float(height) if height else 1.0
    if info.get("empty"):
        return -1000
    white_penalty = 25 if info.get("white_like") else 0
    squareish = SQUARE_ASPECT_MIN <= aspect <= SQUARE_ASPECT_MAX
    if info["kind"] == "svg":
        # Vector art is resolution independent; ignore its nominal pixel size.
        score = 55 if squareish else (35 if aspect <= 2.4 else 15)
        return score + _rank_bonus(rank) + 5 - white_penalty
    score = 0
    if squareish:
        score += 50
    elif 0.6 <= aspect <= 2.0:
        score += 30
    elif aspect <= 2.6:
        score += 20
    elif aspect <= 4.5:
        score += 8
    minimum = min(width, height)
    if minimum >= 256:
        score += 55
    elif minimum >= 128:
        score += 48
    elif minimum >= 96:
        score += 38
    elif minimum >= 64:
        score += 28
    elif minimum >= 48:
        score += 10
    elif minimum >= 32:
        score += 0
    else:
        score -= 35
    if max(width, height) >= 512 and aspect <= SQUARE_ASPECT_MAX:
        score += 5
    score += _rank_bonus(rank)
    if aspect > 2.0 and height >= 40:
        score += 8
    if aspect > 2.5 and height >= 48 and width >= 160:
        score += 18  # legible wordmark; keep it when no decent square icon exists
    return score - white_penalty


def _is_excellent(info):
    if info["kind"] == "svg" or info.get("empty") or info.get("white_like"):
        return False
    aspect = info["width"] / float(info["height"])
    return SQUARE_ASPECT_MIN <= aspect <= SQUARE_ASPECT_MAX and min(info["width"], info["height"]) >= 180


def _mostly_white_border(image):
    width, height = image.size
    if width < 3 or height < 3:
        return False
    step = max(1, min(width, height) // 64)
    samples = []
    for x in range(0, width, step):
        samples.append(image.getpixel((x, 0)))
        samples.append(image.getpixel((x, height - 1)))
    for y in range(0, height, step):
        samples.append(image.getpixel((0, y)))
        samples.append(image.getpixel((width - 1, y)))
    if not samples:
        return False
    white = sum(1 for r, g, b in samples if r >= 242 and g >= 242 and b >= 242)
    return white / len(samples) >= 0.97


def _trim_padding(image):
    """Remove uniform outer transparent/white padding without touching the mark."""
    image = image.convert("RGBA")
    alpha = image.getchannel("A")
    alpha_min, _ = alpha.getextrema()
    if alpha_min < 250:
        bbox = alpha.point(lambda value: 255 if value > 4 else 0).getbbox()
    else:
        rgb = image.convert("RGB")
        if not _mostly_white_border(rgb):
            return image
        white = Image.new("RGB", rgb.size, (255, 255, 255))
        diff = ImageChops.difference(rgb, white).convert("L")
        bbox = diff.point(lambda value: 255 if value > 12 else 0).getbbox()
    if not bbox:
        return image
    left, top, right, bottom = bbox
    if right - left < 2 or bottom - top < 2:
        return image
    return image.crop(bbox)


DARK_MARK = (20, 24, 26)


def _opaque_stats(image):
    """Return (opaque, near_white, colored, average_luminance) on a small sample."""
    image = image.convert("RGBA")
    sample = image.copy()
    sample.thumbnail((160, 160), Image.Resampling.LANCZOS)
    opaque = near_white = colored = 0
    total_luminance = 0.0
    for red, green, blue, alpha in sample.getdata():
        if alpha < 16:
            continue
        opaque += 1
        luminance = (red + green + blue) / 3.0
        total_luminance += luminance
        chroma = max(red, green, blue) - min(red, green, blue)
        if luminance >= 238:
            near_white += 1
        elif chroma >= 24:
            colored += 1
    if not opaque:
        return 0, 0, 0, 0.0
    return opaque, near_white, colored, total_luminance / opaque


def _white_like_image(image):
    """Detect a mark whose visible pixels are almost entirely white."""
    image = image.convert("RGBA")
    if image.getchannel("A").getextrema()[1] == 0:
        return {"empty": True, "white_like": False}
    trimmed = _trim_padding(image.copy())
    opaque, near_white, colored, average = _opaque_stats(trimmed)
    if not opaque:
        return {"empty": True, "white_like": False}
    white_like = (near_white / opaque > 0.95 and colored / opaque < 0.02
                  and average > 235)
    return {"empty": False, "white_like": white_like}


def _invert_white_raster(image):
    """Map a white-on-transparent mark to dark-on-transparent, keeping alpha."""
    image = image.convert("RGBA")
    pixels = image.load()
    width, height = image.size
    for y in range(height):
        for x in range(width):
            red, green, blue, alpha = pixels[x, y]
            if alpha == 0:
                continue
            luminance = (red + green + blue) / 3.0
            if luminance < 150:
                continue
            if max(red, green, blue) - min(red, green, blue) >= 24:
                continue
            value = max(0, min(130, int(round(DARK_MARK[0] + (255 - luminance) * 0.75))))
            pixels[x, y] = (value, value + 4, value + 6, alpha)
    return image


def _svg_white_like(data):
    text = data.decode("utf-8", errors="ignore")
    colors = []
    for match in re.finditer(
            r"(?:fill|stroke|stop-color)\s*[:=]\s*[\"']?(#[0-9a-fA-F]{3,8}|white|rgb\([^)]*\))",
            text):
        colors.append(match.group(1).lower())
    if not colors:
        return False
    for color in colors:
        if color.startswith("#"):
            digits = color[1:]
            if len(digits) == 3:
                digits = "".join(character * 2 for character in digits)
            if len(digits) < 6:
                return False
            if int(digits[0:2], 16) < 235 or int(digits[2:4], 16) < 235 or int(digits[4:6], 16) < 235:
                return False
        elif color == "white":
            continue
        elif color.startswith("rgb("):
            numbers = [int(part) for part in re.findall(r"\d+", color)[:3]]
            if len(numbers) != 3 or min(numbers) < 235:
                return False
        else:
            return False
    return True


def _invert_white_svg(data):
    text = data.decode("utf-8", errors="ignore")
    pattern = re.compile(
        r"(?P<prop>fill|stroke|stop-color)(?P<sep>\s*[:=]\s*)(?P<quote>[\"']?)"
        r"(?P<color>#[0-9a-fA-F]{3,8}|white|rgb\(\s*255\s*,\s*255\s*,\s*255\s*\))",
        re.IGNORECASE)
    updated = pattern.sub(lambda match: match.group("prop") + match.group("sep")
                          + match.group("quote") + "#14181a", text)
    if updated == text:
        return data
    return updated.encode("utf-8")


def _encode_png(image):
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


_SVG_TOKEN = re.compile(r"([MmZzLlHhVvCcSsQqTtAa])|([-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?)")
_SVG_ARITY = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "T": 2, "A": 7}


def _path_bbox(path_data):
    """Approximate the bounding box of a filled SVG path (control points included)."""
    tokens = []
    for match in _SVG_TOKEN.finditer(path_data or ""):
        tokens.append(match.group(1) or match.group(2))
    x_values, y_values = [], []
    index, command = 0, None
    current = (0.0, 0.0)
    start = (0.0, 0.0)

    def add(x, y):
        x_values.append(x)
        y_values.append(y)

    while index < len(tokens):
        token = tokens[index]
        if token.isalpha():
            command = token
            index += 1
            if command.upper() == "Z":
                current = start
            continue
        if command is None:
            return None
        upper = command.upper()
        if upper == "A":
            return None  # arc booleans/radii are not worth estimating
        arity = _SVG_ARITY.get(upper, 0)
        if not arity or index + arity > len(tokens):
            break
        values = [float(value) for value in tokens[index:index + arity]]
        index += arity
        relative = command.islower()
        base_x, base_y = current
        if upper == "M":
            x, y = values
            if relative:
                x, y = base_x + x, base_y + y
            add(x, y)
            current = (x, y)
            start = (x, y)
            command = "l" if relative else "L"
        elif upper == "L":
            x, y = values
            if relative:
                x, y = base_x + x, base_y + y
            add(x, y)
            current = (x, y)
        elif upper == "H":
            x = base_x + values[0] if relative else values[0]
            add(x, base_y)
            current = (x, base_y)
        elif upper == "V":
            y = base_y + values[0] if relative else values[0]
            add(base_x, y)
            current = (base_x, y)
        elif upper == "C":
            points = [(values[0], values[1]), (values[2], values[3]), (values[4], values[5])]
            if relative:
                points = [(base_x + x, base_y + y) for x, y in points]
            for x, y in points:
                add(x, y)
            current = points[-1]
        elif upper == "S":
            points = [(values[0], values[1]), (values[2], values[3])]
            if relative:
                points = [(base_x + x, base_y + y) for x, y in points]
            for x, y in points:
                add(x, y)
            current = points[-1]
        elif upper == "Q":
            points = [(values[0], values[1]), (values[2], values[3])]
            if relative:
                points = [(base_x + x, base_y + y) for x, y in points]
            for x, y in points:
                add(x, y)
            current = points[-1]
        elif upper == "T":
            x, y = values
            if relative:
                x, y = base_x + x, base_y + y
            add(x, y)
            current = (x, y)
    if not x_values:
        return None
    return min(x_values), min(y_values), max(x_values), max(y_values)


def _svg_number(value):
    if value is None:
        return None
    match = re.match(r"^\s*([-+]?(?:\d*\.?\d+)(?:[eE][-+]?\d+)?)", str(value))
    return float(match.group(1)) if match else None


def _svg_set_attr(tag, name, value):
    pattern = re.compile(r"(\s" + re.escape(name) + r"\s*=\s*)([\"']).*?\2", re.IGNORECASE | re.DOTALL)
    if pattern.search(tag):
        return pattern.sub(lambda match: match.group(1) + '"' + value + '"', tag, count=1)
    closing = "/>" if tag.rstrip().endswith("/>") else ">"
    body = tag.rstrip()[:-len(closing)]
    return body + ' ' + name + '="' + value + '"' + closing


def normalize_svg(data):
    """Crop an SVG viewBox to its visible content bbox (8% padding).

    Returns (bytes, (width, height)) or None when the geometry cannot be
    estimated safely (transforms, text, <use>/<image>, unparseable markup).
    """
    import xml.etree.ElementTree as ElementTree

    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError:
        return None

    def local(tag):
        return tag.rsplit("}", 1)[-1].lower() if isinstance(tag, str) else ""

    if local(root.tag) != "svg":
        return None
    parent = {child: node for node in root.iter() for child in node}
    for node in root.iter():
        if not isinstance(node.tag, str):
            continue
        if node.get("transform"):
            return None
        if local(node.tag) in {"text", "tspan", "image", "use", "foreignobject",
                               "animate", "animatetransform", "animatemotion"}:
            return None

    def in_defs(node):
        seen = 0
        while node in parent and seen < 50:
            node = parent[node]
            if local(node.tag) in {"defs", "clippath", "mask", "symbol"}:
                return True
            seen += 1
        return False

    x_values, y_values = [], []
    stroke_widths = []
    for node in root.iter():
        if not isinstance(node.tag, str) or in_defs(node):
            continue
        if (node.get("display") or "").lower() == "none" or (node.get("visibility") or "").lower() == "hidden":
            continue
        if (node.get("opacity") or "") == "0":
            continue
        style = node.get("style") or ""
        fill = node.get("fill") or ""
        stroke = node.get("stroke") or ""
        if "fill:none" in style.replace(" ", "") and "stroke:none" in style.replace(" ", ""):
            continue
        stroke_width = _svg_number(node.get("stroke-width"))
        if "stroke-width:" in style:
            stroke_width = _svg_number(style.split("stroke-width:", 1)[1]) or stroke_width
        if (stroke and stroke.lower() != "none") or "stroke:" in style:
            stroke_widths.append(stroke_width if stroke_width is not None else 1.0)
        kind = local(node.tag)
        if kind == "path":
            box = _path_bbox(node.get("d"))
        elif kind == "rect":
            x, y = _svg_number(node.get("x")) or 0.0, _svg_number(node.get("y")) or 0.0
            width, height = _svg_number(node.get("width")), _svg_number(node.get("height"))
            box = (x, y, x + width, y + height) if width and height else None
        elif kind == "circle":
            cx, cy, radius = _svg_number(node.get("cx")) or 0.0, _svg_number(node.get("cy")) or 0.0, \
                _svg_number(node.get("r"))
            box = (cx - radius, cy - radius, cx + radius, cy + radius) if radius else None
        elif kind == "ellipse":
            cx, cy = _svg_number(node.get("cx")) or 0.0, _svg_number(node.get("cy")) or 0.0
            rx, ry = _svg_number(node.get("rx")), _svg_number(node.get("ry"))
            box = (cx - rx, cy - ry, cx + rx, cy + ry) if rx and ry else None
        elif kind == "line":
            values = [_svg_number(node.get(key)) for key in ("x1", "y1", "x2", "y2")]
            box = (min(values[0], values[2]), min(values[1], values[3]),
                   max(values[0], values[2]), max(values[1], values[3])) if all(v is not None for v in values) else None
        elif kind in {"polyline", "polygon"}:
            numbers = [float(value) for value in re.findall(
                r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?", node.get("points") or "")]
            if len(numbers) >= 4:
                xs, ys = numbers[0::2], numbers[1::2]
                box = (min(xs), min(ys), max(xs), max(ys))
            else:
                box = None
        else:
            continue
        if not box:
            continue
        x_values.extend([box[0], box[2]])
        y_values.extend([box[1], box[3]])
    if not x_values:
        return None
    x1, x2 = min(x_values), max(x_values)
    y1, y2 = min(y_values), max(y_values)
    if stroke_widths:
        pad_stroke = max(stroke_widths) / 2.0
        x1, y1, x2, y2 = x1 - pad_stroke, y1 - pad_stroke, x2 + pad_stroke, y2 + pad_stroke
    if x2 <= x1 or y2 <= y1:
        return None
    viewbox = root.get("viewBox")
    if viewbox:
        parts = [_svg_number(part) for part in re.split(r"[\s,]+", viewbox.strip()) if part]
        if len(parts) != 4 or any(part is None for part in parts):
            return None
        canvas_w, canvas_h = parts[2], parts[3]
    else:
        canvas_w, canvas_h = _svg_number(root.get("width")), _svg_number(root.get("height"))
        if not canvas_w or not canvas_h:
            return None
    if canvas_w <= 0 or canvas_h <= 0:
        return None
    content_w, content_h = x2 - x1, y2 - y1
    if content_w * content_h >= canvas_w * canvas_h * 0.98:
        return None
    if content_w > canvas_w * 3 or content_h > canvas_h * 3:
        return None
    padding = 0.08 * max(content_w, content_h)
    new_x, new_y = x1 - padding, y1 - padding
    new_w, new_h = content_w + 2 * padding, content_h + 2 * padding

    def format_number(value):
        rounded = round(value)
        if abs(value - rounded) < 1e-6:
            return str(int(rounded))
        return ("%.2f" % value).rstrip("0").rstrip(".")

    text = data.decode("utf-8", errors="ignore")
    tag_match = re.search(r"<svg\b[^>]*>", text, re.IGNORECASE | re.DOTALL)
    if not tag_match:
        return None
    tag = tag_match.group(0)
    tag = _svg_set_attr(tag, "viewBox", "%s %s %s %s" % tuple(
        format_number(value) for value in (new_x, new_y, new_w, new_h)))
    tag = _svg_set_attr(tag, "width", format_number(new_w))
    tag = _svg_set_attr(tag, "height", format_number(new_h))
    updated = text[:tag_match.start()] + tag + text[tag_match.end():]
    return updated.encode("utf-8"), (max(1, int(round(new_w))), max(1, int(round(new_h))))


def normalize_raster(image, invert_white=False):
    """Normalize a decoded raster image; returns (PNG bytes, (width, height))."""
    image = image.convert("RGBA")
    image = _trim_padding(image)
    if invert_white:
        image = _invert_white_raster(image)
    width, height = image.size
    if width < 1 or height < 1:
        raise ValueError("empty image")
    aspect = width / float(height)
    if SQUARE_ASPECT_MIN <= aspect <= SQUARE_ASPECT_MAX:
        target = CANVAS_SIZE - 2 * CANVAS_MARGIN
        scale = target / float(max(width, height))
        size = (max(1, int(round(width * scale))), max(1, int(round(height * scale))))
        content = image.resize(size, Image.Resampling.LANCZOS) if size != image.size else image
        canvas = Image.new("RGBA", (CANVAS_SIZE, CANVAS_SIZE), (0, 0, 0, 0))
        canvas.alpha_composite(content, ((CANVAS_SIZE - size[0]) // 2, (CANVAS_SIZE - size[1]) // 2))
        return _encode_png(canvas), (CANVAS_SIZE, CANVAS_SIZE)
    # Wide wordmarks and tall marks keep their natural aspect ratio; the
    # dashboard widens the frame from naturalWidth / naturalHeight.
    longest = max(width, height)
    scale = MIN_LONG_SIDE / float(longest) if longest < MIN_LONG_SIDE else min(
        1.0, MAX_LONG_SIDE / float(longest))
    if scale > 1.0:
        width = max(1, int(round(width * scale)))
        height = max(1, int(round(height * scale)))
        image = image.resize((width, height), Image.Resampling.LANCZOS)
    return _encode_png(image), (image.size[0], image.size[1])


def existing_logo(root, company_id):
    directory = Path(root) / LOGO_DIR
    variants = [path for path in sorted(directory.glob(company_id + ".*"))
                if path.suffix.lower().lstrip(".") in ASSET_EXTENSIONS]
    priority = {"svg": 0, "png": 1, "webp": 2, "jpg": 3, "jpeg": 3, "gif": 4, "ico": 5}
    if not variants:
        return None
    return sorted(variants, key=lambda path: priority.get(path.suffix.lower().lstrip("."), 9))[0]


def _store_asset(root, company_id, data, extension):
    directory = Path(root) / LOGO_DIR
    directory.mkdir(parents=True, exist_ok=True)
    filename = company_id + "." + extension
    for old in directory.glob(company_id + ".*"):
        if old.suffix.lower().lstrip(".") in ASSET_EXTENSIONS and old.name != filename:
            old.unlink()
    (directory / filename).write_bytes(data)
    return (LOGO_DIR / filename).as_posix()


def _kept_result(company_id, existing, reason, website=None, detail=None):
    result = {
        "id": company_id,
        "status": "kept",
        "reason": reason,
        "path": existing,
    }
    if website:
        result["website"] = website
    if detail:
        result["detail"] = detail
    return result


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
    website = _normalized_website(website_for(record))
    if not website:
        return {"id": company_id, "status": "skipped", "reason": "no_website"}
    homepage_error = None
    _FETCH_CONTEXT.referer = None
    try:
        html_bytes, _ = fetcher(website, timeout, MAX_HTML_BYTES)
        html = html_bytes.decode("utf-8", errors="ignore")
        base_url = website
        candidates = _candidate_entries(html, base_url, with_fallback=False)
        if not candidates:
            redirect = _meta_refresh_url(html, website)
            if redirect and redirect != website:
                try:
                    redirect_bytes, _ = fetcher(redirect, timeout, MAX_HTML_BYTES)
                    base_url = redirect
                    candidates = _candidate_entries(
                        redirect_bytes.decode("utf-8", errors="ignore"), redirect,
                        with_fallback=False)
                except (HTTPError, URLError, socket.timeout, TimeoutError,
                        ssl.SSLError, ValueError, OSError):
                    pass
        fallback = urljoin(base_url, "/favicon.ico")
        if fallback not in {url for url, _ in candidates}:
            candidates.append((fallback, 50))
    except (HTTPError, URLError, socket.timeout, TimeoutError, ssl.SSLError, ValueError, OSError) as error:
        homepage_error = type(error).__name__
        candidates = _fallback_candidates(website)
    if not candidates:
        return {"id": company_id, "status": "skipped", "reason": "no_candidates", "website": website}
    _FETCH_CONTEXT.referer = website

    scored = []
    attempts = 0
    for candidate, rank in candidates:
        if attempts >= MAX_CANDIDATES:
            break
        attempts += 1
        try:
            data, image_type = fetcher(candidate, timeout, MAX_IMAGE_BYTES)
        except (HTTPError, URLError, socket.timeout, TimeoutError, ssl.SSLError, ValueError, OSError):
            continue
        info = _decode_image(data, image_type)
        if not info or info.get("empty"):
            continue
        # Declared icons/logo images are trusted wordmarks; only less specific
        # sources (og:image, twitter:image) are screened for banner shapes.
        if rank >= 40 and looks_like_banner(info["data"], info["ext"], candidate):
            continue
        scored.append((score_candidate(info, rank), candidate, info))
        if _is_excellent(info) and rank <= 20:
            break

    if not scored:
        reason = "homepage_failed" if homepage_error else "no_usable_image"
        if existing:
            return _kept_result(company_id, (LOGO_DIR / existing.name).as_posix(), reason,
                                website=website, detail=homepage_error)
        result = {"id": company_id, "status": "skipped", "reason": reason, "website": website}
        if homepage_error:
            result["detail"] = homepage_error
        return result

    # A 16px favicon should not win just because it was declared first.
    best_large = max(max(info["width"], info["height"]) for _, _, info in scored)
    if best_large >= 32:
        scored = [item for item in scored if max(item[2]["width"], item[2]["height"]) >= 32]
    scored.sort(key=lambda item: (item[0], item[2]["width"] * item[2]["height"]), reverse=True)

    last_error = None
    for _, candidate, info in scored:
        try:
            if info["kind"] == "svg":
                normalized = normalize_svg(info["data"])
                payload = normalized[0] if normalized else info["data"]
                width, height = normalized[1] if normalized else (info["width"], info["height"])
                if info.get("white_like"):
                    payload = _invert_white_svg(payload)
                extension, content_type = "svg", "image/svg+xml"
            else:
                if HAS_PIL:
                    payload, (width, height) = normalize_raster(
                        info["image"], invert_white=info.get("white_like", False))
                    extension, content_type = "png", "image/png"
                else:
                    payload, extension = info["data"], info["ext"]
                    width, height = info["width"], info["height"]
                    content_type = "image/" + ("jpeg" if extension == "jpg" else extension)
            path = _store_asset(root, company_id, payload, extension)
        except (OSError, ValueError) as error:
            last_error = type(error).__name__
            continue
        return {
            "id": company_id,
            "status": "fetched",
            "source_url": candidate,
            "website": website,
            "fetched_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "content_type": content_type,
            "bytes": len(payload),
            "width": width,
            "height": height,
            "path": path,
        }
    if existing:
        return _kept_result(company_id, (LOGO_DIR / existing.name).as_posix(), "normalize_failed",
                            website=website, detail=last_error)
    return {"id": company_id, "status": "skipped", "reason": "no_usable_image", "website": website,
            "detail": last_error}


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


def _merge_result(previous, result):
    if result.get("reason") == "already_fetched":
        merged = dict(previous or {})
        merged.update({"id": result["id"], "status": "fetched", "path": result["path"],
                       "reason": "already_fetched"})
        return merged
    if result.get("status") == "kept":
        merged = dict(previous or {})
        merged.update({key: value for key, value in result.items() if value is not None})
        return merged
    merged = dict(previous or {})
    merged.update({key: value for key, value in result.items() if value is not None})
    if result.get("status") == "fetched":
        merged.pop("reason", None)
        merged.pop("detail", None)
    return merged


def _remove_stale_variants(root, company_id, keep_path):
    directory = Path(root) / LOGO_DIR
    keep_name = Path(keep_path).name if keep_path else None
    for path in directory.glob(company_id + ".*"):
        if path.suffix.lower().lstrip(".") in ASSET_EXTENSIONS and path.name != keep_name:
            path.unlink()


def canonical_ids(root=ROOT):
    """IDs that still have a canonical company dossier (any organization type)."""
    directory = Path(root) / "data/companies"
    if not directory.exists():
        return set()
    return {path.stem for path in directory.glob("*.json")}


def prune_logos(root=ROOT):
    """Drop manifest entries and asset files for dossiers that no longer exist."""
    known = canonical_ids(root)
    if not known:
        return []
    directory = Path(root) / LOGO_DIR
    manifest = load_manifest(root)
    entries = []
    removed = set()
    for entry in manifest["entries"]:
        company_id = entry.get("id")
        if company_id in known:
            entries.append(entry)
            continue
        removed.add(company_id)
        path = entry.get("path")
        if path and (Path(root) / path).exists():
            (Path(root) / path).unlink()
    if directory.exists():
        for path in directory.iterdir():
            if path.is_file() and path.suffix.lower().lstrip(".") in ASSET_EXTENSIONS \
                    and path.stem not in known:
                removed.add(path.stem)
                path.unlink()
    if removed:
        save_manifest(entries, root=root)
    return sorted(removed)


def fetch_all(root=ROOT, ids=None, timeout=DEFAULT_TIMEOUT, workers=8, fetcher=fetch_url, force=False):
    records = logo_records(root, ids=ids)
    previous = {entry["id"]: entry for entry in load_manifest(root)["entries"]}
    results = []

    def run(record):
        result = fetch_logo(record, root=root, fetcher=fetcher, timeout=timeout, force=force)
        prior = previous.get(record["id"])
        if result.get("status") == "skipped" and prior and prior.get("path") \
                and (Path(root) / prior["path"]).exists():
            result = {
                "id": record["id"],
                "status": "kept",
                "reason": result.get("reason"),
                "path": prior["path"],
                "website": result.get("website") or prior.get("website"),
                "detail": result.get("detail"),
            }
        return _merge_result(prior, result)

    with ThreadPoolExecutor(max_workers=max(1, min(4, workers))) as pool:
        results.extend(pool.map(run, records))
    merged_entries = dict(previous)
    merged_entries.update({entry["id"]: entry for entry in results})
    for entry in results:
        _remove_stale_variants(root, entry["id"], entry.get("path"))
    save_manifest(list(merged_entries.values()), root=root)
    prune_logos(root)
    return results


def normalize_assets(root=ROOT, ids=None):
    """Normalize existing assets in place and refresh width/height in the manifest."""
    directory = Path(root) / LOGO_DIR
    manifest = load_manifest(root)
    entries = {entry["id"]: entry for entry in manifest["entries"]}
    company_dir = Path(root) / "data/companies"
    known = {}
    for path in sorted(company_dir.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        known[record["id"]] = record
    known = canonical_ids(root)
    if ids:
        stems = sorted(set(ids))
    else:
        stems = sorted({path.stem for path in directory.iterdir()
                        if path.is_file() and path.suffix.lower().lstrip(".") in ASSET_EXTENSIONS}
                       & known)
    results = []
    for company_id in stems:
        existing = existing_logo(root, company_id)
        if not existing:
            results.append({"id": company_id, "status": "skipped", "reason": "no_asset"})
            continue
        existing_mtime = existing.stat().st_mtime
        entry = dict(entries.get(company_id, {"id": company_id, "status": "fetched"}))
        try:
            info = _decode_image(existing.read_bytes(), "")
        except OSError:
            info = None
        if not info:
            entry.update({"status": "kept", "reason": "unreadable_asset",
                          "path": (LOGO_DIR / existing.name).as_posix()})
            entries[company_id] = entry
            results.append(entry)
            continue
        if info.get("empty"):
            existing.unlink()
            entry.update({"status": "skipped", "reason": "empty_asset"})
            for key in ("path", "width", "height", "content_type", "bytes", "source_url"):
                entry.pop(key, None)
            entries[company_id] = entry
            results.append(entry)
            continue
        try:
            if info["kind"] == "svg":
                normalized = normalize_svg(info["data"])
                payload = normalized[0] if normalized else info["data"]
                width, height = normalized[1] if normalized else (info["width"], info["height"])
                if info.get("white_like"):
                    payload = _invert_white_svg(payload)
                extension, content_type = "svg", "image/svg+xml"
            elif HAS_PIL:
                payload, (width, height) = normalize_raster(
                    info["image"], invert_white=info.get("white_like", False))
                extension, content_type = "png", "image/png"
            else:
                payload, extension = info["data"], info["ext"]
                width, height = info["width"], info["height"]
                content_type = "image/" + ("jpeg" if extension == "jpg" else extension)
            path = _store_asset(root, company_id, payload, extension)
        except (OSError, ValueError):
            entry.update({"status": "kept", "reason": "normalize_failed",
                          "path": (LOGO_DIR / existing.name).as_posix()})
            entries[company_id] = entry
            results.append(entry)
            continue
        fetched_at = entry.get("fetched_at")
        if not fetched_at:
            fetched_at = datetime.fromtimestamp(existing_mtime, timezone.utc).replace(
                microsecond=0).isoformat()
        entry.update({
            "status": "fetched",
            "fetched_at": fetched_at,
            "content_type": content_type,
            "bytes": len(payload),
            "width": width,
            "height": height,
            "path": path,
        })
        entry.pop("detail", None)
        entries[company_id] = entry
        results.append(entry)
    save_manifest(list(entries.values()), root=root)
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--id", action="append", dest="ids", help="fetch only one company id (repeatable)")
    parser.add_argument("--workers", type=int, default=4, help="parallel workers (capped at 4)")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--force", action="store_true", help="re-fetch even when a logo file exists")
    parser.add_argument("--normalize-only", action="store_true",
                        help="normalize existing assets without network access")
    parser.add_argument("--prune", action="store_true",
                        help="remove manifest entries and assets whose company dossier no longer exists")
    args = parser.parse_args(argv)
    if args.prune:
        removed = prune_logos(root=args.root)
        print("Logos pruned %d (%s). Manifest: %s"
              % (len(removed), ", ".join(removed) if removed else "none", Path(args.root) / MANIFEST))
        return 0
    if args.normalize_only:
        results = normalize_assets(root=args.root, ids=args.ids)
        normalized = sum(1 for item in results if item.get("status") == "fetched")
        kept = sum(1 for item in results if item.get("status") == "kept")
        print("Logos normalized %d, kept %d. Manifest: %s"
              % (normalized, kept, Path(args.root) / MANIFEST))
        return 0
    results = fetch_all(root=args.root, ids=args.ids, timeout=args.timeout,
                        workers=args.workers, force=args.force)
    fetched = sum(1 for item in results if item.get("status") == "fetched")
    kept = sum(1 for item in results if item.get("status") == "kept")
    skipped = len(results) - fetched - kept
    print("Logos fetched %d, kept %d, skipped %d. Manifest: %s"
          % (fetched, kept, skipped, Path(args.root) / MANIFEST))
    return 0


if __name__ == "__main__":
    sys.exit(main())
