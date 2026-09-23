"""Image fetch with a multi-provider FALLBACK CHAIN. Stdlib urllib only.

Providers (all return downloadable bytes we embed into the card — so they must permit re-hosting):
  - Pexels   (key)     — general photos, no attribution required.
  - Serper   (key)     — Google Images, good for IT/brand terms.
  - Pixabay  (key)     — general photos, no attribution required, generous free tier.
  - Openverse (NO key) — CC0/public-domain only (license-safe to embed); universal last-resort
                         fallback so even a user with zero keys still gets an image.

fetch_image() tries the routed provider first, then the other configured providers, then keyless
Openverse. Each fetcher returns (filename, raw_bytes) for col.media.write_data, or None on any
failure (no key, no match, network) — the image is always optional.
"""
import hashlib
import json
import re
import time
import urllib.parse
import urllib.request

from .providers import open_url

PEXELS_URL = "https://api.pexels.com/v1/search"
SERPER_URL = "https://google.serper.dev/images"
PIXABAY_URL = "https://pixabay.com/api/"
OPENVERSE_URL = "https://api.openverse.org/v1/images/"
UA = {"User-Agent": "Tarkib/1.0"}
_IT_DECK = re.compile(r"\bIT\b")  # word-boundary so "Fitness"/"Politik"/"Mitarbeiter" don't match


def _safe_name(keyword):
    safe = re.sub(r"[^\w]", "_", keyword or "")[:30].strip("_") or "img"
    return "img_%s_%d.jpg" % (safe, int(time.time()))


def _looks_like_raster(b):
    """True only for real raster image bytes (JPEG/PNG/GIF/WebP). Guards against SVGs, HTML error
    pages, or other non-photo payloads that would render as a broken image on the card."""
    return bool(b) and (
        b[:3] == b"\xff\xd8\xff"                       # JPEG
        or b[:8] == b"\x89PNG\r\n\x1a\n"               # PNG
        or b[:6] in (b"GIF87a", b"GIF89a")             # GIF
        or (b[:4] == b"RIFF" and b[8:12] == b"WEBP"))  # WebP


MAX_IMAGE_BYTES = 5 * 1024 * 1024  # a card image; anything bigger is a CDN mistake, not a photo


def _download(url, timeout=15):
    # Provider JSON hands us arbitrary third-party URLs: insist on https and cap the size BEFORE
    # reading everything into RAM (the socket timeout only bounds inactivity, not a slow 300 MB file).
    if not (url or "").lower().startswith("https://"):
        raise ValueError("non-https image url")
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        if not (r.geturl() or "").lower().startswith("https://"):
            raise ValueError("image redirected off https")
        cl = r.headers.get("Content-Length")
        if cl and cl.isdigit() and int(cl) > MAX_IMAGE_BYTES:
            raise ValueError("image too large")
        data = r.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("image too large")
    if not _looks_like_raster(data):
        raise ValueError("not a raster image")  # caught by the fetcher → skip this result/provider
    return data



def _pick(urls, keyword, timeout, exclude):
    """Download candidates in order and return the first one we have not already used.

    Every provider used to take result number one. Two cards asking for near identical things,
    "fresh fruit basket" and "basket of fruit at market", therefore got the same file, and whole
    groups of cards in one deck ended up sharing a photograph. Passing the hashes already
    in the deck and walking down the result list fixes that at the source, for a deck build and
    for a user generating a run of related cards.
    """
    seen = exclude if exclude is not None else set()
    first = None
    for u in urls:
        if not u:
            continue
        try:
            data = _download(u, timeout)
        except Exception:
            continue
        if not data:
            continue
        h = hashlib.sha256(data).hexdigest()
        if first is None:
            first = (data, h)
        if h not in seen:
            seen.add(h)
            return _safe_name(keyword), data
    # every candidate was already used somewhere. A repeat beats no picture at all.
    if first:
        return _safe_name(keyword), first[0]
    return None

def fetch_pexels(keyword, api_key, timeout=15, exclude=None):
    if not keyword or not api_key:
        return None
    try:
        url = "%s?query=%s&per_page=12" % (PEXELS_URL, urllib.parse.quote(keyword))
        req = urllib.request.Request(url, headers={"Authorization": api_key, **UA})
        data = json.loads(open_url(req, timeout).read())
        urls = []
        for ph in data.get("photos", []):
            src = ph.get("src", {})
            urls.append(src.get("medium") or src.get("original"))
        return _pick(urls, keyword, timeout, exclude)
    except Exception:
        return None


def fetch_serper(keyword, api_key, timeout=15, exclude=None):
    if not keyword or not api_key:
        return None
    try:
        body = json.dumps({"q": keyword, "gl": "us", "num": 12}).encode()
        req = urllib.request.Request(SERPER_URL, data=body,
                                     headers={"X-API-KEY": api_key, "Content-Type": "application/json", **UA})
        data = json.loads(open_url(req, timeout).read())
        return _pick([i.get("imageUrl") for i in data.get("images", [])], keyword, timeout, exclude)
    except Exception:
        return None


def fetch_pixabay(keyword, api_key, timeout=15, exclude=None):
    if not keyword or not api_key:
        return None
    try:
        url = "%s?key=%s&q=%s&image_type=photo&safesearch=true&per_page=12" % (
            PIXABAY_URL, urllib.parse.quote(api_key), urllib.parse.quote(keyword))
        data = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read())
        urls = [h.get("webformatURL") or h.get("largeImageURL") for h in data.get("hits", [])]
        return _pick(urls, keyword, timeout, exclude)
    except Exception:
        return None


# Openverse is the keyless last resort, and when it is down it is down for everyone at once. It has
# been returning nothing but timeouts, so a user with no image key was paying the FULL image timeout
# on every single card and getting no picture for it. Two guards: never give the keyless fallback
# more than a few seconds, and once it times out stop asking for ten minutes.
OPENVERSE_MAX_SECONDS = 4
_OPENVERSE_DOWN_UNTIL = 0.0


def fetch_openverse(keyword, timeout=15, exclude=None):
    """Keyless fallback. Restricted to CC0 / public-domain (license=cc0,pdm) so embedding the image
    in a card needs NO attribution — license-safe to ship. Quality varies (aggregated sources)."""
    global _OPENVERSE_DOWN_UNTIL
    if not keyword:
        return None
    if time.time() < _OPENVERSE_DOWN_UNTIL:
        return None                       # it timed out recently; do not spend the card's time again
    timeout = min(timeout, OPENVERSE_MAX_SECONDS)
    try:
        # category=photograph + extension=jpg,png drops logos/clip-art/SVGs/paintings (the junk we saw).
        url = "%s?q=%s&license=cc0,pdm&category=photograph&extension=jpg,png&page_size=12&mature=false" % (
            OPENVERSE_URL, urllib.parse.quote(keyword))
        data = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read())
        # Openverse aggregates third-party CDNs, so _pick also skips the dead links for us
        got = _pick([i.get("url") for i in data.get("results", [])], keyword, timeout, exclude)
        if got:
            _OPENVERSE_DOWN_UNTIL = 0.0
        return got
    except Exception:
        _OPENVERSE_DOWN_UNTIL = time.time() + 600
        return None


def test_pexels(api_key, timeout=15):
    """Validate a Pexels key with a tiny search. Unlike fetch_pexels this does NOT swallow —
    it raises the underlying urllib error so the caller can report why the key failed."""
    url = "%s?query=test&per_page=1" % PEXELS_URL
    req = urllib.request.Request(url, headers={"Authorization": api_key, **UA})
    open_url(req, timeout).read()
    return "Pexels OK"


def test_serper(api_key, timeout=15):
    """Validate a Serper key with a tiny image query. Raises on failure (does not swallow)."""
    body = json.dumps({"q": "test", "num": 1}).encode()
    req = urllib.request.Request(SERPER_URL, data=body,
                                 headers={"X-API-KEY": api_key, "Content-Type": "application/json", **UA})
    open_url(req, timeout).read()
    return "Serper OK"


def test_pixabay(api_key, timeout=15):
    """Validate a Pixabay key with a tiny query (per_page=3 — Pixabay rejects smaller). Raises on
    failure (does not swallow) so the caller can report why the key was rejected."""
    url = "%s?key=%s&q=test&image_type=photo&per_page=3" % (PIXABAY_URL, urllib.parse.quote(api_key))
    urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read()
    return "Pixabay OK"


_KEYED_FETCHERS = {"pexels": fetch_pexels, "serper": fetch_serper, "pixabay": fetch_pixabay}


def fetch_image(keyword, deck, image_source, keys, timeout=15, exclude=None):
    """Try providers in order until one returns an image; keyless Openverse is the final fallback.

    keys: dict {pexels, serper, pixabay} of API keys (any may be empty).
    exclude: a set of sha256 hexdigests already used. Each provider walks its result list and
      returns the first photo not in that set, adding what it returns. Without it, two cards
      asking for near identical things get the same file.
    image_source: 'auto' (default) | 'pexels' | 'serper' | 'pixabay' | 'openverse'.
      auto → Serper first for IT decks, else Pexels first; then the remaining keyed providers.
    A provider with no key is skipped. Openverse needs no key and is always tried last, so an
    image is attempted even when no keys are configured at all.
    """
    keys = keys or {}
    src = (image_source or "auto").lower()
    if src == "serper":
        keyed = ["serper", "pexels", "pixabay"]
    elif src == "pixabay":
        keyed = ["pixabay", "pexels", "serper"]
    elif src == "pexels":
        keyed = ["pexels", "pixabay", "serper"]
    elif src == "openverse":
        keyed = ["pexels", "pixabay", "serper"]
    else:  # auto
        keyed = ["serper", "pexels", "pixabay"] if _IT_DECK.search(deck or "") else ["pexels", "pixabay", "serper"]

    if src == "openverse":  # explicitly forced → try keyless Openverse first
        img = fetch_openverse(keyword, timeout, exclude)
        if img:
            return img
    for name in keyed:
        key = (keys.get(name) or "").strip()
        if not key:
            continue
        img = _KEYED_FETCHERS[name](keyword, key, timeout, exclude)
        if img:
            return img
    return fetch_openverse(keyword, timeout, exclude)  # keyless universal last-resort (CC0/public-domain)
