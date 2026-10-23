#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Every prompt Tarkib can send to the AI, frozen in tests/golden/prompts/<language>/. No Anki, no network.

    python3 tests/test_prompts.py
    UPDATE_GOLDEN=1 python3 tests/test_prompts.py   after a prompt change you meant, then read the diff

A prompt is the product: one changed sentence changes every card made after it. Here a change is a diff
to read and approve, never a side effect of a refactor. The golden cards (test_cards.py) name these
files for every call they make, so the two together cover what is sent and how it is put together.
"""
import json
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import card_scenarios as cs  # noqa: E402  (stubs aqt and puts the add-on on the path)
import golden  # noqa: E402

prompts = cs.prompts


def _table(d):
    return "".join("## %s\n%s\n\n" % (k, v) for k, v in d.items())


def frozen_prompts():
    """name -> text for every frozen file, in a stable order."""
    out = {}
    for lv in prompts.LEVELS:
        out["de/main_%s" % lv] = prompts.system_main_for_level(lv)
    out["de/grammar"] = prompts.SYSTEM_GRAMMAR
    out["de/cloze"] = prompts.SYSTEM_CLOZE
    for lv in ("A1", "A2", "B1"):
        out["de/cloze_level_%s" % lv] = prompts.cloze_level_note(lv)
    out["de/loanwords"] = prompts.SYSTEM_LOANWORDS_EXPANDED
    for lang in ("Arabic", "French"):
        out["de/translation_override_%s" % lang] = prompts.translation_override(lang)
        out["de/secondary_%s" % lang] = prompts.secondary_translation_system(lang)
        out["de/grammar_override_%s" % lang] = prompts.grammar_override(lang)
    out["de/contexts_main"] = _table(prompts.CONTEXTS_MAIN)
    out["de/contexts_cloze"] = _table(prompts.CONTEXTS_CLOZE)
    out["de/starter_decks"] = json.dumps(prompts.STARTER_DECKS, ensure_ascii=False, indent=1)
    out["de/level_labels"] = _table(prompts.LEVEL_LABELS)
    out["de/translation_languages"] = "".join(
        "%s | %s | %s\n" % ((lang,) + tuple(str(x) for x in prompts.language_label(lang)))
        for lang in prompts.COMMON_TRANSLATION_LANGS)
    # English: the generic set with English's note. One translation language and the US voice for every level,
    # then the variants the other facts make (German translation, British voice).
    us, uk = "en-US-JennyNeural", "en-GB-SoniaNeural"
    for lv in prompts.LEVELS:
        out["en/main_%s" % lv] = prompts.main_system("en", lv, "Arabic", voice=us)
    out["en/main_B1_German_British"] = prompts.main_system("en", "B1", "German", voice=uk)
    out["en/main_Native_German_British"] = prompts.main_system("en", "Native", "German", voice=uk)
    out["en/main_user"] = prompts.main_user("en", "give up", "Tarkib English", "to stop trying", "at work",
                                            "a person resting", True, True)
    out["en/grammar"] = prompts.grammar_system("en", "Arabic")
    out["en/cloze"] = prompts.cloze_system("en")
    for lv in ("A1", "A2", "B1", "C1"):
        out["en/cloze_user_%s" % lv] = prompts.cloze_user("en", "give up", "Tarkib English", "يستسلم", lv, "Arabic", us)
    out["en/cloze_user_B1_British"] = prompts.cloze_user("en", "give up", "Tarkib English", "abandonner", "B1", "French", uk)
    for lang in ("Arabic", "French"):
        out["en/secondary_%s" % lang] = prompts.secondary_system("en", lang)
    out["en/translation_languages"] = "\n".join(prompts.translation_languages("en"))
    # The generic set with no note at all, for a made-up language (Italian): what a new language gets.
    with cs.MadeUpLanguage():
        out["generic/main_B1"] = prompts.main_system("it", "B1", "English", voice="it-IT-ElsaNeural")
        out["generic/main_A1_Arabic"] = prompts.main_system("it", "A1", "Arabic", voice="it-IT-ElsaNeural")
        out["generic/main_Native"] = prompts.main_system("it", "Native", "English", voice="it-IT-ElsaNeural")
        out["generic/main_user"] = prompts.main_user("it", "il tavolo", "Tarkib Italian", "", "", "", True, False)
        out["generic/grammar"] = prompts.grammar_system("it", "English")
        out["generic/cloze"] = prompts.cloze_system("it")
        out["generic/cloze_user_A1"] = prompts.cloze_user("it", "il tavolo", "Tarkib Italian", "table", "A1", "English")
        out["generic/secondary_French"] = prompts.secondary_system("it", "French")
        out["generic/secondary_Arabic"] = prompts.secondary_system("it", "Arabic")
    return {k: (v if v.endswith("\n") else v + "\n") for k, v in out.items()}


class FrozenPrompts(unittest.TestCase):
    def test_no_stale_prompt_files(self):
        expected = ["prompts/%s.txt" % name for name in frozen_prompts()]
        self.assertEqual(golden.stale("prompts", expected), [], "frozen prompts nothing produces any more")

    def test_what_is_empty_on_purpose(self):
        for lv in ("B2", "C1", "Native"):
            self.assertEqual(prompts.cloze_level_note(lv), "", lv)
        for english in ("English", "english", "", None, "en"):
            self.assertEqual(prompts.translation_override(english), "", english)
            self.assertEqual(prompts.grammar_override(english), "", english)
        self.assertEqual(prompts.system_main_for_level("Native"), prompts.SYSTEM_MAIN)
        self.assertEqual(prompts.system_main_for_level("nonsense"), prompts.SYSTEM_MAIN)


class GenericSetIsClean(unittest.TestCase):
    """A language on the generic set gets prompts named for it, with every slot filled and nothing that belongs to
    German or to English's note (the Learning Hub's newLanguage test, for the add-on)."""
    OTHER = re.compile(r"German|Deutsch|Denglisch|\bAkk\b|\bDat\b|Formell|phrasal|uncountable|American|British|"
                       r"\bder\b|\bdie\b|\bdas\b|Sie\b|\bdu\b")

    def test_every_generic_prompt(self):
        for name, text in frozen_prompts().items():
            if not name.startswith("generic/"):
                continue
            self.assertNotRegex(text, r"\{[A-Za-z_][A-Za-z0-9_]*\}", name)       # no slot left unfilled
            self.assertNotRegex(text, self.OTHER, name)
            if "secondary" not in name:
                self.assertIn("Italian", text, name)

    def test_english_prompts_name_english_and_never_german(self):
        for name, text in frozen_prompts().items():
            if name.startswith("en/") and name != "en/translation_languages":
                self.assertNotRegex(text, r"\{[A-Za-z_][A-Za-z0-9_]*\}", name)
                self.assertNotRegex(text, r"\bGERMAN\b|Denglisch|\bAkk\b|Formell", name)


def _frozen_test(name, text):
    def test(self):
        golden.check(self, "prompts/%s.txt" % name, text)
    return test


for _name, _text in frozen_prompts().items():
    setattr(FrozenPrompts, "test_" + _name.replace("/", "_"), _frozen_test(_name, _text))


if __name__ == "__main__":
    unittest.main(verbosity=1)
