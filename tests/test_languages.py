#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The language registry (pipeline/languages.py) and every table keyed by it. No Anki, no network.

    python3 tests/test_languages.py

Python has no compiler to point at each place a new language still lacks a value, so this file does
that job: every language in the registry must have every field, a prompt set in prompts.PROMPTS with
every key, and rules in generate.RULES with every key. German's values must equal what the code used
before the registry existed (the golden cards prove the same end to end), and the two functions that
make a card may not contain a German word of their own: German lives in its tables.
"""
import copy
import inspect
import io
import os
import re
import sys
import tokenize
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import card_scenarios as cs  # noqa: E402  (stubs aqt and puts the add-on on the path)
from pipeline import languages  # noqa: E402

generate, prompts, tts = cs.generate, cs.prompts, cs.tts

FIELDS = {"code": str, "name": str, "native_name": str, "label": str, "quotes": tuple, "inner_quotes": tuple,
          "default_voice": str, "headword_prefixes": tuple, "formal_tag": str, "script": str,
          "example_word": str, "default_deck": str, "voice_locales": tuple}


class Registry(unittest.TestCase):
    def test_every_language_has_every_field(self):
        for entry in languages.LANGUAGES:
            self.assertEqual(set(entry), set(FIELDS), entry.get("code"))
            for key, kind in FIELDS.items():
                self.assertIsInstance(entry[key], kind, (entry["code"], key))
                self.assertTrue(entry[key], (entry["code"], key))
            self.assertEqual(len(entry["quotes"]), 2, entry["code"])
            self.assertEqual(len(entry["inner_quotes"]), 2, entry["code"])

    def test_codes_are_unique_and_the_default_is_one_of_them(self):
        codes = [e["code"] for e in languages.LANGUAGES]
        self.assertEqual(len(codes), len(set(codes)))
        self.assertIn(languages.DEFAULT, codes)
        self.assertEqual(languages.codes(), tuple(codes))

    def test_the_default_voice_speaks_the_language(self):
        for entry in languages.LANGUAGES:
            self.assertTrue(entry["default_voice"].lower().startswith(entry["code"] + "-"), entry["default_voice"])
            self.assertTrue(entry["default_voice"].startswith(entry["voice_locales"]), entry["code"])
            self.assertTrue(all(loc.lower().startswith(entry["code"] + "-") for loc in entry["voice_locales"]))

    def test_every_language_has_its_own_default_deck(self):
        decks = [e["default_deck"] for e in languages.LANGUAGES]
        self.assertEqual(len(decks), len(set(decks)))

    def test_resolve_takes_codes_and_names_in_any_case(self):
        self.assertEqual(languages.resolve(None), ("de", None))
        self.assertEqual(languages.resolve(""), ("de", None))
        for value in ("de", "DE", " German ", "german", "Deutsch", "deutsch"):
            self.assertEqual(languages.resolve(value), ("de", None), value)

    def test_resolve_falls_back_with_a_warning_and_a_safe_text(self):
        code, warning = languages.resolve('Klingon"')
        self.assertEqual(code, languages.DEFAULT)
        self.assertIn("Klingon'", warning)

    def test_an_unknown_code_is_an_error_not_a_guess(self):
        with self.assertRaises(KeyError):
            languages.get("xx")
        with self.assertRaises(KeyError):
            prompts.main_system("xx", "B1", "English")


class Tables(unittest.TestCase):
    """Every per-language table has every language, with the same keys as German's."""

    def test_prompt_sets(self):
        keys = set(prompts.PROMPTS[languages.DEFAULT])
        for code in languages.codes():
            self.assertIn(code, prompts.PROMPTS, code)
            self.assertEqual(set(prompts.PROMPTS[code]), keys, code)
            for key, value in prompts.PROMPTS[code].items():
                self.assertTrue(callable(value), (code, key))

    def test_rules(self):
        keys = set(generate.RULES[languages.DEFAULT])
        for code in languages.codes():
            self.assertIn(code, generate.RULES, code)
            rules = generate.RULES[code]
            self.assertEqual(set(rules), keys, code)
            for key, value in rules.items():
                if key == "cloze_cases":
                    self.assertTrue(value and all(isinstance(c, str) for c in value), code)
                    self.assertIn("single_word", value, code)   # build_card's fallback for an unknown case
                elif key == "cloze_no_hint":
                    self.assertTrue(set(value) <= set(rules["cloze_cases"]), code)
                elif key == "grammar_fallback":
                    self.assertIsInstance(value, bool, code)
                elif key == "audio_names":
                    self.assertEqual(set(value), {"target", "translation"}, code)
                    self.assertTrue(all(re.match(r"^[a-z_]+$", v) for v in value.values()), code)
                else:
                    self.assertTrue(callable(value), (code, key))

    def test_no_table_holds_a_language_the_registry_does_not(self):
        self.assertEqual(set(prompts.PROMPTS) - set(languages.codes()), set())
        self.assertEqual(set(generate.RULES) - set(languages.codes()), set())


def _string_literals(func):
    src = inspect.getsource(func)
    return [t.string for t in tokenize.generate_tokens(io.StringIO(src).readline) if t.type == tokenize.STRING]


_GERMAN = re.compile(r"\b(der|die|das|sich|deutsch|german|formell|denglisch)\b|🇩🇪", re.I)


class GermanLivesInItsTables(unittest.TestCase):
    def test_build_card_and_the_renderer_hold_no_german_text(self):
        for func in (generate.build_card, generate.build_back_html):
            found = [s for s in _string_literals(func) if _GERMAN.search(s)]
            self.assertEqual(found, [], "%s holds German text: put it in a table" % func.__name__)


class GermanIsWhatItWas(unittest.TestCase):
    """German through the registry equals German before it."""

    def test_values_the_code_used_before(self):
        de = languages.get("de")
        self.assertEqual(de["default_voice"], tts.DEFAULT_GERMAN_VOICE)
        self.assertEqual(de["default_voice"], cs.DEFAULT_CONFIG["voices"]["target"])
        self.assertEqual(de["formal_tag"], "Formell")
        self.assertEqual(de["label"], "🇩🇪 Deutsch")

    def test_the_headword_stem_matches_the_old_expression(self):
        for w in ("der Tisch", "Die Brille", "das Schloss", "sich freuen", "dieser Tisch", "derzeit",
                  "die  Küche", "  Der Termin ", "Sichtweise", "", None):
            old = re.sub(r"^(der|die|das|sich)\s+", "", (w or "").strip().lower())
            self.assertEqual(generate._headword_stem(w, "de"), old, w)

    def test_the_prompt_functions_return_the_old_strings(self):
        for lv in prompts.LEVELS + ["nonsense"]:
            for helper in ("English", "Arabic", "French", ""):
                for scenario in ("", "beim Arzt"):
                    want = (prompts.system_main_for_level(lv) + prompts.translation_override(helper)
                            + (prompts.SYSTEM_LOANWORDS_EXPANDED if scenario else ""))
                    self.assertEqual(prompts.main_system("de", lv, helper, scenario), want)
        self.assertEqual(prompts.grammar_system("de", "English"), prompts.SYSTEM_GRAMMAR)
        self.assertEqual(prompts.grammar_system("de", "Arabic"), prompts.SYSTEM_GRAMMAR + prompts.grammar_override("Arabic"))
        self.assertIs(prompts.cloze_system("de"), prompts.SYSTEM_CLOZE)
        for helper in ("Arabic", "French", "Turkish"):
            self.assertEqual(prompts.secondary_system("de", helper), prompts.secondary_translation_system(helper))

    def test_a_card_dict_without_a_language_renders_as_german(self):
        # The deck scripts (scripts/apply_pattern_fixes.py) render their own card dicts, with no language.
        card = copy.deepcopy(cs.SCHLOSS)
        card["level"] = "B1"
        old_style = generate.build_back_html(copy.deepcopy(card))
        card["language"] = "de"
        self.assertEqual(generate.build_back_html(card), old_style)
        self.assertIn("🇩🇪 Deutsch", old_style)

    def test_a_learning_language_in_the_config_or_the_options(self):
        s = copy.deepcopy(cs.BY_NAME["noun_b1"])
        for settings, options in (({"defaults": {"learning_language": "de"}}, {}),
                                  ({"defaults": {"learning_language": "Deutsch"}}, {}),
                                  ({}, {"language": "German"})):
            s2 = copy.deepcopy(s)
            s2.settings, s2.options = settings, options
            r = cs.run(s2)
            self.assertEqual(r["violations"], [])
            self.assertEqual([n["fields"] for n in r["notes"]], [n["fields"] for n in cs.run(s)["notes"]])
            self.assertNotIn("language_warning", r["bundle"]["meta"])

    def test_an_unknown_learning_language_makes_a_german_card_and_says_so(self):
        s = copy.deepcopy(cs.BY_NAME["noun_b1"])
        s.settings = {"defaults": {"learning_language": "Klingon"}}
        r = cs.run(s)
        self.assertEqual(r["violations"], [])
        self.assertEqual(r["bundle"]["meta"]["language_warning"],
                         'learning language "Klingon" is not one Tarkib knows, German was used')
        self.assertEqual([n["fields"] for n in r["notes"]], [n["fields"] for n in cs.run(cs.BY_NAME["noun_b1"])["notes"]])



class MadeUpLanguageCard(unittest.TestCase):
    """A language with nothing but its registry entry makes a whole, clean card: the generic prompts and the
    generic rules do the rest, the way the Learning Hub's Italian test proves its generic prompts."""

    def test_a_whole_card_that_keeps_every_card_rule(self):
        import test_cards  # noqa: E402  (the card rules)
        with cs.MadeUpLanguage():
            r = cs.run(cs.ITALIAN_SCENARIO)
            problems = test_cards.card_problems(cs.ITALIAN_SCENARIO, r)
            sent = [c["system"] for c in r["calls"]]
        self.assertEqual(r["violations"], [])
        self.assertEqual(problems, [])
        main = next(n for n in r["notes"] if n["type"] == "main")
        clz = next(n for n in r["notes"] if n["type"] == "cloze")
        back = main["fields"]["Back"]
        for piece in ("🇮🇹 Italiano", "«Un mobile", '<div class="morph">il · Pl. i tavoli</div>',
                      "mettere qualcosa su qualcosa", "to put something on something", "🇬🇧 English"):
            self.assertIn(piece, back)
        self.assertEqual(main["tags"], ["Home", "Level::B1"])
        self.assertEqual(clz["deck"], "Tarkib Italian::Cloze")
        self.assertIn("{{c1::tavolo::tav...}}", clz["fields"]["Text"])
        self.assertTrue(all("Italian" in s for s in sent), "every prompt names the language")
        self.assertTrue(all("German" not in s for s in sent), "no prompt names German")

    def test_the_tables_follow_the_registry(self):
        with cs.MadeUpLanguage():
            self.assertIn("it", languages.codes())
            Tables("test_prompt_sets").test_prompt_sets()
            Tables("test_rules").test_rules()
        self.assertNotIn("it", languages.codes())
        self.assertNotIn("it", prompts.PROMPTS)


if __name__ == "__main__":
    unittest.main(verbosity=1)
