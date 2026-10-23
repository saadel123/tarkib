#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""English's own checks and card parts (pipeline/english.py). No Anki, no network.

    python3 tests/test_english.py

The word line, the value order of the patterns, the anchoring of a pattern in the sentences, the leak check,
the spelling that follows the voice, and the translation languages of an English learner. The golden cards
(tests/golden/cards/en/) show the same pieces on whole cards.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import card_scenarios as cs  # noqa: E402  (stubs aqt and puts the add-on on the path)
from pipeline import english as E  # noqa: E402

generate, prompts, providers = cs.generate, cs.prompts, cs.providers


def noun(singular, plural, countable=True):
    return {"pos": "noun", "singular": singular, "plural": plural, "countable": countable}


def verb(base, past, part, phrasal=False, separable=False):
    return {"pos": "verb", "base": base, "past": past, "past_participle": part, "phrasal": phrasal,
            "separable": separable}


class WordLine(unittest.TestCase):
    """Only what English has to learn: irregular forms, a separable phrasal verb, uncountable."""

    def test_regular_words_show_nothing(self):
        for m in (noun("reason", "reasons"), noun("box", "boxes"), noun("city", "cities"),
                  verb("walk", "walked", "walked"), verb("like", "liked", "liked"), verb("study", "studied", "studied"),
                  verb("stop", "stopped", "stopped"), {"pos": "other"}, None, "garbage"):
            self.assertEqual(E.morphology_html(m), "", m)

    def test_irregular_plural_and_uncountable(self):
        self.assertEqual(E.morphology_html(noun("child", "children")), '<div class="morph">Pl. children</div>')
        self.assertEqual(E.morphology_html(noun("knife", "knives")), '<div class="morph">Pl. knives</div>')
        self.assertEqual(E.morphology_html(noun("sheep", "sheep")), '<div class="morph">Pl. sheep</div>')
        self.assertEqual(E.morphology_html(noun("information", "", countable=False)),
                         '<div class="morph">uncountable</div>')

    def test_irregular_verbs_and_the_repair_of_a_regularized_form(self):
        self.assertEqual(E.morphology_html(verb("go", "went", "gone")), '<div class="morph">go · went · gone</div>')
        self.assertEqual(E.morphology_html(verb("teach", "teached", "teached")),
                         '<div class="morph">teach · taught · taught</div>')
        self.assertEqual(E.morphology_html(verb("to buy", "buyed", "buyed")),
                         '<div class="morph">buy · bought · bought</div>')
        self.assertEqual(E.morphology_html(verb("give up", "gave up", "given up", True, True)),
                         '<div class="morph">give up · gave up · given up · separable</div>')
        self.assertEqual(E.morphology_html(verb("look after", "looked after", "looked after", True, False)), "")
        self.assertEqual(E.morphology_html(verb("pick up", "picked up", "picked up", True, True)),
                         '<div class="morph">separable</div>')

    def test_british_and_older_forms_are_right_too(self):
        self.assertEqual(E.morphology_html(verb("learn", "learnt", "learnt")),
                         '<div class="morph">learn · learnt · learnt</div>')
        self.assertEqual(E.morphology_html(verb("learn", "learned", "learned")), "")     # regular, also right
        self.assertEqual(E.morphology_html(verb("get", "got", "got")), '<div class="morph">get · got · got</div>')

    def test_the_line_is_escaped(self):
        self.assertNotIn("<b>", E.morphology_html(noun("<b>x</b>", "<b>xen</b>")))


class PatternOrder(unittest.TestCase):
    RANKS = [
        ("depend on something", 1), ("talk to someone", 1), ("look after someone", 1), ("sleep on it", 1),
        ("interested in something", 2), ("the reason for something", 2), ("until + time", 2), ("by + -ing", 2),
        ("enjoy + -ing", 3), ("decide to + verb", 3), ("would like to + verb", 3), ("need to + verb", 3),
        ("give up", 4), ("put something off", 4),
        ("make a decision", 5), ("ask a question", 5), ("cancel an appointment", 5),
        ("explain that", 6), ("present perfect", 8), ("only after + -ing, did + subject (inversion)", 8),
        ("could + verb", 5),
        # dropped: a bare object, a preposition alone, only grammar words (the first live run had all three)
        ("buy something", None), ("bring something", None), ("at something", None), ("to + verb", None),
    ]

    def test_ranks(self):
        for pattern, rank in self.RANKS:
            self.assertEqual(E.pattern_rank(pattern), rank, pattern)
        self.assertIsNone(E.pattern_rank(""))


class PatternAnchoring(unittest.TestCase):
    TEXT = "she depends on her parents. i took the bus and slept on it. we put the meeting off until friday."

    def test_forms_of_the_words_count(self):
        for p in ("depend on someone", "take the bus", "sleep on it", "put something off", "until + time"):
            self.assertTrue(E.pattern_in_text(p, self.TEXT), p)

    def test_invented_patterns_and_bare_labels_fail(self):
        for p in ("look forward to + -ing", "present perfect", "make a decision"):
            self.assertFalse(E.pattern_in_text(p, self.TEXT), p)
        self.assertTrue(E.pattern_in_text("ask a question", "can i ask a question?"))   # a grammar word, used as a word

    def test_whole_words_only(self):
        # the second live run kept this: "for" counted, and was found inside "before"
        text = "please make sure the kitchen is clean before the meeting."
        self.assertFalse(E.pattern_in_text("be ready for something", text))
        self.assertTrue(E.pattern_in_text("can + verb", "can you help me?"))
        self.assertFalse(E.pattern_in_text("can + verb", "the scan is ready."))
        self.assertTrue(E.pattern_in_text("stop + -ing", "she stopped smoking."))
        self.assertTrue(E.pattern_in_text("study for something", "he studies for the test."))


class Leak(unittest.TestCase):
    def test_another_script_or_a_foreign_function_word(self):
        self.assertEqual(E.leak("I have an appointment with the طبيب tomorrow."), "ط")
        self.assertEqual(E.leak("We meet und talk."), "und")
        self.assertEqual(E.leak("Привет, how are you?"), "П")

    def test_english_with_loanwords_and_names_is_clean(self):
        for t in ("Let's meet at the café.", "She lives in Los Angeles.", "I hope you don't die laughing.",
                  "What was that?", "He wore a hat.", "She studied at MIT.", "Déjà vu, again."):
            self.assertIsNone(E.leak(t), t)


class SpellingFollowsTheVoice(unittest.TestCase):
    def test_variety(self):
        us = prompts.main_system("en", "B1", "Arabic", voice="en-US-JennyNeural")
        uk = prompts.main_system("en", "B1", "Arabic", voice="en-GB-SoniaNeural")
        self.assertIn("standard American English", us)
        self.assertIn("standard British English", uk)
        self.assertIn("colour, centre, flat", uk)
        self.assertIn("SPELLING: Use British English",
                      prompts.main_system("en", "Native", "Arabic", voice="en-GB-SoniaNeural"))
        self.assertIn("Use American English spelling",
                      prompts.cloze_user("en", "x", "d", "m", "B1", "Arabic", "en-US-JennyNeural"))


class TranslationLanguages(unittest.TestCase):
    def test_an_english_learner_picks_from_the_others_and_must_pick(self):
        langs = prompts.translation_languages("en")
        self.assertNotIn("English", langs)
        self.assertIn("German", langs)
        self.assertIn("Arabic", langs)
        self.assertIsNone(prompts.default_translation_language("en"))

    def test_german_learners_keep_exactly_their_list(self):
        self.assertEqual(prompts.translation_languages("de"), prompts.COMMON_TRANSLATION_LANGS)
        self.assertEqual(prompts.default_translation_language("de"), "English")

    def test_known_language_for_an_english_learner(self):
        allowed = prompts.translation_languages("en")
        self.assertEqual(generate._known_language("deutsch", None, allowed=allowed), ("German", None))
        name, warning = generate._known_language("English", None, allowed=allowed)
        self.assertIsNone(name)
        self.assertIn("the language the cards teach", warning)
        self.assertEqual(generate._known_language("Arabic", None, allowed=allowed), ("Arabic", None))


class Messages(unittest.TestCase):
    def test_not_english(self):
        title, body, kind = providers.friendly_error(RuntimeError('not english: "danke"; suggestion "thanks"'))
        self.assertEqual((title, kind), ("That does not look like English", "retry"))
        self.assertIn('"danke" as an English word or phrase', body)
        self.assertIn('Did you mean "thanks"?', body)

    def test_pick_a_translation_language(self):
        exc = RuntimeError('no translation language: cards that teach "English" need another translation language '
                           'than "English"')
        title, body, kind = providers.friendly_error(exc)
        self.assertEqual((title, kind), ("Pick a translation language", "settings"))
        self.assertIn("Cards that teach English", body)
        self.assertNotIn("json", body.lower())


class LanguageSettings(unittest.TestCase):
    """generate.language_settings: German in the keys every config has, any other language in its own
    block, and a new language borrowing German's translation language when it may."""

    def s(self, cfg, lang):
        return generate.language_settings(cfg, lang)

    def test_german_reads_the_old_keys(self):
        cfg = {"voices": {"target": "de-DE-ConradNeural", "translation": "en-US-AvaMultilingualNeural",
                          "secondary": "ar-SA-ZariyahNeural"},
               "defaults": {"translation_language": "English", "secondary_translation_language": "Arabic"}}
        self.assertEqual(self.s(cfg, "de"), {"voice": "de-DE-ConradNeural", "translation": "English",
                                             "translation_voice": "en-US-AvaMultilingualNeural",
                                             "secondary": "Arabic", "secondary_voice": "ar-SA-ZariyahNeural"})
        self.assertEqual(self.s({"voices": {"de": "de-AT-IngridNeural"}}, "de")["voice"], "de-AT-IngridNeural")
        self.assertEqual(self.s({}, "de"), {"voice": "de-DE-KatjaNeural", "translation": "English",
                                            "translation_voice": "", "secondary": "", "secondary_voice": ""})

    def test_english_has_its_own_block(self):
        cfg = {"voices": {"target": "de-DE-ConradNeural"},
               "languages": {"en": {"voice": "en-GB-SoniaNeural", "translation": "French", "secondary": "German",
                                    "secondary_voice": "de-DE-KatjaNeural"}}}
        self.assertEqual(self.s(cfg, "en"), {"voice": "en-GB-SoniaNeural", "translation": "French",
                                             "translation_voice": "", "secondary": "German",
                                             "secondary_voice": "de-DE-KatjaNeural"})

    def test_a_new_language_borrows_the_translation_language_when_it_may(self):
        arabic = {"defaults": {"translation_language": "Arabic"}, "voices": {"translation": "ar-SA-ZariyahNeural",
                                                                              "secondary": "fr-FR-DeniseNeural"},
                  }
        got = self.s(arabic, "en")
        self.assertEqual((got["voice"], got["translation"], got["translation_voice"]),
                         ("en-US-JennyNeural", "Arabic", "ar-SA-ZariyahNeural"))
        self.assertEqual((got["secondary"], got["secondary_voice"]), ("", ""))      # a second translation is never borrowed
        english = self.s({"defaults": {"translation_language": "English"},
                          "voices": {"translation": "en-US-AvaMultilingualNeural"}}, "en")
        self.assertEqual((english["translation"], english["translation_voice"]), ("", ""))   # must pick
        voice_of_another_language = self.s({"defaults": {"translation_language": "Arabic"},
                                            "voices": {"translation": "en-US-AvaMultilingualNeural"}}, "en")
        self.assertEqual(voice_of_another_language["translation_voice"], "")

    def test_a_choice_made_in_settings_is_never_overruled(self):
        cfg = {"defaults": {"translation_language": "Arabic"}, "languages": {"en": {"translation": ""}}}
        self.assertEqual(self.s(cfg, "en")["translation"], "")        # "(choose one)" stays a choice to make
        self.assertEqual(self.s({"languages": {"en": "garbage"}}, "en")["voice"], "en-US-JennyNeural")

    def test_level_labels_name_the_language(self):
        self.assertEqual(prompts.level_label("Native", "de"), prompts.LEVEL_LABELS["Native"])
        self.assertEqual(prompts.level_label("Native", "en"), "Native: real spoken English")
        self.assertEqual(prompts.level_label("B1", "en"), "B1: Intermediate")


if __name__ == "__main__":
    unittest.main(verbosity=1)
