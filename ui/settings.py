"""Settings dialog: BYOK keys, provider, model dropdown, image keys, voices, secondary language.

v1 edits the FIRST provider (the active one — Groq by default) plus the image keys, voices,
and the optional secondary translation language. The Model field is a dropdown synced from the
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
    QTabWidget, Qt, QTimer,
)
from aqt.utils import askUser, qconnect, tooltip, showText
from aqt.sound import av_player
from aqt.operations import QueryOp, CollectionOp

from ..pipeline import providers, prompts, audio, images
from .support import support_link, decks_link

CUSTOM_LABEL = "Custom…"
CUSTOM_PRESET = "Custom…"          # preset entry that reveals Name / Type / Base URL for any other endpoint
LOADING_LABEL = "Loading…"
NONE_LABEL = "(none)"
MODELS_CACHE_TTL = 7 * 24 * 3600       # 7 days
VOICES_CACHE_TTL = 30 * 24 * 3600      # 30 days (voices change rarely)
VOICE_LOCALES = {"de": ["de-DE", "de-AT", "de-CH"], "en": ["en-US", "en-GB"]}

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


def _voice_cfg(voices, key, legacy_key, default):
    """Role-named voice keys (target / translation / secondary). `legacy_key` reads a pre-rename
    config (de / en) so an existing meta.json keeps working; _save writes only the new names."""
    if key in voices:
        return voices[key]
    if legacy_key in voices:
        return voices[legacy_key]
    return default


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
    def __init__(self, parent=None, initial_tab=None):
        super().__init__(parent)
        self.setWindowTitle("Tarkib Settings (v%s)" % _addon_version())
        self.setMinimumWidth(540)
        self.cfg = _cfg()
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
        voices = self.cfg.get("voices", {}) or {}
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
                           "finds nothing, so add a free Pexels key for photos on most cards.")
        img_intro.setWordWrap(True)
        img_intro.setStyleSheet("font-size: 11px;")
        form.addRow("", img_intro)
        self.pexels_edit = QLineEdit(img.get("pexels_key", ""))
        self._apply_key_echo(self.pexels_edit, "paste your Pexels API key")
        form.addRow("Pexels key", self.pexels_edit)
        self.pixabay_edit = QLineEdit(img.get("pixabay_key", ""))
        self._apply_key_echo(self.pixabay_edit, "optional, free with generous limits")
        form.addRow("Pixabay key", self.pixabay_edit)
        self.serper_edit = QLineEdit(img.get("serper_key", ""))
        self._apply_key_echo(self.serper_edit, "optional (better IT images)")
        form.addRow("Serper key", self.serper_edit)

        # ── Languages tab ── synced voice dropdowns from Microsoft's catalog, filtered per slot.
        form = _new_tab("Languages")
        form.addRow("German voice", self._make_voice_row("target", VOICE_LOCALES["de"],
                                                         _voice_cfg(voices, "target", "de", "de-DE-KatjaNeural")))
        # Primary translation language (the helper shown under German). Default English; pick any
        # language (your learners' native language). Editable combo = common list + custom typing.
        prim_lang = (defaults.get("translation_language") or prompts.DEFAULT_TRANSLATION_LANG).strip()
        # A stored value the closed list does not hold would leave the combo on its first item while
        # the config kept the odd value; show what will really be used, and Save then writes it back.
        prim_lang = next((k for k in prompts.COMMON_TRANSLATION_LANGS if k.lower() == prim_lang.lower()), prompts.DEFAULT_TRANSLATION_LANG)
        self.translation_lang = _make_combo()   # closed list: see prompts.COMMON_TRANSLATION_LANGS
        self.translation_lang.addItems(prompts.COMMON_TRANSLATION_LANGS)
        self.translation_lang.setCurrentText(prim_lang)
        self._last_translation_lang = prim_lang  # guard: only refilter voices on a real change
        form.addRow("Translation language", self.translation_lang)
        # Its voice is filtered to that language's locales (English → English voices).
        prim_is_en = prompts.is_english_language(prim_lang)
        prim_locales = VOICE_LOCALES["en"] if prim_is_en else audio.secondary_locale_prefixes(prim_lang)
        form.addRow("Translation voice", self._make_voice_row("translation", prim_locales,
                                                              _voice_cfg(voices, "translation", "en", ""),
                                                              allow_none=True))  # "(none)" (the default) = text, no audio
        # Refilter the translation-voice list live when the language changes (dropdown or typed).
        qconnect(self.translation_lang.currentIndexChanged, lambda _=None: self._on_translation_lang_changed())
        # Optional SECOND helper language. Editable combo: "(none)" (off) + common languages + custom.
        sec_lang0 = (defaults.get("secondary_translation_language") or "").strip()
        self.secondary = _make_combo()          # closed list
        self.secondary.addItem(NONE_LABEL, "")
        self.secondary.addItems(prompts.COMMON_TRANSLATION_LANGS)
        self.secondary.setCurrentText(sec_lang0 or NONE_LABEL)
        self._last_secondary_lang = sec_lang0
        form.addRow("Secondary translation", self.secondary)
        sec_hint = QLabel("Optional second translation on every card. Leave “(none)” to skip it. Its voice stays off until you pick one below.")
        sec_hint.setWordWrap(True)
        sec_hint.setStyleSheet("font-size: 11px;")
        form.addRow("", sec_hint)
        # Voice row is always present (shows “(none)” when off); refilters live with the language.
        sec_locales = audio.secondary_locale_prefixes(sec_lang0) if sec_lang0 else []
        form.addRow("Secondary voice", self._make_voice_row("secondary", sec_locales,
                                                            voices.get("secondary", ""), allow_none=True))
        qconnect(self.secondary.currentIndexChanged, lambda _=None: self._on_secondary_lang_changed())

        # ── Cards tab ── the CEFR level new cards use unless changed per card in the Add dialog.
        form = _new_tab("Cards")
        self.level_combo = _make_combo()
        for code in prompts.LEVELS:
            self.level_combo.addItem(prompts.LEVEL_LABELS.get(code, code), code)
        cur_level = defaults.get("level") or prompts.DEFAULT_LEVEL
        li = self.level_combo.findData(cur_level if cur_level in prompts.LEVELS else prompts.DEFAULT_LEVEL)
        if li >= 0:
            self.level_combo.setCurrentIndex(li)
        form.addRow("Default level", self.level_combo)
        level_hint = QLabel("New cards use this level. You can still change it per card. "
                            "“Native” = the original real-spoken-German style.")
        level_hint.setWordWrap(True)
        level_hint.setStyleSheet("font-size: 11px;")
        form.addRow("", level_hint)

        # ── Starter decks (optional) ── collapsible checkbox list. Nothing touches the collection
        # until the user expands it, picks decks, and clicks Create. prompts.STARTER_DECKS is the
        # single source of truth for the names + flavor descriptions (shared with _pick_context).
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
        form.addRow(self.starter_toggle)

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
        form.addRow(self.starter_box)

        # One line about the ready-made decks, at the very bottom of the last tab. Hidden entirely
        # until support.DECKS_URL is set, so nothing dead ever ships.
        decks = decks_link(self)
        if decks is not None:
            form.addRow(decks)

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
        path = os.path.join(os.path.dirname(_models_cache_path()), "voice_preview_%s.mp3" % slot)

        def op(col):
            data = audio.synthesize(text, voice, timeout=tts_to, retries=1)
            with open(path, "wb") as f:
                f.write(data)
            return path

        def done():
            btn.setEnabled(True)
            btn.setText("▶")

        def ok(p):
            done()
            av_player.play_file(p)

        def fail(e):
            done()
            self._toast("Couldn't play a sample: %s" % audio.classify_tts_error(e)[1])

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
        """Robust read of the secondary language: '' when off ('(none)' / blank), else trimmed text."""
        txt = (self.secondary.currentText() or "").strip()
        return "" if (not txt or txt == NONE_LABEL) else txt

    def _refilter_voice(self, slot, lang, english_default=False):
        """Repoint a voice slot to a language's locales and repopulate live (cached catalog; fetches
        only if cold). english_default=True → empty/English maps to English voices (primary slot);
        otherwise an empty value means 'no language' (optional secondary slot → only '(none)').
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
        if english_default and prompts.is_english_language(lang):
            info["locales"], info["allow_none"] = list(VOICE_LOCALES["en"]), True  # allow "(none)" (no audio)
        elif lang:
            info["locales"], info["allow_none"] = list(audio.secondary_locale_prefixes(lang)), True
        else:
            info["locales"], info["allow_none"] = [], True
        info["stored"] = ""                     # don't carry the previous language's voice as the pick
        info["combo"].setCurrentIndex(-1)
        if getattr(self, "_voices", None):
            self._voice_populate(slot)
        else:
            self._refresh_voices(announce=False)

    def _on_translation_lang_changed(self):
        lang = self.translation_lang.currentText().strip()
        if lang == getattr(self, "_last_translation_lang", None):
            return  # no real change (e.g. focus left the box) → keep the user's voice selection
        self._last_translation_lang = lang
        self._refilter_voice("translation", lang, english_default=True)

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
        prefer = {slot: self._voice_selected(slot) for slot in self._voice_slots}
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
        cfg.setdefault("voices", {})
        cfg["voices"]["target"] = self._voice_selected("target") or "de-DE-KatjaNeural"
        cfg["voices"]["translation"] = self._voice_selected("translation")  # "" = "(none)" → translation gets no audio
        cfg["voices"].pop("de", None)   # legacy pre-1.0 key names, migrated above
        cfg["voices"].pop("en", None)
        if "secondary" in self._voice_slots:
            cfg["voices"]["secondary"] = self._voice_selected("secondary")
        cfg.setdefault("defaults", {})
        prim_lang = self.translation_lang.currentText().strip() or prompts.DEFAULT_TRANSLATION_LANG
        sec_lang = self._secondary_value()
        if sec_lang and sec_lang.lower() == prim_lang.lower():
            # Parented to mw on purpose: _save usually calls accept() right after this, and a toast
            # parented to the dialog would vanish with it (the user never learned why the second
            # language went to "(none)").
            tooltip("Secondary language is the same as the main one, so it was set to (none).", period=5000, parent=mw)
            sec_lang = ""  # never produce two identical translation sections
        cfg["defaults"]["translation_language"] = prim_lang
        cfg["defaults"]["secondary_translation_language"] = sec_lang
        cfg["defaults"]["level"] = self.level_combo.currentData() or prompts.DEFAULT_LEVEL
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
