#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The real Add window and Settings dialog, offscreen, on a fake collection: the language switch, the deck
that follows it, the banner, and what Settings saves for each learning language. No Anki window, no network.

Needs PyQt6 and aqt, so it runs under Anki's own Python. tests/test_ui_languages.py starts it in a separate
process (the other tests replace aqt with empty stand-ins) and skips it where aqt is missing:

    "$HOME/Library/Application Support/AnkiProgramFiles/.venv/bin/python" tests/ui_check.py
"""
import copy
import importlib
import json
import os
import sys
import types
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    import aqt
    from aqt.qt import QApplication
except Exception:          # no Anki here: tests/test_ui_languages.py reports a skip
    sys.exit(77)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(ROOT, "config.json"), encoding="utf-8") as _f:
    DEFAULT_CONFIG = json.load(_f)
PROVIDER = {"id": "groq", "type": "openai_compatible", "name": "Groq",
            "base_url": "https://api.groq.com/openai/v1", "model": "openai/gpt-oss-120b", "api_key": "test-key"}
CATALOG = [{"ShortName": n, "Locale": n.rsplit("-", 1)[0], "FriendlyName": n.rsplit("-", 1)[1], "Gender": "Female"}
           for n in ("de-DE-KatjaNeural", "de-DE-ConradNeural", "en-US-JennyNeural", "en-US-GuyNeural",
                     "en-GB-SoniaNeural", "ar-SA-ZariyahNeural", "fr-FR-DeniseNeural", "es-ES-ElviraNeural",
                     "es-MX-DaliaNeural")]


class AddonManager:
    def __init__(self, cfg):
        self.cfg = copy.deepcopy(cfg)

    def getConfig(self, _name):
        return copy.deepcopy(self.cfg)

    def writeConfig(self, _name, cfg):
        self.cfg = copy.deepcopy(cfg)


class Decks:
    def __init__(self, names):
        self.names = list(names)

    def all_names_and_ids(self):
        return [types.SimpleNamespace(name=n, id=i + 1) for i, n in enumerate(self.names)]

    def id(self, name, create=False):
        if name not in self.names and create:
            self.names.append(name)
        return self.names.index(name) + 1


class Collection:
    def __init__(self, decks):
        self.decks = Decks(decks)
        self.models = types.SimpleNamespace(by_name=lambda _name: None)
        self.queries = []

    def find_notes(self, query):
        self.queries.append(query)
        return []


class MainWindow:
    def __init__(self):
        self.addonManager = AddonManager({})
        self.col = Collection([])


app = QApplication.instance() or QApplication([])
aqt.mw = MainWindow()          # before the add-on is imported: its modules bind `from aqt import mw`

_pkg = types.ModuleType("tarkib_ui_under_test")
_pkg.__path__ = [ROOT]
sys.modules["tarkib_ui_under_test"] = _pkg
dialog = importlib.import_module("tarkib_ui_under_test.ui.dialog")
settings = importlib.import_module("tarkib_ui_under_test.ui.settings")
notetypes = importlib.import_module("tarkib_ui_under_test.notetypes")
anki_io = importlib.import_module("tarkib_ui_under_test.anki_io")
support = importlib.import_module("tarkib_ui_under_test.ui.support")


class Op:
    """QueryOp and CollectionOp, run on the spot (the add path) or kept (generation is never run)."""
    runs = []

    def __init__(self, parent=None, op=None, success=None):
        self.op, self._success = op, success
        Op.runs.append(self)

    def success(self, fn):
        self._success = fn
        return self

    def failure(self, _fn):
        return self

    def without_collection(self):
        return self

    def with_progress(self, _label):
        return self

    def run_in_background(self):
        if isinstance(self, CollectionOp):
            result = self.op(aqt.mw.col)
            if self._success:
                self._success(result)


class QueryOp(Op):
    pass


class CollectionOp(Op):
    pass


TOASTS = []
for _mod in (dialog, settings):
    _mod.tooltip = lambda msg, *a, **k: TOASTS.append(msg)
    _mod.QueryOp, _mod.CollectionOp = QueryOp, CollectionOp
dialog.askUser = lambda *a, **k: True
settings._read_voices_cache = lambda respect_ttl=True: list(CATALOG)
settings._cached_models = lambda prov, respect_ttl=True: ["openai/gpt-oss-120b"]
anki_io.write_bundle = lambda col, bundle, out: None
support.note_card_added_and_maybe_thank = dialog.note_card_added_and_maybe_thank = lambda parent: 1


def setup(decks=("Default",), **settings_):
    """A config like a user's saved one: config.json, a key, and `settings_` merged on top."""
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    cfg["providers"] = [dict(PROVIDER)]
    for k, v in settings_.items():
        if isinstance(v, dict) and isinstance(cfg.get(k), dict):
            cfg[k].update(v)
        else:
            cfg[k] = v
    aqt.mw.addonManager = AddonManager(cfg)
    aqt.mw.col = Collection(decks)
    TOASTS.clear()
    Op.runs.clear()


def saved():
    return aqt.mw.addonManager.cfg


class AddWindow(unittest.TestCase):
    def window(self):
        w = dialog.AddCardDialog()
        self.addCleanup(w.deleteLater)
        return w

    def pick_language(self, w, code):
        w.lang_combo.setCurrentIndex(w.lang_combo.findData(code))

    def test_a_config_from_before_languages_opens_on_german(self):
        setup()
        w = self.window()
        self.assertEqual((w._lang, w.deck_combo.currentText()), ("de", "Tarkib"))
        self.assertEqual(w.lang_combo.currentText(), "🇩🇪 German")
        self.assertEqual(w.word_edit.placeholderText(), "e.g. die Probe")
        self.assertEqual(w.level_combo.itemText(w.level_combo.findData("Native")), "Native: real spoken German")
        self.assertTrue(w.lang_banner.isHidden())
        self.assertTrue(w.add_btn.isEnabled())
        self.assertFalse(w.decks_footer.isHidden())

    def test_switching_to_english_moves_the_deck_and_asks_for_a_translation_language(self):
        setup()                                  # German cards in English: English cards cannot borrow it
        w = self.window()
        self.pick_language(w, "en")
        self.assertEqual((w._lang, w.deck_combo.currentText()), ("en", "Tarkib English"))
        self.assertEqual(w.word_edit.placeholderText(), "e.g. give up")
        self.assertEqual(w.level_combo.itemText(w.level_combo.findData("Native")), "Native: real spoken English")
        self.assertFalse(w.lang_banner.isHidden())
        self.assertIn("English cards need a translation language", w.lang_banner.text())
        self.assertFalse(w.add_btn.isEnabled())
        self.assertTrue(w.decks_footer.isHidden())          # the ready-made decks teach German
        self.pick_language(w, "de")
        self.assertEqual(w.deck_combo.currentText(), "Tarkib")
        self.assertTrue(w.lang_banner.isHidden())
        self.assertTrue(w.add_btn.isEnabled())
        self.assertFalse(w.decks_footer.isHidden())

    def test_english_borrows_an_arabic_translation_and_keeps_its_own_second_one(self):
        setup(defaults={"translation_language": "Arabic", "secondary_translation_language": "French"})
        w = self.window()
        self.assertFalse(w.secondary_check.isHidden())
        self.pick_language(w, "en")
        self.assertTrue(w.lang_banner.isHidden())
        self.assertTrue(w.add_btn.isEnabled())
        self.assertTrue(w.secondary_check.isHidden())       # never borrowed
        self.assertEqual(w._settings["translation"], "Arabic")

    def test_a_deck_of_no_language_stays_when_the_language_changes(self):
        setup(decks=("Default", "Mixed"))
        w = self.window()
        w.deck_combo.setCurrentText("Mixed")
        self.pick_language(w, "en")
        self.assertEqual(w.deck_combo.currentText(), "Mixed")

    def test_picking_a_deck_of_the_other_language_switches_the_language(self):
        setup(decks=("Default", "My words", "Tarkib"), deck_languages={"My words": "en"})
        w = self.window()
        self.assertEqual(w._lang, "de")
        w.deck_combo.setCurrentIndex(w.deck_combo.findText("My words"))
        w.deck_combo.activated.emit(w.deck_combo.currentIndex())
        self.assertEqual(w._lang, "en")
        self.assertEqual(w.lang_combo.currentData(), "en")
        self.assertEqual(w.deck_combo.currentText(), "My words")       # the deck the learner picked stays
        w.deck_combo.setCurrentText("Default")
        w.deck_combo.lineEdit().editingFinished.emit()
        self.assertEqual(w._lang, "en")                                 # Default belongs to no language

    def test_opens_where_the_learner_left_off(self):
        setup(decks=("Default", "My words"), defaults={"learning_language": "en", "last_decks": {"en": "My words"},
                                                        "translation_language": "Arabic"})
        w = self.window()
        self.assertEqual((w._lang, w.deck_combo.currentText()), ("en", "My words"))

    def test_the_card_request_carries_the_language_and_the_deck_remembers_it(self):
        setup(defaults={"translation_language": "Arabic"})
        w = self.window()
        self.pick_language(w, "en")
        w.word_edit.setText("to give up")
        w._on_add()
        options = w._pending_run["options"]
        self.assertEqual((options["language"], w._pending_run["deck"]), ("en", "Tarkib English"))
        # the duplicate check drops English's "to", not German's articles
        self.assertEqual(aqt.mw.col.queries, [])            # no Tarkib note type yet, nothing searched
        notetypes_find = notetypes.find_main
        notetypes.find_main = lambda mm: {"name": "Tarkib"}
        try:
            w._find_existing("Tarkib English", "to give up")
        finally:
            notetypes.find_main = notetypes_find
        self.assertIn('"Front:*give up*"', aqt.mw.col.queries[-1])
        w._on_built({"main": {}, "cloze": None, "media": {}, "meta": {}})
        cfg = saved()
        self.assertEqual(cfg["deck_languages"], {"Tarkib English": "en"})
        self.assertEqual(cfg["defaults"]["last_decks"], {"en": "Tarkib English"})
        self.assertEqual(cfg["defaults"]["learning_language"], "en")
        self.assertNotEqual(cfg["defaults"].get("last_deck"), "Tarkib English")   # 1.1.0's key stays German's

    def test_spanish_uses_english_at_once_and_each_language_keeps_its_deck(self):
        setup()                                  # German cards in English: Spanish cards may use English too
        w = self.window()
        self.assertEqual([w.lang_combo.itemData(i) for i in range(w.lang_combo.count())], ["de", "en", "es"])
        self.pick_language(w, "es")
        self.assertEqual((w._lang, w.deck_combo.currentText()), ("es", "Tarkib Spanish"))
        self.assertEqual(w.lang_combo.currentText(), "🇪🇸 Spanish")
        self.assertEqual(w.word_edit.placeholderText(), "e.g. darse cuenta")
        self.assertEqual(w.level_combo.itemText(w.level_combo.findData("Native")), "Native: real spoken Spanish")
        self.assertTrue(w.lang_banner.isHidden())
        self.assertTrue(w.add_btn.isEnabled())
        self.assertEqual(w._settings["translation"], "English")
        self.assertTrue(w.decks_footer.isHidden())          # the ready-made decks teach German
        self.pick_language(w, "en")
        self.assertEqual(w.deck_combo.currentText(), "Tarkib English")
        self.assertFalse(w.lang_banner.isHidden())          # English cards cannot use English
        self.pick_language(w, "es")
        self.assertEqual(w.deck_combo.currentText(), "Tarkib Spanish")
        self.assertTrue(w.lang_banner.isHidden())
        self.pick_language(w, "de")
        self.assertEqual(w.deck_combo.currentText(), "Tarkib")

    def test_a_spanish_card_request_and_its_duplicate_check(self):
        setup()
        w = self.window()
        self.pick_language(w, "es")
        w.word_edit.setText("la mesa")
        w._on_add()
        options = w._pending_run["options"]
        self.assertEqual((options["language"], w._pending_run["deck"]), ("es", "Tarkib Spanish"))
        notetypes_find = notetypes.find_main
        notetypes.find_main = lambda mm: {"name": "Tarkib"}
        try:
            w._find_existing("Tarkib Spanish", "la mesa")
        finally:
            notetypes.find_main = notetypes_find
        self.assertIn('"Front:*mesa*"', aqt.mw.col.queries[-1])          # Spanish's article dropped
        w._on_built({"main": {}, "cloze": None, "media": {}, "meta": {}})
        cfg = saved()
        self.assertEqual(cfg["deck_languages"], {"Tarkib Spanish": "es"})
        self.assertEqual(cfg["defaults"]["last_decks"], {"es": "Tarkib Spanish"})
        self.assertEqual(cfg["defaults"]["learning_language"], "es")

    def test_use_my_style_shows_only_with_wishes_and_goes_with_the_card(self):
        setup()
        w = self.window()
        self.assertTrue(w.style_check.isHidden())                       # no wishes: no checkbox, nothing sent
        w.word_edit.setText("der Termin")
        w._on_add()
        self.assertEqual(w._pending_run["options"]["style"], "")
        setup(defaults={"card_style": "Beispiele rund ums Kochen,\nkurze Saetze."})
        w = self.window()
        self.assertFalse(w.style_check.isHidden())
        self.assertTrue(w.style_check.isChecked())
        self.assertEqual(w.style_check.toolTip(), "Beispiele rund ums Kochen, kurze Saetze.")
        w.word_edit.setText("der Termin")
        w._on_add()
        self.assertEqual(w._pending_run["options"]["style"], "Beispiele rund ums Kochen, kurze Saetze.")
        w.style_check.setChecked(False)                                 # one card without the style
        w._sync_from_config()
        self.assertFalse(w.style_check.isChecked())                     # same wishes: the user's choice stays
        w._on_add()
        self.assertEqual(w._pending_run["options"]["style"], "")
        self.pick_language(w, "es")                                     # every language
        self.assertFalse(w.style_check.isHidden())

    def test_a_refusal_for_no_translation_language_opens_settings_on_languages(self):
        setup()
        w = self.window()
        opened = []
        w._open_settings = lambda initial_tab=None: opened.append(initial_tab)
        w._fail(ValueError('no translation language: cards that teach "English" need another translation '
                           'language than "English"'))
        self.assertEqual(opened, ["Languages"])


class SettingsLanguages(unittest.TestCase):
    def dialog(self, **kw):
        d = settings.SettingsDialog(**kw)
        self.addCleanup(d.deleteLater)
        return d

    def pick(self, combo, data):
        i = combo.findData(data)
        self.assertGreaterEqual(i, 0, data)
        combo.setCurrentIndex(i)

    def test_opens_on_german_as_before(self):
        setup(voices={"target": "de-DE-ConradNeural", "translation": "", "secondary": ""})
        d = self.dialog()
        self.assertEqual(d.learning_lang.currentData(), "de")
        self.assertEqual(d.target_voice_label.text(), "German voice")
        self.assertEqual(d._voice_selected("target"), "de-DE-ConradNeural")
        self.assertEqual(d._translation_value(), "English")
        self.assertFalse(d.german_extras.isHidden())

    def test_english_from_the_add_window_then_back_and_forth_then_save(self):
        setup()
        d = self.dialog(initial_language="en")
        self.assertEqual(d.target_voice_label.text(), "English voice")
        self.assertEqual(d._voice_selected("target"), "en-US-JennyNeural")
        self.assertEqual(d.translation_lang.currentText(), "(choose one)")
        self.assertEqual(d.translation_lang.findData("English"), -1)    # never the language itself
        self.assertTrue(d.german_extras.isHidden())
        self.assertEqual(d.level_combo.itemText(d.level_combo.findData("Native")), "Native: real spoken English")
        self.pick(d.translation_lang, "Arabic")
        self.pick(d._voice_slots["target"]["combo"], "en-GB-SoniaNeural")
        self.pick(d.learning_lang, "de")                 # German shows its own values
        self.assertEqual(d.target_voice_label.text(), "German voice")
        self.assertEqual(d._voice_selected("target"), "de-DE-KatjaNeural")
        self.assertEqual(d._translation_value(), "English")
        self.assertFalse(d.german_extras.isHidden())
        self.pick(d.learning_lang, "en")                 # and English what was picked before
        self.assertEqual(d._translation_value(), "Arabic")
        self.assertEqual(d._voice_selected("target"), "en-GB-SoniaNeural")
        self.assertEqual(d._voice_selected("translation"), "")    # silent until a voice is picked
        d._save()
        cfg = saved()
        self.assertEqual(cfg["languages"]["en"], {"voice": "en-GB-SoniaNeural", "translation": "Arabic",
                                                  "translation_voice": "", "secondary": "", "secondary_voice": ""})
        self.assertEqual(cfg["defaults"]["learning_language"], "en")
        self.assertEqual(cfg["defaults"]["translation_language"], "English")     # German's, untouched
        self.assertEqual(cfg["voices"]["target"], "de-DE-KatjaNeural")

    def test_spanish_in_settings_borrows_english_then_saves_its_own(self):
        setup()
        d = self.dialog(initial_language="es")
        self.assertEqual(d.target_voice_label.text(), "Spanish voice")
        self.assertEqual(d._voice_selected("target"), "es-ES-ElviraNeural")
        self.assertEqual(d._translation_value(), "English")             # what the German cards use
        self.assertEqual(d.translation_lang.findData("Spanish"), -1)    # never the language itself
        self.assertGreaterEqual(d.translation_lang.findData("German"), 0)
        self.assertTrue(d.german_extras.isHidden())
        self.assertEqual(d.level_combo.itemText(d.level_combo.findData("Native")), "Native: real spoken Spanish")
        self.pick(d._voice_slots["target"]["combo"], "es-MX-DaliaNeural")
        self.pick(d.translation_lang, "Arabic")
        self.pick(d.learning_lang, "en")                 # English keeps asking for its own
        self.assertEqual(d.translation_lang.currentText(), "(choose one)")
        self.pick(d.learning_lang, "es")
        self.assertEqual((d._voice_selected("target"), d._translation_value()), ("es-MX-DaliaNeural", "Arabic"))
        d._save()
        cfg = saved()
        self.assertEqual(cfg["languages"]["es"], {"voice": "es-MX-DaliaNeural", "translation": "Arabic",
                                                  "translation_voice": "", "secondary": "", "secondary_voice": ""})
        self.assertEqual(cfg["defaults"]["learning_language"], "es")
        self.assertEqual(cfg["defaults"]["translation_language"], "English")     # German's, untouched

    def test_your_style_is_saved_and_the_window_follows(self):
        setup()
        w = dialog.AddCardDialog()
        self.addCleanup(w.deleteLater)
        self.assertTrue(w.style_check.isHidden())
        d = self.dialog(initial_tab="Cards")
        self.assertEqual(d.style_edit.toPlainText(), "")
        d.style_edit.setPlainText("  Examples about cooking.  " + "x" * 600)
        d._save()
        saved_style = saved()["defaults"]["card_style"]
        self.assertTrue(saved_style.startswith("Examples about cooking."))
        self.assertLessEqual(len(saved_style), 500)
        w._sync_from_config()
        self.assertFalse(w.style_check.isHidden())
        self.assertTrue(w.style_check.isChecked())

    def test_speech_speed_is_saved_and_test_plays_the_slower_speed(self):
        import tempfile
        tts = settings.tts
        setup()
        d = self.dialog(initial_tab="Voice")
        self.assertEqual([d.tts_speed.itemData(i) for i in range(d.tts_speed.count())], list(tts.SPEEDS))
        self.assertEqual(d.tts_speed.currentData(), "normal")      # a config saved before speeds existed
        self.pick(d.tts_speed, "slower_a1_a2")
        rates, real = [], (tts.synthesize, settings._models_cache_path)
        tmp = tempfile.mkdtemp()
        tts.synthesize = lambda service, text, voice, values, timeout=30, rate=1.0: (
            rates.append(rate) or tts.Clip(b"audio", "mp3", service, voice, rate))
        settings._models_cache_path = lambda: os.path.join(tmp, "models_cache.json")
        try:
            d._test_tts("edge", d.tts_test)
            Op.runs[-1].op(None)                  # the sample, as the background step would read it
        finally:
            tts.synthesize, settings._models_cache_path = real
        self.assertEqual(rates, [tts.SLOW_RATE])
        d._save()
        self.assertEqual(saved()["tts"]["speed"], "slower_a1_a2")
        self.assertEqual(self.dialog(initial_tab="Voice").tts_speed.currentData(), "slower_a1_a2")

    def test_the_add_window_follows_what_settings_saved(self):
        setup()
        w = dialog.AddCardDialog()
        self.addCleanup(w.deleteLater)
        w.lang_combo.setCurrentIndex(w.lang_combo.findData("en"))
        self.assertFalse(w.lang_banner.isHidden())
        d = self.dialog(initial_language=w._lang)
        self.pick(d.translation_lang, "French")
        d._save()
        w._sync_from_config()
        self.assertEqual(w._lang, "en")
        self.assertTrue(w.lang_banner.isHidden())
        self.assertTrue(w.add_btn.isEnabled())
        d2 = self.dialog(initial_language=w._lang)        # Settings picks German: the window goes along
        self.pick(d2.learning_lang, "de")
        d2._save()
        w._sync_from_config()
        self.assertEqual((w._lang, w.deck_combo.currentText()), ("de", "Tarkib"))

    def test_a_doubled_second_translation_is_turned_off_on_save(self):
        setup(defaults={"translation_language": "French", "secondary_translation_language": "French"})
        d = self.dialog()
        self.assertEqual(d._secondary_value(), "French")
        d._save()
        self.assertEqual(saved()["defaults"]["secondary_translation_language"], "")
        self.assertTrue(any("set to (none)" in t for t in TOASTS))


if __name__ == "__main__":
    unittest.main(verbosity=1)
