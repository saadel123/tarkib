#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Offline unit tests for the deterministic guards. No Anki, no network, no quota.

    python3 tests/test_guards.py

The aqt/anki modules are stubbed so the pipeline imports outside Anki. Anything that talks to a provider is out of scope here; see docs/testing.md.
"""
import json, os, sys, types, unittest
for _n in ("aqt", "aqt.qt", "aqt.utils", "aqt.operations", "anki", "anki.collection", "anki.notes", "anki.hooks"):
    sys.modules.setdefault(_n, types.ModuleType(_n))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline import generate as g, prompts, providers  # noqa: E402


class SentenceLikePatterns(unittest.TestCase):
    """The Native grammar call can return whole sentences instead of patterns."""
    DE = ["Kannst du mir bitte mal den Auftrag schicken?",
          "Wir bestätigen hiermit die Beauftragung des Projekts zum 1. Oktober."]

    def test_whole_sentence_is_dropped(self):
        self.assertTrue(g._sentence_like("Kannst du mir bitte mal den Auftrag schicken?", self.DE))

    def test_truncated_sentence_is_dropped(self):
        self.assertTrue(g._sentence_like("Wir bestätigen hiermit die Beauftragung des …", self.DE))
        self.assertTrue(g._sentence_like("Wir bestätigen hiermit die Beauftragung des ...", self.DE))

    def test_sentence_with_a_gap_is_dropped(self):
        self.assertTrue(g._sentence_like("Kano tiri mal la ... sendi?", ["Kano tiri mal la zara sendi?"]))

    def test_real_short_patterns_pass(self):
        for pat in ("warten auf (+Akk)", "eine Entscheidung treffen", "Wo ist ...?", "um ... zu + Infinitiv",
                    "jemandem etwas geben (+Dat, +Akk)", "Könnten Sie ...? (formell)", "den Auftrag schicken (+Akk)"):
            self.assertFalse(g._sentence_like(pat, self.DE), pat)

    def test_fragment_of_a_short_sentence_passes(self):
        # a real gloss can cover most of a five-word sentence without being the sentence
        self.assertFalse(g._sentence_like("turn on the light", ["Will you turn on the light?"]))
        self.assertFalse(g._sentence_like("ein gutes Angebot", ["Du hast ein gutes Angebot."]))
        self.assertTrue(g._sentence_like("Wie alt bist du?", ["Wie alt bist du?", "Wie alt sind Sie?"]))

    def test_validate_end_to_end(self):
        card = {"word": "die Beauftragung", "example_casual": self.DE[0], "example_formal": self.DE[1],
                "example_casual_en": "Can you send me the order?", "example_formal_en": "We hereby confirm the commissioning.",
                "grammar_patterns": [self.DE[1], "den Auftrag schicken (+Akk)"],
                "grammar_patterns_en": ["Can you send me the order?", "to send the order"]}
        g._validate_grammar_patterns(card)
        self.assertEqual(card["grammar_patterns"], ["den Auftrag schicken (+Akk)"])
        self.assertEqual(card["grammar_patterns_en"], ["to send the order"])


class KnownLanguage(unittest.TestCase):
    """An unknown language name told the model to write in 'Chihasa', and it did."""

    def test_english_and_aliases(self):
        for v in ("English", "english", " en ", "Englisch"):
            self.assertEqual(g._known_language(v, "English"), ("English", None))

    def test_listed_language_any_case(self):
        self.assertEqual(g._known_language("arabic", "English"), ("Arabic", None))
        self.assertEqual(g._known_language("Chinese (simplified)", "English"), ("Chinese (Simplified)", None))

    def test_unknown_falls_back_with_warning(self):
        name, warn = g._known_language("Chihasa", "English")
        self.assertEqual(name, "English"); self.assertIn("Chihasa", warn)

    def test_empty_is_fallback_without_warning(self):
        self.assertEqual(g._known_language("", "English"), ("English", None))
        self.assertEqual(g._known_language(None, ""), ("", None))


class InputGate(unittest.TestCase):
    """A made-up word must not come back as a German noun with two fluent sentences around it."""

    def test_explicit_false_refuses(self):
        for v in (False, "false", "False", "0", "no", "nein"):
            self.assertTrue(g._input_not_german({"input_is_german": v}), repr(v))

    def test_true_or_missing_passes(self):
        for card in ({"input_is_german": True}, {"input_is_german": "true"}, {}, {"input_is_german": None}):
            self.assertFalse(g._input_not_german(card), repr(card))

    def test_friendly_message(self):
        title, body, kind = providers.friendly_error(RuntimeError('not german: "Blorptex"; suggestion "der Termin"'))
        self.assertEqual(title, "That does not look like German")
        self.assertEqual(kind, "retry")
        self.assertIn("Blorptex", body); self.assertIn("der Termin", body)

    def test_friendly_message_without_suggestion(self):
        title, body, kind = providers.friendly_error(RuntimeError('not german: "xqzv"; suggestion ""'))
        self.assertNotIn("Did you mean", body)

    def test_schema_carries_the_keys_in_both_prompts(self):
        for prompt in (prompts.SYSTEM_MAIN, prompts.SYSTEM_MAIN_LEVELED):
            self.assertIn('"input_is_german":true', prompt)
            self.assertIn('"input_suggestion":""', prompt)


class PatternInText(unittest.TestCase):
    def test_irregular_and_separable_forms(self):
        cases = [("helfen bei (+Dat)", "weil sie mir beim übersetzen hilft.", True),
                 ("teilnehmen an (+Dat)", "sie nimmt an dem kurs teil.", True),
                 ("aufpassen auf (+Akk)", "hast du auf die kinder aufgepasst?", True),
                 ("sich ändern", "der termin hat sich plötzlich geändert.", True),
                 ("um ... zu + Infinitiv", "ich lerne, um besser zu sprechen.", True),
                 ("denken an (+Akk)", "wir treffen uns an der brücke.", False),
                 ("warten auf (+Akk)", "ich gehe nach hause.", False),
                 ("W-Frage: Verb auf Position 2", "wie spät ist es?", False)]
        for pat, txt, want in cases:
            self.assertEqual(g._pattern_in_text(pat, txt), want, pat)

    def test_self_referential_phrase(self):
        self.assertTrue(g._self_referential("zwei Fliegen mit einer Klappe schlagen (Redewendung)", "zwei Fliegen mit einer Klappe schlagen"))
        self.assertFalse(g._self_referential("die Nase voll haben von (+Dat)", "die Nase voll haben"))
        self.assertFalse(g._self_referential("Zeit haben", "Zeit"))


class ImageKeyword(unittest.TestCase):
    def test_denied_scene_is_replaced_by_the_word(self):
        out = g._clean_image_keyword("friends drinking beer in a bar", "die Freundschaft", "friendship")
        self.assertNotIn("beer", out.lower()); self.assertNotIn("bar", out.lower().split())

    def test_clean_keyword_untouched(self):
        self.assertEqual(g._clean_image_keyword("train at the station", "der Zug", "train"), "train at the station")


class GuardOrderAndOverride(unittest.TestCase):
    """The refusal must run before the word-mismatch guard, need a second opinion, and be overridable."""

    def test_two_agreeing_verdicts_refuse_with_one_extra_call(self):
        calls = []
        def call_main(strict):
            calls.append(strict); return {"word": "der Tisch", "input_is_german": False, "input_suggestion": "der Tisch"}
        with self.assertRaises(RuntimeError) as cm:
            g._refuse_if_not_german({"word": "der Tisch", "input_is_german": False, "input_suggestion": "der Tisch"}, call_main, "table")
        self.assertIn('not german: "table"', str(cm.exception)); self.assertIn('"der Tisch"', str(cm.exception))
        self.assertEqual(calls, [True])

    def test_a_single_hallucinated_false_does_not_refuse(self):
        good = {"word": "das Meeting", "input_is_german": True}
        out = g._refuse_if_not_german({"word": "das Meeting", "input_is_german": False}, lambda strict: good, "das Meeting")
        self.assertIs(out, good)

    def test_force_skips_the_check_and_the_extra_call(self):
        card = {"word": "Moin", "input_is_german": False}
        out = g._refuse_if_not_german(card, lambda strict: self.fail("must not be called"), "Moin", force=True)
        self.assertIs(out, card)

    def test_quotes_in_the_input_cannot_break_the_message(self):
        with self.assertRaises(RuntimeError) as cm:
            g._refuse_if_not_german({"input_is_german": False, "input_suggestion": 'a "b"'}, lambda strict: None, 'x"y')
        title, body, kind = providers.friendly_error(cm.exception)
        self.assertEqual(kind, "retry"); self.assertIn("x'y", body); self.assertIn("a 'b'", body)

    def test_german_side_empty_means_english_side_empty(self):
        card = {"word": "alt", "example_casual": "Wie alt bist du?", "example_formal": "Wie alt sind Sie?",
                "example_casual_en": "How old are you?", "example_formal_en": "How old are you?",
                "grammar_patterns": ["Wie alt bist du?", "Wie alt sind Sie?"], "grammar_patterns_en": ["how old", "informal you"]}
        g._validate_grammar_patterns(card)
        self.assertEqual(card["grammar_patterns"], []); self.assertEqual(card["grammar_patterns_en"], [])

    def test_openers_survive_short_sentences(self):
        self.assertFalse(g._sentence_like("Es tut mir leid, dass", ["Es tut mir leid, dass ich gehe."]))
        self.assertFalse(g._sentence_like("Sehr geehrte Damen und Herren", ["Sehr geehrte Damen und Herren, danke."]))
        self.assertTrue(g._sentence_like("Wir bestätigen hiermit die Beauftragung des ...", ["Wir bestätigen hiermit die Beauftragung des Projekts."]))
        self.assertTrue(g._sentence_like("Kannst du mir bitte mal den Auftrag schicken", ["Kannst du mir bitte mal den Auftrag schicken?"]))

    def test_language_aliases_and_odd_config_values(self):
        self.assertEqual(g._known_language("ar", "English"), ("Arabic", None))
        self.assertEqual(g._known_language("français", "English"), ("French", None))
        self.assertEqual(g._known_language("farsi", "English"), ("Persian", None))
        self.assertEqual(g._known_language(12, "English")[0], "English")
        self.assertEqual(g._known_language(["x"], "")[0], "")


class TypoQuestion(unittest.TestCase):
    """'benachrichtigong' used to end in 'Couldn't match your word' although the card for
    die Benachrichtigung was already made."""

    def test_near_misses_are_typos(self):
        self.assertTrue(g._looks_like_typo("benachrichtigong", "benachrichtigung"))
        self.assertTrue(g._looks_like_typo("tisch", "fisch"))          # a question is right here too
        self.assertTrue(g._looks_like_typo("wohnug", "wohnung"))

    def test_different_words_are_not(self):
        self.assertFalse(g._looks_like_typo("tisch", "stuhl"))
        self.assertFalse(g._looks_like_typo("zug", "bahn"))
        self.assertFalse(g._looks_like_typo("blorptex", "termin"))

    def test_short_words_never_count(self):
        self.assertFalse(g._looks_like_typo("an", "am"))


class PatternRank(unittest.TestCase):
    """The value order for grammar patterns; filler is dropped, the rest ranked."""

    def test_kept_with_rank(self):
        for pat, rank in (("warten auf (+Akk)", 1), ("sich freuen auf (+Akk)", 1), ("teilnehmen an (+Dat)", 1),
                          ("Angst vor (+Dat)", 2), ("Interesse an (+Dat)", 2), ("helfen (+Dat)", 3),
                          ("jemandem etwas geben (+Dat, +Akk)", 3), ("eine Entscheidung treffen", 4),
                          ("die Benachrichtigung erhalten", 4), ("den Auftrag schicken", 4), ("Bescheid geben", 4),
                          ("mitteilen, dass", 5), ("Es ist ärgerlich, dass ...", 5), ("um ... zu + Infinitiv", 6),
                          ("sich beeilen", 7), ("anrufen (trennbar)", 7), ("hat + Partizip II (Perfekt)", 8),
                          ("Könnten Sie ...? (Konjunktiv II)", 8), ("den Kandidaten (n-Deklination)", 8)):
            self.assertEqual(g._pattern_rank(pat), rank, pat)

    def test_only_the_two_seen_shapes_are_dropped(self):
        for pat in ("ist wirklich hervorragend", "Arzttermin bestätigt ist", "Verb an Position 2", "Frage: Verb an Position 2"):
            self.assertIsNone(g._pattern_rank(pat), pat)

    def test_everything_else_anchored_is_kept_at_the_lowest_rank(self):
        # shapes a stricter filter would reject are still worth learning: they stay, ranked last
        for pat in ("kaufen (+Akk)", "brauchen (+Akk)", "das Wetter ist schön", "gesund sein", "dein/Ihr + Nomen",
                    "einen Balkon (Akk.)", "sehr + Adjektiv", "sehr groß", "Können Sie ...?", "gut schlafen",
                    "einen Termin haben", "keine Ahnung haben", "Perfekt mit haben", "Teil der Gemeinschaft werden",
                    "wissen, woran man ist", "indirekte Frage: wie ... entstanden ist",
                    "Possessivartikel (Ihre/deine)", "zu + Adjektiv (zu laut)"):
            self.assertIsNotNone(g._pattern_rank(pat), pat)
        self.assertEqual(g._pattern_rank("kaufen (+Akk)"), 9)

    def test_selection_keeps_the_three_best_and_stays_parallel(self):
        card = {"word": "die Benachrichtigung",
                "example_casual": "Hey, ich hab gerade die Benachrichtigung bekommen, dass unser Meeting morgen klappt.",
                "example_formal": "Anbei erhalten Sie die Benachrichtigung, dass Ihr Arzttermin am 15. März bestätigt ist.",
                "example_casual_en": "Hey, I just got the notification that our meeting tomorrow works.",
                "example_formal_en": "Please find the notification that your appointment on March 15 has been confirmed.",
                "grammar_patterns": ["die Benachrichtigung bekommen", "die Benachrichtigung erhalten", "Arzttermin bestätigt ist"],
                "grammar_patterns_en": ["got the notification", "find the notification", "has been confirmed"]}
        g._validate_grammar_patterns(card)
        self.assertEqual(card["grammar_patterns"], ["die Benachrichtigung bekommen", "die Benachrichtigung erhalten"])
        self.assertEqual(card["grammar_patterns_en"], ["got the notification", "find the notification"])


class ReviewProposedTests(unittest.TestCase):
    """Signature-level regression tests for the helper guards."""
    def test_english_leak_matches_whole_tokens_only(self):
        self.assertEqual(g._has_english_leak("Ich habe the Termin vergessen."), "the")
        self.assertEqual(g._has_english_leak("Kannst du mir Help geben?"), "help")
        for german in ("Wir gehen heute ins Theater.", "Das Wetter ist hier sehr schoen.",
                       "Die Thermoskanne steht auf dem Tisch.", "Hast du Zeit?", "Was machst du?"):
            self.assertIsNone(g._has_english_leak(german), german)

    def test_english_leak_reports_the_first_token_and_tolerates_empty_fields(self):
        self.assertIsNone(g._has_english_leak(None, "", "Guten Morgen."))
        self.assertEqual(g._has_english_leak(None, "Er ist SORRY, and das ist alles."), "sorry")
        self.assertIsNone(g._has_english_leak())

    def test_emoji_field_blanks_garbage_and_expands_shortcodes(self):
        self.assertEqual(g._clean_emoji_field(":pencil:"), "\U0001f4dd")
        self.assertEqual(g._clean_emoji_field("  \U0001f697  "), "\U0001f697")
        self.assertEqual(g._clean_emoji_field("✉️"), "✉️")
        self.assertEqual(g._clean_emoji_field("Ἶ6"), "")
        self.assertEqual(g._clean_emoji_field(":unknown_thing:"), "")
        self.assertEqual(g._clean_emoji_field("نص"), "")
        self.assertEqual(g._clean_emoji_field(None), "")

    def test_sanitize_touches_emoji_fields_only_never_the_sentences(self):
        card = {"emoji": ":fire:", "emoji_casual": "Ἶ6", "emoji_formal": "\U0001f4bc",
                "example_casual": "Gut :thumbs_up: gemacht.",
                "example_formal": "Wir bestätigen den Termin.",
                "example_casual_en": "Well done.", "grammar_patterns": ["warten auf (+Akk)"]}
        g._sanitize_card_emojis(card)
        self.assertEqual(card["emoji"], "\U0001f525")
        self.assertEqual(card["emoji_casual"], "")
        self.assertEqual(card["emoji_formal"], "\U0001f4bc")
        self.assertEqual(card["example_casual"], "Gut \U0001f44d gemacht.")
        self.assertEqual(card["example_formal"], "Wir bestätigen den Termin.")
        self.assertEqual(card["grammar_patterns"], ["warten auf (+Akk)"])

    def test_word_object_survives_the_type_coercion_that_runs_before_it(self):
        card = g._coerce_card_types({"word": {"value": "der Termin"}, "translation_en": "appointment"})
        self.assertEqual(g._normalize_word_field(card), "der Termin")
        card2 = g._coerce_card_types({"word": {"text": "die Frage"}})
        self.assertEqual(g._normalize_word_field(card2), "die Frage")

    def test_morphology_hides_the_genitive_at_a1_and_a2(self):
        m = {"pos": "noun", "article": "der", "plural": "die Termine", "genitive": "des Termins"}
        for lvl in ("A1", "A2"):
            out = g._morphology_html(m, lvl)
            self.assertIn("Pl. die Termine", out)
            self.assertNotIn("Gen.", out)
        for lvl in ("B1", "Native", None):
            self.assertIn("Gen. des Termins", g._morphology_html(m, lvl))

    def test_morphology_drops_the_no_plural_marker_and_escapes_html(self):
        out = g._morphology_html({"pos": "noun", "article": "der", "plural": "—",
                                  "genitive": "des Durstes"}, "B1")
        self.assertNotIn("—", out)
        self.assertIn("Gen. des Durstes", out)
        self.assertIn('<span class="g-der">der</span>', out)
        bad = g._morphology_html({"pos": "noun", "article": "die", "plural": "die <b>Frauen</b>"}, "C1")
        self.assertNotIn("<b>", bad)
        self.assertIn("&lt;b&gt;", bad)

    def test_morphology_degrades_to_empty_instead_of_raising(self):
        for m in (None, "noun", ["der"], 7, {}, {"pos": "other"},
                  {"pos": "noun"}, {"pos": "verb"}, {"pos": "verb", "separable": False}):
            self.assertEqual(g._morphology_html(m, "B1"), "", repr(m))
        self.assertEqual(g._morphology_html({"pos": "verb", "present_3sg": "holt ab",
                                             "past_3sg": "holte ab", "perfect": "hat abgeholt",
                                             "separable": True}, "B1"),
                         '<div class="morph">holt ab · holte ab · hat abgeholt · trennbar</div>')

    def test_letter_hint_never_gives_the_answer_away(self):
        self.assertEqual(g._letter_hint("Supermarkt"), "Sup...")
        self.assertEqual(g._letter_hint("kommt"), "k...")
        self.assertEqual(g._letter_hint("kommt", beginner=True), "ko...")
        self.assertEqual(g._letter_hint("Buch", beginner=True), "Bu...")
        self.assertEqual(g._letter_hint("ist", beginner=True), "i...")
        for w in ("Supermarkt", "kommt", "Buch", "ist", "ab"):
            for beg in (False, True):
                hint = g._letter_hint(w, beg)
                self.assertTrue(hint.endswith("..."), (w, beg))
                self.assertLess(len(hint) - 3, len(w), (w, beg, hint))

    def test_cloze_text_only_wraps_the_answer_and_keeps_the_sentence(self):
        import re
        cases = [("Ich gehe in den Supermarkt.", "den Supermarkt", "single_word"),
                 ("Die Frage zum Thema ist wichtig.", "zum", "noun_prep"),
                 ("Wir müssen eine Entscheidung treffen.", "treffen", "nvv"),
                 ("Er hat die Nase voll davon.", "Nase, voll", "idiom")]
        for sentence, answer, case in cases:
            text = g.build_cloze_text(sentence, answer, case)
            self.assertIn("{{c1::", text, (sentence, answer))
            for ans in [a.strip() for a in answer.split(",") if a.strip()]:
                self.assertIn("{{c1::" + ans, text, ans)
            plain = re.sub(r"\{\{c1::([^:}]*)(?:::[^}]*)?\}\}", r"\1", text)
            self.assertEqual(plain, sentence, (case, text))

    def test_cloze_never_blanks_a_fragment_of_another_word(self):
        # audio.split_for_cloze already uses \b for exactly this reason; the text must agree with it.
        self.assertEqual(g.build_cloze_text("Damit fahre ich mit dem Bus.", "mit", "single_word"),
                         "Damit fahre ich {{c1::mit::m...}} dem Bus.")
        self.assertEqual(g.build_cloze_text("Wir haben dann Zeit an dem Tag.", "an", "noun_prep"),
                         "Wir haben dann Zeit {{c1::an}} dem Tag.")

    def test_idiom_cloze_hints_every_blank_and_hides_the_meaning(self):
        text = g.build_cloze_text("Er hat die Nase voll davon.", "Nase, voll", "idiom",
                                  "genug von etwas haben")
        self.assertNotIn("genug von etwas haben", text)
        self.assertIn("{{c1::Nase::N...}}", text)
        self.assertIn("{{c1::voll::v...}}", text)
        self.assertNotIn("{{c1::Nase}}", text)

    def test_parse_json_recovers_json_wrapped_in_prose_and_fences(self):
        self.assertEqual(providers.parse_json(
            'Sure! Here is the card:\n```json\n{"word": "der Termin", "tags": ["Alltag"]}\n```\nHope it helps!'),
            {"word": "der Termin", "tags": ["Alltag"]})
        self.assertEqual(providers.parse_json('```\n{"x": 1}\n```'), {"x": 1})
        self.assertEqual(providers.parse_json('{"a": {"b": "c"}}'), {"a": {"b": "c"}})

    def test_parse_json_repairs_unescaped_quotes_inside_a_value(self):
        self.assertEqual(providers.parse_json('{"explanation_de": "Man sagt "Guten Tag" dazu.", "n": 1}'),
                         {"explanation_de": 'Man sagt "Guten Tag" dazu.', "n": 1})
        self.assertEqual(providers.repair_json('{"a": 1}'), '{"a": 1}')
        self.assertEqual(providers.repair_json('{"a": '), '{"a": ')

    def test_parse_json_raises_a_provider_error_the_ui_can_explain(self):
        for bad in ("", None, "no json here at all", "[1, 2, 3]", '"just a string"'):
            with self.assertRaises(providers.ProviderError, msg=repr(bad)):
                providers.parse_json(bad)
        title, _body, kind = providers.friendly_error(
            providers.ProviderError("could not parse provider JSON: expected an object, got list"))
        self.assertEqual((title, kind), ("Unreadable response", "settings"))

    def test_parse_wait_reads_every_unit_the_providers_send(self):
        self.assertAlmostEqual(providers._parse_wait("Rate limit reached, please try again in 7.66s"), 7.66)
        self.assertAlmostEqual(providers._parse_wait("try again in 232.599ms"), 0.232599)
        self.assertAlmostEqual(providers._parse_wait("try again in 2m30s"), 150.0)
        self.assertAlmostEqual(providers._parse_wait("try again in 16h3m10s"), 57790.0)
        self.assertAlmostEqual(providers._parse_wait("try again in 1m"), 60.0)
        self.assertLess(providers._parse_wait("try again in 232.599ms"), 30)
        self.assertGreater(providers._parse_wait("try again in 16h3m10s"), 30)

    def test_parse_wait_falls_back_instead_of_raising(self):
        for body in ("", None, "no hint at all", "try again in a minute", "429 Too Many Requests"):
            self.assertEqual(providers._parse_wait(body), 5.0, repr(body))
        self.assertEqual(providers._parse_wait("nothing here", default=12.5), 12.5)

    def test_classify_tts_error_and_worst_category(self):
        from pipeline import audio
        self.assertEqual(audio.classify_tts_error(Exception("WS handshake failed: 429"))[0], "rate_limit")
        self.assertEqual(audio.classify_tts_error(Exception("server closed 1008"))[0], "rate_limit")
        self.assertEqual(audio.classify_tts_error(Exception("HTTP Error 403: Forbidden"))[0], "auth")
        self.assertEqual(audio.classify_tts_error(Exception("1007 invalid token"))[0], "auth")
        self.assertEqual(audio.classify_tts_error(Exception("connection reset by peer"))[0], "network")
        self.assertEqual(audio.classify_tts_error(Exception(""))[0], "network")
        for cat, msg in (audio.classify_tts_error(Exception("429")),
                         audio.classify_tts_error(Exception("403")),
                         audio.classify_tts_error(Exception("boom"))):
            self.assertEqual(msg, audio.TTS_ERROR_MESSAGES[cat])
        self.assertEqual(audio.worse_category("network", "auth"), "auth")
        self.assertEqual(audio.worse_category("auth", "network"), "auth")
        self.assertEqual(audio.worse_category("network", "rate_limit"), "rate_limit")
        self.assertEqual(audio.worse_category(None, "network"), "network")
        self.assertEqual(audio.worse_category("network", None), "network")

    def test_image_magic_byte_guard(self):
        from pipeline import images
        for ok in (b"\xff\xd8\xff\xe0" + b"\x00" * 16, b"\x89PNG\r\n\x1a\n" + b"\x00" * 8,
                   b"GIF87a" + b"\x00" * 8, b"GIF89a" + b"\x00" * 8,
                   b"RIFF\x24\x00\x00\x00WEBPVP8 "):
            self.assertTrue(images._looks_like_raster(ok), ok[:8])
        for bad in (b"", None, b"\xff\xd8", b"<svg xmlns='http://www.w3.org/2000/svg'/>",
                    b"<!DOCTYPE html><html>403 Forbidden</html>", b'{"error": "quota"}',
                    b"RIFF\x24\x00\x00\x00WAVEfmt ", b"%PDF-1.4"):
            self.assertFalse(images._looks_like_raster(bad), repr(bad)[:40])

    def test_safe_name_is_always_a_usable_jpg_filename(self):
        from pipeline import images
        for kw in ("woman cooking in a big kitchen with fresh vegetables", "", None,
                   "///", "Männer beim Fußball", "a/b\\c:d*e?f"):
            name = images._safe_name(kw)
            self.assertTrue(name.startswith("img_"), name)
            self.assertTrue(name.endswith(".jpg"), name)
            self.assertFalse(any(c in name for c in '/\\:*?"<>|'), name)
            self.assertGreater(len(name), len("img_.jpg"))


class ReleaseSecurity(unittest.TestCase):
    """Keys stay on their host, remote http is refused, tags never carry markup."""

    def test_remote_http_base_url_is_refused_localhost_is_allowed(self):
        with self.assertRaises(providers.ProviderError):
            providers._base_url({"base_url": "http://example.com/v1"})
        self.assertEqual(providers._base_url({"base_url": "http://localhost:11434/v1/"}), "http://localhost:11434/v1")
        self.assertEqual(providers._base_url({"base_url": "https://api.groq.com/openai/v1"}), "https://api.groq.com/openai/v1")
        self.assertEqual(providers._base_url({}), "https://api.openai.com/v1")
        title, _, kind = providers.friendly_error(providers.ProviderError("insecure base URL: http://x"))
        self.assertEqual((title, kind), ("Base URL must use https", "settings"))

    def _redirect(self, old, new, headers):
        import urllib.request
        req = urllib.request.Request(old, headers=headers)
        return providers._KeepKeyHome().redirect_request(req, None, 302, "Found", {}, new)

    def test_redirect_to_another_host_drops_the_key(self):
        new = self._redirect("https://api.groq.com/openai/v1/models", "https://evil.example/models",
                             {"Authorization": "Bearer gsk_x", "User-Agent": "ua"})
        self.assertNotIn("authorization", {h.lower() for h in new.headers})
        self.assertIn("User-agent", new.headers)

    def test_redirect_down_to_http_drops_the_key(self):
        new = self._redirect("https://api.anthropic.com/v1/models", "http://api.anthropic.com/v1/models",
                             {"x-api-key": "k"})
        self.assertNotIn("x-api-key", {h.lower() for h in new.headers})

    def test_redirect_on_the_same_https_host_keeps_the_key(self):
        new = self._redirect("https://api.groq.com/openai/v1/models", "https://api.groq.com/openai/v1/models/",
                             {"Authorization": "Bearer gsk_x"})
        self.assertIn("authorization", {h.lower() for h in new.headers})

    def test_tags_are_stripped_of_markup(self):
        src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "anki_io.py"),
                   encoding="utf-8").read()
        ns = {}
        exec(src.split("def write_bundle")[0].replace("from .notetypes import", "#"), ns)
        self.assertEqual(ns["_clean_tags"](["case_x<img/src/onerror=alert(1)>", "a b", "a_b", ""]),
                         ["case_ximg/src/onerror=alert(1)", "a_b"])

    def test_unknown_cloze_case_is_not_a_tag(self):
        self.assertIn("single_word", g._CLOZE_CASES)
        self.assertNotIn("x<img>", g._CLOZE_CASES)


class PromoRules(unittest.TestCase):
    """The quiet pointers: three thank-yous in an install, and a decks hint that stays polite."""

    def setUp(self):
        from ui import promo_rules
        self.r = promo_rules

    def test_thank_you_only_at_the_milestones(self):
        shown = [n for n in range(1, 1001) if self.r.should_thank(n, {})]
        self.assertEqual(shown, [50, 200, 500])

    def test_thank_you_respects_the_opt_out(self):
        self.assertFalse(self.r.should_thank(50, {"hide_support_thanks": True}))

    def test_hint_waits_for_the_fifth_card(self):
        self.assertFalse(self.r.hint_should_show({"cards_added": 4}, False, False))
        self.assertTrue(self.r.hint_should_show({"cards_added": 5}, False, False))

    def test_hint_stops_after_three_showings_or_x(self):
        self.assertFalse(self.r.hint_should_show({"cards_added": 9, "decks_hint_shows": 3}, False, False))
        self.assertFalse(self.r.hint_should_show({"cards_added": 9, "decks_hint_done": True}, False, False))

    def test_hint_never_when_decks_imported_or_blocked(self):
        self.assertFalse(self.r.hint_should_show({"cards_added": 9}, True, False))
        self.assertFalse(self.r.hint_should_show({"cards_added": 9}, False, True))

    def test_footer_link_free_a1_then_all_levels(self):
        free, shop = "https://ko-fi.com/s/a1", "https://ko-fi.com/tarkib/shop"
        self.assertEqual(self.r.footer_decks_link(False, free, shop), "free")
        self.assertEqual(self.r.footer_decks_link(True, free, shop), "shop")      # never hidden once a deck is in
        self.assertEqual(self.r.footer_decks_link(True, free, ""), "free")       # no shop URL: the free A1 link
        self.assertIsNone(self.r.footer_decks_link(False, "", shop))            # no URL for the link it needs
        self.assertIsNone(self.r.footer_decks_link(True, "", ""))

    def test_hint_survives_missing_or_odd_stats(self):
        self.assertFalse(self.r.hint_should_show(None, False, False))
        self.assertTrue(self.r.hint_should_show({"cards_added": "7", "decks_hint_shows": None}, False, False))


class TranslationVoiceDefault(unittest.TestCase):
    """Learners want to hear the German. The translation is read aloud only once the user picks its voice."""

    def test_default_config_reads_only_the_german_aloud(self):
        with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json"),
                  encoding="utf-8") as f:
            voices = json.load(f)["voices"]
        self.assertTrue(voices["target"].startswith("de-"))
        self.assertEqual(voices["translation"], "")
        self.assertEqual(voices["secondary"], "")


if __name__ == "__main__":
    unittest.main(verbosity=1)
