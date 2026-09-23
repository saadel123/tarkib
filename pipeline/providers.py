"""LLM provider layer — HTTPS only, stdlib urllib (no SDKs, no subprocess).

Two adapter types today, extensible:
  - "openai_compatible": OpenAI / Groq / OpenRouter / Mistral / Ollama / local (configurable base_url)
  - "anthropic": the Messages API (different shape, no JSON mode)

`complete()` returns the model's text; `complete_json()` parses it (with the ported
JSON-repair walker, which runs unconditionally — required for Anthropic).
"""
import calendar
import json
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_TIMEOUT = 60

# Groq (and other APIs) sit behind Cloudflare, which returns 403 to the default
# "Python-urllib/x.y" agent. We send a browser-like User-Agent so every user's requests look
# legitimate — this is a fixed HTTP header (NOT per-user, not a secret). It's the same value
# for everyone who installs the add-on. It can be overridden via config ("user_agent") without
# touching code, in case Cloudflare ever needs a different string; this default is the fallback.
DEFAULT_USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


class ProviderError(Exception):
    pass


_AUTH_HEADERS = ("authorization", "x-api-key", "x-goog-api-key")


class _KeepKeyHome(urllib.request.HTTPRedirectHandler):
    """urllib copies every header onto a redirected request, the API key included, to any host and
    even from https down to http. Follow a redirect only while it stays on the same host over https;
    anywhere else the key headers are dropped, so a redirect can never carry a key off its host."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is None:
            return None
        old_u, new_u = urllib.parse.urlsplit(req.full_url), urllib.parse.urlsplit(new.full_url)
        if new_u.hostname != old_u.hostname or (old_u.scheme == "https" and new_u.scheme != "https"):
            for h in list(new.headers):
                if h.lower() in _AUTH_HEADERS:
                    del new.headers[h]
            for h in list(new.unredirected_hdrs):
                if h.lower() in _AUTH_HEADERS:
                    del new.unredirected_hdrs[h]
        return new


_OPENER = urllib.request.build_opener(_KeepKeyHome)


def open_url(req, timeout):
    """urlopen through the redirect-safe opener. Use it for every request that carries a key."""
    return _OPENER.open(req, timeout=timeout)


_LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1")


def _base_url(provider):
    """The provider's base URL, https only. Plain http is allowed for a model running on this
    computer (Ollama), never for a remote host, because the key would travel unencrypted."""
    base = (provider.get("base_url") or "https://api.openai.com/v1").strip().rstrip("/")
    u = urllib.parse.urlsplit(base)
    if u.scheme != "https" and not (u.scheme == "http" and u.hostname in _LOCAL_HOSTS):
        raise ProviderError("insecure base URL: %s (use https://, or http:// only for localhost)" % base)
    return base


def _post(url, body, headers, timeout, user_agent=DEFAULT_USER_AGENT):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json", "User-Agent": user_agent, **headers},
    )
    with open_url(req, timeout) as r:
        return json.loads(r.read())


def _get(url, headers, timeout, user_agent=DEFAULT_USER_AGENT):
    req = urllib.request.Request(url, headers={"User-Agent": user_agent, **headers})
    with open_url(req, timeout) as r:
        return json.loads(r.read())


# Provider 429 bodies say things like "try again in 7.66s", "in 232.599ms", "in 2m30s", "in 16h3m10s".
# Units are parsed explicitly: the old regex read "232.599ms" as 232 MINUTES (instant fast-fail on a
# sub-second limit) and "16h3m10s" as 16 seconds (retried a daily wall three times).
_WAIT_RE = re.compile(
    r"try again in\s+(?:(\d+(?:\.\d+)?)\s*h)?\s*(?:(\d+(?:\.\d+)?)\s*m(?!s))?\s*(?:(\d+(?:\.\d+)?)\s*(ms|s))?",
    re.IGNORECASE)


def _parse_wait(body, default=5.0):
    """Seconds the provider asked us to wait, or `default` when the body has no parseable hint.
    Never raises: a parse failure must not replace the real HTTPError."""
    m = _WAIT_RE.search(body or "")
    if not m:
        return default
    hours, mins, val, unit = m.groups()
    if not (hours or mins or val):
        return default
    try:
        secs = 0.0
        if hours:
            secs += float(hours) * 3600
        if mins:
            secs += float(mins) * 60
        if val:
            secs += float(val) / 1000.0 if (unit or "").lower() == "ms" else float(val)
        return secs
    except (TypeError, ValueError):
        return default


def _retry_429(fn, max_retries=3, retry_cap=30):
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except urllib.error.HTTPError as he:
            if he.code != 429:
                raise
            body = he.read().decode("utf-8", "ignore")
            he._cached_body = body  # body is now consumed; cache it so _provider_detail still works
            wait = _parse_wait(body)
            # Fail FAST on a long wait (daily TPD/RPD limit that won't reset for minutes) — retrying
            # there just makes the user wait ~90s for nothing. Only retry short per-minute limits.
            if wait > retry_cap or attempt >= max_retries:
                raise
            time.sleep(min(wait + 1, retry_cap))
    raise ProviderError("unreachable")


def complete(provider, system, user, temperature=0.4, max_tokens=1000, timeout=DEFAULT_TIMEOUT,
             user_agent=DEFAULT_USER_AGENT):
    """Call the provider and return the raw text completion. `provider` is a config dict:
    {type, base_url?, model, api_key}."""
    ptype = (provider.get("type") or "openai_compatible").lower()
    key = provider.get("api_key") or ""
    model = provider.get("model") or ""
    if not key:
        raise ProviderError("no API key set for provider %r" % provider.get("name", ptype))

    if ptype == "anthropic":
        def call():
            resp = _post(
                "https://api.anthropic.com/v1/messages",
                {"model": model, "max_tokens": max_tokens, "temperature": temperature,
                 "system": system, "messages": [{"role": "user", "content": user}]},
                {"x-api-key": key, "anthropic-version": "2023-06-01"},
                timeout, user_agent,
            )
            parts = [b.get("text", "") for b in resp.get("content", []) if b.get("type") == "text"]
            return "".join(parts)
        return _retry_429(call)

    # openai_compatible
    base = _base_url(provider)

    def call():
        body = {
            "model": model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        resp = _post(base + "/chat/completions", body, {"Authorization": "Bearer " + key}, timeout, user_agent)
        return resp.get("choices", [{}])[0].get("message", {}).get("content", "") or ""
    try:
        return _retry_429(call)
    except urllib.error.HTTPError as he:
        # Some OpenAI-compatible servers reject response_format; retry once without it.
        if he.code in (400, 422):
            def call_plain():
                body = {
                    "model": model,
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }
                resp = _post(base + "/chat/completions", body, {"Authorization": "Bearer " + key}, timeout, user_agent)
                return resp.get("choices", [{}])[0].get("message", {}).get("content", "") or ""
            return _retry_429(call_plain)
        raise


# ── JSON parsing + repair ────────────────────────────────────
def _json_ok(s):
    try:
        c = re.sub(r"^```\w*\n?|\n?```$", "", s.strip(), flags=re.MULTILINE).strip()
        a, b = c.find("{"), c.rfind("}")
        if a >= 0 and b >= 0:
            c = c[a:b + 1]
        json.loads(c)
        return True
    except Exception:
        return False


def repair_json(s):
    """Escape stray ASCII double-quotes that appear INSIDE string values (no-op if already
    valid). Required for models without a JSON mode (e.g. Anthropic)."""
    if not s or _json_ok(s):
        return s
    out, in_string, escape_next = [], False, False
    for i, c in enumerate(s):
        if escape_next:
            out.append(c)
            escape_next = False
            continue
        if c == "\\":
            out.append(c)
            escape_next = True
            continue
        if c == '"':
            if not in_string:
                in_string = True
                out.append(c)
            else:
                j = i + 1
                while j < len(s) and s[j] in " \t\n\r":
                    j += 1
                if j >= len(s) or s[j] in ",}]:":
                    in_string = False
                    out.append(c)
                else:
                    out.append('\\"')
            continue
        out.append(c)
    repaired = "".join(out)
    return repaired if _json_ok(repaired) else s


def parse_json(text):
    if not text:
        raise ProviderError("empty provider response")
    c = repair_json(text)
    c = re.sub(r"^```\w*\n?|\n?```$", "", c.strip(), flags=re.MULTILINE).strip()
    a, b = c.find("{"), c.rfind("}")
    if a >= 0 and b >= 0:
        c = c[a:b + 1]
    # Raise a ProviderError (not a raw JSONDecodeError) so friendly_error maps it to the actionable
    # "Unreadable response, switch to a stronger model" hint instead of a traceback dialog.
    try:
        obj = json.loads(c)
    except ValueError as e:
        raise ProviderError("could not parse provider JSON: %s" % e)
    if not isinstance(obj, dict):
        raise ProviderError("could not parse provider JSON: expected an object, got %s" % type(obj).__name__)
    return obj


def complete_json(provider, system, user, temperature=0.4, max_tokens=1000, timeout=DEFAULT_TIMEOUT,
                  user_agent=DEFAULT_USER_AGENT):
    return parse_json(complete(provider, system, user, temperature, max_tokens, timeout, user_agent))


def test_provider(provider, timeout=20, user_agent=DEFAULT_USER_AGENT):
    """Lightweight key/connectivity check. Returns a short status string, or raises.

    OpenAI-compatible: GET /models — validates auth with no token cost and no dependence on
    the model name or JSON mode. Anthropic: a tiny messages call (no /models endpoint)."""
    ptype = (provider.get("type") or "openai_compatible").lower()
    key = provider.get("api_key") or ""
    if not key:
        raise ProviderError("no API key set")
    if ptype == "anthropic":
        complete(provider, "Reply with exactly: OK", "ping", temperature=0, max_tokens=5, timeout=timeout, user_agent=user_agent)
        return "Anthropic reachable"
    base = _base_url(provider)
    data = _get(base + "/models", {"Authorization": "Bearer " + key}, timeout, user_agent)
    n = len(data.get("data", []) or [])
    return "%d models available" % n


# ── model listing (for the Settings dropdown) ───────────────────────────────────────────
# Anthropic has no public /models endpoint, so we ship a curated list. Updating it = a release.
CURATED_ANTHROPIC_MODELS = [
    "claude-opus-4-8",
    "claude-sonnet-4-6",
    "claude-haiku-4-5",
]

# Non-chat models to hide from the dropdown across ALL providers. Groq's /models now returns
# speech-to-text (whisper), TTS (orpheus / playai), and safety-classifier (guard / safeguard)
# models alongside the chat models, so filtering only OpenAI let junk through (whisper /
# orpheus / prompt-guard appeared in the Groq list). Matched as a substring of the model id;
# none of these tokens occur in a real chat model id, so universal filtering is safe.
_NONCHAT = ("whisper", "tts", "dall-e", "dalle", "embedding", "moderation",
            "guard", "safeguard", "rerank", "orpheus", "playai", "imagen",
            "transcribe", "babbage", "davinci")


def _created_ts(m):
    """Epoch seconds for newest-first sorting. OpenAI-style payloads carry an int `created`;
    Anthropic's /v1/models carries an RFC3339 `created_at` string. Unknown -> 0 (sorts last)."""
    c = m.get("created")
    if isinstance(c, (int, float)):
        return c
    ca = m.get("created_at")
    if isinstance(ca, str) and len(ca) >= 19:
        try:
            return calendar.timegm(time.strptime(ca[:19], "%Y-%m-%dT%H:%M:%S"))
        except (ValueError, OverflowError):
            pass
    return 0


def _rank_models(data):
    """Pure (no network): the /models `data` array → filtered, de-duped, sorted id list.
    Drops non-chat models (STT/TTS/embedding/guard/...) for every provider. Newest-first using
    the API's `created` timestamp when present, then alphabetical."""
    items, seen = [], set()
    for m in (data or []):
        if m is None:
            continue
        if isinstance(m, dict):
            mid = m.get("id")
            mid = mid.strip() if isinstance(mid, str) else ""   # LiteLLM/self-hosted payloads vary
            created = _created_ts(m)
        else:
            mid, created = str(m).strip(), 0
        if not mid or mid in seen:
            continue
        if any(tok in mid.lower() for tok in _NONCHAT):
            continue
        seen.add(mid)
        items.append((mid, created))
    items.sort(key=lambda t: (-t[1], t[0]))  # newest-first, then alphabetical
    return [mid for mid, _ in items]


def _anthropic_models(key, timeout, user_agent):
    """Anthropic now exposes GET /v1/models — try it live, fall back to the curated list
    on any failure (older keys, network, shape change)."""
    try:
        data = _get("https://api.anthropic.com/v1/models",
                    {"x-api-key": key, "anthropic-version": "2023-06-01"}, timeout, user_agent)
        ranked = _rank_models(data.get("data", []) or [])
        return ranked or list(CURATED_ANTHROPIC_MODELS)
    except Exception:
        return list(CURATED_ANTHROPIC_MODELS)


def list_models(provider, timeout=15, user_agent=DEFAULT_USER_AGENT):
    """Return a list of model-id strings for the Settings dropdown, always live when a key is set.
    Anthropic → GET /v1/models (curated fallback). OpenAI-compatible (Groq / OpenAI / OpenRouter /
    Gemini / Mistral / Ollama) → GET {base}/models. Non-chat models are filtered for all of them."""
    ptype = (provider.get("type") or "openai_compatible").lower()
    key = provider.get("api_key") or ""
    if ptype == "anthropic":
        return _anthropic_models(key, timeout, user_agent) if key else list(CURATED_ANTHROPIC_MODELS)
    if not key:
        raise ProviderError("no API key set")
    base = _base_url(provider)
    data = _get(base + "/models", {"Authorization": "Bearer " + key}, timeout, user_agent)
    return _rank_models(data.get("data", []) or [])


# ── user-facing error mapping (shared by the dialog + settings) ──────────────────────────
def _provider_detail(exc):
    """Best-effort extraction of the provider's own human message from an HTTPError body.
    Safe to call once (consumes the body); returns '' if unavailable."""
    if not isinstance(exc, urllib.error.HTTPError):
        return ""
    try:
        cached = getattr(exc, "_cached_body", None)  # _retry_429 may have already consumed the body
        raw = (cached if cached is not None else (exc.read() or b"").decode("utf-8", "ignore")).strip()
    except Exception:
        return ""
    if not raw:
        return ""
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            err = obj.get("error")
            if isinstance(err, dict) and err.get("message"):
                return str(err["message"]).strip()[:300]
            if isinstance(err, str) and err.strip():
                return err.strip()[:300]
            if obj.get("message"):
                return str(obj["message"]).strip()[:300]
    except Exception:
        pass
    return raw[:200]


def friendly_error(exc, model=None):
    """Turn a pipeline/provider exception into (title, body, kind) for the UI.

    kind: 'settings' = the user can fix it in Settings (key / model choice);
          'retry'    = transient (network, timeout, provider 5xx) — just try again;
          'unknown'  = unexpected — the UI should also show the copyable traceback.
    The body is plain, jargon-free guidance that names the model and the next step.
    """
    mq = ('"%s"' % model) if model else "the selected model"
    detail = _provider_detail(exc)
    said = ("\n\nProvider said: " + detail) if detail else ""

    if isinstance(exc, urllib.error.HTTPError):
        code = exc.code
        low = (detail or "").lower()
        if code == 429:
            daily = any(k in low for k in ("per day", "tokens per day", "requests per day",
                                           "daily", "quota", "tpd", "rpd"))
            if daily:
                return ("Daily limit reached",
                        "You've reached today's usage limit for %s.\n\n"
                        "• This kind of free-tier limit usually resets later (often the next day).\n"
                        "• To keep making cards right now, open Settings and pick a different model "
                        "(click ↻ Refresh to list every model your key can use).\n\n"
                        "Smaller / free models tend to run out sooner." % mq + said, "settings")
            return ("Rate limit reached",
                    "Too many requests in a short time for %s.\n\n"
                    "• Wait about a minute, then click Add again, or\n"
                    "• open Settings and switch to a different model (↻ Refresh)." % mq + said,
                    "settings")
        if code == 401:
            return ("API key not accepted",
                    "Your API key was rejected (401). It may be wrong, expired, or revoked.\n\n"
                    "Open Settings, paste a valid key, and click “Test key”." + said, "settings")
        if code == 403:
            return ("Access blocked",
                    "The provider refused the request (403). Your key may not be allowed to use %s, "
                    "or the provider blocked it.\n\n"
                    "Try “Test key” in Settings, or choose a different model or provider." % mq
                    + said, "settings")
        if code == 404:
            return ("Model not found",
                    "%s could not be found (404). It may have been retired, or the Base URL is wrong.\n\n"
                    "Open Settings → ↻ Refresh and pick a current model." % mq + said, "settings")
        if code in (400, 422):
            return ("Request rejected",
                    "The provider rejected the request (%d). The most common cause is an invalid or "
                    "retired model name (%s).\n\n"
                    "Open Settings → ↻ Refresh and choose a current model." % (code, mq) + said,
                    "settings")
        if 500 <= code <= 599:
            return ("The provider is having trouble",
                    "The provider returned a server error (%d). This is on their side, not yours.\n\n"
                    "Wait a moment and click Add again. If it keeps happening, switch model or provider "
                    "in Settings." % code + said, "retry")
        return ("Provider error (HTTP %d)" % code, (detail or "The provider returned an error."), "unknown")

    if isinstance(exc, (socket.timeout, TimeoutError)):
        return ("It timed out",
                "The provider took too long to answer.\n\n"
                "• Click Add to try again, or\n"
                "• pick a faster model in Settings, or raise the timeout in the add-on config.", "retry")
    if isinstance(exc, urllib.error.URLError):
        return ("Can't reach the provider",
                "There was no connection to the provider.\n\n"
                "• Check your internet connection.\n"
                "• Check the Base URL in Settings (“Test key” confirms it works).", "retry")

    text = (str(exc) or "").strip()
    low = text.lower()
    if isinstance(exc, ProviderError) and "insecure base url" in low:
        return ("Base URL must use https",
                "The Base URL in Settings starts with http://, so your API key would travel unencrypted. "
                "Change it to https://. Plain http:// only works for a model running on this computer "
                "(localhost).", "settings")
    if isinstance(exc, ProviderError) and "no api key" in low:
        return ("No API key set",
                "This provider has no API key.\n\nOpen Settings and paste your key (a free Groq key works).",
                "settings")
    if "not german:" in low:
        # exc text is: not german: "<input>"; suggestion "<german word or empty>"
        quoted = re.findall(r'"([^"]*)"', text)
        w = quoted[0] if quoted else ""
        sug = quoted[1] if len(quoted) > 1 else ""
        hint = ('\n\nDid you mean "%s"?' % sug) if sug else ""
        return ("That does not look like German",
                'The model could not recognise "%s" as a German word or phrase, so no card was made.%s\n\n'
                "Check the spelling, or type the German word you want to learn. Names and loanwords that\n"
                "are used in German are fine." % (w, hint), "retry")
    if "word mismatch" in low:
        # exc text is: word mismatch: expected "<your word>", got "<what the model returned>"
        quoted = re.findall(r'"([^"]*)"', text)
        if len(quoted) >= 2:
            got = ', it returned "%s" instead of "%s"' % (quoted[1], quoted[0])
        elif quoted:
            got = ' than "%s"' % quoted[0]
        else:
            got = ""
        return ("Couldn't match your word",
                "The model kept generating a card for a different word than the one you typed%s.\n\n"
                "• Add a short meaning hint (e.g. which sense you mean), or\n"
                "• click Add to try again, or\n"
                "• switch to a stronger model in Settings." % got, "settings")
    if any(k in low for k in ("empty provider response", "could not parse", "no json", "json", "no audio received")):
        return ("Unreadable response",
                "The model returned an empty or badly-formatted reply. Smaller models sometimes can't "
                "follow the required format.\n\n"
                "• Click Add to try again, or\n"
                "• switch to a stronger model in Settings.", "settings")
    if ("customclozede" in low or "'german ai'" in low or ("missing" in low and "field" in low)
            or "not a cloze note type" in low):
        return ("Note type conflict", text, "unknown")
    return ("Something went wrong", text or exc.__class__.__name__, "unknown")
