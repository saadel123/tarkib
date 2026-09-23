"""Pure-Python Edge-TTS client + cloze pause-drill audio.

NO third-party dependencies: stdlib only (socket, ssl, hashlib, struct, base64, json, uuid,
datetime, time, re, html). No aiohttp, no pydub, no ffmpeg. This is the audio backbone for
the add-on — it must run inside Anki's bundled Python with nothing vendored.

What it does:
  - synthesize(text, voice) -> MP3 bytes   (talks the Edge "read-aloud" WebSocket protocol,
    incl. the Sec-MS-GEC security token Microsoft requires)
  - cloze_clips(sentence, answer, voice) -> (front_mp3, back_mp3)
      front = the sentence with the answer slot turned into a SENTENCE BOUNDARY (period),
              which the TTS renders as a ~0.9s pause (SSML <break> is
              rejected by this endpoint, so we use the period-split fallback).
      back  = the full sentence with the answer spoken.
"""
import base64
import hashlib
import html
import json
import os
import re
import socket
import ssl
import struct
import time

_MAX_FRAME = 16 * 1024 * 1024   # bound one WebSocket frame and one clip, so a bad server cannot fill RAM
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone

# --- Edge read-aloud protocol constants -------------------------------------------------
# These are Microsoft's own service values (endpoint, client token, anti-abuse hash scheme), as
# documented publicly by the rany2/edge-tts project (GPL-3.0). Only the protocol FACTS are shared;
# the WebSocket client below is an original, stdlib-only implementation (no edge-tts code is used).
# This is Edge's unofficial read-aloud endpoint, not a public API: if Microsoft changes it, audio
# fails gracefully (cards still generate silently, see classify_tts_error).
TRUSTED_CLIENT_TOKEN = "6A5AA1D4EAFF4E9FB37E23D68491D6F4"
WSS_HOST = "speech.platform.bing.com"
WSS_PATH = "/consumer/speech/synthesize/readaloud/edge/v1"
SEC_MS_GEC_VERSION = "1-143.0.3650.75"
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36 Edg/143.0.0.0")
ORIGIN = "chrome-extension://jdiccldimpdaibmpdkjnbmckianbfold"
OUTPUT_FORMAT = "audio-24khz-48kbitrate-mono-mp3"

WIN_EPOCH = 11644473600       # seconds between 1601-01-01 and 1970-01-01
TICKS_PER_SECOND = 10000000   # 100-ns intervals per second


class EdgeTTSError(Exception):
    pass


def _sec_ms_gec():
    """Microsoft's required anti-abuse token: SHA256 of (file-time rounded to 5 min) + token.

    Computed in pure integers. The Windows file-time here is ~1.3e17 — far beyond float64's
    exact-integer range (2**53 ≈ 9e15), so doing this in float (the old `time.time()` math)
    was a latent precision trap that happened to round correctly today. Integers are exact.
    """
    ticks = (int(time.time()) + WIN_EPOCH) // 300 * 300 * TICKS_PER_SECOND
    return hashlib.sha256(("%d%s" % (ticks, TRUSTED_CLIENT_TOKEN)).encode("ascii")).hexdigest().upper()


def _timestamp():
    return datetime.now(timezone.utc).strftime("%a %b %d %Y %H:%M:%S GMT+0000 (Coordinated Universal Time)")


def _mkssml(text, voice):
    safe = html.escape(text, quote=False)
    return (
        "<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='en-US'>"
        "<voice name='%s'><prosody pitch='+0Hz' rate='+0%%' volume='+0%%'>%s</prosody></voice></speak>"
        % (voice, safe)
    )


# --- Minimal WebSocket client over stdlib socket+ssl (client frames are masked) ---------
class _WS:
    def __init__(self, host, path_qs, timeout):
        raw = socket.create_connection((host, 443), timeout=timeout)
        self.sock = ssl.create_default_context().wrap_socket(raw, server_hostname=host)
        self.sock.settimeout(timeout)
        self.buf = b""
        key = base64.b64encode(os.urandom(16)).decode()
        req = (
            "GET %s HTTP/1.1\r\nHost: %s\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
            "Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\nOrigin: %s\r\n"
            "User-Agent: %s\r\nPragma: no-cache\r\nCache-Control: no-cache\r\n\r\n"
            % (path_qs, host, key, ORIGIN, USER_AGENT)
        )
        self.sock.sendall(req.encode())
        resp = self._read_until(b"\r\n\r\n")
        status = resp.split(b"\r\n", 1)[0]
        if b" 101 " not in status:
            raise EdgeTTSError("WebSocket handshake failed: %s" % status.decode("latin1", "replace"))

    def _read_until(self, marker):
        while marker not in self.buf:
            chunk = self.sock.recv(8192)
            if not chunk:
                raise EdgeTTSError("connection closed during handshake")
            self.buf += chunk
        head, _, rest = self.buf.partition(marker)
        self.buf = rest
        return head + marker

    def _readn(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise EdgeTTSError("connection closed")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def send(self, data, opcode=0x1):
        n = len(data)
        frame = bytearray([0x80 | opcode])
        if n <= 125:
            frame.append(0x80 | n)
        elif n <= 0xFFFF:
            frame.append(0x80 | 126)
            frame += struct.pack(">H", n)
        else:
            frame.append(0x80 | 127)
            frame += struct.pack(">Q", n)
        mask = os.urandom(4)
        frame += mask
        frame += bytes(b ^ mask[i & 3] for i, b in enumerate(data))
        self.sock.sendall(bytes(frame))

    def recv_message(self):
        """Return (opcode, payload) for one full (possibly fragmented) message."""
        data = bytearray()
        first_opcode = None
        while True:
            b0, b1 = self._readn(2)
            fin = b0 & 0x80
            opcode = b0 & 0x0F
            length = b1 & 0x7F
            if length == 126:
                length = struct.unpack(">H", self._readn(2))[0]
            elif length == 127:
                length = struct.unpack(">Q", self._readn(8))[0]
            if length > _MAX_FRAME:
                raise ConnectionError("TTS frame too large")   # a sane clip is well under 1 MB
            mask = self._readn(4) if (b1 & 0x80) else b""
            payload = self._readn(length) if length else b""
            if mask:
                payload = bytes(c ^ mask[i & 3] for i, c in enumerate(payload))
            if opcode == 0x9:           # ping -> pong, keep reading
                self.send(payload, opcode=0xA)
                continue
            if opcode == 0xA:           # pong, ignore
                continue
            if opcode == 0x8:           # close — return the close frame payload (first 2 bytes = code)
                return 0x8, payload
            if first_opcode is None:
                first_opcode = opcode   # 0x1 text / 0x2 binary
            data += payload
            if fin:
                return first_opcode, bytes(data)

    def close(self):
        try:
            self.send(b"", opcode=0x8)
        except Exception:
            pass
        try:
            self.sock.close()
        except Exception:
            pass


def _synthesize_once(text, voice, timeout):
    qs = "%s?TrustedClientToken=%s&Sec-MS-GEC=%s&Sec-MS-GEC-Version=%s&ConnectionId=%s" % (
        WSS_PATH, TRUSTED_CLIENT_TOKEN, _sec_ms_gec(), SEC_MS_GEC_VERSION, uuid.uuid4().hex)
    ws = _WS(WSS_HOST, qs, timeout)
    try:
        ts = _timestamp()
        cfg = ('{"context":{"synthesis":{"audio":{"metadataoptions":'
               '{"sentenceBoundaryEnabled":"false","wordBoundaryEnabled":"false"},'
               '"outputFormat":"%s"}}}}' % OUTPUT_FORMAT)
        ws.send(("X-Timestamp:%s\r\nContent-Type:application/json; charset=utf-8\r\n"
                 "Path:speech.config\r\n\r\n%s" % (ts, cfg)).encode())
        ws.send(("X-RequestId:%s\r\nContent-Type:application/ssml+xml\r\n"
                 "X-Timestamp:%sZ\r\nPath:ssml\r\n\r\n%s"
                 % (uuid.uuid4().hex, ts, _mkssml(text, voice))).encode())
        audio = bytearray()
        while True:
            opcode, payload = ws.recv_message()
            if opcode == 0x2:                         # binary audio frame
                hlen = struct.unpack(">H", payload[:2])[0]
                audio += payload[2 + hlen:]
                if len(audio) > _MAX_FRAME:
                    raise ConnectionError("TTS audio too large")
            elif opcode == 0x1:                       # text control frame
                if b"Path:turn.end" in payload:
                    break
            elif opcode == 0x8:
                code = struct.unpack(">H", payload[:2])[0] if len(payload) >= 2 else 0
                if code and code != 1000:
                    # Surface the close code so the caller can tell rate-limit (1008) from a
                    # token/auth rejection (1007) — see classify_tts_error.
                    raise EdgeTTSError("websocket closed: code=%d" % code)
                break
        if not audio:
            raise EdgeTTSError("no audio received")
        return bytes(audio)
    finally:
        ws.close()


def synthesize(text, voice, timeout=30, retries=4):
    """Return MP3 bytes for `text` in `voice`. Retries transient failures (the free endpoint
    rate-limits); re-raises clearly-terminal ones (token/auth rejection) immediately so the
    user isn't made to wait ~15s for a guaranteed failure."""
    text = " ".join((text or "").split())
    if not text:
        raise EdgeTTSError("empty text")
    last = None
    for attempt in range(retries):
        try:
            return _synthesize_once(text, voice, timeout)
        except EdgeTTSError as e:
            # Terminal — retrying won't help (token/auth rejected). Everything else (network,
            # 1008 rate-limit, no-audio, a 5xx handshake) still retries exactly as before.
            s = str(e).lower()
            if "code=1007" in s or "invalid token" in s or " 403" in s or " 401" in s:
                raise
            last = e
            time.sleep(1.5 * (attempt + 1))
        except Exception as e:
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise EdgeTTSError("synthesis failed after %d attempts: %s" % (retries, last))


# --- Cloze pause-drill via sentence-boundary split --------------------------------------
def split_for_cloze(sentence, answer):
    """Turn the answer slot into a sentence boundary so the TTS renders a ~0.9s pause.

    'Ich gehe in den Supermarkt am Wochenende.' + 'Supermarkt'
      -> 'Ich gehe in den. Am Wochenende.'
    Answers may be comma-separated (idioms with multiple blanks) — each slot is split.
    """
    out = sentence
    for ans in [a.strip() for a in answer.split(",") if a.strip()]:
        # Whole-word match ONLY, case-insensitive (an earlier slot may have capitalized the next
        # word, e.g. "in" -> "In"). NEVER fall back to substring search: a short answer like "in"
        # then splits inside another word ("Keine" -> "Ke e") and the TTS reads garbage. A missed
        # pause is harmless; corrupt audio is not.
        m = re.search(r"\b%s\b" % re.escape(ans), out, re.IGNORECASE)
        idx = m.start() if m else -1
        if idx == -1:
            continue
        before = out[:idx].rstrip()
        after = out[idx + len(ans):].lstrip()
        if before and before[-1] not in ".!?…":
            before += "."
        if after:
            after = after[0].upper() + after[1:]
        out = (before + " " + after).strip()
    return out


def cloze_clips(sentence, answer, voice, timeout=30):
    """Return (front_mp3_bytes, back_mp3_bytes) for the cloze card."""
    front = synthesize(split_for_cloze(sentence, answer), voice, timeout=timeout)
    back = synthesize(sentence, voice, timeout=timeout)
    return front, back


# --- Voice catalog (for the Settings voice dropdowns) -----------------------------------
# Microsoft's public voice list. The TrustedClientToken in the query string is fixed and
# public (same as the synth endpoint) — a plain GET, no auth header needed.
VOICES_LIST_URL = ("https://speech.platform.bing.com/consumer/speech/synthesize/readaloud/"
                   "voices/list?trustedclienttoken=" + TRUSTED_CLIENT_TOKEN)


def list_voices(timeout=20):
    """Fetch the full Microsoft voice catalog. Returns a list of dicts with
    Name/ShortName/Gender/Locale/FriendlyName. Raises on network/HTTP error."""
    req = urllib.request.Request(VOICES_LIST_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read())
    return data if isinstance(data, list) else []


def voice_label(v):
    """Friendly dropdown text, e.g. 'Katja (de-DE, Female)'."""
    fn = (v.get("FriendlyName") or v.get("ShortName") or "").strip()
    bits = ", ".join(b for b in ((v.get("Locale") or "").strip(), (v.get("Gender") or "").strip()) if b)
    return "%s (%s)" % (fn, bits) if bits else fn


def filter_voices(voices, locale_prefixes):
    """Voices whose Locale starts with any prefix (case-insensitive), sorted by Locale then name.
    Empty/falsy locale_prefixes → return all (sorted)."""
    out = list(voices or [])
    prefixes = tuple(p.lower() for p in (locale_prefixes or []) if p)
    if prefixes:
        out = [v for v in out if (v.get("Locale") or "").lower().startswith(prefixes)]
    out.sort(key=lambda v: ((v.get("Locale") or ""), (v.get("FriendlyName") or v.get("ShortName") or "")))
    return out


# Map a secondary-translation language (name or code) to voice-locale prefixes. Unknown → []
# (= show all voices, so the user can still pick one).
_SECONDARY_LOCALES = {
    "arabic": ["ar"], "msa": ["ar"], "fusha": ["ar"], "ar": ["ar"], "العربية": ["ar"],
    "french": ["fr"], "français": ["fr"], "fr": ["fr"],
    "spanish": ["es"], "español": ["es"], "es": ["es"],
    "english": ["en-US", "en-GB"], "en": ["en-US", "en-GB"],
    "german": ["de-DE", "de-AT", "de-CH"], "de": ["de-DE", "de-AT", "de-CH"],
    "italian": ["it"], "it": ["it"], "portuguese": ["pt"], "pt": ["pt"],
    "russian": ["ru"], "ru": ["ru"], "turkish": ["tr"], "tr": ["tr"],
    "polish": ["pl"], "pl": ["pl"], "ukrainian": ["uk"], "uk": ["uk"],
    "persian": ["fa"], "farsi": ["fa"], "fa": ["fa"],
    "dutch": ["nl"], "nl": ["nl"], "greek": ["el"], "el": ["el"], "czech": ["cs"], "cs": ["cs"],
    "romanian": ["ro"], "ro": ["ro"], "hungarian": ["hu"], "hu": ["hu"], "swedish": ["sv"], "sv": ["sv"],
    "indonesian": ["id"], "id": ["id"], "vietnamese": ["vi"], "vi": ["vi"], "hindi": ["hi"], "hi": ["hi"],
    "urdu": ["ur"], "ur": ["ur"], "japanese": ["ja"], "ja": ["ja"],
    "korean": ["ko"], "ko": ["ko"], "chinese (simplified)": ["zh-CN"], "chinese": ["zh-CN"], "zh": ["zh-CN"],
}


def secondary_locale_prefixes(lang):
    return _SECONDARY_LOCALES.get((lang or "").strip().lower(), [])


# One short, neutral sample sentence per language, keyed by the voice's language code (the part
# of the ShortName before the first '-'). Played by the Settings voice-preview button. Arabic is
# Modern Standard Arabic (content rule 2). Unknown languages fall back to English.
VOICE_SAMPLES = {
    "de": "Hallo! So klinge ich. Viel Erfolg beim Lernen.",
    "en": "Hello! This is how I sound. Enjoy your learning.",
    "ar": "مرحبا! هكذا يبدو صوتي. حظا موفقا في دراستك.",
    "fr": "Bonjour ! Voici ma voix. Bon courage pour vos études.",
    "es": "¡Hola! Así sueno. Mucho éxito en tus estudios.",
    "tr": "Merhaba! Sesim böyle. Çalışmalarında başarılar.",
    "ru": "Здравствуйте! Вот так звучит мой голос. Удачи в учёбе.",
    "uk": "Вітаю! Ось так звучить мій голос. Успіхів у навчанні.",
    "it": "Ciao! Questa è la mia voce. Buono studio.",
    "pl": "Cześć! Tak brzmi mój głos. Powodzenia w nauce.",
    "pt": "Olá! É assim que eu soo. Bons estudos.",
    "fa": "سلام! صدای من این طور است. در یادگیری موفق باشید.",
    "nl": "Hallo! Zo klink ik. Veel succes met leren.",
    "el": "Γεια σας! Έτσι ακούγομαι. Καλή επιτυχία στη μελέτη σας.",
    "cs": "Dobrý den! Takto zním. Hodně štěstí při učení.",
    "ro": "Bună ziua! Așa sună vocea mea. Mult succes la învățat.",
    "hu": "Jó napot! Így hangzik a hangom. Sok sikert a tanuláshoz.",
    "sv": "Hej! Så här låter jag. Lycka till med studierna.",
    "id": "Halo! Begini suara saya. Semoga sukses belajar.",
    "vi": "Xin chào! Đây là giọng của tôi. Chúc bạn học tốt.",
    "hi": "नमस्ते! मेरी आवाज़ ऐसी है। आपकी पढ़ाई के लिए शुभकामनाएँ।",
    "ur": "السلام علیکم! میری آواز ایسی ہے۔ آپ کی تعلیم کے لیے نیک خواہشات۔",
    "ja": "こんにちは。これが私の声です。学習を楽しんでください。",
    "ko": "안녕하세요! 제 목소리는 이렇습니다. 즐겁게 공부하세요.",
    "zh": "你好！这是我的声音。祝你学习愉快。",
}


def sample_text_for_voice(short_name):
    code = (short_name or "").split("-")[0].strip().lower()
    return VOICE_SAMPLES.get(code, VOICE_SAMPLES["en"])


# --- TTS failure classification (so failures are triagable, not generic) ----------------
TTS_ERROR_MESSAGES = {
    "network": "Microsoft TTS unreachable, check your network",
    "rate_limit": "TTS rate-limited, try again in a minute",
    "auth": "Microsoft TTS auth changed, update the add-on",
}
_TTS_CAT_PRIORITY = {"auth": 3, "rate_limit": 2, "network": 1, None: 0}


def classify_tts_error(exc):
    """Map a TTS exception to (category, human_message). Categories: network | rate_limit | auth.
    `synthesize()` wraps the underlying error's text, so we match on the message string."""
    s = (str(exc) or "").lower()
    if "429" in s or "1008" in s or "too many requests" in s:
        return ("rate_limit", TTS_ERROR_MESSAGES["rate_limit"])
    if "403" in s or "401" in s or "invalid token" in s or "1007" in s or "forbidden" in s:
        return ("auth", TTS_ERROR_MESSAGES["auth"])
    # Anything else that stopped synthesis is treated as a connectivity/endpoint problem.
    return ("network", TTS_ERROR_MESSAGES["network"])


def tts_error_message(category):
    return TTS_ERROR_MESSAGES.get(category, TTS_ERROR_MESSAGES["network"])


def worse_category(a, b):
    """The more actionable of two categories (auth > rate_limit > network); auth is the canary."""
    return a if _TTS_CAT_PRIORITY.get(a, 0) >= _TTS_CAT_PRIORITY.get(b, 0) else b
