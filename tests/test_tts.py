#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Offline tests for the voice services: the Edge v2 token, the Edge client (fake socket), every
paid service against fake HTTP answers, the fallback chain and the audio filenames. No Anki, no
network, no key.

    python3 tests/test_tts.py
"""
import base64, io, json, os, socket, struct, sys, time, types, unittest, urllib.error, wave
for _n in ("aqt", "aqt.qt", "aqt.utils", "aqt.operations", "anki", "anki.collection", "anki.notes", "anki.hooks"):
    sys.modules.setdefault(_n, types.ModuleType(_n))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline import audio, edge_drm, generate, providers, tts  # noqa: E402


# ── the v2 token ───────────────────────────────────────────────────────────────────────────
class EdgeTokenV2(unittest.TestCase):
    """Microsoft refuses the v1 token with 403 since 2026-10-13. Vectors from edge-tts 7.3.1."""
    VECTORS = {
        0: "52BC7A17B50DFEC9-28C4394775C8751CD2F6859C030C06DB1489ACAB3B3A7651831FC26895177ED6",
        1700000000: "2CD23A2CA0B2595A-F3C846C370E05F9CC83ACC5F995C5F5D87A4D0F14CE8936A0F902E64099E38A2",
        1791966434.686: "38EDA4423CB96308-74A1E5BEEE77670AF4CD9CFE0AA0DF16A21AFE8CEF599ED437C50D8381415173",
        1800000123.9: "99E54519B490BE5C-E162DB0977FBDCB9B86DD8148BF1BCDC3C0303176CE39852A42B415935C20654",
        2000000000: "2D62557F1142BC5D-FD9C30C68FF194A5EE6B45FEFC5E2BA1D1239F88A90569AB55CFFFAA7799F40E",
    }

    def test_vectors(self):
        for ts, want in self.VECTORS.items():
            self.assertEqual(edge_drm.generate_sec_ms_gec_v2(ts), want, ts)

    def test_same_five_minute_window_same_token(self):
        self.assertEqual(edge_drm.generate_sec_ms_gec_v2(1800000000), edge_drm.generate_sec_ms_gec_v2(1800000199.9))
        self.assertNotEqual(edge_drm.generate_sec_ms_gec_v2(1800000000), edge_drm.generate_sec_ms_gec_v2(1800000300))

    def test_client_sends_v2_with_the_v2_version(self):
        self.assertTrue(audio.SEC_MS_GEC_VERSION.startswith("2-"))
        self.assertEqual(edge_drm.TRUSTED_CLIENT_TOKEN, audio.TRUSTED_CLIENT_TOKEN)
        tok = audio._sec_ms_gec()
        self.assertRegex(tok, r"^[0-9A-F]{16}-[0-9A-F]{64}$")

    def test_clock_skew_moves_the_token(self):
        old = audio._clock_skew
        try:
            audio._clock_skew = 0.0
            now = audio._sec_ms_gec()
            audio._clock_skew = 3600.0
            self.assertNotEqual(now, audio._sec_ms_gec())
        finally:
            audio._clock_skew = old


# ── a fake Edge server behind the socket ───────────────────────────────────────────────────
def _frame(opcode, payload):
    n = len(payload)
    head = bytes([0x80 | opcode])
    if n <= 125:
        head += bytes([n])
    elif n <= 0xFFFF:
        head += bytes([126]) + struct.pack(">H", n)
    else:
        head += bytes([127]) + struct.pack(">Q", n)
    return head + payload


def _audio_answer(mp3=b"\xff\xf3" + b"A" * 300):
    hdr = b"X-RequestId:1\r\nContent-Type:audio/mpeg\r\nPath:audio\r\n"
    return (b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n\r\n"
            + _frame(0x2, struct.pack(">H", len(hdr)) + hdr + mp3)
            + _frame(0x1, b"X-RequestId:1\r\nPath:turn.end\r\n\r\n{}"))


class FakeSock:
    """Plays one scripted server answer. answer=None: accept and then never send anything."""
    def __init__(self, answer):
        self.data, self.sent, self.timeout = answer, [], None

    def settimeout(self, t):
        self.timeout = t

    def sendall(self, b):
        self.sent.append(b)

    def recv(self, n):
        if self.data is None:
            time.sleep(min(self.timeout or 0.05, 0.05))
            raise socket.timeout("timed out")
        out, self.data = self.data[:n], self.data[n:]
        return out

    def close(self):
        pass


class FakeEdge:
    """Patches the connection in audio.py (no network at all); each new connection takes the next
    scripted answer."""
    def __init__(self, answers):
        self.answers, self.socks = list(answers), []

    def __enter__(self):
        self._conn, self._ctx = audio._WS._connect, audio.ssl.create_default_context
        fake = self

        class Ctx:
            def wrap_socket(self, raw, server_hostname=None):
                return raw

        def connect(ws, host, port):
            s = FakeSock(fake.answers.pop(0))
            fake.socks.append(s)
            return s
        audio._WS._connect = connect
        audio.ssl.create_default_context = lambda: Ctx()
        self._sleep, audio.time.sleep = audio.time.sleep, lambda s: None
        return self

    def __exit__(self, *a):
        audio._WS._connect, audio.ssl.create_default_context = self._conn, self._ctx
        audio.time.sleep = self._sleep


FORBIDDEN = (b"HTTP/1.1 403 Forbidden\r\nDate: Wed, 14 Oct 2026 09:15:31 GMT\r\nContent-Length: 0\r\n\r\n")


class EdgeClient(unittest.TestCase):
    def setUp(self):
        self._skew = audio._clock_skew
        audio._clock_skew = 0.0

    def tearDown(self):
        audio._clock_skew = self._skew

    def test_audio_and_the_request_carries_the_v2_token(self):
        with FakeEdge([_audio_answer()]) as fe:
            mp3 = audio.synthesize("Das Schloss ist alt.", "de-DE-KatjaNeural")
        self.assertTrue(mp3.startswith(b"\xff\xf3"))
        req = fe.socks[0].sent[0].decode()
        self.assertIn("Sec-MS-GEC-Version=2-", req)
        self.assertRegex(req, r"Sec-MS-GEC=[0-9A-F]{16}-[0-9A-F]{64}&")

    def test_403_corrects_the_clock_from_the_date_header_and_retries_once(self):
        with FakeEdge([FORBIDDEN, _audio_answer()]) as fe:
            mp3 = audio.synthesize("Hallo.", "de-DE-KatjaNeural")
        self.assertTrue(mp3)
        self.assertEqual(len(fe.socks), 2)
        server = 1791969331.0         # Wed, 14 Oct 2026 09:15:31 GMT
        self.assertAlmostEqual(audio._clock_skew, server - time.time(), delta=5)

    def test_403_twice_is_final_with_a_readable_reason(self):
        with FakeEdge([FORBIDDEN, FORBIDDEN, _audio_answer()]) as fe:
            with self.assertRaises(audio.EdgeTTSError) as cm:
                audio.synthesize("Hallo.", "de-DE-KatjaNeural")
        e = cm.exception
        self.assertEqual((e.status, e.kind), (403, "auth"))
        self.assertEqual(str(e), "Microsoft Edge refused the connection: HTTP 403 Forbidden")
        self.assertEqual(len(fe.socks), 2)          # one clock retry, no more

    def test_a_silent_server_costs_one_deadline_per_attempt_then_a_clear_timeout(self):
        t0 = time.monotonic()
        with FakeEdge([None, None]) as fe:
            with self.assertRaises(audio.EdgeTTSError) as cm:
                audio.synthesize("Hallo.", "de-DE-KatjaNeural", timeout=0.3)
        self.assertEqual(cm.exception.kind, "timeout")
        self.assertEqual(len(fe.socks), 2)          # one retry on a fresh connection
        self.assertLess(time.monotonic() - t0, 2.0)
        for sock in fe.socks:                       # every wait got only what was left of the deadline
            self.assertLessEqual(sock.timeout, 0.3)

    def test_rate_limit_close_gets_one_retry(self):
        busy = b"HTTP/1.1 101 Switching Protocols\r\n\r\n" + _frame(0x8, struct.pack(">H", 1008))
        with FakeEdge([busy, _audio_answer()]) as fe:
            self.assertTrue(audio.synthesize("Hallo.", "de-DE-KatjaNeural"))
        self.assertEqual(len(fe.socks), 2)

    def test_unsupported_voice_close_is_final_for_this_clip_and_names_the_reason(self):
        # what Microsoft really sends for a voice it does not have (checked live 2026-10-14)
        bad = (b"HTTP/1.1 101 Switching Protocols\r\n\r\n"
               + _frame(0x8, struct.pack(">H", 1007) + b"Unsupported voice de-DE-KatjaNeural2."))
        with FakeEdge([bad, _audio_answer()]) as fe:
            with self.assertRaises(audio.EdgeTTSError) as cm:
                audio.synthesize("Hallo.", "de-DE-KatjaNeural2")
        self.assertEqual(cm.exception.kind, "bad_request")      # soft in the chain: other voices still work
        self.assertEqual(str(cm.exception),
                         "Microsoft Edge refused this voice or text (code 1007: Unsupported voice de-DE-KatjaNeural2.)")
        self.assertEqual(len(fe.socks), 1)

    def test_the_deadline_covers_the_tls_handshake_with_real_sockets(self):
        # a server that accepts TCP and then says nothing: TLS must give up at the deadline
        srv = socket.socket()
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        try:
            t0 = time.monotonic()
            with self.assertRaises(audio.EdgeTTSError) as cm:
                audio._WS("127.0.0.1", "/x", time.monotonic() + 0.4, port=srv.getsockname()[1])
            self.assertEqual(cm.exception.kind, "timeout")
            self.assertLess(time.monotonic() - t0, 1.5)
        finally:
            srv.close()

    def test_server_date_parser_is_the_upstream_one(self):
        self.assertEqual(edge_drm.parse_rfc2616_date("Wed, 14 Oct 2026 09:15:31 GMT"), 1791969331.0)
        self.assertIsNone(edge_drm.parse_rfc2616_date("not a date"))
        self.assertIsNone(audio._skew_from_date(None))

    def test_no_audio_is_an_error_not_a_silent_empty_clip(self):
        empty = b"HTTP/1.1 101 Switching Protocols\r\n\r\n" + _frame(0x1, b"Path:turn.end\r\n\r\n")
        with FakeEdge([empty, empty]):
            with self.assertRaises(audio.EdgeTTSError) as cm:
                audio.synthesize("Hallo.", "de-DE-KatjaNeural")
        self.assertEqual(cm.exception.kind, "no_audio")


# ── fake HTTP for the paid services ────────────────────────────────────────────────────────
class FakeResponse(io.BytesIO):
    def __init__(self, body, ctype):
        super().__init__(body)
        self.headers = {"Content-Type": ctype}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


class FakeHTTP:
    """Patches providers.open_url. Each call pops the next answer: (status, body, content_type)."""
    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def __enter__(self):
        self._open, self._sleep = providers.open_url, tts.time.sleep
        tts.providers.open_url = self._fake
        tts.time.sleep = lambda s: None
        return self

    def __exit__(self, *a):
        tts.providers.open_url, tts.time.sleep = self._open, self._sleep

    def _fake(self, req, timeout):
        self.calls.append(req)
        status, body, ctype = self.answers.pop(0)
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        if status == 200:
            return FakeResponse(body, ctype)
        raise urllib.error.HTTPError(req.full_url, status, "error", {"Retry-After": "1"}, io.BytesIO(body))

    def last(self):
        req = self.calls[-1]
        return req.full_url, {k.lower(): v for k, v in req.header_items()}, req.data


MP3 = (200, b"\xff\xf3" + b"B" * 200, "audio/mpeg")


def cfg(service, **fields):
    c = {"service": service}
    c[service] = dict(fields)
    return c


class KeysNeverLeak(unittest.TestCase):
    def test_a_key_with_a_line_break_is_refused_before_any_request_and_never_shown(self):
        key = "sk_live_SECRETPART1\nSECRETPART2"
        for service, extra in (("elevenlabs", {"voice": "v"}), ("openai", {}), ("azure", {"region": "westeurope"}),
                               ("google", {}), ("gemini", {})):
            with FakeHTTP() as h:
                with self.assertRaises(tts.TTSError) as cm:
                    tts.synthesize(service, "Hallo", "de-DE-KatjaNeural", cfg(service, key=key, **extra))
            self.assertEqual((cm.exception.kind, h.calls), ("config", []), service)
            self.assertNotIn("SECRET", str(cm.exception))
        with self.assertRaises(tts.TTSError) as cm:
            tts.elevenlabs_voices(key)
        self.assertNotIn("SECRET", str(cm.exception))


class Azure(unittest.TestCase):
    def test_request_shape(self):
        with FakeHTTP(MP3) as h:
            clip = tts.synthesize("azure", "Tom & Jerry <3", "de-DE-KatjaNeural",
                                  cfg("azure", key="k" * 32, region="West Europe"))
        url, hdr, body = h.last()
        self.assertEqual(url, "https://westeurope.tts.speech.microsoft.com/cognitiveservices/v1")
        self.assertEqual(hdr["ocp-apim-subscription-key"], "k" * 32)
        self.assertEqual(hdr["content-type"], "application/ssml+xml")
        self.assertEqual(hdr["x-microsoft-outputformat"], "audio-24khz-48kbitrate-mono-mp3")
        self.assertTrue(hdr["user-agent"])
        ssml = body.decode()
        self.assertIn("xml:lang='de-DE'", ssml)
        self.assertIn("<voice name='de-DE-KatjaNeural'>Tom &amp; Jerry &lt;3</voice>", ssml)
        self.assertIn("xmlns='http://www.w3.org/2001/10/synthesis'", ssml)
        self.assertEqual((clip.ext, clip.service, clip.voice), ("mp3", "azure", "de-DE-KatjaNeural"))

    def test_region_cannot_change_the_host(self):
        self.assertEqual(tts.azure_region("evil.com/x?"), "evilcomx")
        self.assertEqual(tts.azure_region(" Germany West Central "), "germanywestcentral")

    def test_401_names_the_region(self):
        with FakeHTTP((401, b"", "")):
            with self.assertRaises(tts.TTSError) as cm:
                tts.synthesize("azure", "Hallo", "de-DE-KatjaNeural", cfg("azure", key="x", region="westeurope"))
        self.assertEqual(cm.exception.kind, "auth")
        self.assertIn("region", str(cm.exception))
        self.assertFalse(str(cm.exception).endswith(": str"))       # the real 401 has an empty body
        self.assertTrue(str(cm.exception).endswith("Settings, Voice"))

    def test_not_set_up_never_calls_out(self):
        with FakeHTTP() as h:
            with self.assertRaises(tts.TTSError) as cm:
                tts.synthesize("azure", "Hallo", "de-DE-KatjaNeural", cfg("azure", key="x"))
        self.assertEqual(cm.exception.kind, "config")
        self.assertEqual(h.calls, [])

    def test_json_with_status_200_is_not_audio(self):
        with FakeHTTP((200, b'{"x":1}', "application/json")):
            with self.assertRaises(tts.TTSError) as cm:
                tts.synthesize("azure", "Hallo", "de-DE-KatjaNeural", cfg("azure", key="x", region="westeurope"))
        self.assertEqual(cm.exception.kind, "no_audio")


class ElevenLabs(unittest.TestCase):
    def test_request_shape_multilingual_v2_has_no_language_code(self):
        with FakeHTTP(MP3) as h:
            clip = tts.synthesize("elevenlabs", "Hallo", "de-DE-KatjaNeural",
                                  cfg("elevenlabs", key="sk_test", voice="abc/12", model="eleven_multilingual_v2"))
        url, hdr, body = h.last()
        self.assertEqual(url, "https://api.elevenlabs.io/v1/text-to-speech/abc%2F12?output_format=mp3_44100_64")
        self.assertEqual(hdr["xi-api-key"], "sk_test")
        self.assertEqual(json.loads(body), {"text": "Hallo", "model_id": "eleven_multilingual_v2"})
        self.assertEqual(clip.voice, "eleven_multilingual_v2/abc/12")

    def test_other_models_pin_the_language(self):
        with FakeHTTP(MP3) as h:
            tts.synthesize("elevenlabs", "Hello", "en-US-AvaMultilingualNeural",
                           cfg("elevenlabs", key="k", voice="v", model="eleven_flash_v2_5"))
        self.assertEqual(json.loads(h.last()[2])["language_code"], "en")

    def test_error_codes_beat_the_http_status(self):
        cases = [
            (401, {"detail": {"status": "quota_exceeded", "message": "This request exceeds your quota."}}, "quota"),
            (402, {"detail": {"code": "insufficient_credits", "message": "Not enough credits."}}, "quota"),
            (401, {"detail": {"status": "missing_permissions",
                              "message": "The API key you used is missing the permission text_to_speech."}}, "auth"),
            (401, {"detail": {"status": "invalid_api_key", "message": "Invalid API key"}}, "auth"),
            # the live answer to a bad key on 2026-10-14: HTTP 400, the code says what it is
            (400, {"detail": {"type": "authentication_error", "code": "invalid_api_key", "message": "API key is invalid.",
                              "status": "invalid_api_key", "request_id": "bb525ce8e5e07a0d6dbfed43c49836eb",
                              "param": "api_key"}}, "auth"),
            (404, {"detail": {"code": "voice_not_found", "message": "The specified voice ID does not exist."}}, "config"),
            (403, {"detail": {"code": "voice_access_denied", "message": "You do not have access to this voice."}}, "config"),
            (403, {"detail": {"code": "subscription_required", "message": "This feature needs a subscription."}}, "config"),
            (422, {"detail": [{"loc": ["body", "text"], "msg": "field required", "type": "missing"}]}, "bad_request"),
        ]
        for status, body, kind in cases:
            with FakeHTTP((status, body, "application/json")):
                with self.assertRaises(tts.TTSError) as cm:
                    tts.synthesize("elevenlabs", "Hallo", "de-DE-KatjaNeural", cfg("elevenlabs", key="k", voice="v"))
            self.assertEqual(cm.exception.kind, kind, body)

    def test_voice_list_pages(self):
        p1 = {"voices": [{"voice_id": "b1", "name": "Bea", "labels": {"language": "de"}}], "has_more": True,
              "next_page_token": "t2"}
        p2 = {"voices": [{"voice_id": "a1", "name": "Alex"}], "has_more": False}
        with FakeHTTP((200, json.dumps(p1).encode(), "application/json"),
                      (200, json.dumps(p2).encode(), "application/json")) as h:
            voices = tts.elevenlabs_voices("k")
        self.assertEqual(voices, [("Alex", "a1"), ("Bea (de)", "b1")])
        self.assertIn("next_page_token=t2", h.calls[1].full_url)

    def test_two_voices_with_one_name_stay_apart(self):
        page = {"voices": [{"voice_id": "premade123", "name": "Sarah"}, {"voice_id": "clone98765", "name": "Sarah"}],
                "has_more": False}
        with FakeHTTP((200, json.dumps(page).encode(), "application/json")):
            voices = tts.elevenlabs_voices("k")
        self.assertEqual(voices, [("Sarah, clone9", "clone98765"), ("Sarah, premad", "premade123")])


class OpenAI(unittest.TestCase):
    def test_request_shape(self):
        with FakeHTTP(MP3) as h:
            clip = tts.synthesize("openai", "Guten Morgen", "de-DE-KatjaNeural", cfg("openai", key="sk-test"))
        url, hdr, body = h.last()
        self.assertEqual(url, "https://api.openai.com/v1/audio/speech")
        self.assertEqual(hdr["authorization"], "Bearer sk-test")
        b = json.loads(body)
        self.assertEqual((b["model"], b["voice"], b["response_format"], b["input"]),
                         ("gpt-4o-mini-tts", "marin", "mp3", "Guten Morgen"))
        self.assertIn("German", b["instructions"])
        self.assertEqual(clip.voice, "gpt-4o-mini-tts/marin")

    def test_tts1_takes_no_instructions_and_only_its_nine_voices(self):
        with FakeHTTP(MP3) as h:
            tts.synthesize("openai", "Hi", "en-US-AvaMultilingualNeural", cfg("openai", key="k", model="tts-1", voice="nova"))
        self.assertNotIn("instructions", json.loads(h.last()[2]))
        with FakeHTTP() as h:
            with self.assertRaises(tts.TTSError) as cm:
                tts.synthesize("openai", "Hi", "en-US-AvaMultilingualNeural", cfg("openai", key="k", model="tts-1", voice="marin"))
        self.assertEqual((cm.exception.kind, h.calls), ("config", []))

    def test_used_up_quota_is_not_retried_but_a_busy_service_is(self):
        quota = {"error": {"message": "You exceeded your current quota, please check your plan and billing details.",
                           "type": "insufficient_quota", "code": "insufficient_quota"}}
        with FakeHTTP((429, quota, "application/json"), MP3) as h:
            with self.assertRaises(tts.TTSError) as cm:
                tts.synthesize("openai", "Hi", "de-DE-KatjaNeural", cfg("openai", key="k"))
        self.assertEqual((cm.exception.kind, len(h.calls)), ("quota", 1))
        busy = {"error": {"message": "Rate limit reached for requests", "type": "requests", "code": "rate_limit_exceeded"}}
        with FakeHTTP((429, busy, "application/json"), MP3) as h:
            clip = tts.synthesize("openai", "Hi", "de-DE-KatjaNeural", cfg("openai", key="k"))
        self.assertEqual((clip.service, len(h.calls)), ("openai", 2))

    def test_a_key_echoed_in_an_error_is_redacted(self):
        key = "sk-proj-abcdef1234567890ABCDEF"
        body = {"error": {"message": "Incorrect API key provided: %s. You can find your key at ..." % key,
                          "type": "invalid_request_error", "code": "invalid_api_key"}}
        masked = {"error": {"message": "Incorrect API key provided: sk-proj-************************0000. You can "
                                       "find your API key at https://platform.openai.com/account/api-keys.",
                            "type": "invalid_request_error", "code": "invalid_api_key", "param": None}, "status": 401}
        with FakeHTTP((401, masked, "application/json")):         # the live answer on 2026-10-14
            with self.assertRaises(tts.TTSError) as cm:
                tts.synthesize("openai", "Hi", "de-DE-KatjaNeural", cfg("openai", key="sk-proj-x"))
        self.assertNotIn("0000", str(cm.exception))
        with FakeHTTP((401, body, "application/json")):
            with self.assertRaises(tts.TTSError) as cm:
                tts.synthesize("openai", "Hi", "de-DE-KatjaNeural", cfg("openai", key=key))
        self.assertNotIn("abcdef1234567890", str(cm.exception))
        self.assertEqual(cm.exception.kind, "auth")


class GoogleCloud(unittest.TestCase):
    def test_request_shape_and_base64_answer(self):
        audio_b = b"\xff\xf3" + b"C" * 100
        with FakeHTTP((200, json.dumps({"audioContent": base64.b64encode(audio_b).decode()}).encode(),
                       "application/json")) as h:
            clip = tts.synthesize("google", "Hallo", "de-DE-KatjaNeural", cfg("google", key="AIzaTest"))
        url, hdr, body = h.last()
        self.assertEqual(url, "https://texttospeech.googleapis.com/v1/text:synthesize")
        self.assertEqual(hdr["x-goog-api-key"], "AIzaTest")
        self.assertNotIn("key=", url)                 # never in the URL
        b = json.loads(body)
        self.assertEqual(b["voice"], {"languageCode": "de-DE", "name": "de-DE-Chirp3-HD-Kore"})
        self.assertEqual(b["audioConfig"], {"audioEncoding": "MP3"})
        self.assertEqual((clip.data, clip.ext), (audio_b, "mp3"))

    def test_translation_gets_the_same_chirp_speaker_or_googles_default(self):
        ok = (200, b'{"audioContent": "AAAA"}', "application/json")
        with FakeHTTP(ok, ok, ok) as h:
            tts.synthesize("google", "Hi", "en-US-AvaMultilingualNeural", cfg("google", key="k", voice="de-DE-Chirp3-HD-Kore"))
            self.assertEqual(json.loads(h.last()[2])["voice"], {"languageCode": "en-US", "name": "en-US-Chirp3-HD-Kore"})
            tts.synthesize("google", "مرحبا", "ar-SA-HamedNeural", cfg("google", key="k", voice="de-DE-Chirp3-HD-Kore"))
            self.assertEqual(json.loads(h.last()[2])["voice"], {"languageCode": "ar-XA", "name": "ar-XA-Chirp3-HD-Kore"})
            tts.synthesize("google", "Hi", "en-GB-SoniaNeural", cfg("google", key="k", voice="de-DE-Wavenet-G"))
            self.assertEqual(json.loads(h.last()[2])["voice"], {"languageCode": "en-GB"})

    def test_regional_locales_map_to_ones_google_serves(self):
        ok = (200, b'{"audioContent": "AAAA"}', "application/json")
        with FakeHTTP(ok, ok, ok) as h:
            tts.synthesize("google", "Hola", "es-AR-ElenaNeural", cfg("google", key="k", voice="de-DE-Wavenet-G"))
            self.assertEqual(json.loads(h.last()[2])["voice"], {"languageCode": "es-US"})
            tts.synthesize("google", "Bonjour", "fr-BE-CharlineNeural", cfg("google", key="k", voice="de-DE-Wavenet-G"))
            self.assertEqual(json.loads(h.last()[2])["voice"], {"languageCode": "fr-FR"})
            tts.synthesize("google", "Hallo", "de-AT-IngridNeural", cfg("google", key="k", voice="de-DE-Wavenet-G"))
            self.assertEqual(json.loads(h.last()[2])["voice"], {"languageCode": "de-DE", "name": "de-DE-Wavenet-G"})

    def test_a_missing_chirp_speaker_falls_back_to_googles_default_voice(self):
        bad = (400, {"error": {"code": 400, "message": "Voice 'xx-YY-Chirp3-HD-Kore' does not exist.",
                               "status": "INVALID_ARGUMENT"}}, "application/json")
        ok = (200, b'{"audioContent": "AAAA"}', "application/json")
        with FakeHTTP(bad, ok) as h:
            clip = tts.synthesize("google", "Merhaba", "tr-TR-EmelNeural", cfg("google", key="k", voice="de-DE-Chirp3-HD-Kore"))
        self.assertEqual(json.loads(h.calls[0].data)["voice"]["name"], "tr-TR-Chirp3-HD-Kore")
        self.assertEqual(json.loads(h.calls[1].data)["voice"], {"languageCode": "tr-TR"})
        self.assertEqual(clip.voice, "tr-TR")

    def test_a_language_google_does_not_serve_is_refused_without_a_request(self):
        with FakeHTTP() as h:
            with self.assertRaises(tts.TTSError) as cm:
                tts.synthesize("google", "سلام", "fa-IR-DilaraNeural", cfg("google", key="k"))
        self.assertEqual((cm.exception.kind, h.calls), ("bad_request", []))
        self.assertEqual(str(cm.exception), "Google Cloud has no Persian voice")

    def test_a_bare_gemini_voice_name_is_refused_before_any_request(self):
        with FakeHTTP() as h:
            with self.assertRaises(tts.TTSError) as cm:
                tts.synthesize("google", "Hallo", "de-DE-KatjaNeural", cfg("google", key="k", voice="Kore"))
        self.assertEqual((cm.exception.kind, h.calls), ("config", []))

    def test_per_minute_limit_is_a_rate_limit(self):
        busy = (429, {"error": {"code": 429, "message": "Quota exceeded for quota metric 'Requests' and limit "
                                "'Requests per minute' of service 'texttospeech.googleapis.com'",
                                "status": "RESOURCE_EXHAUSTED", "details": [{"reason": "RATE_LIMIT_EXCEEDED"}]}},
                "application/json")
        with FakeHTTP(busy, busy):
            with self.assertRaises(tts.TTSError) as cm:
                tts.synthesize("google", "Hallo", "de-DE-KatjaNeural", cfg("google", key="k"))
        self.assertEqual(cm.exception.kind, "rate_limit")

    def test_google_error_reasons(self):
        def err(status, reason, msg):
            return (status, {"error": {"code": status, "message": msg, "status": "X",
                                       "details": [{"@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": reason}]}},
                    "application/json")
        for answer, kind in ((err(400, "API_KEY_INVALID", "API key not valid. Please pass a valid API key."), "auth"),
                             (err(403, "SERVICE_DISABLED", "Cloud Text-to-Speech API has not been used in project 1"), "auth"),
                             (err(403, "BILLING_DISABLED", "This API method requires billing to be enabled."), "quota")):
            with FakeHTTP(answer):
                with self.assertRaises(tts.TTSError) as cm:
                    tts.synthesize("google", "Hallo", "de-DE-KatjaNeural", cfg("google", key="k"))
            self.assertEqual(cm.exception.kind, kind, answer)


def _wav(pcm, rate=24000):
    return tts.pcm_to_wav(pcm, rate=rate)


class Gemini(unittest.TestCase):
    def _answer(self, data, mime="audio/wav"):
        return (200, json.dumps({"candidates": [{"content": {"parts": [{"inlineData": {
            "mimeType": mime, "data": base64.b64encode(data).decode()}}]}, "finishReason": "STOP"}]}).encode(),
            "application/json")

    def test_request_is_the_text_alone(self):
        with FakeHTTP(self._answer(_wav(b"\x01\x00" * 100))) as h:
            tts.synthesize("gemini", "Das Schloss ist alt.", "de-DE-KatjaNeural", cfg("gemini", key="AIzaG"))
        url, hdr, body = h.last()
        self.assertEqual(url, "https://generativelanguage.googleapis.com/v1beta/models/"
                              "gemini-3.8-flash-lite-tts:generateContent")
        self.assertEqual(hdr["x-goog-api-key"], "AIzaG")
        b = json.loads(body)
        self.assertEqual(b["contents"], [{"parts": [{"text": "Das Schloss ist alt."}]}])   # no "Say:"
        self.assertEqual(b["generationConfig"]["responseModalities"], ["AUDIO"])
        self.assertEqual(b["generationConfig"]["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"], "Kore")

    def test_a_wav_answer_is_kept_and_bare_pcm_is_wrapped(self):
        wav = _wav(b"\x02\x00" * 50)
        with FakeHTTP(self._answer(wav)):
            clip = tts.synthesize("gemini", "Hallo", "de-DE-KatjaNeural", cfg("gemini", key="k"))
        self.assertEqual((clip.data, clip.ext), (wav, "wav"))
        with FakeHTTP(self._answer(b"\x03\x00" * 120 + b"\x07", "audio/L16;codec=pcm;rate=16000")):
            clip = tts.synthesize("gemini", "Hallo", "de-DE-KatjaNeural", cfg("gemini", key="k", model="gemini-2.5-flash-preview-tts"))
        w = wave.open(io.BytesIO(clip.data))
        self.assertEqual((w.getframerate(), w.getsampwidth(), w.getnchannels(), w.getnframes()), (16000, 2, 1, 120))

    def test_no_audio_part_is_a_clear_error(self):
        body = {"candidates": [{"content": {}, "finishReason": "OTHER"}]}
        with FakeHTTP((200, json.dumps(body).encode(), "application/json")):
            with self.assertRaises(tts.TTSError) as cm:
                tts.synthesize("gemini", "Hallo", "de-DE-KatjaNeural", cfg("gemini", key="k"))
        self.assertEqual(cm.exception.kind, "no_audio")
        self.assertIn("OTHER", str(cm.exception))

    def test_free_tier_limit_is_a_rate_limit_not_billing_and_402_is_billing(self):
        limit = {"error": {"code": 429, "message": "You exceeded your current quota. Please retry in 17s.",
                           "status": "RESOURCE_EXHAUSTED"}}
        with FakeHTTP((429, limit, "application/json"), (429, limit, "application/json")) as h:
            with self.assertRaises(tts.TTSError) as cm:
                tts.synthesize("gemini", "Hallo", "de-DE-KatjaNeural", cfg("gemini", key="k"))
        self.assertEqual((cm.exception.kind, len(h.calls)), ("rate_limit", 2))     # one short retry
        broke = {"error": {"code": 402, "message": "Your Prepay credit balance is depleted.", "status": "RESOURCE_EXHAUSTED"}}
        with FakeHTTP((402, broke, "application/json")) as h:
            with self.assertRaises(tts.TTSError) as cm:
                tts.synthesize("gemini", "Hallo", "de-DE-KatjaNeural", cfg("gemini", key="k"))
        self.assertEqual((cm.exception.kind, len(h.calls)), ("quota", 1))

    def test_a_retired_model_is_a_setting_to_fix(self):
        gone = {"error": {"code": 404, "message": "models/gemini-2.5-flash-preview-tts is not found for API version v1beta",
                          "status": "NOT_FOUND"}}
        with FakeHTTP((404, gone, "application/json")):
            with self.assertRaises(tts.TTSError) as cm:
                tts.synthesize("gemini", "Hallo", "de-DE-KatjaNeural", cfg("gemini", key="k", model="gemini-2.5-flash-preview-tts"))
        self.assertEqual(cm.exception.kind, "config")
        self.assertIn("Settings, Voice", str(cm.exception))
        bad = {"error": {"code": 400, "message": "API key not valid. Please pass a valid API key.",
                         "status": "INVALID_ARGUMENT", "details": [{"reason": "API_KEY_INVALID"}]}}
        with FakeHTTP((400, bad, "application/json")):
            with self.assertRaises(tts.TTSError) as cm:
                tts.synthesize("gemini", "Hallo", "de-DE-KatjaNeural", cfg("gemini", key="k"))
        self.assertEqual(cm.exception.kind, "auth")


# ── the chain ──────────────────────────────────────────────────────────────────────────────
class FakeAdapters:
    """Replaces the service adapters: script maps service -> list of results (Clip data or TTSError)."""
    def __init__(self, **script):
        self.script, self.calls, self.rates = script, [], []

    def __enter__(self):
        self._saved = dict(tts._ADAPTERS)
        for s in tts.SERVICES:
            tts._ADAPTERS[s] = self._make(s)
        return self

    def __exit__(self, *a):
        tts._ADAPTERS.clear()
        tts._ADAPTERS.update(self._saved)

    def _make(self, service):
        def adapter(text, role_voice, sc, timeout, rate=1.0):
            self.calls.append(service)
            self.rates.append(rate)
            out = self.script[service].pop(0) if self.script.get(service) else b"audio-" + service.encode()
            if isinstance(out, Exception):
                raise out
            return tts.Clip(out, "mp3", service, role_voice, rate)
        return adapter


SET_UP = {"azure": {"key": "k", "region": "westeurope"}, "openai": {"key": "k"},
          "elevenlabs": {"key": "k", "voice": "v"}, "google": {"key": "k"}, "gemini": {"key": "k"}}


class Chain(unittest.TestCase):
    def test_default_is_edge_only(self):
        self.assertEqual(tts.chain({}), ["edge"])
        self.assertEqual(tts.chain(None), ["edge"])
        self.assertEqual(tts.chain({"service": "nonsense"}), ["edge"])

    def test_chosen_first_then_set_up_backups_in_the_users_order_then_edge(self):
        c = dict(SET_UP, service="azure", order=["gemini", "openai", "azure"])
        self.assertEqual(tts.chain(c), ["azure", "gemini", "openai", "elevenlabs", "google", "edge"])
        c = {"service": "openai", "openai": {"key": "k"}, "google": {"key": ""}}
        self.assertEqual(tts.chain(c), ["openai", "edge"])

    def test_a_chosen_service_that_is_not_set_up_says_so_and_edge_reads(self):
        with FakeAdapters():
            sp = tts.Speaker({"service": "elevenlabs", "elevenlabs": {"key": "k"}})   # no voice
            tts._ADAPTERS["elevenlabs"] = tts._elevenlabs                            # the real check runs
            clip = sp.speak("Hallo", "de-DE-KatjaNeural")
        self.assertEqual(clip.service, "edge")
        summary = sp.summary()
        self.assertEqual(summary["backup"], "edge")
        self.assertEqual(summary["category"], "config")
        self.assertIn("ElevenLabs is not set up", summary["failures"][0])

    def test_a_hard_failure_skips_the_service_for_the_rest_of_the_card(self):
        err = tts.TTSError("azure", "auth", "Azure AI Speech did not accept the key", 401)
        with FakeAdapters(azure=[err]) as fa:
            sp = tts.Speaker(dict(SET_UP, service="azure", order=["openai"]))
            for _ in range(4):
                self.assertEqual(sp.speak("x", "de-DE-KatjaNeural").service, "openai")
        self.assertEqual(fa.calls.count("azure"), 1)
        self.assertEqual(sp.summary()["used"], {"openai": 4})

    def test_a_refused_voice_is_skipped_for_that_voice_only(self):
        # Google has no Persian voice: the Persian clips go to Edge without asking Google again,
        # while Google still reads the German.
        no_fa = tts.TTSError("google", "bad_request", "Google Cloud refused the request (HTTP 400)", 400)
        with FakeAdapters(google=[no_fa]) as fa:
            sp = tts.Speaker({"service": "google", "google": {"key": "k"}})
            self.assertEqual(sp.speak("fa 1", "fa-IR-DilaraNeural").service, "edge")
            self.assertEqual(sp.speak("de 1", "de-DE-KatjaNeural").service, "google")
            self.assertEqual(sp.speak("fa 2", "fa-IR-DilaraNeural").service, "edge")
        self.assertEqual(fa.calls, ["google", "edge", "google", "edge"])

    def test_no_audio_for_one_text_tries_the_service_again_on_the_next_clip(self):
        soft = tts.TTSError("gemini", "no_audio", "Gemini sent no audio (OTHER)")
        with FakeAdapters(gemini=[soft]) as fa:
            sp = tts.Speaker({"service": "gemini", "gemini": {"key": "k"}})
            self.assertEqual(sp.speak("a", "de-DE-KatjaNeural").service, "edge")
            self.assertEqual(sp.speak("b", "de-DE-KatjaNeural").service, "gemini")
        self.assertEqual(fa.calls, ["gemini", "edge", "gemini"])

    def test_everything_fails_raises_and_the_summary_names_the_worst_reason(self):
        edge_err = tts.TTSError("edge", "auth", "Microsoft Edge refused the connection: HTTP 403 Forbidden", 403)
        with FakeAdapters(edge=[edge_err, edge_err]):
            sp = tts.Speaker({})
            with self.assertRaises(tts.TTSError):
                sp.speak("a", "de-DE-KatjaNeural")
            with self.assertRaises(tts.TTSError):        # dead now: no second request
                sp.speak("b", "de-DE-KatjaNeural")
        s = sp.summary()
        self.assertEqual((s["category"], s["failures"]),
                         ("auth", ["Microsoft Edge refused the connection: HTTP 403 Forbidden"]))

    def test_a_bug_in_an_adapter_is_contained(self):
        with FakeAdapters(azure=[ZeroDivisionError("boom")]):
            sp = tts.Speaker(dict(SET_UP, service="azure", order=["openai"]))
            self.assertEqual(sp.speak("a", "de-DE-KatjaNeural").service, "openai")
        self.assertIn("Azure AI Speech failed (ZeroDivisionError)", sp.summary()["failures"][0])
        self.assertNotIn("boom", sp.summary()["failures"][0])    # never the text: it could quote a key

    def test_the_chosen_services_own_failure_explains_first(self):
        busy = tts.TTSError("azure", "rate_limit", "Azure AI Speech is busy or rate limited (HTTP 429)", 429)
        broke = tts.TTSError("elevenlabs", "quota", "ElevenLabs says the credits, quota or billing need attention", 402)
        with FakeAdapters(azure=[busy], elevenlabs=[broke]):
            sp = tts.Speaker(dict(SET_UP, service="azure", order=["elevenlabs", "openai"]))
            self.assertEqual(sp.speak("a", "de-DE-KatjaNeural").service, "openai")
        s = sp.summary()
        self.assertTrue(s["failures"][0].startswith("Azure AI Speech is busy"))
        self.assertEqual(s["backups"], ["openai"])

    def test_edge_alone_keeps_trying_after_a_rate_limit(self):
        busy = tts.TTSError("edge", "rate_limit", "Microsoft Edge closed the connection: too many requests (code 1008)")
        with FakeAdapters(edge=[b"ok", busy, b"ok", b"ok"]) as fa:
            sp = tts.Speaker({})
            got = []
            for i in range(4):
                try:
                    got.append(sp.speak("clip %d" % i, "de-DE-KatjaNeural").service)
                except tts.TTSError:
                    got.append(None)
        self.assertEqual(got, ["edge", None, "edge", "edge"])
        self.assertEqual(fa.calls, ["edge"] * 4)

    def test_edge_alone_gets_one_more_try_after_a_timeout(self):
        # A test run: one slow Edge answer cost "bring up" all three clips and "la mano" three of four.
        slow = tts.TTSError("edge", "timeout", "Microsoft Edge did not answer in time")
        with FakeAdapters(edge=[slow, b"ok", b"ok"]) as fa:
            sp = tts.Speaker({})
            got = []
            for i in range(3):
                try:
                    got.append(sp.speak("clip %d" % i, "de-DE-KatjaNeural").service)
                except tts.TTSError:
                    got.append(None)
        self.assertEqual(got, [None, "edge", "edge"])
        self.assertEqual(fa.calls, ["edge"] * 3)

    def test_edge_alone_is_skipped_after_a_second_timeout(self):
        slow = tts.TTSError("edge", "timeout", "Microsoft Edge did not answer in time")
        with FakeAdapters(edge=[slow, slow]) as fa:
            sp = tts.Speaker({})
            for i in range(4):
                with self.assertRaises(tts.TTSError):
                    sp.speak("clip %d" % i, "de-DE-KatjaNeural")
        self.assertEqual(fa.calls, ["edge"] * 2)       # two waits at most, never one per clip

    def test_a_timeout_with_a_backup_left_moves_on_to_the_backup(self):
        slow = tts.TTSError("openai", "timeout", "OpenAI did not answer in time")
        with FakeAdapters(openai=[slow]) as fa:
            sp = tts.Speaker({"service": "openai", "openai": {"key": "k"}})
            self.assertEqual([sp.speak(str(i), "de-DE-KatjaNeural").service for i in range(3)], ["edge"] * 3)
        self.assertEqual(fa.calls.count("openai"), 1)

    def test_a_rate_limit_with_a_backup_left_moves_on_to_the_backup(self):
        busy = tts.TTSError("openai", "rate_limit", "OpenAI is busy or rate limited (HTTP 429)", 429)
        with FakeAdapters(openai=[busy]) as fa:
            sp = tts.Speaker({"service": "openai", "openai": {"key": "k"}})
            self.assertEqual([sp.speak(str(i), "de-DE-KatjaNeural").service for i in range(3)], ["edge"] * 3)
        self.assertEqual(fa.calls.count("openai"), 1)

    def test_odd_value_types_never_reach_the_settings_widgets(self):
        sc = tts.service_cfg({"azure": {"key": 12345, "region": ["west"]}, "openai": {"voice": True}}, "azure")
        self.assertEqual(sc, {"key": "12345", "region": ""})
        self.assertEqual(tts.service_cfg({"openai": {"voice": True}}, "openai")["voice"], "")

    def test_a_hand_edited_broken_config_falls_back_to_edge(self):
        for broken in ("azure", ["x"], 5, {"service": 1}, {"order": 5}, {"service": "azure", "azure": "k"},
                       {"order": [None, 3, "gemini"]}, {"openai": {"key": ["k"]}}):
            self.assertEqual(tts.chain(broken)[-1], "edge", broken)
            tts.service_cfg(broken, "openai")
            tts.backup_order(broken)
            tts.Speaker(broken)

    def test_old_config_without_tts_keys_still_works(self):
        self.assertEqual(tts.service_cfg({"openai": {"key": "k"}}, "openai")["model"], "gpt-4o-mini-tts")
        self.assertEqual(tts.backup_order({"order": ["bogus", "gemini"]})[0], "gemini")
        self.assertEqual(sorted(tts.backup_order({})), sorted(tts.DEFAULT_ORDER))


class AudioNote(unittest.TestCase):
    """The words the Add dialog shows after a card (ui/dialog.py adds the icon, escaping and link)."""

    def test_every_case(self):
        edge403 = "Microsoft Edge refused the connection: HTTP 403 Forbidden"
        self.assertEqual(tts.audio_note({"ok": 0, "total": 3, "failures": [edge403]}),
                         ("No audio, because " + edge403, "The last card has no audio, because %s." % edge403, True))
        self.assertEqual(tts.audio_note({"ok": 2, "total": 4, "failures": [edge403]})[0],
                         "2 of 4 audio clips are missing, because " + edge403)
        note = tts.audio_note({"ok": 3, "total": 3, "failures": ["ElevenLabs is not set up: add its API key in "
                                                                  "Settings, Voice"], "backups": ["edge"]})
        self.assertEqual(note[0], "Read by Microsoft Edge, because ElevenLabs is not set up: add its API key in Settings, Voice")
        self.assertFalse(note[2])
        two = tts.audio_note({"ok": 3, "total": 3, "failures": ["x"], "backups": ["openai", "edge"]})
        self.assertTrue(two[1].startswith("OpenAI and Microsoft Edge read the last card"))
        self.assertEqual(tts.audio_note({"ok": 3, "total": 3, "failures": []}), ("", "", False))
        self.assertEqual(tts.audio_note({"ok": 0, "total": 0}), ("", "", False))       # no clips asked
        self.assertEqual(tts.audio_note(None), ("", "", False))
        self.assertEqual(tts.audio_note({"ok": 0, "total": 2})[0], "No audio, because the voice service did not answer")


# ── speech speed ───────────────────────────────────────────────────────────────────────────
class Speed(unittest.TestCase):
    """Settings, Voice, Speech speed: the language you learn read about 20% slower, at every level or
    at A1 and A2. A normal request is byte for byte the request of 1.2.0."""

    def test_the_setting_and_the_rate_of_each_level(self):
        for value in (None, {}, {"speed": "fast"}, {"speed": 0.8}, {"speed": ["slower"]}, "slower"):
            self.assertEqual(tts.speed(value), "normal", value)
        self.assertEqual(tts.speed({"speed": " Slower "}), "slower")
        beginners, always = {"speed": "slower_a1_a2"}, {"speed": "slower"}
        for level in ("A1", "A2"):
            self.assertEqual(tts.speech_rate(beginners, level), tts.SLOW_RATE)
        for level in ("B1", "B2", "C1", "Native"):
            self.assertEqual(tts.speech_rate(beginners, level), 1.0)
            self.assertEqual(tts.speech_rate(always, level), tts.SLOW_RATE)
            self.assertEqual(tts.speech_rate({}, level), 1.0)
        # A sample in Settings (no level) plays the slower speed whenever one is picked.
        self.assertEqual(tts.speech_rate(beginners), tts.SLOW_RATE)
        self.assertEqual(tts.speech_rate({"speed": "normal"}), 1.0)
        self.assertEqual(tts.SLOW_RATE, 0.8)

    def test_ssml_rate(self):
        self.assertEqual((tts.ssml_rate(1.0), tts.ssml_rate(0.8)), ("+0%", "-20%"))
        for odd in ("0.8", None, True, 9, 0.1):
            self.assertEqual(tts.ssml_rate(odd), "+0%", odd)

    def test_edge_ssml_carries_the_rate_and_a_normal_one_is_unchanged(self):
        self.assertEqual(audio._mkssml("Hallo", "de-DE-KatjaNeural"),
                         "<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='en-US'>"
                         "<voice name='de-DE-KatjaNeural'><prosody pitch='+0Hz' rate='+0%' volume='+0%'>Hallo"
                         "</prosody></voice></speak>")
        self.assertIn("rate='-20%'", audio._mkssml("Hallo", "de-DE-KatjaNeural", "-20%"))
        self.assertIn("rate='+0%'", audio._mkssml("Hallo", "v", "'/><x a='"))   # only a signed percent
        seen, real = [], audio._mkssml
        audio._mkssml = lambda text, voice, rate="+0%": seen.append(rate) or real(text, voice, rate)
        try:
            with FakeEdge([_audio_answer(), _audio_answer()]):
                slow = tts.synthesize("edge", "Hallo.", "de-DE-KatjaNeural", {}, rate=0.8)
                normal = tts.synthesize("edge", "Hallo.", "de-DE-KatjaNeural", {})
        finally:
            audio._mkssml = real
        self.assertEqual(seen, ["-20%", "+0%"])
        self.assertEqual((slow.rate, normal.rate), (0.8, 1.0))

    def test_azure_wraps_the_text_in_a_prosody_rate(self):
        with FakeHTTP(MP3, MP3) as h:
            clip = tts.synthesize("azure", "Tom & Jerry", "de-DE-KatjaNeural",
                                  cfg("azure", key="k", region="westeurope"), rate=0.8)
            slow = h.last()[2].decode()
            tts.synthesize("azure", "Tom & Jerry", "de-DE-KatjaNeural", cfg("azure", key="k", region="westeurope"))
            normal = h.last()[2].decode()
        self.assertIn("<voice name='de-DE-KatjaNeural'><prosody rate='-20%'>Tom &amp; Jerry</prosody></voice>", slow)
        self.assertIn("<voice name='de-DE-KatjaNeural'>Tom &amp; Jerry</voice>", normal)
        self.assertEqual(clip.rate, 0.8)

    def test_elevenlabs_openai_and_google_take_their_own_speed_field(self):
        google = (200, json.dumps({"audioContent": base64.b64encode(b"\xff\xf3audio").decode()}).encode(),
                  "application/json")
        cases = (("elevenlabs", cfg("elevenlabs", key="k", voice="v"), MP3,
                  lambda b: b.get("voice_settings"), {"speed": 0.8}),
                 ("openai", cfg("openai", key="k"), MP3, lambda b: b.get("speed"), 0.8),
                 ("openai", cfg("openai", key="k", model="tts-1", voice="nova"), MP3, lambda b: b.get("speed"), 0.8),
                 ("google", cfg("google", key="k"), google, lambda b: b["audioConfig"].get("speakingRate"), 0.8))
        for service, c, answer, field, slow_value in cases:
            with FakeHTTP(answer, answer) as h:
                clip = tts.synthesize(service, "Hallo", "de-DE-KatjaNeural", c, rate=0.8)
                slow = json.loads(h.last()[2])
                tts.synthesize(service, "Hallo", "de-DE-KatjaNeural", c)
                normal = json.loads(h.last()[2])
            self.assertEqual(field(slow), slow_value, service)
            self.assertIsNone(field(normal), service)          # nothing new in a normal request
            self.assertEqual(clip.rate, 0.8, service)
        self.assertEqual(normal["audioConfig"], {"audioEncoding": "MP3"})

    def test_gemini_has_no_speed_and_its_clip_says_normal(self):
        answer = Gemini()._answer(_wav(b"\x01\x00" * 50))
        with FakeHTTP(answer, answer) as h:
            clip = tts.synthesize("gemini", "Hallo", "de-DE-KatjaNeural", cfg("gemini", key="k"), rate=0.8)
            slow = h.last()[2]
            tts.synthesize("gemini", "Hallo", "de-DE-KatjaNeural", cfg("gemini", key="k"))
        self.assertEqual(slow, h.last()[2])
        self.assertEqual(clip.rate, 1.0)

    def test_a_backup_reads_at_the_same_speed(self):
        err = tts.TTSError("azure", "auth", "Azure AI Speech did not accept the key", 401)
        with FakeAdapters(azure=[err]) as fa:
            clip = tts.Speaker(dict(SET_UP, service="azure", order=["openai"])).speak("Hallo", "de-DE-KatjaNeural", 0.8)
        self.assertEqual((fa.calls, fa.rates, clip.service, clip.rate), (["azure", "openai"], [0.8, 0.8], "openai", 0.8))

    def test_a_slower_clip_gets_its_own_filename_and_a_normal_one_keeps_its_old_name(self):
        import hashlib
        normal = tts.Clip(b"", "mp3", "edge", "de-DE-KatjaNeural")
        self.assertEqual(tts.audio_tag("Hallo", normal),
                         hashlib.sha1(b"edge|de-DE-KatjaNeural|Hallo").hexdigest()[:10])
        self.assertEqual(tts.audio_tag("Hallo", tts.Clip(b"", "mp3", "edge", "de-DE-KatjaNeural", 1.0)),
                         tts.audio_tag("Hallo", normal))
        self.assertNotEqual(tts.audio_tag("Hallo", tts.Clip(b"", "mp3", "edge", "de-DE-KatjaNeural", 0.8)),
                            tts.audio_tag("Hallo", normal))


# ── filenames and WAV ──────────────────────────────────────────────────────────────────────
class Filenames(unittest.TestCase):
    def test_same_text_service_and_voice_same_name_else_different(self):
        a = tts.Clip(b"", "mp3", "edge", "de-DE-KatjaNeural")
        self.assertEqual(tts.audio_tag("Hallo", a), tts.audio_tag("Hallo", a))
        for other in (tts.Clip(b"", "mp3", "edge", "de-DE-ConradNeural"), tts.Clip(b"", "mp3", "azure", "de-DE-KatjaNeural")):
            self.assertNotEqual(tts.audio_tag("Hallo", a), tts.audio_tag("Hallo", other))
        self.assertNotEqual(tts.audio_tag("Hallo", a), tts.audio_tag("Hallo!", a))

    def test_generate_names_use_the_services_extension(self):
        wav = tts.Clip(b"", "wav", "gemini", "gemini-3.8-flash-lite-tts/Kore")
        name = generate._audio_name("tts_de", "🏰 das Schloss.", "das Schloss. ... Text", wav)
        self.assertRegex(name, r"^tts_de_das_Schloss_[0-9a-f]{10}\.wav$")

    def test_pcm_to_wav_trims_a_half_sample(self):
        w = wave.open(io.BytesIO(tts.pcm_to_wav(b"\x00\x01" * 10 + b"\x05")))
        self.assertEqual((w.getnframes(), w.getframerate()), (10, 24000))


# ── build_card wiring: names, fallback summary, cloze clips ────────────────────────────────
class BuildCardAudio(unittest.TestCase):
    CARD = {"emoji": "🏰", "word": "das Schloss", "translation_en": "castle", "register": "neutral",
            "casual_alternatives": [], "casual_alternatives_en": [],
            "example_casual": "Das Schloss ist sehr alt.", "example_formal": "Das Schloss steht auf dem Berg.",
            "example_casual_en": "The castle is very old.", "example_formal_en": "The castle stands on the hill.",
            "explanation_de": "ein großes Gebäude", "tags": ["Alltag"], "imageKeyword": "castle",
            "emoji_formal": "🏰", "emoji_casual": "🏰", "grammar_patterns": [], "grammar_patterns_en": [],
            "morphology": {"pos": "noun", "article": "das", "plural": "die Schlösser", "genitive": "des Schlosses"},
            "input_is_german": True, "input_suggestion": ""}
    CLOZE = {"case": "single_word", "sentence": "Wir besuchen das Schloss am Sonntag.", "answer": "Schloss",
             "translation_en": "We visit the castle on Sunday.", "grammar_hint": "", "idiom_meaning_de": ""}

    def _run(self, tts_cfg, edge_script=(), translation_voice="", level="B1"):
        calls = []

        def fake_json(provider, system, user, **kw):
            calls.append(system)
            return dict(self.CLOZE) if system == generate.prompts.SYSTEM_CLOZE else json.loads(json.dumps(self.CARD))
        saved = (providers.complete_json, generate.images.fetch_image)
        providers.complete_json = fake_json
        generate.images.fetch_image = lambda *a, **k: None
        try:
            with FakeAdapters(edge=list(edge_script)) as fa:
                bundle = generate.build_card(
                    {"voices": {"target": "de-DE-KatjaNeural", "translation": translation_voice}, "tts": tts_cfg},
                    {"type": "openai_compatible", "model": "m", "api_key": "k"}, "Tarkib", "das Schloss",
                    {"generate_cloze": True, "level": level})
        finally:
            providers.complete_json, generate.images.fetch_image = saved
        return bundle, fa

    def test_every_clip_is_named_from_text_service_and_voice(self):
        bundle, fa = self._run({}, translation_voice="en-US-AvaMultilingualNeural")
        media = bundle["media"]
        self.assertEqual(sorted(media), ["CLOZE_BACK", "CLOZE_FRONT", "TTS_DE", "TTS_EN"])
        for token, (name, data) in media.items():
            self.assertRegex(name, r"_[0-9a-f]{10}\.mp3$", token)
            self.assertEqual(data, b"audio-edge")
        self.assertEqual(bundle["meta"]["audio"]["ok"], 4)
        self.assertIsNone(bundle["meta"]["audio"]["category"])
        self.assertIn("[sound:@@TTS_DE@@][sound:@@TTS_EN@@]", bundle["main"]["fields"]["Back"])

    def test_edge_down_means_no_audio_and_the_reason_reaches_the_dialog(self):
        err = tts.TTSError("edge", "auth", "Microsoft Edge refused the connection: HTTP 403 Forbidden", 403)
        bundle, fa = self._run({}, edge_script=[err])
        a = bundle["meta"]["audio"]
        self.assertEqual((a["ok"], a["total"], a["category"]), (0, 3, "auth"))
        self.assertEqual(fa.calls, ["edge"])                 # the dead service is not asked again
        self.assertFalse([k for k in bundle["media"] if k.startswith(("TTS", "CLOZE"))])
        self.assertIn("HTTP 403", a["failures"][0])

    def test_the_language_you_learn_is_read_slower_and_the_translation_is_not(self):
        voice = "en-US-AvaMultilingualNeural"
        slow, normal = tts.SLOW_RATE, 1.0
        # Clips in order: the word and its sentences, the translation, the cloze front and back.
        for speed, level, rates in (("slower_a1_a2", "A1", [slow, normal, slow, slow]),
                                    ("slower_a1_a2", "B1", [normal] * 4),
                                    ("slower", "C1", [slow, normal, slow, slow]),
                                    ("normal", "A1", [normal] * 4)):
            bundle, fa = self._run({"speed": speed}, translation_voice=voice, level=level)
            self.assertEqual(fa.rates, rates, (speed, level))
            self.assertEqual(bundle["meta"]["audio"]["ok"], 4)
        names = lambda b: {k: v[0] for k, v in b["media"].items()}
        slow_names = names(self._run({"speed": "slower"}, translation_voice=voice)[0])
        normal_names = names(self._run({}, translation_voice=voice)[0])
        self.assertEqual(slow_names["TTS_EN"], normal_names["TTS_EN"])
        for token in ("TTS_DE", "CLOZE_FRONT", "CLOZE_BACK"):
            self.assertNotEqual(slow_names[token], normal_names[token], token)


if __name__ == "__main__":
    unittest.main(verbosity=1)
