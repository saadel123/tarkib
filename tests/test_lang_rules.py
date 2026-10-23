#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The Add window's language and deck rules (ui/lang_rules.py). No Anki, no network.

    python3 tests/test_lang_rules.py
"""
import importlib
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import card_scenarios  # noqa: E402,F401  (stubs aqt and sets up the add-on as a package)

R = importlib.import_module("tarkib_under_test.ui.lang_rules")
DECKS = ["Default", "Tarkib", "Tarkib English", "Deutsch::Verben", "My words"]


class Start(unittest.TestCase):
    def test_a_config_from_before_languages_starts_in_german_where_it_was(self):
        self.assertEqual(R.start({}, DECKS), ("de", "Tarkib"))
        self.assertEqual(R.start({"defaults": {"last_deck": "Deutsch::Verben"}}, DECKS), ("de", "Deutsch::Verben"))

    def test_the_last_chosen_language_and_its_last_deck(self):
        cfg = {"defaults": {"learning_language": "en", "last_decks": {"en": "My words", "de": "Tarkib"}},
               "deck_languages": {"My words": "en"}}
        self.assertEqual(R.start(cfg, DECKS), ("en", "My words"))

    def test_a_deleted_last_deck_falls_back_to_the_default_deck(self):
        cfg = {"defaults": {"learning_language": "en", "last_decks": {"en": "Gone"}}}
        self.assertEqual(R.start(cfg, DECKS), ("en", "Tarkib English"))
        self.assertEqual(R.start({"defaults": {"learning_language": "en"}}, []), ("en", "Tarkib English"))

    def test_the_deck_decides_when_it_belongs_to_another_language(self):
        cfg = {"defaults": {"learning_language": "de", "last_decks": {"de": "Shared"}},
               "deck_languages": {"Shared": "en"}}
        self.assertEqual(R.start(cfg, DECKS + ["Shared"]), ("en", "Shared"))

    def test_odd_config_values_never_break_it(self):
        for cfg in ({"defaults": None}, {"defaults": {"learning_language": "Klingon"}},
                    {"defaults": {"last_decks": "x"}}, {"deck_languages": ["x"]}):
            lang, deck = R.start(cfg, DECKS)
            self.assertEqual(lang, "de", cfg)


class DeckLanguage(unittest.TestCase):
    def test_remembered_then_default_deck_then_none(self):
        cfg = {"deck_languages": {"My words": "en"}}
        self.assertEqual(R.deck_language(cfg, "My words"), "en")
        self.assertEqual(R.deck_language(cfg, "Tarkib English"), "en")
        self.assertEqual(R.deck_language(cfg, "Tarkib"), "de")
        self.assertIsNone(R.deck_language(cfg, "Default"))
        self.assertIsNone(R.deck_language(cfg, ""))
        self.assertIsNone(R.deck_language({"deck_languages": {"X": "xx"}}, "X"))     # a code no longer listed

    def test_a_configured_german_default_deck_belongs_to_german(self):
        cfg = {"defaults": {"default_deck": "Deutsch"}}
        self.assertEqual(R.default_deck(cfg, "de"), "Deutsch")
        self.assertEqual(R.deck_language(cfg, "Deutsch"), "de")
        self.assertIsNone(R.deck_language(cfg, "Tarkib"))


class Switch(unittest.TestCase):
    def test_a_deck_of_the_old_language_makes_way(self):
        self.assertEqual(R.deck_after_switch({}, "Tarkib", "en", DECKS), "Tarkib English")
        cfg = {"defaults": {"last_decks": {"en": "My words"}}}
        self.assertEqual(R.deck_after_switch(cfg, "Tarkib", "en", DECKS), "My words")
        self.assertEqual(R.deck_after_switch({}, "Tarkib English", "de", DECKS), "Tarkib")

    def test_a_deck_of_no_language_or_of_the_new_one_stays(self):
        self.assertEqual(R.deck_after_switch({}, "Default", "en", DECKS), "Default")
        self.assertEqual(R.deck_after_switch({}, "Tarkib English", "en", DECKS), "Tarkib English")


class Remember(unittest.TestCase):
    def test_after_a_card(self):
        cfg = {}
        R.remember(cfg, "My words", "en")
        self.assertEqual(cfg["deck_languages"], {"My words": "en"})
        self.assertEqual(cfg["defaults"]["last_decks"], {"en": "My words"})
        self.assertEqual(cfg["defaults"]["learning_language"], "en")
        self.assertNotIn("last_deck", cfg["defaults"])           # 1.1.0's key stays German's
        R.remember(cfg, "Tarkib", "de")
        self.assertEqual(cfg["defaults"]["last_deck"], "Tarkib")
        self.assertEqual(R.start(cfg, DECKS), ("de", "Tarkib"))
        self.assertEqual(R.deck_after_switch(cfg, "Tarkib", "en", DECKS), "My words")

    def test_repairs_odd_shapes(self):
        cfg = {"defaults": {"last_decks": "x"}, "deck_languages": None}
        R.remember(cfg, "Tarkib English", "en")
        self.assertEqual(cfg["deck_languages"], {"Tarkib English": "en"})


class PickerLabel(unittest.TestCase):
    def test_flag_and_english_name(self):
        self.assertEqual(R.picker_label("de"), "🇩🇪 German")
        self.assertEqual(R.picker_label("en"), "🇬🇧 English")


class StoreLanguageSettings(unittest.TestCase):
    """What Settings saves for a learning language comes back the same through generate.language_settings,
    the one function the cards read."""
    read = staticmethod(card_scenarios.generate.language_settings)

    def values(self, **kw):
        out = {"voice": "", "translation": "", "translation_voice": "", "secondary": "", "secondary_voice": ""}
        out.update(kw)
        return out

    def test_german_round_trip_in_the_keys_of_1_0(self):
        cfg = {"voices": {"de": "de-DE-ConradNeural", "en": "en-US-AriaNeural"}, "defaults": {}}
        v = self.values(voice="de-AT-JonasNeural", translation="Arabic", translation_voice="ar-SA-ZariyahNeural",
                        secondary="French", secondary_voice="fr-FR-DeniseNeural")
        self.assertEqual(R.store_language_settings(cfg, "de", v), [])
        self.assertEqual(cfg["voices"], {"target": "de-AT-JonasNeural", "translation": "ar-SA-ZariyahNeural",
                                         "secondary": "fr-FR-DeniseNeural"})      # the names before 1.0 are gone
        self.assertEqual(cfg["defaults"], {"translation_language": "Arabic",
                                           "secondary_translation_language": "French"})
        self.assertNotIn("languages", cfg)
        self.assertEqual(self.read(cfg, "de"), v)

    def test_german_without_a_translation_language_means_english(self):
        cfg = {}
        R.store_language_settings(cfg, "de", self.values())
        self.assertEqual(cfg["defaults"]["translation_language"], "English")
        self.assertEqual(cfg["voices"]["target"], "de-DE-KatjaNeural")

    def test_english_round_trip_in_its_own_block(self):
        cfg = {"defaults": {"translation_language": "Arabic"}, "voices": {"target": "de-DE-KatjaNeural"}}
        v = self.values(voice="en-GB-SoniaNeural", translation="German", translation_voice="de-DE-KatjaNeural",
                        secondary="Arabic", secondary_voice="")
        self.assertEqual(R.store_language_settings(cfg, "en", v), [])
        self.assertEqual(cfg["languages"]["en"]["translation"], "German")
        self.assertEqual(cfg["defaults"], {"translation_language": "Arabic"})     # German's keys untouched
        self.assertEqual(cfg["voices"], {"target": "de-DE-KatjaNeural"})
        self.assertEqual(self.read(cfg, "en"), v)

    def test_english_with_no_translation_language_keeps_borrowing(self):
        cfg = {"defaults": {"translation_language": "English"}}
        R.store_language_settings(cfg, "en", self.values(voice="en-US-JennyNeural"))
        self.assertNotIn("translation", cfg["languages"]["en"])
        self.assertEqual(self.read(cfg, "en")["translation"], "")                   # the card asks for one
        cfg["defaults"]["translation_language"] = "French"                          # German's changes later
        self.assertEqual(self.read(cfg, "en")["translation"], "French")

    def test_a_chosen_translation_language_stops_the_borrowing(self):
        cfg = {"defaults": {"translation_language": "Arabic"}}
        R.store_language_settings(cfg, "en", self.values(translation="Turkish"))
        cfg["defaults"]["translation_language"] = "French"
        self.assertEqual(self.read(cfg, "en")["translation"], "Turkish")

    def test_a_second_translation_equal_to_the_first_is_turned_off(self):
        for lang, first in (("de", "French"), ("en", "French"), ("de", "")):
            cfg = {}
            notes = R.store_language_settings(cfg, lang, self.values(
                translation=first, secondary=first or "english", secondary_voice="fr-FR-DeniseNeural"))
            self.assertEqual(notes, ["secondary"], (lang, first))
            back = self.read(cfg, lang)
            self.assertEqual((back["secondary"], back["secondary_voice"]), ("", ""), (lang, first))

    def test_other_keys_of_a_language_block_survive(self):
        cfg = {"languages": {"en": {"later_setting": 1, "translation": "Arabic", "translation_voice": "x"}}}
        R.store_language_settings(cfg, "en", self.values(voice="en-US-GuyNeural"))
        self.assertEqual(cfg["languages"]["en"], {"later_setting": 1, "voice": "en-US-GuyNeural",
                                                  "secondary": "", "secondary_voice": ""})


if __name__ == "__main__":
    unittest.main(verbosity=1)
