"""Settings dialog: BYOK keys, provider, model dropdown, image keys, voices, voice service, secondary language.

v1 edits the FIRST provider (the active one — Groq by default) plus the image keys, voices,
and the optional secondary translation language. The Languages tab starts with the language you learn:
each learning language keeps its own voice and translation languages (generate.language_settings reads
them, lang_rules.store_language_settings writes them). The Model field is a dropdown synced from the
provider: OpenAI-compatible providers expose GET /models, Anthropic exposes GET /v1/models (a
curated list is shown first and used as the fallback). Results are cached to
user_files/models_cache.json (7-day TTL) so opening Settings never blocks on the network. The
provider-scoped helpers (_test_key, _refresh_models) take a provider dict.
All values are stored in the add-on config (mw.addonManager), never logged, never committed.
"""
import json
import os
import re
import time
import traceback
import urllib.error

from aqt import mw
from aqt.qt import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, QComboBox,
    QPushButton, QLabel, QCheckBox, QToolButton, QWidget, QScrollArea, QFrame,
    QTabWidget, Qt, QTimer, QListWidget, QListWidgetItem, QSizePolicy, QPlainTextEdit,
)
from aqt.utils import askUser, qconnect, tooltip, showText
from aqt.sound import av_player
from aqt.operations import QueryOp, CollectionOp

from ..pipeline import generate, languages, providers, prompts, audio, images, tts
from . import lang_rules
from .support import support_link, decks_link, DECKS_LANGUAGE

CUSTOM_LABEL = "Custom…"
CUSTOM_PRESET = "Custom…"          # preset entry that reveals Name / Type / Base URL for any other endpoint
LOADING_LABEL = "Loading…"
NONE_LABEL = "(none)"
CHOOSE_LABEL = "(choose one)"      # a learning language with no translation language yet
MODELS_CACHE_TTL = 7 * 24 * 3600       # 7 days
VOICES_CACHE_TTL = 30 * 24 * 3600      # 30 days (voices change rarely)

def _make_combo(editable=False):
    """Single source of truth for every dropdown in this dialog. Long items (voice names, model
    ids) must NEVER widen the tab: the combo sizes to a small minimum, fills its column, and
    truncates with '…' — the full text still shows in the open popup."""
    c = QComboBox()
    c.setEditable(editable)
    c.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
    c.setMinimumContentsLength(12)
    return c


PRESETS = {
    # label -> (type, base_url, default_model)
    "Groq (OpenAI-compatible)": ("openai_compatible", "https://api.groq.com/openai/v1", "openai/gpt-oss-120b"),
    "OpenAI": ("openai_compatible", "https://api.openai.com/v1", "gpt-4o-mini"),
    "OpenRouter": ("openai_compatible", "https://openrouter.ai/api/v1", "openai/gpt-4o-mini"),
    "Gemini (OpenAI-compatible)": ("openai_compatible", "https://generativelanguage.googleapis.com/v1beta/openai/", "gemini-2.5-flash"),
    "Mistral": ("openai_compatible", "https://api.mistral.ai/v1", "mistral-large-latest"),
    "Ollama (local)": ("openai_compatible", "http://localhost:11434/v1", "llama3.1"),
    "Anthropic": ("anthropic", "", "claude-sonnet-4-6"),
}

# Where each preset's API key comes from: (host label, URL, note). Shown as a clickable hint under
# the key field so a first-time user never has to leave Anki to find out where to get a key.
KEY_SOURCES = {
    "Groq (OpenAI-compatible)": ("console.groq.com", "https://console.groq.com/keys",
                                 "Free, no card needed: sign up, open API Keys, click Create API Key, copy it here."),
    "OpenAI": ("platform.openai.com", "https://platform.openai.com/api-keys", "Paid account required."),
    "OpenRouter": ("openrouter.ai", "https://openrouter.ai/keys", "One key for many models. Some are free."),
    "Gemini (OpenAI-compatible)": ("aistudio.google.com", "https://aistudio.google.com/apikey",
                                   "Free tier available with a Google account."),
    "Mistral": ("console.mistral.ai", "https://console.mistral.ai/api-keys", "Free tier available."),
    "Anthropic": ("console.anthropic.com", "https://console.anthropic.com/settings/keys", "Paid account required."),
    "Ollama (local)": ("", "", "Ollama runs on your own computer and needs no real key: type anything, e.g. ollama."),
}


# ── Settings, Voice: who reads the cards aloud (the work is in pipeline/tts.py) ──────────────
TTS_ITEMS = {"edge": "Microsoft Edge (free, no key)", "azure": "Azure AI Speech", "elevenlabs": "ElevenLabs",
             "openai": "OpenAI", "google": "Google Cloud", "gemini": "Gemini"}
# The speech speed dropdown, in the order of tts.SPEEDS.
SPEED_ITEMS = (("normal", "Normal"), ("slower_a1_a2", "Slower at A1 and A2"), ("slower", "Slower at every level"))
# One short paragraph per service: what it is, what it costs, where the key comes from. Facts
# checked against each provider's own pages on 2026-10-14.
TTS_HELP = {
    "edge": "Free and needs no key. It reads with the voices you pick on the Languages tab. It is not an "
            "official service, so it can stop working without notice. Set up a backup below to be safe.",
    "azure": "Official Microsoft voices with the same names as on the Languages tab. Free tier: 0.5 million "
             "characters a month. You need an Azure account (it asks for a card to check who you are) and a "
             "Speech resource: its key and region are under Keys and Endpoint in the "
             '<a href="https://portal.azure.com/">Azure portal</a>.',
    "elevenlabs": "Very natural voices. The voice you pick here reads every language. The free plan has "
                  "10,000 credits a month, for personal use, and can use your own voices and the default ones, "
                  "not voices saved from the Voice Library. Press ↻ to list your account's voices. When you "
                  "create the key, allow Text to Speech and Voices (read). Key: "
                  '<a href="https://elevenlabs.io/app/settings/api-keys">elevenlabs.io</a>.',
    "openai": "Paid, there is no free tier. The voice you pick here reads every language, marin and cedar "
              "sound best. OpenAI plans to retire these speech models on 6 January 2027. Key: "
              '<a href="https://platform.openai.com/api-keys">platform.openai.com</a>.',
    "google": "Google Cloud Text-to-Speech, free up to 1 million characters a month with Chirp 3 HD voices "
              "(4 million with Standard and WaveNet). It needs a Google Cloud project with billing turned on "
              "and the Text-to-Speech API enabled. The voice you set here reads the language you learn, and the "
              "same speaker reads the other languages when it is a Chirp 3 HD voice. Key: "
              '<a href="https://console.cloud.google.com/apis/credentials">console.cloud.google.com</a>.',
    "gemini": "Gemini speech, with a free tier and the same kind of key as Gemini for cards (no card needed): "
              '<a href="https://aistudio.google.com/apikey">aistudio.google.com</a>. The voice reads every '
              "language. The free tier allows only a few clips a minute, and the audio is saved as WAV, which "
              "takes more space (about 50 KB per second).",
}
TTS_KEY_HINTS = {"azure": "paste your Speech resource key", "elevenlabs": "paste your ElevenLabs API key",
                 "openai": "paste your OpenAI API key, sk-…", "google": "paste your Google Cloud API key",
                 "gemini": "paste your Gemini API key"}


def _tts_reason(e):
    """What a failed voice request may show: the service's own readable reason, never the text of an
    unexpected error (it could quote a request header, and with it a key)."""
    if isinstance(e, tts.TTSError):
        return str(e)
    return "Something unexpected went wrong (%s). Check the key and try again." % e.__class__.__name__


def _combo_value(combo):
    """The value of an editable dropdown: the selected item's data when the text is still that item
    (a voice NAME shown, its id stored), else the item with that text, else the typed text itself.
    The selected item comes first: two voices can share a name, and findText finds only the first."""
    text = (combo.currentText() or "").strip()
    i = combo.currentIndex()
    if i >= 0 and (combo.itemText(i) or "").strip() == text and combo.itemData(i):
        return str(combo.itemData(i)).strip()
    i = combo.findText(text)
    if i >= 0:
        data = combo.itemData(i)
        if data:
            return str(data).strip()
    return text


def _fill_combo(combo, items, value, value_label=""):
    """items: plain strings or (label, data) pairs. Selects `value` (data or text), adding it as an
    item when the list does not hold it, so a stored or typed id is never lost."""
    combo.blockSignals(True)
    combo.clear()
    for it in items:
        if isinstance(it, (tuple, list)):
            combo.addItem(it[0], it[1])
        else:
            combo.addItem(it, it)
    value = (value or "").strip()
    if value:
        i = combo.findData(value)
        if i < 0:
            combo.insertItem(0, value_label or value, value)
            i = 0
        combo.setCurrentIndex(i)
    elif combo.isEditable():
        combo.setCurrentIndex(-1)
        combo.setEditText("")
    combo.blockSignals(False)


def _cfg():
    return mw.addonManager.getConfig(__name__) or {}


def _addon_version():
    """human_version from manifest.json (so bug reports can name the version); '?' if unreadable."""
    try:
        p = os.path.join(os.path.dirname(os.path.dirname(__file__)), "manifest.json")
        with open(p, "r", encoding="utf-8") as f:
            return str(json.load(f).get("human_version") or "?")
    except Exception:
        return "?"


def _key_err_reason(e):
    """A short, plain reason a key test failed — for the combined report / save warning."""
    if isinstance(e, urllib.error.HTTPError):
        if e.code in (401, 403):
            return "rejected (HTTP %d, key wrong or not allowed)" % e.code
        if e.code == 429:
            return "rate-limited (HTTP 429, try again later)"
        return "error (HTTP %d)" % e.code
    if isinstance(e, urllib.error.URLError):
        return "no connection"
    return (str(e) or e.__class__.__name__)[:80]


# ── model cache (user_files/models_cache.json) ───────────────────────────────────────────
def _models_cache_path():
    d = os.path.join(os.path.dirname(os.path.dirname(__file__)), "user_files")
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass
    return os.path.join(d, "models_cache.json")


def _provider_cache_id(prov):
    """Stable cache key, by endpoint (survives provider renames). Anthropic is a single bucket."""
    if (prov.get("type") or "").lower() == "anthropic":
        return "anthropic"
    base = (prov.get("base_url") or "").strip().lower()
    return re.sub(r"[^a-z0-9]+", "_", base).strip("_") or (prov.get("id") or "provider")


def _read_models_cache():
    try:
        with open(_models_cache_path(), "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def _cached_models(prov, respect_ttl=True):
    """Cached id list for this provider, or None. respect_ttl=False = use it even if stale
    (good enough to display on open); respect_ttl=True = treat stale as missing (re-fetch)."""
    entry = _read_models_cache().get(_provider_cache_id(prov))
    if not entry:
        return None
    if respect_ttl and (time.time() - (entry.get("fetched_at") or 0)) > MODELS_CACHE_TTL:
        return None
    return (entry.get("models") or []) or None


def _store_models_cache(prov, models):
    cache = _read_models_cache()
    cache[_provider_cache_id(prov)] = {"fetched_at": int(time.time()), "models": list(models)}
    try:
        with open(_models_cache_path(), "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ── voice catalog cache (user_files/voices_cache.json — single global bucket) ────────────
def _voices_cache_path():
    d = os.path.join(os.path.dirname(os.path.dirname(__file__)), "user_files")
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass
    return os.path.join(d, "voices_cache.json")


def _read_voices_cache(respect_ttl=True):
    try:
        with open(_voices_cache_path(), "r", encoding="utf-8") as f:
            entry = json.load(f) or {}
    except Exception:
        return None
    if respect_ttl and (time.time() - (entry.get("fetched_at") or 0)) > VOICES_CACHE_TTL:
        return None
    return (entry.get("voices") or []) or None


def _store_voices_cache(voices):
    try:
        with open(_voices_cache_path(), "w", encoding="utf-8") as f:
            json.dump({"fetched_at": int(time.time()), "voices": list(voices)}, f, ensure_ascii=False)
    except Exception:
        pass


class SettingsDialog(QDialog):
    def __init__(self, parent=None, initial_tab=None, initial_language=None):
        super().__init__(parent)
        self.setWindowTitle("Tarkib Settings (v%s)" % _addon_version())
        self.setMinimumWidth(540)
        self.cfg = _cfg()
        # The learning language the Languages tab shows: the Add window's (initial_language), else the
        # one last chosen. Each language's values, once shown, are kept in _lang_edits until Save.
        self._lang = initial_language if initial_language in languages.codes() else \
            languages.resolve((self.cfg.get("defaults") or {}).get("learning_language"))[0]
        self._lang_edits = {}
        # True once _save has written the config. The first Save on a fresh install keeps this
        # dialog open while models and voices load, so a later Cancel or x still means "saved",
        # and whoever opened it refreshes on this rather than on exec() alone.
        self.saved = False

        provs = self.cfg.get("providers") or []
        self.prov = provs[0] if provs else {
            "id": "groq", "type": "openai_compatible", "name": "Groq",
            "base_url": "https://api.groq.com/openai/v1", "model": "openai/gpt-oss-120b", "api_key": "",
        }
        img = self.cfg.get("image", {}) or {}
        defaults = self.cfg.get("defaults", {}) or {}

        # Originals, so Save can detect which keys CHANGED (for the non-blocking warn-check).
        self._orig_ai_key = self.prov.get("api_key") or ""
        # The key the current model list was fetched with — guards against redundant refetches
        # when the key field loses focus without its value having changed.
        self._model_fetch_key = self._orig_ai_key
        self._key_endpoint = _provider_cache_id(self.prov)   # endpoint the stored key was entered for
        self._keys_by_endpoint = {}                           # keys typed this session, per endpoint
        self._orig_pexels = img.get("pexels_key") or ""
        self._orig_serper = img.get("serper_key") or ""
        self._orig_pixabay = img.get("pixabay_key") or ""

        self._models = []              # current model dropdown source list
        self._prev_model = ""          # selection captured before a fetch (survives Loading…)
        self._voices = []              # cached/fetched full voice catalog (list of dicts)
        self._voice_slots = {}         # slot -> {combo, refresh, locales, stored, allow_none}
        self._loading = 0              # in-flight fetches; >0 disables Save/Test
        self._fetched_session = False  # auto-fetch-on-Save fires at most once per dialog

        layout = QVBoxLayout(self)

        # Tabbed body: one short, self-explanatory screen per group. Each tab scrolls on its own so
        # nothing overflows on small 13" laptops; the action buttons stay pinned below all tabs.
        tabs = QTabWidget()

        def _new_tab(title):
            host = QWidget()
            f = QFormLayout(host)
            f.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            f.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
            f.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
            sc = QScrollArea()
            sc.setWidgetResizable(True)
            sc.setFrameShape(QFrame.Shape.NoFrame)
            sc.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            sc.setWidget(host)
            tabs.addTab(sc, title)
            return f

        # ── Provider tab ──
        # Progressive disclosure: Preset is the only control most users touch. Picking a known
        # preset fills Type / Base URL / Name behind the scenes and HIDES them; "Custom…" reveals
        # them for any other endpoint. So the common path is just Preset → Model → API key.
        form = _new_tab("Provider")
        self.prov_form = form
        self.preset = _make_combo()
        self.preset.addItems(list(PRESETS.keys()))
        self.preset.addItem(CUSTOM_PRESET)
        qconnect(self.preset.currentTextChanged, self._apply_preset)
        form.addRow("Preset", self.preset)

        # The three "advanced" rows. A known preset fills them and keeps them hidden; only
        # "Custom…" reveals them. Each carries a hover TOOLTIP instead of an inline hint to stay
        # compact (these are power-user fields, rarely seen). Collected in self._advanced so
        # _set_advanced_visible toggles them as one group.
        self.name_edit = QLineEdit(self.prov.get("name", "Groq"))
        self.name_edit.setToolTip("Just a label for you. It has no effect on your cards, "
                                  "so anything is fine.")
        form.addRow("Name", self.name_edit)

        self.type_combo = _make_combo()
        self.type_combo.addItems(["openai_compatible", "anthropic"])
        self.type_combo.setCurrentText(self.prov.get("type", "openai_compatible"))
        self.type_combo.setToolTip("The request format your provider speaks. Groq, OpenAI, OpenRouter, "
                                   "Gemini and Ollama all use openai_compatible. Only Claude (Anthropic) "
                                   "uses anthropic.")
        qconnect(self.type_combo.currentTextChanged, lambda _=None: self._on_provider_changed())
        form.addRow("Type", self.type_combo)

        self.base_edit = QLineEdit(self.prov.get("base_url", ""))
        self.base_edit.setToolTip("The provider's web address (for example Groq is "
                                  "https://api.groq.com/openai/v1). All of one provider's models share "
                                  "it, so change it only for a provider that isn't in the preset list.")
        form.addRow("Base URL", self.base_edit)

        self._advanced = [self.name_edit, self.type_combo, self.base_edit]

        # Model: dropdown synced from the provider, a Refresh button, and a revealed Custom… field.
        model_row = QHBoxLayout()
        self.model_combo = _make_combo()
        qconnect(self.model_combo.currentTextChanged, self._on_model_changed)
        self.model_refresh = QPushButton("↻ Refresh")
        self.model_refresh.setToolTip("Fetch the latest model list from the provider")
        qconnect(self.model_refresh.clicked, lambda: self._refresh_models())
        model_row.addWidget(self.model_combo, 1)
        model_row.addWidget(self.model_refresh, 0)
        form.addRow("Model", model_row)
        self.model_custom = QLineEdit()
        self.model_custom.setPlaceholderText("custom model id, e.g. a fine-tune or self-hosted slug")
        self.model_custom.hide()
        form.addRow("", self.model_custom)
        self.model_combo.setToolTip("Bigger models usually make better cards. Small / free models are "
                                    "faster and cheaper, but can write weaker sentences or hit limits sooner.")
        model_hint = QLabel("💡 Bigger models make better cards. Small / free models are faster and cheaper, "
                            "but may write weaker sentences or hit their limit sooner. Switch up if results look off.")
        model_hint.setWordWrap(True)
        model_hint.setStyleSheet("font-size: 11px;")
        form.addRow("", model_hint)

        self.key_edit = QLineEdit(self.prov.get("api_key", ""))
        self._apply_key_echo(self.key_edit, "paste your API key, e.g. sk-…")
        # Reactive sync: paste a key + tab out → the model list fetches automatically (no need to
        # hunt for Refresh). Guarded so it only fires when the key actually changed.
        qconnect(self.key_edit.editingFinished, self._on_key_edited)
        form.addRow("API key", self.key_edit)
        key_privacy = QLabel("🔒 Stored only on this computer. It is never synced by Anki and never sent "
                             "to us. Your key goes directly to the provider you chose (e.g. Groq) to "
                             "make your cards, and nowhere else.")
        key_privacy.setWordWrap(True)
        key_privacy.setStyleSheet("font-size: 11px;")
        form.addRow("", key_privacy)
        # Where to GET a key, per preset. This is the hardest first-run step for a non-technical
        # user, so it lives right under the field as a clickable link (refreshed by _apply_preset).
        self.key_help = QLabel()
        self.key_help.setWordWrap(True)
        self.key_help.setOpenExternalLinks(True)
        self.key_help.setTextFormat(Qt.TextFormat.RichText)
        self.key_help.setStyleSheet("font-size: 11px;")
        form.addRow("", self.key_help)

        # ── Images tab ──
        form = _new_tab("Images")
        img_intro = QLabel("Optional, to put pictures on your cards. Any one key is enough, and the add-on "
                           "falls back across them. With no key at all it tries free Openverse, which often "
                           "finds nothing, so add a free Pixabay key for photos on most cards. Pexels has "
                           "paused new keys, but a Pexels key you already have still works.")
        img_intro.setWordWrap(True)
        img_intro.setStyleSheet("font-size: 11px;")
        form.addRow("", img_intro)
        self.pexels_edit = QLineEdit(img.get("pexels_key", ""))
        self._apply_key_echo(self.pexels_edit, "paste your Pexels API key")
        form.addRow("Pexels key", self.pexels_edit)
        self.pixabay_edit = QLineEdit(img.get("pixabay_key", ""))
        self._apply_key_echo(self.pixabay_edit, "paste your Pixabay API key (free, at pixabay.com/api/docs)")
        form.addRow("Pixabay key", self.pixabay_edit)
        self.serper_edit = QLineEdit(img.get("serper_key", ""))
        self._apply_key_echo(self.serper_edit, "optional (better IT images)")
        form.addRow("Serper key", self.serper_edit)

        # ── Languages tab ── the language you learn, then ITS voice and translation languages. The voice
        # dropdowns are synced from Microsoft's catalog, filtered per slot.
        form = _new_tab("Languages")
        self.learning_lang = _make_combo()
        for code in languages.codes():
            self.learning_lang.addItem(lang_rules.picker_label(code), code)
        self.learning_lang.setCurrentIndex(max(0, self.learning_lang.findData(self._lang)))
        form.addRow("Language you learn", self.learning_lang)
        learn_hint = QLabel("Each language you learn keeps its own voice and translation languages below. "
                            "The Add window has the same choice, above the deck.")
        learn_hint.setWordWrap(True)
        learn_hint.setStyleSheet("font-size: 11px;")
        form.addRow("", learn_hint)
        lang_values = generate.language_settings(self.cfg, self._lang)
        entry = languages.get(self._lang)
        self.target_voice_label = QLabel("%s voice" % entry["name"])
        form.addRow(self.target_voice_label, self._make_voice_row("target", entry["voice_locales"],
                                                                  lang_values["voice"]))
        # Translation language (shown under the words you learn). A closed list, the learning language's
        # own (prompts.translation_languages): never the language itself. German's defaults to English;
        # another language with nothing to borrow shows "(choose one)" until the learner picks one.
        self.translation_lang = _make_combo()
        prim_lang = self._fill_translation_langs(self._lang, lang_values["translation"])
        form.addRow("Translation language", self.translation_lang)
        # Its voice is filtered to that language's locales (English → English voices).
        form.addRow("Translation voice", self._make_voice_row("translation", audio.secondary_locale_prefixes(prim_lang),
                                                              lang_values["translation_voice"] if prim_lang else "",
                                                              allow_none=True))  # "(none)" (the default) = text, no audio
        # Refilter the translation-voice list live when the language changes.
        qconnect(self.translation_lang.currentIndexChanged, lambda _=None: self._on_translation_lang_changed())
        # Optional SECOND helper language: "(none)" (off) + the same closed list.
        self.secondary = _make_combo()
        sec_lang0 = self._fill_secondary_langs(self._lang, lang_values["secondary"])
        form.addRow("Secondary translation", self.secondary)
        sec_hint = QLabel("Optional second translation on every card. Leave “(none)” to skip it. Its voice stays off until you pick one below.")
        sec_hint.setWordWrap(True)
        sec_hint.setStyleSheet("font-size: 11px;")
        form.addRow("", sec_hint)
        # Voice row is always present (shows “(none)” when off); refilters live with the language.
        form.addRow("Secondary voice", self._make_voice_row("secondary", audio.secondary_locale_prefixes(sec_lang0),
                                                            lang_values["secondary_voice"] if sec_lang0 else "",
                                                            allow_none=True))
        qconnect(self.secondary.currentIndexChanged, lambda _=None: self._on_secondary_lang_changed())
        qconnect(self.learning_lang.currentIndexChanged, lambda _=None: self._on_learning_lang_changed())

        # ── Voice tab ── who reads the cards aloud: free Edge, or a service with the user's own key,
        # plus the order of the backups.
        self._build_voice_tab(_new_tab("Voice"))

        # ── Cards tab ── the CEFR level new cards use unless changed per card in the Add dialog.
        form = _new_tab("Cards")
        self.level_combo = _make_combo()
        for code in prompts.LEVELS:
            self.level_combo.addItem(prompts.level_label(code, self._lang), code)
        cur_level = defaults.get("level") or prompts.DEFAULT_LEVEL
        li = self.level_combo.findData(cur_level if cur_level in prompts.LEVELS else prompts.DEFAULT_LEVEL)
        if li >= 0:
            self.level_combo.setCurrentIndex(li)
        form.addRow("Default level", self.level_combo)
        self.level_hint = QLabel()
        self.level_hint.setWordWrap(True)
        self.level_hint.setStyleSheet("font-size: 11px;")
        form.addRow("", self.level_hint)

        # "Your style": wishes for every card in every language (topics, names, tone, length), sent with the
        # card while "Use my style" is ticked in the Tarkib window (prompts.style_main, style_cloze).
        self.style_edit = QPlainTextEdit()
        self.style_edit.setPlaceholderText("e.g. Examples about cooking, football and travel. Short sentences. "
                                           "A friendly tone.")
        self.style_edit.setPlainText(str(defaults.get("card_style") or ""))
        self.style_edit.setTabChangesFocus(True)
        self.style_edit.setFixedHeight(72)
        # Fixed, not the text box's default Expanding: an expanding row made the form spread every row of the Cards
        # tab apart in a tall Settings window.
        self.style_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        form.addRow("Your style", self.style_edit)
        self.style_hint = QLabel(
            "Optional, in any language: the topics, names, tone or length you want in your cards, up to %d "
            "characters. Tarkib sends these wishes with every card, in every language you learn, while “Use my "
            "style” is ticked in the Tarkib window. The level and the card’s rules stay as they are."
            % prompts.STYLE_MAX)
        self.style_hint.setWordWrap(True)
        self.style_hint.setStyleSheet("font-size: 11px;")
        form.addRow("", self.style_hint)

        # The German extras: the starter decks (German deck names and themes) and the line about the
        # ready-made decks, which teach German. One box, shown while the Languages tab is on German.
        self.german_extras = QWidget()
        extras = QVBoxLayout(self.german_extras)
        extras.setContentsMargins(0, 0, 0, 0)
        form.addRow(self.german_extras)

        # ── Starter decks (optional) ── collapsible checkbox list. Nothing touches the collection
        # until the user expands it, picks decks, and clicks Create. prompts.STARTER_DECKS is the
        # single source of truth for the names + flavor descriptions (shared with prompts.deck_context_de).
        self._starter_checks = []
        self.starter_toggle = QToolButton()
        self.starter_toggle.setText("Starter decks (optional)")
        self.starter_toggle.setCheckable(True)
        self.starter_toggle.setChecked(False)
        self.starter_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.starter_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.starter_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.starter_toggle.setStyleSheet("QToolButton { border: none; font-weight: 700; margin-top: 10px; }")
        qconnect(self.starter_toggle.toggled, self._toggle_starter)
        extras.addWidget(self.starter_toggle)

        self.starter_box = QWidget()
        sb = QVBoxLayout(self.starter_box)
        sb.setContentsMargins(18, 2, 0, 0)
        hint = QLabel("Pick the decks you want, then create them. Existing decks are skipped.")
        hint.setWordWrap(True)
        sb.addWidget(hint)
        for d in prompts.STARTER_DECKS:
            cb = QCheckBox(d["name"])
            cb.setChecked(bool(d.get("default_checked", True)))
            sb.addWidget(cb)
            # Description on its OWN full-width line below the name (wraps cleanly like the hints),
            # indented to sit under the checkbox label.
            desc = QLabel(d.get("description", ""))
            desc.setWordWrap(True)
            desc.setStyleSheet("font-size: 11px; margin-left: 22px; margin-bottom: 6px;")
            sb.addWidget(desc)
            self._starter_checks.append((cb, d["name"]))
        create_row = QHBoxLayout()
        create_row.addStretch()
        self.starter_create = QPushButton("Create selected decks")
        qconnect(self.starter_create.clicked, self._create_starter_decks)
        create_row.addWidget(self.starter_create)
        sb.addLayout(create_row)
        self.starter_box.setVisible(False)
        extras.addWidget(self.starter_box)

        # One line about the ready-made decks, at the very bottom of the last tab. Hidden entirely
        # until support.DECKS_URL is set, so nothing dead ever ships.
        decks = decks_link(self)
        if decks is not None:
            extras.addWidget(decks)
        self._show_cards_language(self._lang)

        layout.addWidget(tabs, 1)

        row = QHBoxLayout()
        row.addWidget(support_link(self))
        row.addSpacing(12)
        self.test_btn = QPushButton("Test keys")
        self.test_btn.setToolTip("Check the AI key works, and Pexels/Pixabay/Serper too if they're set")
        qconnect(self.test_btn.clicked, lambda: self._test_key())
        row.addWidget(self.test_btn)
        row.addStretch()
        cancel = QPushButton("Cancel")
        qconnect(cancel.clicked, self.reject)
        row.addWidget(cancel)
        self.save_btn = QPushButton("Save")
        self.save_btn.setDefault(True)
        qconnect(self.save_btn.clicked, self._save)
        row.addWidget(self.save_btn)
        layout.addLayout(row)

        self._init_model_list()
        self._init_voice_lists()
        # Reflect the stored provider in the Preset dropdown WITHOUT clobbering its loaded values:
        # match by (type, base_url); unknown endpoints land on "Custom…" with the fields revealed.
        detected = self._detect_preset(self.prov)
        self.preset.blockSignals(True)
        self.preset.setCurrentText(detected)
        self.preset.blockSignals(False)
        self._update_key_help(detected)   # signals were blocked, so set the key hint by hand
        self._set_advanced_visible(detected == CUSTOM_PRESET)
        self.resize(600, 560)   # each tab is short; tabs scroll on their own if a screen is tiny
        # Optional deep-link: open straight to a named tab (e.g. "Cards" from the Add dialog).
        if initial_tab:
            for i in range(tabs.count()):
                if tabs.tabText(i) == initial_tab:
                    tabs.setCurrentIndex(i)
                    break

    # ── key field echo: empty → show placeholder (visibly unset); filled → mask ──
    def _apply_key_echo(self, edit, placeholder):
        edit.setPlaceholderText(placeholder)
        # Always masked: Qt draws placeholderText unmasked even in Password mode, so the empty
        # first-run field still shows its hint, and a freshly pasted key is never on screen in clear.
        edit.setEchoMode(QLineEdit.EchoMode.Password)

    # ── model dropdown ──
    def _init_model_list(self):
        """Populate the dropdown without blocking: curated for Anthropic, cache for the rest,
        falling back to the stored model. If the cache is cold but a key is already saved, fetch
        in the background so the dropdown fills on open (mirrors the voice dropdowns)."""
        ptype = self.type_combo.currentText()
        stored = (self.prov.get("model") or "").strip()
        cached = None
        if ptype == "anthropic":
            self._models = providers.list_models({"type": "anthropic"})
        else:
            cached = _cached_models({"type": ptype, "base_url": self.base_edit.text().strip()},
                                    respect_ttl=False)
            self._models = cached if cached else ([stored] if stored else [])
        self._populate_models(self._models, stored)
        # Quiet live auto-load on open when a key is already saved: Anthropic (curated shown first,
        # then live GET /v1/models); OpenAI-compatible only when the 7-day cache is cold.
        has_key = bool((self.prov.get("api_key") or "").strip())
        if ptype == "anthropic":
            if has_key:
                self._refresh_models(announce=False)
        elif not cached and has_key and self.base_edit.text().strip():
            self._refresh_models(announce=False)

    def _populate_models(self, models, select):
        self._models = list(models)
        combo = self.model_combo
        combo.blockSignals(True)
        combo.clear()
        combo.addItems(self._models)
        combo.addItem(CUSTOM_LABEL)
        select = (select or "").strip()
        if select and select in self._models:
            combo.setCurrentText(select)
            self.model_custom.clear()
            self.model_custom.hide()
        elif select:
            combo.setCurrentText(CUSTOM_LABEL)
            self.model_custom.setText(select)
            self.model_custom.show()
        else:
            combo.setCurrentIndex(0)
            self.model_custom.setVisible(combo.currentText() == CUSTOM_LABEL)
        combo.blockSignals(False)

    def _on_model_changed(self, text):
        self.model_custom.setVisible(text == CUSTOM_LABEL)

    def _selected_model_value(self):
        if self.model_combo.currentText() == CUSTOM_LABEL:
            return self.model_custom.text().strip()
        cur = self.model_combo.currentText().strip()
        # While a fetch is in flight the combo shows the Loading… sentinel; fall back to the
        # selection captured before loading so nothing (Save/Test) ever sees an empty model.
        return self._prev_model if cur == LOADING_LABEL else cur

    def _begin_busy(self):
        """A fetch started. Lock Save/Test (counted) so a click mid-load can't persist a
        half-loaded value. Survives concurrent model + voice fetches."""
        self._loading += 1
        self.save_btn.setEnabled(False)
        self.test_btn.setEnabled(False)

    def _end_busy(self):
        self._loading = max(0, self._loading - 1)
        if self._loading == 0:
            self.save_btn.setEnabled(True)
            self.test_btn.setEnabled(True)

    def _toast(self, msg, period=3000):
        """Show a tooltip anchored to THIS dialog. The Settings dialog is modal (opened via
        .exec()), so a default self._toast() anchors to the main window and renders BEHIND the modal
        where the user never sees it. Parenting to self makes confirmations (Test keys, Refresh,
        etc.) actually visible."""
        tooltip(msg, period=period, parent=self)

    def _set_models_loading(self):
        combo = self.model_combo
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(LOADING_LABEL)
        combo.blockSignals(False)
        combo.setEnabled(False)
        self.model_refresh.setEnabled(False)
        self._begin_busy()

    def _unlock_after_models(self):
        self.model_combo.setEnabled(True)
        self.model_refresh.setEnabled(True)
        self._end_busy()

    def _key_belongs_here(self, prov):
        """True when the key in the field was entered/verified for THIS endpoint. After a preset
        switch the field still holds the PREVIOUS provider's key, so auto-fetching would send that
        secret to the wrong host and then toast 'your key is wrong' about a perfectly valid key."""
        return bool(prov.get("api_key")) and self._key_endpoint == _provider_cache_id(prov)

    def _on_provider_changed(self, default_model=None):
        """Provider/preset switched: re-seed the dropdown from the right source, NEVER blocking the
        UI and never sending a key to an endpoint it wasn't entered for. Anthropic shows the curated
        list instantly; a live fetch (any provider) only runs in the background QueryOp, and only
        when the key belongs to this endpoint (see _key_belongs_here)."""
        prov = self._current_provider()
        select = default_model or self._selected_model_value() or (self.prov.get("model") or "")
        if (prov.get("type") or "").lower() == "anthropic":
            self._populate_models(list(providers.CURATED_ANTHROPIC_MODELS), select)   # instant, no network
            if self._key_belongs_here(prov):
                self._refresh_models(announce=False)                                   # background, quiet
            return
        cached = _cached_models(prov, respect_ttl=False)
        if cached:
            self._populate_models(cached, select)
        else:
            self._populate_models([select] if select else [], select)
            if self._key_belongs_here(prov) and prov.get("base_url"):
                self._refresh_models()

    def _on_key_edited(self):
        """Key field lost focus. If its value actually changed, auto-sync the model list so the
        user gets live models just by pasting a key (no need to click Refresh). Deferred one event-
        loop turn so a Save/Test click that caused the focus-out still lands before the buttons are
        disabled by the fetch (on Windows/Linux the focus-out fires on mouse press)."""
        key = self.key_edit.text().strip()
        if not key or key == self._model_fetch_key:
            return
        self._model_fetch_key = key
        self._key_endpoint = _provider_cache_id(self._current_provider())   # typed for THIS endpoint
        QTimer.singleShot(0, lambda: self._refresh_models(announce=True))

    def _refresh_models(self, provider_getter=None, announce=True):
        """On-demand re-fetch, always live when a key is present. Non-blocking (no progress modal);
        the dropdown shows Loading…. announce=False fully silences toasts (quiet auto-load on open).
        Anthropic now fetches live too (GET /v1/models), so it runs in the background like the rest;
        with no key it falls back to the instant curated list."""
        prov = (provider_getter or self._current_provider)()
        ptype = (prov.get("type") or "").lower()
        if not prov.get("api_key"):
            if ptype == "anthropic":               # curated list is instant, no network
                self._populate_models(providers.list_models(prov), self._selected_model_value())
            elif announce:
                self._toast("Enter an API key first.")
            return
        if ptype != "anthropic" and not prov.get("base_url"):
            if announce:
                self._toast("Enter a Base URL first.")
            return
        prev_select = self._selected_model_value()
        self._prev_model = prev_select
        self._set_models_loading()

        ua = self._ua()

        def op(col):
            return providers.list_models(prov, timeout=15, user_agent=ua)

        def ok(models):
            self._unlock_after_models()
            self._model_fetch_key = prov.get("api_key") or ""  # record the key this list came from
            self._key_endpoint = _provider_cache_id(prov)
            if not models:
                self._populate_models(self._models, prev_select)
                if announce:
                    self._toast("No models returned, keeping current.")
                return
            _store_models_cache(prov, models)
            self._populate_models(models, prev_select)
            if announce:
                self._toast("✓ %d models loaded." % len(models))

        def fail(e):
            self._unlock_after_models()
            self._populate_models(self._models, prev_select)  # keep current selection
            if announce:
                self._models_error(e)

        QueryOp(parent=self, op=op, success=ok).without_collection() \
            .failure(fail).run_in_background()

    def _models_error(self, e):
        if isinstance(e, urllib.error.HTTPError) and e.code == 401:
            self._toast("Authentication failed (HTTP 401). Your API key is wrong or revoked.")
        elif isinstance(e, urllib.error.HTTPError) and e.code == 403:
            self._toast("Forbidden (HTTP 403). Wrong key, or the provider blocked the request.")
        else:
            self._toast("Couldn't fetch model list, keeping current.")

    # ── voice dropdowns ──
    def _make_voice_row(self, slot, locales, stored, allow_none=False):
        combo = _make_combo()
        refresh = QPushButton("↻")
        refresh.setFixedWidth(36)
        refresh.setToolTip("Fetch the latest voices from Microsoft")
        qconnect(refresh.clicked, lambda: self._refresh_voices())
        preview = QPushButton("▶")
        preview.setFixedWidth(36)
        preview.setToolTip("Play a short sample sentence in the selected voice")
        qconnect(preview.clicked, lambda: self._preview_voice(slot))
        self._voice_slots[slot] = {"combo": combo, "refresh": refresh, "preview": preview,
                                   "locales": list(locales or []),
                                   "stored": (stored or "").strip(), "allow_none": allow_none}
        rowl = QHBoxLayout()
        rowl.addWidget(combo, 1)
        rowl.addWidget(preview, 0)
        rowl.addWidget(refresh, 0)
        return rowl

    def _preview_voice(self, slot):
        """Synthesize a sample sentence (language picked from the voice's locale) off the UI thread,
        then play it with Anki's own player. Nothing is stored; the temp mp3 is overwritten per slot."""
        info = self._voice_slots.get(slot)
        voice = (self._voice_selected(slot) or "").strip() if info else ""
        if not voice:
            self._toast("Pick a voice first.")
            return
        text = audio.sample_text_for_voice(voice)
        btn = info["preview"]
        btn.setEnabled(False)
        btn.setText("…")
        tts_to = int((self.cfg.get("timeouts", {}) or {}).get("tts_seconds", 30))
        # These are Edge voice names. Azure has the same voices, so it previews them when it is the
        # chosen service and set up; every other service has voices of its own (its Test button).
        values = self._tts_values() if getattr(self, "tts_service", None) is not None else {}
        service = "azure" if (values.get("service") == "azure" and tts.configured("azure", values)) else "edge"
        folder = os.path.dirname(_models_cache_path())

        def op(col):
            clip = tts.synthesize(service, text, voice, values, timeout=tts_to)
            path = os.path.join(folder, "voice_preview_%s.%s" % (slot, clip.ext))
            with open(path, "wb") as f:
                f.write(clip.data)
            return path

        def done():
            btn.setEnabled(True)
            btn.setText("▶")

        def ok(p):
            done()
            av_player.play_file(p)

        def fail(e):
            done()
            self._toast("Couldn't play a sample: %s" % _tts_reason(e), period=6000)

        QueryOp(parent=self, op=op, success=ok).without_collection().failure(fail).run_in_background()

    def _init_voice_lists(self):
        """Populate every voice dropdown from cache. If the cache is cold, fetch in the
        background — the voice endpoint needs no API key, so it's always safe and non-blocking."""
        self._voices = _read_voices_cache(respect_ttl=False) or []
        for slot in self._voice_slots:
            self._voice_populate(slot)
        if not self._voices and self._voice_slots:
            self._refresh_voices(announce=False)  # quiet auto-load on open

    def _voice_populate(self, slot, prefer=None):
        info = self._voice_slots[slot]
        combo = info["combo"]
        # _voice_selected already falls back to the stored voice when nothing is selected. An explicit
        # "(none)" ("") must not fall back to it, or a catalog refresh (↻, or the auto-fetch on the
        # first Save) would switch the voice the user turned off back on.
        want = (prefer or self._voice_selected(slot) or "").strip()
        # No locales = no language chosen (secondary set to "(none)"): offer nothing but "(none)"
        # and grey the row out. filter_voices([]) would otherwise return the WHOLE catalog.
        active = bool(info["locales"])
        voices = audio.filter_voices(self._voices, info["locales"]) if (self._voices and active) else []
        if not active:
            want = ""
        for w in (combo, info["refresh"], info["preview"]):
            w.setEnabled(active)
        combo.blockSignals(True)
        combo.clear()
        if info["allow_none"]:
            combo.addItem(NONE_LABEL, "")
        present = False
        for v in voices:
            sn = (v.get("ShortName") or "").strip()
            if not sn:
                continue
            combo.addItem(audio.voice_label(v), sn)
            if sn == want:
                present = True
        if want and not present:
            combo.insertItem(0, want, want)  # keep a stored/unknown voice that the filter excluded
        idx = combo.findData(want)
        if not want and info.pop("pick_first", False) and voices:
            # Language just changed on a slot that had a voice (see _refilter_voice): keep the audio
            # on with the new language's first voice. A slot that showed '(none)' never gets here,
            # so a language change never turns audio on by itself.
            idx = 1 if info["allow_none"] else 0
        combo.setCurrentIndex(idx if idx >= 0 else (0 if combo.count() else -1))
        combo.blockSignals(False)

    def _secondary_value(self):
        """Robust read of the secondary language: '' when off ('(none)' / blank), else the language."""
        return (self.secondary.currentData() or "").strip()

    def _translation_value(self):
        """The translation language, '' while a learning language shows '(choose one)'."""
        return (self.translation_lang.currentData() or "").strip()

    # ── the language you learn: each keeps its own voice and translation languages ──
    def _fill_translation_langs(self, lang, value):
        """List the learning language's translation languages and select `value` (any case). German
        falls back to English; another language with nothing usable shows '(choose one)'. Returns the
        language selected, '' for '(choose one)'."""
        names = prompts.translation_languages(lang)
        value = next((n for n in names if n.lower() == (value or "").strip().lower()), "")
        if not value and lang == languages.DEFAULT:
            value = prompts.DEFAULT_TRANSLATION_LANG
        c = self.translation_lang
        c.blockSignals(True)
        c.clear()
        if not value:
            c.addItem(CHOOSE_LABEL, "")
        for n in names:
            c.addItem(n, n)
        c.setCurrentIndex(max(0, c.findData(value)))
        c.blockSignals(False)
        self._last_translation_lang = value      # guard: only refilter voices on a real change
        return value

    def _fill_secondary_langs(self, lang, value):
        """'(none)' and the learning language's translation languages; selects `value`. Returns it, ''
        for '(none)'."""
        names = prompts.translation_languages(lang)
        value = next((n for n in names if n.lower() == (value or "").strip().lower()), "")
        c = self.secondary
        c.blockSignals(True)
        c.clear()
        c.addItem(NONE_LABEL, "")
        for n in names:
            c.addItem(n, n)
        c.setCurrentIndex(max(0, c.findData(value)))
        c.blockSignals(False)
        self._last_secondary_lang = value
        return value

    def _current_lang_values(self):
        """What the Languages tab shows now, for the learning language it is on."""
        return {"voice": self._voice_selected("target"),
                "translation": self._translation_value(),
                "translation_voice": self._voice_selected("translation"),
                "secondary": self._secondary_value(),
                "secondary_voice": self._voice_selected("secondary")}

    def _on_learning_lang_changed(self):
        new = self.learning_lang.currentData() or languages.DEFAULT
        if new == self._lang:
            return
        self._lang_edits[self._lang] = self._current_lang_values()   # kept until Save, or Cancel drops it
        self._lang = new
        self._show_language(new, self._lang_edits.get(new) or generate.language_settings(self.cfg, new))

    def _show_language(self, lang, values):
        """Point the Languages tab (and the language bits of the Cards tab) at one learning language."""
        entry = languages.get(lang)
        self.target_voice_label.setText("%s voice" % entry["name"])
        self._point_voice("target", entry["voice_locales"], values.get("voice") or entry["default_voice"], False)
        tr = self._fill_translation_langs(lang, values.get("translation"))
        self._point_voice("translation", audio.secondary_locale_prefixes(tr),
                          values.get("translation_voice") if tr else "", True)
        sec = self._fill_secondary_langs(lang, values.get("secondary"))
        self._point_voice("secondary", audio.secondary_locale_prefixes(sec),
                          values.get("secondary_voice") if sec else "", True)
        self._show_cards_language(lang)

    def _point_voice(self, slot, locales, voice, allow_none):
        """Load a slot with a saved voice for other locales. Unlike a language change in place
        (_refilter_voice), the voice is exactly the one saved, '' included."""
        info = self._voice_slots[slot]
        info.update(locales=list(locales or []), allow_none=allow_none, stored=(voice or "").strip())
        info.pop("pick_first", None)
        combo = info["combo"]
        combo.blockSignals(True)
        combo.clear()                  # empty: _voice_selected answers the stored voice
        combo.blockSignals(False)
        if self._voices:
            self._voice_populate(slot)
        # else the catalog is still loading: _refresh_voices fills the slot from the stored voice

    def _show_cards_language(self, lang):
        """The level names, the Native hint and the German extras follow the language you learn."""
        for i in range(self.level_combo.count()):
            self.level_combo.setItemText(i, prompts.level_label(self.level_combo.itemData(i), lang))
        self.level_hint.setText("New cards use this level. You can still change it per card. “Native” = real "
                                "spoken %s, the way native speakers talk." % languages.get(lang)["name"])
        self.german_extras.setVisible(lang == DECKS_LANGUAGE)

    def _refilter_voice(self, slot, lang):
        """Repoint a voice slot to a language's locales and repopulate live (cached catalog; fetches
        only if cold). An empty value means 'no language' (secondary '(none)', translation '(choose
        one)' → only '(none)', greyed out).
        A language change never turns audio on by itself: a slot showing '(none)' while it has a
        language keeps it."""
        info = self._voice_slots.get(slot)
        if not info:
            return
        # Decide before repointing. A slot that had a voice gets the new language's first voice (the
        # user wants audio). A slot showing '(none)' stays '(none)': the translation and the second
        # language are both silent until the user picks a voice, including when the second language
        # is first switched on (product rule: learners want the German read aloud, not their own
        # language). Index -1 = an earlier change is still waiting for the catalog: keep
        # the decision it made.
        if info["combo"].currentIndex() >= 0:
            info["pick_first"] = bool(self._voice_selected(slot))
        lang = (lang or "").strip()
        # English → en-US and en-GB voices; "" (no language) → no locales, only "(none)"
        info["locales"], info["allow_none"] = list(audio.secondary_locale_prefixes(lang) if lang else []), True
        info["stored"] = ""                     # don't carry the previous language's voice as the pick
        info["combo"].setCurrentIndex(-1)
        if getattr(self, "_voices", None):
            self._voice_populate(slot)
        else:
            self._refresh_voices(announce=False)

    def _on_translation_lang_changed(self):
        lang = self._translation_value()
        if lang == getattr(self, "_last_translation_lang", None):
            return  # no real change (e.g. focus left the box) → keep the user's voice selection
        self._last_translation_lang = lang
        self._refilter_voice("translation", lang)

    def _on_secondary_lang_changed(self):
        lang = self._secondary_value()
        if lang == getattr(self, "_last_secondary_lang", None):
            return
        self._last_secondary_lang = lang
        self._refilter_voice("secondary", lang)

    def _voice_selected(self, slot):
        info = self._voice_slots.get(slot)
        if not info:
            return ""
        data = info["combo"].currentData()
        if data is None:                 # combo empty → fall back to the stored value
            return info["stored"]
        return (data or "").strip()      # "" = the explicit "none" choice

    def _set_voices_loading(self):
        for info in self._voice_slots.values():
            info["combo"].setEnabled(False)
            info["refresh"].setEnabled(False)
        self._begin_busy()

    def _unlock_after_voices(self):
        for info in self._voice_slots.values():
            info["combo"].setEnabled(True)
            info["refresh"].setEnabled(True)
        self._end_busy()

    def _refresh_voices(self, announce=True):
        """Re-fetch the whole catalog (one GET) and repopulate every slot. Non-blocking.
        announce=False suppresses the success toast (used for the quiet auto-load on open)."""
        self._set_voices_loading()

        def op(col):
            return audio.list_voices(timeout=20)

        def ok(catalog):
            self._unlock_after_voices()
            if not catalog:
                if announce:
                    self._toast("No voices returned, keeping current.")
                return
            self._voices = catalog
            _store_voices_cache(catalog)
            # Each slot's pick as it is NOW: a language changed while the list loaded (the learning
            # language, a translation language) already repointed its slot, and a pick taken before
            # the fetch would put the previous language's voice back.
            prefer = {slot: self._voice_selected(slot) for slot in self._voice_slots}
            for slot in self._voice_slots:
                self._voice_populate(slot, prefer.get(slot))
            if announce:
                self._toast("✓ %d voices loaded." % len(catalog))

        def fail(e):
            self._unlock_after_voices()
            if announce:
                self._toast("Couldn't fetch voice list, keeping current.")

        QueryOp(parent=self, op=op, success=ok).without_collection() \
            .failure(fail).run_in_background()

    # ── voice service (Voice tab) ──
    def _build_voice_tab(self, form):
        """Voice tab: the service that reads the cards, one collapsible section per paid service
        (key, voice, model, its own Test), and the backup order. tts.chain() turns these values into
        the order a clip tries the services in: the chosen one, the backups that are set up, Edge."""
        tts_cfg = self.cfg.get("tts") or {}
        self._tts = {}               # service -> {"toggle", "box", "fields", "test", "refresh"}
        intro = QLabel("Who reads your cards aloud. Microsoft Edge is free. The other services are "
                       "official and use your own key. If the service you pick fails, Tarkib tries your "
                       "backups, then Microsoft Edge, and tells you which one read the card.")
        intro.setWordWrap(True)
        intro.setStyleSheet("font-size: 11px;")
        form.addRow("", intro)

        self.tts_service = _make_combo()
        for s in tts.SERVICES:
            self.tts_service.addItem(TTS_ITEMS[s], s)
        i = self.tts_service.findData(tts.chosen(tts_cfg))
        self.tts_service.setCurrentIndex(i if i >= 0 else 0)
        self.tts_test = QPushButton("▶ Test")
        self.tts_test.setToolTip("Read a short sample in the language you learn, with this service and the "
                                 "settings on this tab")
        qconnect(self.tts_test.clicked, lambda: self._test_tts(self._tts_selected(), self.tts_test))
        row = QHBoxLayout()
        row.addWidget(self.tts_service, 1)
        row.addWidget(self.tts_test, 0)
        form.addRow("Voice service", row)
        self.tts_help = QLabel()
        self.tts_help.setWordWrap(True)
        self.tts_help.setOpenExternalLinks(True)
        self.tts_help.setTextFormat(Qt.TextFormat.RichText)
        self.tts_help.setStyleSheet("font-size: 11px;")
        form.addRow("", self.tts_help)

        self.tts_speed = _make_combo()
        for value, label in SPEED_ITEMS:
            self.tts_speed.addItem(label, value)
        i = self.tts_speed.findData(tts.speed(tts_cfg))
        self.tts_speed.setCurrentIndex(i if i >= 0 else 0)
        self.tts_speed.setToolTip("How fast the language you learn is read aloud")
        form.addRow("Speech speed", self.tts_speed)
        speed_hint = QLabel("Slower means about 20% slower, for the language you learn: the word, its sentences "
                            "and the cloze card. The translations keep the normal speed. It changes new cards "
                            "only. Gemini always reads at the normal speed. ▶ Test plays the slower speed when "
                            "one is picked.")
        speed_hint.setWordWrap(True)
        speed_hint.setStyleSheet("font-size: 11px;")
        form.addRow("", speed_hint)

        for s in tts.DEFAULT_ORDER:
            self._add_tts_section(form, s, tts.service_cfg(tts_cfg, s))

        self.tts_order = QListWidget()
        self.tts_order.setFixedHeight(5 * self.tts_order.fontMetrics().height() + 14)   # the five services
        for s in tts.backup_order(tts_cfg):
            item = QListWidgetItem(TTS_ITEMS[s])
            item.setData(Qt.ItemDataRole.UserRole, s)
            self.tts_order.addItem(item)
        self.tts_order.setCurrentRow(0)
        up, down = QPushButton("▲"), QPushButton("▼")
        for b, step, tip in ((up, -1, "Try this backup earlier"), (down, 1, "Try this backup later")):
            b.setFixedWidth(36)
            b.setToolTip(tip)
            qconnect(b.clicked, lambda _=False, step=step: self._move_tts_backup(step))
        buttons = QVBoxLayout()
        buttons.setAlignment(Qt.AlignmentFlag.AlignTop)
        buttons.addWidget(up)
        buttons.addWidget(down)
        order_row = QHBoxLayout()
        order_row.addWidget(self.tts_order, 1, Qt.AlignmentFlag.AlignTop)
        order_row.addLayout(buttons)
        form.addRow("Backup order", order_row)
        order_hint = QLabel("If your voice service fails, Tarkib tries the services in this list that are "
                            "set up, top to bottom, then Microsoft Edge.")
        order_hint.setWordWrap(True)
        order_hint.setStyleSheet("font-size: 11px;")
        form.addRow("", order_hint)
        privacy = QLabel("🔒 Voice keys are stored like your other keys, in Anki's add-on config on this "
                         "computer (meta.json in this add-on's folder). Anki never syncs them, and each key "
                         "goes only to its own service. The text read aloud (the words you learn, and a "
                         "translation when its voice is on) goes to the service that reads it.")
        privacy.setWordWrap(True)
        privacy.setStyleSheet("font-size: 11px;")
        form.addRow("", privacy)
        # Spare height in a tall window collects here, under the last row, instead of between rows.
        filler = QWidget()
        filler.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        form.addRow(filler)

        qconnect(self.tts_service.currentIndexChanged, lambda _=None: self._on_tts_service_changed())
        self._on_tts_service_changed()

    def _add_tts_section(self, form, service, sc):
        toggle = QToolButton()
        toggle.setCheckable(True)
        toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        toggle.setArrowType(Qt.ArrowType.RightArrow)
        toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        # Bold through the font, not the style sheet: Qt sizes the button from its font, so a style
        # sheet weight made the longer titles come out cut in the middle.
        bold = toggle.font()
        bold.setBold(True)
        toggle.setFont(bold)
        toggle.setStyleSheet("QToolButton { border: none; margin-top: 6px; }")
        form.addRow(toggle)
        box = QWidget()
        f = QFormLayout(box)
        f.setContentsMargins(18, 0, 0, 6)
        f.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        f.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        fields, refresh = {}, None
        key = QLineEdit(sc.get("key", ""))
        self._apply_key_echo(key, TTS_KEY_HINTS[service])
        qconnect(key.textChanged, lambda _=None: self._refresh_tts_status())
        f.addRow("API key", key)
        fields["key"] = key

        def combo_row(name, label, items, value, value_label="", tip="", with_refresh=False):
            c = _make_combo(editable=True)
            _fill_combo(c, items, value, value_label)
            if tip:
                c.setToolTip(tip)
            qconnect(c.currentTextChanged, lambda _=None: self._refresh_tts_status())
            fields[name] = c
            if not with_refresh:
                f.addRow(label, c)
                return None
            r = QPushButton("↻")
            r.setFixedWidth(36)
            qconnect(r.clicked, lambda: self._load_tts_voices(service))
            line = QHBoxLayout()
            line.addWidget(c, 1)
            line.addWidget(r, 0)
            f.addRow(label, line)
            return r

        if service == "azure":
            combo_row("region", "Region", tts.AZURE_REGIONS, sc.get("region"),
                      tip="The region of your Speech resource, as the Azure portal shows it under Keys and "
                          "Endpoint (for example westeurope). The key works only there.")
        elif service == "elevenlabs":
            refresh = combo_row("voice", "Voice", [], sc.get("voice"), sc.get("voice_name"),
                                tip="Press ↻ to list the voices of your account, or paste a voice ID.",
                                with_refresh=True)
            refresh.setToolTip("List the voices of your ElevenLabs account")
            combo_row("model", "Model", tts.ELEVENLABS_MODELS, sc.get("model"),
                      tip="eleven_multilingual_v2 is the safe default. eleven_flash_v2_5 costs half as "
                          "much. Press Test after a change.")
        elif service == "openai":
            combo_row("voice", "Voice", tts.OPENAI_VOICES, sc.get("voice"))
            combo_row("model", "Model", tts.OPENAI_MODELS, sc.get("model"),
                      tip="gpt-4o-mini-tts sounds best and knows every voice. tts-1 and tts-1-hd know nine.")
        elif service == "google":
            refresh = combo_row("voice", "Voice", tts.GOOGLE_GERMAN_VOICES, sc.get("voice"),
                                tip="The voice that reads the language you learn. Press ↻ to list Google's "
                                    "voices for it, or type a voice name.",
                                with_refresh=True)
            refresh.setToolTip("List Google's voices for the language you learn")
        elif service == "gemini":
            combo_row("voice", "Voice", tts.GEMINI_VOICES, sc.get("voice"))
            combo_row("model", "Model", tts.GEMINI_MODELS, sc.get("model"),
                      tip="gemini-3.8-flash-lite-tts is fast and cheap, gemini-3.8-flash-tts sounds richer.")
        help_label = QLabel(TTS_HELP[service])
        help_label.setWordWrap(True)
        help_label.setOpenExternalLinks(True)
        help_label.setTextFormat(Qt.TextFormat.RichText)
        help_label.setStyleSheet("font-size: 11px;")
        f.addRow("", help_label)
        test = QPushButton("▶ Test %s" % tts.LABELS[service])
        test.setToolTip("Read a short sample in the language you learn with %s and the settings above"
                        % tts.LABELS[service])
        qconnect(test.clicked, lambda: self._test_tts(service, test))
        test_row = QHBoxLayout()
        test_row.addStretch()
        test_row.addWidget(test)
        f.addRow("", test_row)
        box.setVisible(False)
        form.addRow(box)
        qconnect(toggle.toggled, lambda on: self._toggle_tts_section(service, on))
        self._tts[service] = {"toggle": toggle, "box": box, "fields": fields, "test": test, "refresh": refresh}

    def _toggle_tts_section(self, service, expanded):
        info = self._tts[service]
        info["box"].setVisible(expanded)
        info["toggle"].setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)

    def _tts_selected(self):
        return self.tts_service.currentData() or "edge"

    def _on_tts_service_changed(self):
        service = self._tts_selected()
        if service == "edge":
            text = TTS_HELP["edge"]
        else:
            text = "Set up %s below, then press Test." % tts.LABELS[service]
            self._tts[service]["toggle"].setChecked(True)    # open its section; never close one
        self.tts_help.setText(text + " Microsoft Edge and Azure read with the voices on the Languages tab. "
                              "Those voices also decide which languages are read aloud, whichever "
                              "service you pick.")
        self._refresh_tts_status()

    def _refresh_tts_status(self):
        """Section titles and backup rows say which services are set up, so the order list shows
        what will really be tried."""
        if getattr(self, "tts_order", None) is None:
            return                     # still building the tab
        values = self._tts_values()
        for service, info in self._tts.items():
            state = "set up" if tts.configured(service, values) else "not set up"
            info["toggle"].setText("%s: %s" % (tts.LABELS[service], state))
        for i in range(self.tts_order.count()):
            item = self.tts_order.item(i)
            service = item.data(Qt.ItemDataRole.UserRole)
            ok = tts.configured(service, values)
            item.setText("%s%s" % (TTS_ITEMS[service], "" if ok else " (not set up, skipped)"))

    def _move_tts_backup(self, step):
        row = self.tts_order.currentRow()
        new = row + step
        if row < 0 or not (0 <= new < self.tts_order.count()):
            return
        item = self.tts_order.takeItem(row)
        self.tts_order.insertItem(new, item)
        self.tts_order.setCurrentRow(new)

    def _tts_values(self):
        """The Voice tab as a config["tts"] dict (pipeline/tts.py reads exactly this shape)."""
        out = {"service": self._tts_selected(),
               "order": [self.tts_order.item(i).data(Qt.ItemDataRole.UserRole)
                         for i in range(self.tts_order.count())]
               if getattr(self, "tts_order", None) is not None else list(tts.DEFAULT_ORDER),
               "speed": (self.tts_speed.currentData() or "normal")
               if getattr(self, "tts_speed", None) is not None else "normal"}
        for service, info in self._tts.items():
            d = {}
            for name, w in info["fields"].items():
                d[name] = w.text().strip() if isinstance(w, QLineEdit) else _combo_value(w)
            d["key"] = "".join((d.get("key") or "").split())     # keys never contain spaces or line breaks
            if service == "azure":
                d["region"] = tts.azure_region(d.get("region"))
            if service == "elevenlabs":
                shown = info["fields"]["voice"].currentText().strip()
                d["voice_name"] = shown if shown != d.get("voice") else ""   # the name, for display only
            out[service] = d
        return out

    def _test_tts(self, service, btn):
        """Read a sample in the language you learn (the one on the Languages tab) with ONE service (no
        backups) and the values on this tab, saved or not, and play it with Anki's player, at the slower
        speed when one is picked. A failure shows the service's own reason."""
        values = self._tts_values()
        rate = tts.speech_rate(values)
        voice = self._voice_selected("target") or languages.get(self._lang)["default_voice"]
        text = audio.sample_text_for_voice(voice)
        tts_to = int((self.cfg.get("timeouts", {}) or {}).get("tts_seconds", 30))
        folder = os.path.dirname(_models_cache_path())
        label = btn.text()
        btn.setEnabled(False)
        btn.setText("Testing…")

        def op(col):
            clip = tts.synthesize(service, text, voice, values, timeout=tts_to, rate=rate)
            path = os.path.join(folder, "voice_test_%s.%s" % (service, clip.ext))
            with open(path, "wb") as fh:
                fh.write(clip.data)
            return path

        def done():
            btn.setEnabled(True)
            btn.setText(label)

        def ok(path):
            done()
            av_player.play_file(path)
            slower = " at the slower speed" if rate != 1.0 and service != "gemini" else ""
            self._toast("✓ %s works. Playing the sample%s." % (tts.LABELS[service], slower), period=4000)

        def fail(e):
            done()
            showText("%s test failed.\n\n%s" % (tts.LABELS[service], _tts_reason(e)), parent=self, copyBtn=False)

        QueryOp(parent=self, op=op, success=ok).without_collection().failure(fail).run_in_background()

    def _load_tts_voices(self, service):
        """↻ next to a voice: list the voices this key can use (ElevenLabs) or Google's voices for the
        language you learn (the one on the Languages tab)."""
        info = self._tts[service]
        key = self._tts_values()[service].get("key") or ""      # cleaned exactly like Test and Save
        if not key:
            self._toast("Enter the %s API key first." % tts.LABELS[service])
            return
        btn = info["refresh"]
        btn.setEnabled(False)
        locale_lang = self._lang

        def op(col):
            if service == "elevenlabs":
                return tts.elevenlabs_voices(key)
            return tts.google_voices(key, languages.get(locale_lang)["voice_locales"][0])

        def ok(items):
            btn.setEnabled(True)
            combo = info["fields"]["voice"]
            if not items:
                self._toast("No voices found for this key.")
                return
            current = _combo_value(combo)
            first = items[0][1] if isinstance(items[0], (tuple, list)) else items[0]
            _fill_combo(combo, items, current or first)
            self._refresh_tts_status()
            self._toast("✓ %d voices loaded." % len(items))

        def fail(e):
            btn.setEnabled(True)
            showText("Couldn't list the voices.\n\n%s" % _tts_reason(e), parent=self, copyBtn=False)

        QueryOp(parent=self, op=op, success=ok).without_collection().failure(fail).run_in_background()

    # ── provider helpers ──
    def _current_provider(self):
        return {
            "type": self.type_combo.currentText(),
            "name": self.name_edit.text().strip() or "Provider",
            "base_url": self.base_edit.text().strip(),
            "model": self._selected_model_value(),
            "api_key": self.key_edit.text().strip(),
        }

    def _ua(self):
        """Resolved User-Agent for provider HTTP calls (config override or the shared default)."""
        return (self.cfg.get("user_agent") or "").strip() or providers.DEFAULT_USER_AGENT

    def _begin_test_busy(self):
        """Test button doubles as the busy indicator (no progress modal — see _test_key)."""
        self.test_btn.setEnabled(False)
        self.test_btn.setText("Testing…")

    def _end_test_busy(self):
        self.test_btn.setEnabled(True)
        self.test_btn.setText("Test keys")

    def _test_key(self, provider_getter=None):
        prov = (provider_getter or self._current_provider)()
        if not prov["api_key"]:
            self._toast("Enter an API key first.")
            return
        if not self._key_belongs_here(prov) and not askUser(
                "This API key was entered for a different provider.\n\nSend it to %s to test it?"
                % (prov.get("base_url") or prov.get("name") or "this provider"), parent=self):
            return
        if not prov["model"]:
            self._toast("Enter or pick a model first.")
            return

        ua = self._ua()
        pexels = self.pexels_edit.text().strip()
        serper = self.serper_edit.text().strip()
        pixabay = self.pixabay_edit.text().strip()

        def op(col):
            # Test every key that's filled in. AI is required; image keys are all optional.
            results = []
            try:
                status = providers.test_provider(prov, timeout=20, user_agent=ua)
                results.append(("AI provider", True, status))
            except Exception as e:
                results.append(("AI provider", False, _key_err_reason(e)))
            for label, key, tester in (("Pexels", pexels, images.test_pexels),
                                       ("Pixabay", pixabay, images.test_pixabay),
                                       ("Serper", serper, images.test_serper)):
                if not key:
                    continue
                try:
                    tester(key, timeout=15)
                    results.append((label, True, "OK"))
                except Exception as e:
                    results.append((label, False, _key_err_reason(e)))
            return results

        def ok(results):
            self._end_test_busy()
            if all(r[1] for r in results):
                self._toast("✓ All keys OK (%s)" % " · ".join(r[0] for r in results), period=4000)
            else:
                lines = "\n".join("%s  %s: %s" % ("✓" if r[1] else "✗", r[0], r[2]) for r in results)
                showText("Key test results:\n\n" + lines, parent=self, copyBtn=False)

        def fail(e):
            self._end_test_busy()
            showText("Couldn't run the test: %s" % _key_err_reason(e), parent=self, copyBtn=False)

        # No with_progress(): Anki's progress modal is parented to the main window and does NOT
        # compose with this dialog when it is shown modally (.exec()) — the loader can fail to
        # close and the result message renders behind it, so the user sees "spinner, no message".
        # _refresh_models proves the fix: same QueryOp pattern minus the progress modal works. We
        # use the Test button itself as the busy indicator instead.
        self._begin_test_busy()
        QueryOp(parent=self, op=op, success=ok).without_collection() \
            .failure(fail).run_in_background()

    def _toggle_starter(self, expanded):
        self.starter_box.setVisible(expanded)
        self.starter_toggle.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        # No resize here: the scroll area absorbs the extra height, so the dialog never outgrows
        # the screen (this is what used to push "Create selected decks" off small laptops).

    def _create_starter_decks(self):
        checked = [name for (cb, name) in self._starter_checks if cb.isChecked()]
        if not checked:
            self._toast("No decks selected.")
            return
        existing = {d.name for d in mw.col.decks.all_names_and_ids()}
        to_create = [n for n in checked if n not in existing]
        already = len(checked) - len(to_create)
        if not to_create:
            self._toast("All %d selected deck(s) already exist." % already)
            return

        def op(col):
            # One merged undo entry for the whole batch, like anki_io.write_bundle.
            target = col.add_custom_undo_entry("Create starter decks")
            for name in to_create:
                col.decks.id(name, create=True)  # idempotent: only the missing ones
            return col.merge_undo_entries(target)

        def ok(_changes):
            if already:
                self._toast("✓ Created %d deck(s) (%d already existed)." % (len(to_create), already))
            else:
                self._toast("✓ Created %d deck(s)." % len(to_create))

        CollectionOp(parent=self, op=op).success(ok).run_in_background()

    def _detect_preset(self, prov):
        """Which preset matches this stored provider (by type + base_url), or CUSTOM_PRESET."""
        ptype = (prov.get("type") or "").lower()
        base = (prov.get("base_url") or "").strip().rstrip("/").lower()
        for label, (t, b, _m) in PRESETS.items():
            if t == ptype and b.strip().rstrip("/").lower() == base:
                return label
        return CUSTOM_PRESET

    def _set_advanced_visible(self, visible):
        """Show/hide the Name / Type / Base URL rows + their hints. They're only needed for a
        Custom endpoint; a known preset supplies all three, so they stay hidden to keep the
        common path (Preset → Model → API key) tiny."""
        f = self.prov_form
        for w in self._advanced:
            if hasattr(f, "setRowVisible"):
                f.setRowVisible(w, visible)        # Qt ≥6.4: collapses the row cleanly
            else:
                w.setVisible(visible)
                lbl = f.labelForField(w)
                if lbl is not None:
                    lbl.setVisible(visible)

    def _update_key_help(self, label):
        """Refresh the get-a-key hint under the API key field for the selected preset."""
        src = KEY_SOURCES.get(label)
        if not src:
            self.key_help.setText("🔑 Use the API key your provider gave you.")
            return
        host, url, note = src
        if url:
            self.key_help.setText('🔑 No key yet? Get one at <a href="%s">%s</a>. %s' % (url, host, note))
        else:
            self.key_help.setText("🔑 " + note)

    def _apply_preset(self, label):
        self._update_key_help(label)
        if label == CUSTOM_PRESET:
            self._set_advanced_visible(True)       # user edits Name / Type / Base URL by hand
            return
        spec = PRESETS.get(label)
        if not spec:
            return
        ptype, base, model = spec
        self.type_combo.blockSignals(True)
        self.type_combo.setCurrentText(ptype)
        self.type_combo.blockSignals(False)
        self.base_edit.setText(base)
        self.name_edit.setText(label.split(" (")[0])
        self._set_advanced_visible(False)          # preset supplies them — keep them hidden
        self._swap_key_for_endpoint()
        self._on_provider_changed(default_model=model)

    def _swap_key_for_endpoint(self):
        """A key belongs to the provider it was entered for. When the endpoint changes, park the
        current key under its own endpoint and show the key last typed for the new one (usually
        none), so Test, Save and every later card can never send one provider's key to another."""
        new_ep = _provider_cache_id(self._current_provider())
        if new_ep == self._key_endpoint:
            return
        key = self.key_edit.text().strip()
        if key:
            self._keys_by_endpoint[self._key_endpoint] = key
        restored = self._keys_by_endpoint.get(new_ep, "")
        self.key_edit.setText(restored)
        self._model_fetch_key = restored
        self._key_endpoint = new_ep
        if key and not restored:
            self._toast("Paste your API key for this provider.")

    def _warn_invalid_keys(self, prov, check_ai, pexels, serper, pixabay=""):
        """Background, non-blocking: after Save, test the given (changed) keys and show ONE warning
        if any were rejected. Parented to mw so it survives the dialog closing. Never blocks Save."""
        ua = self._ua()
        jobs = []
        if check_ai and (prov.get("api_key") or "").strip():
            jobs.append(("AI key", lambda: providers.test_provider(prov, timeout=20, user_agent=ua)))
        if pexels:
            jobs.append(("Pexels key", lambda: images.test_pexels(pexels, timeout=15)))
        if pixabay:
            jobs.append(("Pixabay key", lambda: images.test_pixabay(pixabay, timeout=15)))
        if serper:
            jobs.append(("Serper key", lambda: images.test_serper(serper, timeout=15)))
        if not jobs:
            return

        def op(col):
            bad = []
            for name, fn in jobs:
                try:
                    fn()
                except Exception as e:
                    bad.append("%s %s" % (name, _key_err_reason(e)))
            return bad

        def ok(bad):
            if bad:
                tooltip("⚠ Saved, but: %s. Fix it in Settings. Everything else still works."
                        % "; ".join(bad), period=8000)

        QueryOp(parent=mw, op=op, success=ok).without_collection() \
            .failure(lambda e: None).run_in_background()

    def _save(self):
        cfg = _cfg()
        prov = {
            "id": (self.name_edit.text().strip().lower().replace(" ", "_") or "provider"),
            "type": self.type_combo.currentText(),
            "name": self.name_edit.text().strip() or "Provider",
            "base_url": self.base_edit.text().strip(),
            "model": self._selected_model_value(),
            "api_key": self.key_edit.text().strip(),
        }
        provs = cfg.get("providers") or []
        if provs:
            provs[0] = prov
        else:
            provs = [prov]
        cfg["providers"] = provs
        cfg.setdefault("image", {})
        cfg["image"]["pexels_key"] = self.pexels_edit.text().strip()
        cfg["image"]["serper_key"] = self.serper_edit.text().strip()
        cfg["image"]["pixabay_key"] = self.pixabay_edit.text().strip()
        # Every learning language shown in this session, the current one with what is on screen now.
        # German goes to the keys of 1.0 ("" translation voice = "(none)" → the translation gets no
        # audio), any other language to languages.<code> (lang_rules.store_language_settings).
        self._lang_edits[self._lang] = self._current_lang_values()
        doubled = []
        for code, values in self._lang_edits.items():
            if "secondary" in lang_rules.store_language_settings(cfg, code, values):
                doubled.append(languages.get(code)["name"])
                values.update(secondary="", secondary_voice="")
                if code == self._lang:
                    self._fill_secondary_langs(code, "")
                    self._point_voice("secondary", [], "", True)
        if doubled:
            # Parented to mw on purpose: _save usually calls accept() right after this, and a toast
            # parented to the dialog would vanish with it (the user never learned why the second
            # language went to "(none)").
            which = " for the %s cards" % " and ".join(doubled) if len(self._lang_edits) > 1 else ""
            tooltip("Secondary language is the same as the main one, so it was set to (none)%s." % which,
                    period=5000, parent=mw)
        cfg["tts"] = self._tts_values()
        cfg.setdefault("defaults", {})
        cfg["defaults"]["learning_language"] = self._lang
        cfg["defaults"]["level"] = self.level_combo.currentData() or prompts.DEFAULT_LEVEL
        cfg["defaults"]["card_style"] = self.style_edit.toPlainText().strip()[:prompts.STYLE_MAX]
        mw.addonManager.writeConfig(__name__, cfg)
        self.cfg = cfg
        self.saved = True

        # Detect which keys changed (so we only re-check what's new).
        pexels = cfg["image"]["pexels_key"]
        serper = cfg["image"]["serper_key"]
        pixabay = cfg["image"]["pixabay_key"]
        ai_changed = prov["api_key"] != self._orig_ai_key
        pexels_changed = pexels != self._orig_pexels
        serper_changed = serper != self._orig_serper
        pixabay_changed = pixabay != self._orig_pixabay
        self._orig_ai_key, self._orig_pexels, self._orig_serper = prov["api_key"], pexels, serper
        self._orig_pixabay = pixabay

        # Auto-fetch on first Save: warm whatever caches are cold (models and/or voices). Keep the
        # dialog open so the populated dropdowns are visible; a second Save (caches warm) closes.
        need_models = (prov["type"] != "anthropic" and prov["api_key"] and prov["base_url"]
                       and self._key_belongs_here(prov) and not _cached_models(prov, respect_ttl=True))
        need_voices = not _read_voices_cache(respect_ttl=True)
        # Non-blocking: warn (never block) if a CHANGED key was rejected. The AI key is implicitly
        # validated by the first-Save model fetch, so only warn-check it here when no fetch runs.
        self._warn_invalid_keys(prov, check_ai=(ai_changed and not need_models),
                                pexels=(pexels if pexels_changed else ""),
                                serper=(serper if serper_changed else ""),
                                pixabay=(pixabay if pixabay_changed else ""))
        if not self._fetched_session and (need_models or need_voices):
            self._fetched_session = True
            self._toast("Saved. Loading models and voices. Pick them, then Save again to finish.")
            if need_models:
                self._refresh_models()
            if need_voices:
                self._refresh_voices()
            return
        self.accept()
