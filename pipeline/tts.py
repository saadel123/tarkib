"""Voice services for the card audio, and the order they are tried in.

The free Microsoft Edge read-aloud voices (audio.py) are the default and need no key. They are an
unofficial endpoint, so they can break (on 13 Oct 2026 Microsoft started refusing the old token).
A user can pick a service with their own key instead, or keep one as a backup:

  edge        Microsoft Edge read-aloud: free, no key (audio.synthesize)
  azure       Azure AI Speech: key + region, the same neural voice names as Edge
  elevenlabs  ElevenLabs: key + voice id + model
  openai      OpenAI text to speech: key + voice + model
  google      Google Cloud Text-to-Speech: key, optionally a German voice name
  gemini      Gemini API speech generation: key + voice + model (raw PCM, saved as WAV)

The chain for every clip: the chosen service, then each other service that is set up, in the
user's order, then Edge. A service that fails hard (key, quota, network) is skipped for the rest of
the card, so a broken service costs one wait, not one per clip. Every failure is kept
(Speaker.failures) and logged, so the Add dialog can say exactly why a card has no audio, or which
service read it instead.

Pure stdlib (urllib, json, base64, wave). Runs off the UI thread and never touches Anki or Qt.
Keys go only to their own service (providers.open_url drops key headers on a redirect to another
host) and are never logged or shown: error details are redacted before they leave this module.
"""
import base64
import hashlib
import html
import http.client
import io
import json
import logging
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import wave
from collections import namedtuple

from . import audio, providers

# Anki gives every logger named "addon.<add-on folder>" a log file of its own
# (Anki2/logs/addons/<folder>/<folder>.log, kept 10 days). Outside Anki this is a plain logger.
log = logging.getLogger("addon." + __name__.split(".")[0])
log.addHandler(logging.NullHandler())

SERVICES = ("edge", "azure", "elevenlabs", "openai", "google", "gemini")
LABELS = {"edge": "Microsoft Edge", "azure": "Azure AI Speech", "elevenlabs": "ElevenLabs",
          "openai": "OpenAI", "google": "Google Cloud", "gemini": "Gemini"}
DEFAULT_ORDER = ("azure", "elevenlabs", "openai", "google", "gemini")
DEFAULT_GERMAN_VOICE = "de-DE-KatjaNeural"
USER_AGENT = "Tarkib-Anki-addon"
MAX_AUDIO = 16 * 1024 * 1024          # a sane clip is well under 1 MB

# What each paid service needs, and the defaults a fresh config starts from (config.json "tts").
# Checked against each provider's own documentation on 2026-10-14.
DEFAULTS = {
    "azure": {"key": "", "region": ""},
    # No ElevenLabs voice id works for every account (the old default voices end on 2026-12-31 and
    # free keys cannot use Voice Library voices), so the user picks one from their own list.
    "elevenlabs": {"key": "", "voice": "", "voice_name": "", "model": "eleven_multilingual_v2"},
    "openai": {"key": "", "voice": "marin", "model": "gpt-4o-mini-tts"},
    "google": {"key": "", "voice": "de-DE-Chirp3-HD-Kore"},
    "gemini": {"key": "", "voice": "Kore", "model": "gemini-3.8-flash-lite-tts"},
}
REQUIRED = {"azure": ("key", "region"), "elevenlabs": ("key", "voice"), "openai": ("key",),
            "google": ("key",), "gemini": ("key",)}

# Dropdown choices in Settings. The dropdowns stay editable, so a newer id works without a release.
# The public Azure regions that serve text to speech (the region of the Speech resource).
AZURE_REGIONS = ["westeurope", "germanywestcentral", "northeurope", "francecentral", "swedencentral",
                 "switzerlandnorth", "switzerlandwest", "italynorth", "norwayeast", "uksouth", "ukwest",
                 "eastus", "eastus2", "westus", "westus2", "westus3", "centralus", "northcentralus",
                 "southcentralus", "westcentralus", "canadacentral", "canadaeast", "brazilsouth",
                 "southafricanorth", "uaenorth", "qatarcentral", "centralindia", "eastasia",
                 "southeastasia", "japaneast", "japanwest", "koreacentral", "australiaeast"]
# eleven_turbo_v2_5 is deprecated (use eleven_flash_v2_5); eleven_flash_v2 is English only. ElevenLabs'
# own pages disagree on whether eleven_v4 is served by this endpoint (or only by Text to Dialogue),
# so it is offered last; a refusal falls back like any other failure.
ELEVENLABS_MODELS = ["eleven_multilingual_v2", "eleven_flash_v2_5", "eleven_v3", "eleven_v4"]
# OpenAI announced that all of these are removed from the API on 2027-01-06 (the only named
# replacement is a Realtime model, which this endpoint does not serve).
OPENAI_MODELS = ["gpt-4o-mini-tts", "tts-1-hd", "tts-1"]
OPENAI_VOICES = ["marin", "cedar", "alloy", "ash", "ballad", "coral", "echo", "fable", "nova", "onyx",
                 "sage", "shimmer", "verse"]
_OPENAI_TTS1_VOICES = ("alloy", "ash", "coral", "echo", "fable", "onyx", "nova", "sage", "shimmer")
# Current German voices (Chirp 3 HD is Google's latest family; Neural2, WaveNet and Standard cost less).
GOOGLE_GERMAN_VOICES = ["de-DE-Chirp3-HD-Kore", "de-DE-Chirp3-HD-Charon", "de-DE-Chirp3-HD-Aoede",
                        "de-DE-Chirp3-HD-Puck", "de-DE-Chirp3-HD-Leda", "de-DE-Chirp3-HD-Fenrir",
                        "de-DE-Neural2-G", "de-DE-Neural2-H", "de-DE-Wavenet-G", "de-DE-Wavenet-H",
                        "de-DE-Standard-G", "de-DE-Standard-H"]
# 3.8 models are GA since 2026-09-22; the 2.5 and 3.1 previews may shut down from 2026-11-17.
GEMINI_MODELS = ["gemini-3.8-flash-lite-tts", "gemini-3.8-flash-tts", "gemini-3.1-flash-tts-preview",
                 "gemini-2.5-flash-preview-tts"]
GEMINI_VOICES = ["Zephyr", "Puck", "Charon", "Kore", "Fenrir", "Leda", "Orus", "Aoede", "Callirrhoe",
                 "Autonoe", "Enceladus", "Iapetus", "Umbriel", "Algieba", "Despina", "Erinome",
                 "Algenib", "Rasalgethi", "Laomedeia", "Achernar", "Alnilam", "Schedar", "Gacrux",
                 "Pulcherrima", "Achird", "Zubenelgenubi", "Vindemiatrix", "Sadachbia",
                 "Sadaltager", "Sulafat"]

# One clip of audio. voice names exactly what spoke (model/voice for the services that have
# both), so generate.py can hash it into the filename: same text, service and voice = same file.
Clip = namedtuple("Clip", "data ext service voice")


class TTSError(Exception):
    """A voice service failed. The message is one readable sentence that names the service.

    kind: config (not set up) | auth (key refused) | quota (credits or billing) | rate_limit |
    network | timeout | server (5xx) | bad_request (this text, voice or model refused) | no_audio."""

    def __init__(self, service, kind, message, status=None):
        super().__init__(message)
        self.service = service
        self.kind = kind
        self.status = status


# The order the Add dialog uses to name the most useful cause first: something the user must fix
# in Settings beats something that clears up by itself.
_KIND_RANK = {"config": 8, "auth": 7, "quota": 6, "bad_request": 5, "rate_limit": 4, "server": 3,
              "timeout": 2, "network": 2, "no_audio": 1, None: 0}
# Failures that say nothing about the next clip (this text, voice or model): try the service again.
_SOFT_KINDS = ("bad_request", "no_audio")


def worse_kind(a, b):
    return a if _KIND_RANK.get(a, 0) >= _KIND_RANK.get(b, 0) else b


def _as_dict(tts_cfg):
    """config["tts"] as a dict, whatever a hand edit left there (a string, a list, None)."""
    return tts_cfg if isinstance(tts_cfg, dict) else {}


def service_cfg(tts_cfg, service):
    """The settings of one service, with defaults filled in. Anki merges a stored config only one
    level deep, so a config saved by an older version can lack any of these keys."""
    out = dict(DEFAULTS.get(service, {}))
    stored = _as_dict(tts_cfg).get(service)
    if isinstance(stored, dict):
        out.update({k: v for k, v in stored.items() if v is not None})
    def text(v):
        if isinstance(v, str):
            return v.strip()
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return str(v)
        return ""                    # a list, a dict or a bool from a hand edit: treat as not set
    return {k: text(v) for k, v in out.items()}


def configured(service, tts_cfg):
    """True when the service has everything it needs (Edge needs nothing)."""
    if service == "edge":
        return True
    sc = service_cfg(tts_cfg, service)
    return service in REQUIRED and all(sc.get(k) for k in REQUIRED[service])


def chosen(tts_cfg):
    s = _as_dict(tts_cfg).get("service")
    s = s.strip().lower() if isinstance(s, str) else ""
    return s if s in SERVICES else "edge"


def backup_order(tts_cfg):
    """The user's backup order: every paid service once, stored order first, unknown ids dropped."""
    order = _as_dict(tts_cfg).get("order")
    stored = [s for s in order if isinstance(s, str) and s in DEFAULT_ORDER] if isinstance(order, list) else []
    out = []
    for s in stored + list(DEFAULT_ORDER):
        if s not in out:
            out.append(s)
    return out


def chain(tts_cfg):
    """The services one clip may try, in order: the chosen one (even when it is not set up, so the
    user hears why it was skipped), then the backups that are set up, then Edge."""
    first = chosen(tts_cfg)
    out = [first]
    for s in backup_order(tts_cfg) + ["edge"]:
        if s not in out and configured(s, tts_cfg):
            out.append(s)
    return out


class Speaker:
    """Speaks the clips of ONE card. Holds what the services did so far, so a service that failed
    hard is skipped for the next clips and the dialog can report every reason afterwards."""

    def __init__(self, tts_cfg, timeout=30):
        self.cfg = _as_dict(tts_cfg)
        self.timeout = timeout
        self.order = chain(self.cfg)
        self.dead = set()
        # (service, voice) pairs refused with bad_request: a voice or language that service will not
        # read (Edge's 1007 for a retired voice, Google for a language it does not serve). Skipped
        # for later clips in that voice, while the service still reads the other voices.
        self.refused = set()
        self.failures = []          # TTSError, one per distinct (service, message)
        self.used = {}              # service -> clips it read

    def speak(self, text, role_voice):
        """A Clip from the first service that works, or the last TTSError when none did."""
        last = None
        for service in self.order:
            if service in self.dead or (service, role_voice) in self.refused:
                continue
            try:
                clip = synthesize(service, text, role_voice, self.cfg, self.timeout)
            except TTSError as e:
                last = e
                self._note(e)
                if e.kind == "bad_request":
                    self.refused.add((service, role_voice))
                elif e.kind not in _SOFT_KINDS and not (e.kind in ("rate_limit", "server")
                                                        and self._last_alive(service)):
                    self.dead.add(service)
                continue
            except Exception as e:            # a bug in an adapter must not cost the card its audio
                # Only the error's type: an unexpected message could quote a header, and so a key.
                last = TTSError(service, "network", "%s failed (%s)" % (LABELS[service], e.__class__.__name__))
                self._note(last)
                self.dead.add(service)
                continue
            self.used[service] = self.used.get(service, 0) + 1
            if service != self.order[0]:
                log.info("audio: %s read a clip instead of %s", LABELS[service], LABELS[self.order[0]])
            return clip
        raise last or TTSError("edge", "config", "No voice service is available")

    def _last_alive(self, service):
        """True when no service after this one is left to try. A busy service is then asked again on
        the next clip (it may have cooled down); with a backup left, the backup is the better try."""
        rest = self.order[self.order.index(service) + 1:]
        return not [s for s in rest if s not in self.dead]

    def _note(self, e):
        if any(f.service == e.service and str(f) == str(e) for f in self.failures):
            return
        self.failures.append(e)
        log.warning("audio: %s [%s%s] %s", e.service, e.kind,
                    (", HTTP %s" % e.status) if e.status else "", e)

    def summary(self):
        """What the dialog needs: the worst failure kind, the readable reasons (most useful first),
        which services read clips, and whether a backup stepped in."""
        kind = None
        for f in self.failures:
            kind = worse_kind(kind, f.kind)
        # The chosen service's own failure explains best why it did not read; then the rest by rank.
        first = self.order[0]
        reasons = [str(f) for f in sorted(self.failures, key=lambda f: (f.service != first,
                                                                        -_KIND_RANK.get(f.kind, 0)))]
        backups = [s for s in self.used if s != first]
        return {"category": kind, "failures": reasons[:3], "used": dict(self.used),
                "chosen": first, "backup": backups[0] if backups else None, "backups": backups}


def audio_note(a):
    """(toast sentence, banner sentence, wants_fix_hint) about one card's audio, or ("", "", False)
    when the chosen service read every clip. `a` is meta["audio"]: ok/total plus Speaker.summary().
    Plain text: the dialog escapes it and adds the Settings link."""
    a = a if isinstance(a, dict) else {}
    ok_n, total_n = a.get("ok", 0) or 0, a.get("total", 0) or 0
    reason = ((a.get("failures") or [""])[0] or "").rstrip(".") or "the voice service did not answer"
    if total_n and ok_n == 0:
        return ("No audio, because %s" % reason, "The last card has no audio, because %s." % reason, True)
    if total_n and ok_n < total_n:
        missing = total_n - ok_n
        return ("%d of %d audio clips are missing, because %s" % (missing, total_n, reason),
                "The last card is missing %d of %d audio clips, because %s." % (missing, total_n, reason), True)
    backups = [LABELS.get(s, s) for s in (a.get("backups") or ([a["backup"]] if a.get("backup") else []))]
    if total_n and backups and a.get("failures"):
        names = " and ".join(backups) if len(backups) <= 2 else ", ".join(backups[:-1]) + " and " + backups[-1]
        return ("Read by %s, because %s" % (names, reason),
                "%s read the last card, because %s." % (names, reason), False)
    return "", "", False


def synthesize(service, text, role_voice, tts_cfg, timeout=30):
    """One service, no fallback (the Settings Test buttons call this directly). Returns a Clip or
    raises TTSError. role_voice is the Edge/Azure voice of the role (German, translation or second
    language): Edge and Azure speak with it, the others take its language from it."""
    text = " ".join((text or "").split())
    if not text:
        raise TTSError(service, "bad_request", "There was no text to read aloud")
    if service not in _ADAPTERS:
        raise TTSError(service, "config", "Unknown voice service: %s" % service)
    sc = service_cfg(tts_cfg, service)
    for k in REQUIRED.get(service, ()):
        if not sc.get(k):
            raise TTSError(service, "config", "%s is not set up: add its %s in Settings, Voice"
                           % (LABELS[service], _FIELD_NAMES.get(k, k)))
    _check_key(service, sc.get("key"))
    return _ADAPTERS[service](text, role_voice or DEFAULT_GERMAN_VOICE, sc, timeout)


def _check_key(service, key):
    """A key with a space or line break inside (two lines pasted from a note) would make urllib raise
    an error that quotes the whole key. Refuse it here, before any request, without showing it."""
    if key and re.search(r"[\s\x00-\x1f\x7f]", key):
        raise TTSError(service, "config", "%s: the API key has a space or line break in it, paste it again "
                       "in Settings, Voice" % LABELS[service])


_FIELD_NAMES = {"key": "API key", "region": "region", "voice": "voice"}


# ── helpers ────────────────────────────────────────────────────────────────────────────────
def _locale(voice):
    """'de-DE-KatjaNeural' -> 'de-DE'; '' when the name has no locale."""
    m = re.match(r"^([a-z]{2,3})-([A-Z]{2}|[A-Za-z]{4})(?:-|$)", voice or "")
    return "%s-%s" % (m.group(1), m.group(2)) if m else ""


def _language(voice):
    """'de-DE-KatjaNeural' -> 'de'."""
    return (_locale(voice) or "de-DE").split("-")[0].lower()


_LANGUAGE_NAMES = {"de": "German", "en": "English", "ar": "Arabic", "fr": "French", "es": "Spanish",
                   "tr": "Turkish", "ru": "Russian", "uk": "Ukrainian", "it": "Italian", "pl": "Polish",
                   "pt": "Portuguese", "fa": "Persian", "nl": "Dutch", "el": "Greek", "cs": "Czech",
                   "ro": "Romanian", "hu": "Hungarian", "sv": "Swedish", "id": "Indonesian",
                   "vi": "Vietnamese", "hi": "Hindi", "ur": "Urdu", "ja": "Japanese", "ko": "Korean",
                   "zh": "Chinese"}


def _short(e, limit=160):
    """One line, at most `limit` characters. An exception without a message gives its class name;
    an empty string stays empty (Azure answers a refused key with an empty body)."""
    s = " ".join(str(e).split())
    if not s and isinstance(e, BaseException):
        s = e.__class__.__name__
    return s if len(s) <= limit else s[:limit - 3].rstrip() + "..."


def _redact(text, secret):
    """Error bodies can echo a key, whole or masked. Never let one reach a message or the log."""
    s = text or ""
    if secret:
        s = s.replace(secret, "[key]")
    s = re.sub(r"\b(?:sk-|sk_|AIza)[-_A-Za-z0-9*]{8,}", "[key]", s)
    return re.sub(r"\b[A-Fa-f0-9]{32,}\b", "[key]", s)


def _parse_error(body):
    """(message, code) from an error body. The shapes differ per service:
    Google and Gemini {"error": {"message", "status", "details": [{"reason"}]}},
    OpenAI {"error": {"message", "code", "type"}}, ElevenLabs {"detail": {"message", "code"|"status"}}
    (or a list for a 422), Azure often an empty body."""
    text = (body or b"").decode("utf-8", "replace")
    try:
        data = json.loads(text)
    except Exception:
        return " ".join(text.split())[:200], ""
    if not isinstance(data, dict):
        return "", ""
    msg, code = "", ""
    for key in ("error", "detail"):
        node = data.get(key)
        if isinstance(node, str):
            msg = msg or node
        elif isinstance(node, list):              # ElevenLabs 422: [{"loc", "msg", "type"}]
            first = node[0] if node and isinstance(node[0], dict) else {}
            msg = msg or str(first.get("msg") or "")
        elif isinstance(node, dict):
            msg = msg or str(node.get("message") or "")
            for d in node.get("details") or []:
                if isinstance(d, dict) and d.get("reason"):
                    code = code or str(d["reason"])
            for k in ("code", "status", "type"):
                v = node.get(k)
                if isinstance(v, str) and v and not code:
                    code = v
    return (msg or str(data.get("message") or "")).strip(), code


# Provider error codes that decide the kind better than the HTTP status does (ElevenLabs sends a
# used-up quota with 400 or 401, Google a bad key with 400).
_AUTH_CODES = {"API_KEY_INVALID", "invalid_api_key", "missing_api_key", "authentication_error",
               "ACCESS_TOKEN_TYPE_UNSUPPORTED", "authentication"}
_PERMISSION_CODES = {"SERVICE_DISABLED", "API_KEY_SERVICE_BLOCKED", "API_KEY_HTTP_REFERRER_BLOCKED",
                     "API_KEY_IP_ADDRESS_BLOCKED", "missing_permissions", "insufficient_permissions",
                     "feature_not_available", "permission_denied"}
_PLAN_CODES = {"subscription_required"}
_QUOTA_CODES = {"BILLING_DISABLED", "insufficient_quota", "credit_balance_exhausted",
                "organization_spend_limit_exceeded", "project_spend_limit_exceeded",
                "organization_usage_limit_exceeded", "quota_exceeded", "insufficient_credits",
                "payment_required", "FAILED_PRECONDITION"}
_RATE_CODES = {"RATE_LIMIT_EXCEEDED", "rate_limit_exceeded", "slow_down", "concurrent_limit_exceeded",
               "too_many_concurrent_requests", "system_busy", "too_many_requests", "RESOURCE_EXHAUSTED"}
_SETUP_CODES = {"voice_not_found", "invalid_voice_id", "model_not_found", "unsupported_model", "NOT_FOUND",
                "voice_access_denied", "model_access_denied"}
_QUOTA_WORDS = ("quota", "credit", "billing", "prepay", "exceeded your current", "not available in your country")


def _http_error(service, status, body, secret):
    name = LABELS[service]
    msg, code = _parse_error(body)
    detail = _short(_redact(msg, secret))
    low = detail.lower()
    tail = (": " + detail) if detail else ""
    quota = TTSError(service, "quota", "%s says the credits, quota or billing need attention (HTTP %d)%s"
                     % (name, status, tail), status)
    if status == 402 or code in _QUOTA_CODES:
        return quota
    if code in _RATE_CODES:
        # Google and Gemini send every per-minute (and the free daily) limit as 429 RESOURCE_EXHAUSTED
        # with "quota" in the text; that is a limit that resets, not billing (402 above is billing).
        return TTSError(service, "rate_limit", "%s is busy or rate limited (HTTP %d), try again later%s"
                        % (name, status, tail), status)
    if status in (400, 403, 429) and any(w in low for w in _QUOTA_WORDS):
        return quota
    if code in _PLAN_CODES:
        return TTSError(service, "config", "%s needs a paid plan for this voice or model (HTTP %d)%s, pick "
                        "another in Settings, Voice" % (name, status, tail), status)
    if code in _PERMISSION_CODES:
        return TTSError(service, "auth", "%s refused the API key for this (HTTP %d)%s" % (name, status, tail), status)
    if service == "azure" and status == 401:
        # An Azure key works only in the region of its Speech resource; a wrong region looks the same.
        return TTSError(service, "auth", "%s did not accept the key for this region (HTTP 401), check the "
                        "key and the region in Settings, Voice%s" % (name, tail), status)
    if code in _AUTH_CODES or status == 401:
        return TTSError(service, "auth", "%s did not accept the API key (HTTP %d)%s" % (name, status, tail), status)
    if code in _SETUP_CODES or status == 404:
        return TTSError(service, "config", "%s cannot use this voice or model (HTTP %d)%s, pick another "
                        "in Settings, Voice" % (name, status, tail), status)
    if status == 403:
        return TTSError(service, "auth", "%s refused the request (HTTP 403)%s" % (name, tail), status)
    if status == 429 or code in _RATE_CODES:
        return TTSError(service, "rate_limit", "%s is busy or rate limited (HTTP %d), try again in a minute%s"
                        % (name, status, tail), status)
    if status >= 500:
        return TTSError(service, "server", "%s is having trouble (HTTP %d)%s" % (name, status, tail), status)
    return TTSError(service, "bad_request", "%s refused the request (HTTP %d)%s" % (name, status, tail), status)


def _request(service, url, headers, body, timeout, secret, method="POST"):
    """An HTTPS request to a voice service: (content_type, bytes), or TTSError. A busy service
    (429 that is not a used-up quota), a 5xx or a dropped connection gets one more try on a fresh
    connection after a short pause; a timeout does not (it already cost the full wait, and the next
    service in the chain is the better retry). A key refusal or a bad request is final at once."""
    try:
        return _request_once(service, url, headers, body, timeout, secret, method)
    except TTSError as e:
        wait = getattr(e, "retry_after", 0) or 0
        if e.kind not in ("rate_limit", "server", "network") or wait > 5:
            raise                              # a long Retry-After: the next service is the better retry
        time.sleep(wait or (1.5 if e.kind == "rate_limit" else 0.5))
    return _request_once(service, url, headers, body, timeout, secret, method)


def _request_once(service, url, headers, body, timeout, secret, method):
    if not url.startswith("https://"):
        raise TTSError(service, "config", "%s: refusing a non-https address" % LABELS[service])
    hdrs = {"User-Agent": USER_AGENT}
    hdrs.update(headers)
    req = urllib.request.Request(url, data=body, headers=hdrs, method=method)
    try:
        with providers.open_url(req, timeout) as r:
            data = r.read(MAX_AUDIO + 1)
            ctype = r.headers.get("Content-Type", "") or ""
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read(65536)
        except Exception:
            err_body = b""
        err = _http_error(service, e.code, err_body, secret)
        try:
            err.retry_after = max(0.0, float((e.headers or {}).get("Retry-After") or 0))
        except (TypeError, ValueError):
            err.retry_after = 0.0              # an HTTP date: treat as no hint
        raise err
    except (socket.timeout, TimeoutError):
        raise TTSError(service, "timeout", "%s did not answer within %d seconds" % (LABELS[service], timeout))
    except urllib.error.URLError as e:
        if isinstance(e.reason, (socket.timeout, TimeoutError)):
            raise TTSError(service, "timeout", "%s did not answer within %d seconds" % (LABELS[service], timeout))
        raise TTSError(service, "network", "%s could not be reached (%s)"
                       % (LABELS[service], _short(_redact(str(e.reason), secret))))
    except (OSError, http.client.HTTPException) as e:     # reset, refused, TLS, a cut-off answer
        raise TTSError(service, "network", "%s could not be reached (%s)"
                       % (LABELS[service], _short(_redact(str(e), secret))))
    except ValueError:                                     # e.g. an invalid header value: never quote it
        raise TTSError(service, "config", "%s: the request could not be sent, check the API key in "
                       "Settings, Voice" % LABELS[service])
    if len(data) > MAX_AUDIO:
        raise TTSError(service, "no_audio", "%s sent more audio than any clip needs" % LABELS[service])
    return ctype, data


def _json(service, data):
    try:
        out = json.loads(data.decode("utf-8"))
    except Exception:
        raise TTSError(service, "no_audio", "%s sent an answer that is not readable" % LABELS[service])
    if not isinstance(out, dict):
        raise TTSError(service, "no_audio", "%s sent an answer that is not readable" % LABELS[service])
    return out


def _audio_bytes(service, ctype, data):
    """Raw audio from a service that answers with the audio itself. A JSON or HTML page with
    status 200 (a proxy, a captive portal) is not audio, and neither is an empty body."""
    if not data or ctype.split(";")[0].strip().lower() in ("application/json", "text/html", "text/plain"):
        raise TTSError(service, "no_audio", "%s sent no audio" % LABELS[service])
    return data


def _b64(service, value):
    try:
        out = base64.b64decode(value or "", validate=False)
    except Exception:
        out = b""
    if not out:
        raise TTSError(service, "no_audio", "%s sent no audio" % LABELS[service])
    return out


def pcm_to_wav(pcm, rate=24000, channels=1, width=2):
    """Wrap raw little-endian PCM in a WAV header (Gemini returns bare 16-bit samples). Anki plays
    WAV on every platform; stdlib has no MP3 encoder, so WAV it is (about 48 KB per second)."""
    pcm = pcm[:len(pcm) - (len(pcm) % (channels * width))]
    buf = io.BytesIO()
    w = wave.open(buf, "wb")
    try:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(pcm)
    finally:
        w.close()
    return buf.getvalue()


# ── the services ───────────────────────────────────────────────────────────────────────────
def _edge(text, role_voice, sc, timeout):
    # Edge answers a short clip in about a second, so it never waits longer than its own cap.
    try:
        data = audio.synthesize(text, role_voice, timeout=min(float(timeout), audio.REQUEST_TIMEOUT))
    except audio.EdgeTTSError as e:
        raise TTSError("edge", e.kind, str(e), e.status)
    return Clip(data, "mp3", "edge", role_voice)


def azure_region(value):
    """'West Europe' or 'westeurope' -> 'westeurope'. Only letters and digits survive, so a region
    can never change the host the key is sent to."""
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def _azure(text, role_voice, sc, timeout):
    region = azure_region(sc["region"])
    if not region:
        raise TTSError("azure", "config", "Azure AI Speech is not set up: add its region in Settings, Voice")
    ssml = ("<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='%s'>"
            "<voice name='%s'>%s</voice></speak>"
            % (_locale(role_voice) or "de-DE", html.escape(role_voice, quote=True),
               html.escape(text, quote=False)))
    ctype, data = _request("azure", "https://%s.tts.speech.microsoft.com/cognitiveservices/v1" % region,
                           {"Ocp-Apim-Subscription-Key": sc["key"], "Content-Type": "application/ssml+xml",
                            "X-Microsoft-OutputFormat": audio.OUTPUT_FORMAT},
                           ssml.encode("utf-8"), timeout, sc["key"])
    return Clip(_audio_bytes("azure", ctype, data), "mp3", "azure", role_voice)


def _elevenlabs(text, role_voice, sc, timeout):
    model = sc.get("model") or DEFAULTS["elevenlabs"]["model"]
    body = {"text": text, "model_id": model}
    # language_code (ISO 639-1) pins the language; multilingual_v2 does not take it and detects
    # the language itself. Other models ignore a code they do not support.
    if model != "eleven_multilingual_v2":
        body["language_code"] = _language(role_voice)
    # 64 kbps: half the size of the 128 kbps default, plenty for speech, allowed on the free plan.
    url = ("https://api.elevenlabs.io/v1/text-to-speech/%s?output_format=mp3_44100_64"
           % urllib.parse.quote(sc["voice"], safe=""))
    ctype, data = _request("elevenlabs", url, {"xi-api-key": sc["key"], "Content-Type": "application/json",
                                               "Accept": "audio/mpeg"},
                           json.dumps(body).encode("utf-8"), timeout, sc["key"])
    return Clip(_audio_bytes("elevenlabs", ctype, data), "mp3", "elevenlabs", "%s/%s" % (model, sc["voice"]))


def _openai(text, role_voice, sc, timeout):
    model = sc.get("model") or DEFAULTS["openai"]["model"]
    voice = sc.get("voice") or DEFAULTS["openai"]["voice"]
    if model.startswith("tts-1") and voice not in _OPENAI_TTS1_VOICES:
        raise TTSError("openai", "config", "OpenAI: the voice %s needs the model gpt-4o-mini-tts, pick it "
                       "in Settings, Voice" % voice)
    body = {"model": model, "input": text, "voice": voice, "response_format": "mp3"}
    if not model.startswith("tts-1"):
        # gpt-4o-mini-tts takes a style instruction; naming the language keeps a lone German
        # word from being read with an English accent.
        body["instructions"] = ("The text is %s. Read it exactly as written, clearly and at a calm, "
                                "natural pace." % _LANGUAGE_NAMES.get(_language(role_voice), "German"))
    ctype, data = _request("openai", "https://api.openai.com/v1/audio/speech",
                           {"Authorization": "Bearer " + sc["key"], "Content-Type": "application/json"},
                           json.dumps(body).encode("utf-8"), timeout, sc["key"])
    return Clip(_audio_bytes("openai", ctype, data), "mp3", "openai", "%s/%s" % (model, voice))


# Google serves fewer regional variants than Edge has voices for (es-AR, fr-BE, de-AT ...), and
# names a few languages differently. A locale it does not serve is mapped to one it does; a
# language missing here keeps its locale, and Google may substitute a region itself when no voice
# name is sent.
_GOOGLE_LOCALES = {"ar": "ar-XA", "zh-CN": "cmn-CN", "zh-TW": "cmn-TW", "zh-HK": "yue-HK", "zh": "cmn-CN",
                   "de": "de-DE", "fr-CA": "fr-CA", "fr": "fr-FR", "es-ES": "es-ES", "es": "es-US",
                   "en-US": "en-US", "en-GB": "en-GB", "en-AU": "en-AU", "en-IN": "en-IN", "en": "en-US",
                   "pt-BR": "pt-BR", "pt": "pt-PT", "it": "it-IT", "nl-BE": "nl-BE", "nl": "nl-NL",
                   "ur": "ur-IN", "fa": "fa-IR", "tr": "tr-TR", "ru": "ru-RU", "uk": "uk-UA", "pl": "pl-PL",
                   "el": "el-GR", "cs": "cs-CZ", "ro": "ro-RO", "hu": "hu-HU", "sv": "sv-SE", "id": "id-ID",
                   "vi": "vi-VN", "hi": "hi-IN", "ja": "ja-JP", "ko": "ko-KR"}


# Helper languages Tarkib offers that Google Cloud Text-to-Speech has no voice for.
_GOOGLE_UNSERVED = {"fa": "Persian"}


def _google_locale(locale):
    return _GOOGLE_LOCALES.get(locale) or _GOOGLE_LOCALES.get(locale.split("-")[0]) or locale


def _google(text, role_voice, sc, timeout):
    if _language(role_voice) in _GOOGLE_UNSERVED:
        raise TTSError("google", "bad_request", "Google Cloud has no %s voice"
                       % _GOOGLE_UNSERVED[_language(role_voice)])
    lang = _google_locale(_locale(role_voice) or "de-DE")
    name = sc.get("voice") or ""
    if name and not re.match(r"^[a-z]{2,3}-[A-Za-z]{2,4}-", name):
        # Bare names (Kore, Charon) are Gemini voices, which Cloud TTS only serves with a model.
        raise TTSError("google", "config", "Google Cloud: %s is not a Text-to-Speech voice name (they look "
                       "like de-DE-Chirp3-HD-Kore), pick one in Settings, Voice" % name)
    derived = False
    voice = {"languageCode": lang}
    m = re.match(r"^[a-z]{2,3}-[A-Z]{2}-Chirp3-HD-([A-Za-z]+)$", name)
    if name and _language(name) == _language(role_voice):
        voice = {"languageCode": _locale(name) or lang, "name": name}
    elif m:
        # The configured voice is German. Chirp 3 HD has the same speakers in many languages
        # (en-US-Chirp3-HD-Kore, ar-XA-Chirp3-HD-Kore), so the translation gets the same speaker.
        voice, derived = {"languageCode": lang, "name": "%s-Chirp3-HD-%s" % (lang, m.group(1))}, True
    # Any other German voice: Google picks its default voice for the translation's language.

    def ask(v):
        body = {"input": {"text": text}, "voice": v, "audioConfig": {"audioEncoding": "MP3"}}
        _, data = _request("google", "https://texttospeech.googleapis.com/v1/text:synthesize",
                           {"X-Goog-Api-Key": sc["key"], "Content-Type": "application/json; charset=utf-8"},
                           json.dumps(body).encode("utf-8"), timeout, sc["key"])
        return _b64("google", _json("google", data).get("audioContent"))

    try:
        audio_data = ask(voice)
    except TTSError as e:
        if not (derived and e.kind in ("bad_request", "config")):
            raise
        # That language has no Chirp 3 HD voice (or not this speaker): let Google pick its default.
        voice = {"languageCode": lang}
        audio_data = ask(voice)
    return Clip(audio_data, "mp3", "google", voice.get("name") or lang)


def _gemini(text, role_voice, sc, timeout):
    model = sc.get("model") or DEFAULTS["gemini"]["model"]
    voice = sc.get("voice") or DEFAULTS["gemini"]["voice"]
    # The text alone: the 3.8 models read their input word for word as a transcript, so an
    # instruction such as "Say:" would be spoken too. The language is detected from the text.
    body = {"contents": [{"parts": [{"text": text}]}],
            "generationConfig": {"responseModalities": ["AUDIO"],
                                 "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}}}
    url = ("https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent"
           % urllib.parse.quote(model, safe="-._"))
    _, data = _request("gemini", url, {"x-goog-api-key": sc["key"], "Content-Type": "application/json"},
                       json.dumps(body).encode("utf-8"), timeout, sc["key"])
    out = _json("gemini", data)
    part = None
    try:
        for p in out["candidates"][0]["content"]["parts"]:
            if isinstance(p, dict) and isinstance(p.get("inlineData"), dict):
                part = p["inlineData"]
                break
    except (KeyError, IndexError, TypeError):
        part = None
    if not part:
        reason = ""
        try:
            reason = out["candidates"][0].get("finishReason") or ""
        except (KeyError, IndexError, TypeError, AttributeError):
            reason = (out.get("promptFeedback") or {}).get("blockReason") or ""
        raise TTSError("gemini", "no_audio", "Gemini sent no audio%s" % ((" (%s)" % reason) if reason else ""))
    raw = _b64("gemini", part.get("data"))
    if raw[:4] == b"RIFF":
        wav = raw                                    # 3.8 models send a finished WAV file
    else:                                            # older models send bare 16-bit PCM
        m = re.search(r"rate=(\d+)", part.get("mimeType") or "")
        wav = pcm_to_wav(raw, rate=int(m.group(1)) if m else 24000)
    return Clip(wav, "wav", "gemini", "%s/%s" % (model, voice))


_ADAPTERS = {"edge": _edge, "azure": _azure, "elevenlabs": _elevenlabs, "openai": _openai,
             "google": _google, "gemini": _gemini}


# ── Settings helpers (voice lists) ─────────────────────────────────────────────────────────
def elevenlabs_voices(key, timeout=20, pages=3):
    """[(label, voice_id)] for the voices this ElevenLabs account can use (its own, the default and
    saved ones), up to `pages` pages of 100. The key needs the Voices (read) permission. Saved Voice
    Library voices are listed too; a free key cannot use them (that refusal says so)."""
    _check_key("elevenlabs", key)
    out, token = [], ""
    for _ in range(pages):
        url = "https://api.elevenlabs.io/v2/voices?page_size=100"
        if token:
            url += "&next_page_token=" + urllib.parse.quote(token, safe="")
        _, data = _request("elevenlabs", url, {"xi-api-key": key}, None, timeout, key, method="GET")
        page = _json("elevenlabs", data)
        for v in page.get("voices") or []:
            if isinstance(v, dict) and v.get("voice_id"):
                label = (v.get("name") or v["voice_id"]).strip()
                lang = ((v.get("labels") or {}).get("language") or "") if isinstance(v.get("labels"), dict) else ""
                out.append(("%s (%s)" % (label, lang) if lang else label, v["voice_id"]))
        token = page.get("next_page_token") or ""
        if not (page.get("has_more") and token):
            break
    out = sorted(set(out), key=lambda x: (x[0].lower(), x[1]))
    # Two voices can share a name (a default "Sarah" and your own "Sarah"): tell them apart.
    names = [label for label, _ in out]
    return [("%s, %s" % (label, vid[:6]) if names.count(label) > 1 else label, vid) for label, vid in out]


def google_voices(key, language_code="de-DE", timeout=20):
    """Google Cloud voice names for one language, best families first."""
    _check_key("google", key)
    url = "https://texttospeech.googleapis.com/v1/voices?languageCode=%s" % urllib.parse.quote(language_code)
    _, data = _request("google", url, {"X-Goog-Api-Key": key}, None, timeout, key, method="GET")
    names = [v.get("name") for v in (_json("google", data).get("voices") or []) if isinstance(v, dict)
             and re.match(r"^[a-z]{2,3}-[A-Za-z]{2,4}-", v.get("name") or "")]   # not the bare Gemini names
    rank = lambda n: (0 if "Chirp3-HD" in n else 1 if "Chirp-HD" in n else 2 if "Neural2" in n
                      else 3 if "Studio" in n else 4 if "Wavenet" in n else 5, n)
    return sorted(set(names), key=rank)


def audio_tag(text, clip):
    """Deterministic filename part: the same text, service and voice always give the same name, so
    re-adding a card reuses its file, and different speech never takes another clip's name."""
    return hashlib.sha1(("%s|%s|%s" % (clip.service, clip.voice, text or "")).encode("utf-8")).hexdigest()[:10]
