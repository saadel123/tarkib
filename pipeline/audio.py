"""Pure-Python Edge-TTS client + cloze pause-drill audio.

NO third-party dependencies: stdlib only (socket, ssl, struct, base64, json, uuid, datetime,
email.utils, time, re, html). No aiohttp, no pydub, no ffmpeg. This is the audio backbone for the
add-on — it must run inside Anki's bundled Python with nothing vendored. The other voice services
(Azure, ElevenLabs, OpenAI, Google Cloud, Gemini) and the fallback order live in pipeline/tts.py.

What it does:
  - synthesize(text, voice) -> MP3 bytes   (talks the Edge "read-aloud" WebSocket protocol,
    incl. the Sec-MS-GEC security token Microsoft requires, see edge_drm.py)
  - cloze_clips(sentence, answer, voice) -> (front_mp3, back_mp3)
      front = the sentence with the answer slot turned into a SENTENCE BOUNDARY (period),
              which the TTS renders as a ~0.9s pause (SSML <break> is
              rejected by this endpoint, so we use the period-split fallback).
      back  = the full sentence with the answer spoken.
"""
import base64
import html
import json
import logging
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

from . import edge_drm   # LGPL-3.0 third-party code, see licenses/README.md

log = logging.getLogger("addon." + __name__.split(".")[0])   # Anki's per-add-on log file (see tts.py)

# --- Edge read-aloud protocol constants -------------------------------------------------
# These are Microsoft's own service values (endpoint, client token, anti-abuse token scheme), as
# documented publicly by the rany2/edge-tts project (LGPL-3.0). Only the protocol FACTS are shared;
# the WebSocket client below is an original, stdlib-only implementation. The one exception is the
# v2 token (edge_drm.py), ported from edge-tts 7.3.1 and kept under its LGPL-3.0 license.
# This is Edge's unofficial read-aloud endpoint, not a public API: if Microsoft changes it (as on
# 13 Oct 2026, when the v1 token started getting HTTP 403), the card still lands, the user is told
# why it has no audio, and tts.py falls back to another voice service when one is set up.
TRUSTED_CLIENT_TOKEN = "6A5AA1D4EAFF4E9FB37E23D68491D6F4"
WSS_HOST = "speech.platform.bing.com"
WSS_PATH = "/consumer/speech/synthesize/readaloud/edge/v1"
SEC_MS_GEC_VERSION = "2-143.0.3650.75"     # "1-..." (the v1 token) is refused with 403 since 2026-10-13
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36 Edg/143.0.0.0")
ORIGIN = "chrome-extension://jdiccldimpdaibmpdkjnbmckianbfold"
OUTPUT_FORMAT = "audio-24khz-48kbitrate-mono-mp3"
REQUEST_TIMEOUT = 10          # seconds for ONE whole request (connect, handshake, all audio); a clip takes ~1 s

# Seconds to add to this computer's clock so the token matches Microsoft's. The token depends on
# the time (rounded to 5 minutes), so a wrong clock gives a wrong token and a 403. When that
# happens, synthesize() sets this from the server's Date header and tries once more, the way
# edge-tts does it. Module-level on purpose: one correction serves every later request.
_clock_skew = 0.0


class EdgeTTSError(Exception):
    """A failed read-aloud request. The message is a full sentence a user can read.

    status: the HTTP status of a refused handshake (403, 429, ...), else None.
    code: the WebSocket close code when the server closed the connection (1007, 1008), else None.
    kind: auth | rate_limit | network | timeout | server | no_audio | bad_request (see tts.py).
    server_date: the Date header of a refused handshake, used to correct the clock."""

    def __init__(self, message, status=None, kind=None, code=None, server_date=None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.kind = kind or _kind_for(status, code)
        self.server_date = server_date


def _kind_for(status, code):
    if status == 429 or code == 1008:
        return "rate_limit"
    if code == 1007:
        # Microsoft closes with 1007 for a voice or text it will not read ("Unsupported voice X.",
        # checked live 2026-10-14). A bad token never gets this far: it is refused with 403 at the
        # handshake. So this is about the request, and the other voices still work.
        return "bad_request"
    if status in (401, 403):
        return "auth"
    if status and status >= 500:
        return "server"
    if status:
        return "bad_request"
    return "network"


def _sec_ms_gec():
    """Microsoft's required anti-abuse token, v2 (edge_drm.py), on the clock-corrected time."""
    return edge_drm.generate_sec_ms_gec_v2(time.time() + _clock_skew)


def _skew_from_date(server_date):
    """Seconds between the server's Date header and this computer's clock, or None if unreadable."""
    try:
        server = edge_drm.parse_rfc2616_date(server_date)
    except (IndexError, AttributeError):
        server = None
    return None if server is None else server - time.time()


def _timestamp():
    return datetime.now(timezone.utc).strftime("%a %b %d %Y %H:%M:%S GMT+0000 (Coordinated Universal Time)")


def _mkssml(text, voice, rate="+0%"):
    """rate is the prosody rate ("-20%" reads about 20% slower); anything but a signed whole percent
    is the normal "+0%", so the SSML stays exactly what it was before speeds existed."""
    safe = html.escape(text, quote=False)
    if not re.match(r"^[+-]\d{1,2}%$", rate or ""):
        rate = "+0%"
    return (
        "<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='en-US'>"
        "<voice name='%s'><prosody pitch='+0Hz' rate='%s' volume='+0%%'>%s</prosody></voice></speak>"
        % (voice, rate, safe)
    )


# --- Minimal WebSocket client over stdlib socket+ssl (client frames are masked) ---------
class _WS:
    """One read-aloud connection. `deadline` (time.monotonic()) bounds the WHOLE request: every
    socket wait gets only the time that is left, so a server that trickles bytes or goes quiet
    cannot hold a card past it (a plain socket timeout restarts on every byte)."""

    def __init__(self, host, path_qs, deadline, port=443):
        self.deadline = deadline
        self.buf = b""
        self.sock = None
        raw = self._connect(host, port)
        try:
            raw.settimeout(self._left())       # the TLS handshake gets only what is left, too
            try:
                self.sock = ssl.create_default_context().wrap_socket(raw, server_hostname=host)
            except socket.timeout:
                raise EdgeTTSError("Microsoft Edge did not answer in time", kind="timeout")
            self._handshake(host, path_qs)
        except BaseException:
            # A refused handshake (403) raises here, before the caller holds the object to close.
            try:
                (self.sock or raw).close()
            except Exception:
                pass
            raise

    def _connect(self, host, port):
        """TCP connect within the deadline. socket.create_connection would give EVERY address of the
        host the full timeout (the host has two), so a silent firewall would cost double."""
        err = None
        addrs = socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM)
        for n, (family, kind, proto, _, addr) in enumerate(addrs):
            sock = socket.socket(family, kind, proto)
            try:
                # Each address gets its share of the time left, so one silent address cannot use it
                # all up before the next one is tried.
                sock.settimeout(self._left() / (len(addrs) - n))
                sock.connect(addr)
                return sock
            except EdgeTTSError:
                sock.close()
                raise
            except socket.timeout as e:
                sock.close()
                err = EdgeTTSError("Microsoft Edge did not answer in time", kind="timeout")
            except OSError as e:
                sock.close()
                err = e
        raise err or OSError("no address for %s" % host)

    def _handshake(self, host, path_qs):
        key = base64.b64encode(os.urandom(16)).decode()
        req = (
            "GET %s HTTP/1.1\r\nHost: %s\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
            "Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\nOrigin: %s\r\n"
            "User-Agent: %s\r\nPragma: no-cache\r\nCache-Control: no-cache\r\n\r\n"
            % (path_qs, host, key, ORIGIN, USER_AGENT)
        )
        self._sendall(req.encode())
        head = self._read_until(b"\r\n\r\n")
        status_line, _, header_block = head.partition(b"\r\n")
        parts = status_line.decode("latin1", "replace").split(None, 2)
        status = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
        if status != 101:
            headers = {}
            for line in header_block.decode("latin1", "replace").split("\r\n"):
                name, sep, value = line.partition(":")
                if sep:
                    headers[name.strip().lower()] = value.strip()
            reason = parts[2].strip() if len(parts) > 2 else ""
            raise EdgeTTSError(
                ("Microsoft Edge refused the connection: HTTP %d %s" % (status, reason)).strip()
                if status else "Microsoft Edge sent an unreadable answer to the connection request",
                status=status or None, server_date=headers.get("date"))

    def _left(self):
        left = self.deadline - time.monotonic()
        if left <= 0:
            raise EdgeTTSError("Microsoft Edge did not answer in time", kind="timeout")
        return left

    def _sendall(self, data):
        self.sock.settimeout(self._left())
        try:
            self.sock.sendall(data)
        except socket.timeout:
            raise EdgeTTSError("Microsoft Edge did not answer in time", kind="timeout")

    def _recv(self, n):
        self.sock.settimeout(self._left())
        try:
            return self.sock.recv(n)
        except socket.timeout:
            raise EdgeTTSError("Microsoft Edge did not answer in time", kind="timeout")

    def _read_until(self, marker):
        while marker not in self.buf:
            chunk = self._recv(8192)
            if not chunk:
                raise EdgeTTSError("Microsoft Edge closed the connection during the handshake")
            if len(self.buf) > 65536:
                raise EdgeTTSError("Microsoft Edge sent an unreadable answer to the connection request")
            self.buf += chunk
        head, _, rest = self.buf.partition(marker)
        self.buf = rest
        return head + marker

    def _readn(self, n):
        while len(self.buf) < n:
            chunk = self._recv(65536)
            if not chunk:
                raise EdgeTTSError("Microsoft Edge closed the connection before the audio was complete")
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
        self._sendall(bytes(frame))

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


def _synthesize_once(text, voice, deadline, rate="+0%"):
    qs = "%s?TrustedClientToken=%s&Sec-MS-GEC=%s&Sec-MS-GEC-Version=%s&ConnectionId=%s" % (
        WSS_PATH, TRUSTED_CLIENT_TOKEN, _sec_ms_gec(), SEC_MS_GEC_VERSION, uuid.uuid4().hex)
    ws = _WS(WSS_HOST, qs, deadline)
    try:
        ts = _timestamp()
        cfg = ('{"context":{"synthesis":{"audio":{"metadataoptions":'
               '{"sentenceBoundaryEnabled":"false","wordBoundaryEnabled":"false"},'
               '"outputFormat":"%s"}}}}' % OUTPUT_FORMAT)
        ws.send(("X-Timestamp:%s\r\nContent-Type:application/json; charset=utf-8\r\n"
                 "Path:speech.config\r\n\r\n%s" % (ts, cfg)).encode())
        ws.send(("X-RequestId:%s\r\nContent-Type:application/ssml+xml\r\n"
                 "X-Timestamp:%sZ\r\nPath:ssml\r\n\r\n%s"
                 % (uuid.uuid4().hex, ts, _mkssml(text, voice, rate))).encode())
        audio = bytearray()
        while True:
            opcode, payload = ws.recv_message()
            if opcode == 0x2:                         # binary audio frame
                if len(payload) < 2:
                    raise EdgeTTSError("Microsoft Edge sent an unreadable audio frame", kind="no_audio")
                hlen = struct.unpack(">H", payload[:2])[0]
                audio += payload[2 + hlen:]
                if len(audio) > _MAX_FRAME:
                    raise EdgeTTSError("Microsoft Edge sent more audio than any clip needs", kind="no_audio")
            elif opcode == 0x1:                       # text control frame
                if b"Path:turn.end" in payload:
                    break
            elif opcode == 0x8:
                code = struct.unpack(">H", payload[:2])[0] if len(payload) >= 2 else 0
                if code and code != 1000:
                    # The close code tells a rate limit (1008) from a voice or text it will not read
                    # (1007); the reason text after the code says which, e.g. "Unsupported voice X."
                    reason = " ".join(payload[2:300].decode("utf-8", "replace").split())
                    if code == 1007:
                        msg = "Microsoft Edge refused this voice or text (code 1007%s)" % (": " + reason if reason else "")
                    elif code == 1008:
                        msg = "Microsoft Edge closed the connection: too many requests (code 1008)"
                    else:
                        msg = "Microsoft Edge closed the connection (code %d%s)" % (code, ": " + reason if reason else "")
                    raise EdgeTTSError(msg, code=code)
                break
        if not audio:
            raise EdgeTTSError("Microsoft Edge sent no audio", kind="no_audio")
        return bytes(audio)
    finally:
        ws.close()


def synthesize(text, voice, timeout=REQUEST_TIMEOUT, retries=2, rate="+0%"):
    """Return MP3 bytes for `text` in `voice`, or raise EdgeTTSError with a readable reason. `rate` is
    the prosody rate ("-20%" for the slower speech speed, tts.ssml_rate).

    `timeout` bounds each attempt as a WHOLE (connect, handshake and all audio, see _WS), so a
    server that goes quiet costs at most that long. `retries` is the number of attempts for an
    ordinary failure: a network error, a timeout, a 5xx, no audio, or a rate limit (after a short
    pause) gets one more try on a fresh connection by default. A 403 is different: a wrong clock
    gives a wrong token, so the clock is first corrected from the server's Date header and the
    request tried once more, the way edge-tts does it (that extra try does not count against
    `retries`). Any other refusal (401, another 4xx) is final at once, since retrying cannot help."""
    global _clock_skew
    text = " ".join((text or "").split())
    if not text:
        raise EdgeTTSError("There was no text to read aloud", kind="bad_request")
    timeout = float(timeout or REQUEST_TIMEOUT)
    attempts, clock_fixed = 0, False
    while True:
        attempts += 1
        try:
            return _synthesize_once(text, voice, time.monotonic() + timeout, rate)
        except EdgeTTSError as e:
            err = e
        except (OSError, ValueError, struct.error) as e:      # DNS, refused, reset, TLS, bad frame
            err = EdgeTTSError("Microsoft Edge could not be reached (%s)" % (str(e) or e.__class__.__name__),
                               kind="network")
        if err.status == 403 and not clock_fixed:
            skew = _skew_from_date(err.server_date)
            if skew is not None:
                clock_fixed = True
                log.info("audio: Edge answered 403, clock corrected by %.0f s from its Date header", skew - _clock_skew)
                _clock_skew = skew
                attempts -= 1                  # the clock retry is extra, it does not use up `retries`
                continue
        if err.kind in ("auth", "bad_request") or attempts >= max(1, retries):
            raise err
        time.sleep(1.5 if err.kind == "rate_limit" else 0.3)


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


def cloze_clips(sentence, answer, voice, timeout=REQUEST_TIMEOUT):
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
