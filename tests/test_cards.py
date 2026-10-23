#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Golden cards: every kind of card Tarkib makes, end to end, checked two ways. No Anki, no network, no key.

    python3 tests/test_cards.py
    UPDATE_GOLDEN=1 python3 tests/test_cards.py    after a change you meant, then read `git diff tests/golden`
    python3 tests/preview_cards.py                 every card in a browser page: out/card-preview.html

The scenarios (tests/card_scenarios.py) run the real build_card and anki_io.write_bundle with a scripted
AI, fake pictures and fake voices. Each one is checked by:

1. the card rules: what every stored card keeps, whatever the AI wrote. The HTML is balanced, AI text
   is escaped, every media file is referenced and every reference has its file, there is no empty
   box, the tags are clean and the cloze blanks a whole word. A rule a scenario breaks today on
   purpose is listed in KNOWN_ISSUES, and the test fails once the issue is gone, so the list stays true.
2. its golden file, tests/golden/cards/<language>/<scenario>.txt: every message sent to the AI (system
   prompts by their frozen name, see test_prompts.py), the picture search, what was read aloud and in
   which voice, the stored notes and the warnings for the dialog. Any change is a diff to read.
"""
import html.parser
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import card_scenarios as cs  # noqa: E402
import golden  # noqa: E402

# Rule failures a scenario shows today on purpose, as message prefixes, e.g.
#     "phrase_a2": ["front: "],
# Fixing one makes its test fail until the line is removed here. Empty since 2026-10-23, when the three
# issues the first run found were fixed: "Wie spät ist es?." on the front, empty boxes when the AI
# leaves fields out, and a pattern sent as an object shifting the glosses (PatternPairs below).
KNOWN_ISSUES = {
}

_VOID = {"img", "br", "hr", "input", "meta", "link", "source", "wbr"}
_TAGS = {"div", "span", "img", "br"}           # what the add-on itself puts into a field
_ATTRS = {"class", "style", "src"}


class _Html(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.problems, self.elements = [], [], []

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, attrs))
        if tag not in _VOID:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.elements.append((tag, attrs))

    def handle_endtag(self, tag):
        if tag in _VOID:
            return
        if self.stack and self.stack[-1] == tag:
            self.stack.pop()
        else:
            self.problems.append("closes <%s> that is not open" % tag)


def _parse(text):
    p = _Html()
    p.feed(text or "")
    p.close()
    return p


def card_problems(s, r):
    """Every card rule the stored notes of scenario `s` break, as readable lines."""
    out = list("script: " + v for v in r["violations"])
    for c in r["calls"]:
        if cs.prompt_name(c["system"], s) is None:
            out.append("prompt: a %s call used a system prompt that is not frozen in tests/golden/prompts" % c["kind"])
    if r["error"]:
        return out
    notes = {n["type"]: n for n in r["notes"]}
    main, clz = notes.get("main"), notes.get("cloze")
    if main is None:
        return out + ["notes: no main note was stored"]
    files = set(r["files"])
    used = set()
    for note in r["notes"]:
        for field, value in note["fields"].items():
            where = "%s %s" % (note["type"], field)
            p = _parse(value)
            out += ["html: %s %s" % (where, x) for x in p.problems]
            if p.stack:
                out.append("html: %s leaves <%s> open" % (where, ">, <".join(p.stack)))
            for tag, attrs in p.elements:
                if tag not in _TAGS:
                    out.append("markup: %s holds a <%s> element" % (where, tag))
                for k, v in attrs:
                    if k not in _ATTRS or "javascript:" in (v or "").lower():
                        out.append("markup: %s has the attribute %s" % (where, k))
                    if tag == "img" and k == "src":
                        used.add(v)
                        if v not in files:
                            out.append("media: %s shows a picture that was not stored: %s" % (where, v))
            for name in re.findall(r"\[sound:([^\]]*)\]", value):
                used.add(name)
                if name not in files:
                    out.append("media: %s plays a sound that was not stored: %r" % (where, name))
            for bad in ("@@", "{{IMAGE}}", "—", "–"):
                if bad in value:
                    out.append("leftover: %s contains %r" % (where, bad))
            if re.search("[\u064B-\u0652\u0670]", value):
                out.append("arabic: %s keeps a diacritic (Arabic is written without them)" % where)
    for name in sorted(files - used):
        out.append("media: %s was stored but no field uses it" % name)

    back = main["fields"].get("Back", "")
    front = main["fields"].get("Front", "")
    if front != front.strip() or "  " in front:
        out.append("front: %r has a stray space" % front)
    if not re.search(r"[.?!…]$", front):
        out.append("front: %r does not end with a full stop or its own mark" % front)
    if re.search(r"[?!…]\.$", front) or (front.endswith("..") and not re.search(r"(?<!\.)\.\.\.$", front)):
        out.append("front: %r ends with a doubled mark" % front)
    if re.search(r'<div class="patterns-box"><div class="patterns-label">[^<]*</div></div>', back):
        out.append("empty: a patterns box without a pattern")
    if '<div class="morph"></div>' in back:
        out.append("empty: an empty word line")
    for kind in re.findall(r'<div class="sentence (\w+)"><span class="emoji">[^<]*</span>\s*</div>', back):
        out.append("empty: an empty %s sentence" % kind)
    if re.search(r'<div class="explanation">👉 [^\w<]*</div>', back):
        out.append("empty: an empty explanation")
    if re.search(r'<div class="card-translation"[^>]*>(<span class="level-chip[^>]*>[^<]*</span> )?\S*\s*</div>', back):
        out.append("empty: no translation on the top line")
    if re.search(r'<div class="secondary-word"[^>]*>\S*\s*</div>', back):
        out.append("empty: an empty second-language word")
    sounds = re.findall(r"\[sound:[^\]]*\]", back)
    if sounds and not re.search(r"<br>(\[sound:[^\]]*\])+$", back):
        out.append("audio: the sound buttons are not at the end of the back")

    tags = main["tags"]
    if [t for t in tags if t.startswith("Level::")] != ["Level::%s" % s.level]:
        out.append("tags: the main note does not carry exactly Level::%s: %s" % (s.level, tags))
    formal, ftag = "formal-mark" in back, cs.languages.get(s.language)["formal_tag"]
    if formal != (ftag in tags):
        out.append("tags: %s is %s but the card %s formal" % (ftag, "missing" if formal else "there",
                                                               "is" if formal else "is not"))
    for note in r["notes"]:
        for t in note["tags"]:
            if re.search(r"\s|[<>&\"']", t):
                out.append("tags: %s note tag %r has a space or markup" % (note["type"], t))

    if clz is not None:
        text = clz["fields"].get("Text", "")
        answers = re.findall(r"\{\{c1::(.*?)(?:::[^}]*)?\}\}", text)
        plain = re.sub(r"\{\{c1::(.*?)(?:::[^}]*)?\}\}", r"\1", text)
        if not answers:
            out.append("cloze: the cloze text has no blank")
        for a in answers:
            if not re.search(r"(?<![\w])" + re.escape(a) + r"(?![\w])", plain):
                out.append("cloze: the blank %r is not a whole word of its sentence" % a)
        if clz["deck"] != main["deck"] + "::Cloze":
            out.append("cloze: deck %r is not under the main deck %r" % (clz["deck"], main["deck"]))
        ctags = clz["tags"]
        cases = [t for t in ctags if t.startswith("case_")]
        if "cloze" not in ctags or len(cases) != 1 or cases[0][5:] not in cs.generate.RULES[s.language]["cloze_cases"]:
            out.append("cloze: tags %s need cloze and one known case_" % ctags)
        if [t for t in ctags if t.startswith("Level::")] != ["Level::%s" % s.level]:
            out.append("cloze: the cloze note does not carry exactly Level::%s" % s.level)

    lang = (s.settings.get("defaults") or {}).get("translation_language", "English")
    if lang == "Arabic" and not ("direction:rtl" in back and 'class="section arabic"' in back):
        out.append("rtl: the Arabic translation is not right to left")
    if s.options.get("secondary_language") == "Arabic" and '<div class="secondary-word">' not in back:
        out.append("rtl: the Arabic second-language word is not in its right-to-left box")
    return out


class PatternPairs(unittest.TestCase):
    """Each German pattern keeps its own gloss: the two lists pair up by position. Found by the
    messy_answer_b1 golden card (the card showed "Erfahrung haben" next to "experience with"), fixed
    2026-10-23: _coerce_card_types keeps every position of these two lists."""
    SENTENCES = {"word": "die Erfahrung", "example_casual": "Ich habe viel Erfahrung mit Kindern.",
                 "example_formal": "Sie haben Erfahrung mit Kunden."}

    def _pairs(self, de, en):
        card = dict(self.SENTENCES, grammar_patterns=de, grammar_patterns_en=en)
        cs.generate._validate_grammar_patterns(cs.generate._coerce_card_types(card))
        return list(zip(card["grammar_patterns"], card["grammar_patterns_en"]))

    def test_a_pattern_sent_as_an_object_keeps_its_own_gloss(self):
        self.assertEqual(self._pairs([{"pattern": "Erfahrung mit (+Dat)"}, "Erfahrung haben"],
                                     ["experience with", "to have experience"]),
                         [("Erfahrung mit (+Dat)", "experience with"), ("Erfahrung haben", "to have experience")])

    def test_an_empty_or_missing_entry_drops_its_pair_only(self):
        self.assertEqual(self._pairs(["", "Erfahrung haben"], ["experience with", "to have experience"]),
                         [("Erfahrung haben", "to have experience")])
        self.assertEqual(self._pairs([None, "Erfahrung haben"], ["experience with", "to have experience"]),
                         [("Erfahrung haben", "to have experience")])

    def test_other_lists_still_drop_what_is_not_text(self):
        card = cs.generate._coerce_card_types({"tags": ["Arbeit", {"x": 1}, "", "Bildung"],
                                               "casual_alternatives": ["falls nötig", None, " "]})
        self.assertEqual(card["tags"], ["Arbeit", "Bildung"])
        self.assertEqual(card["casual_alternatives"], ["falls nötig"])


class FrontLine(unittest.TestCase):
    """The main card's front: the emoji, the word, one end mark. "Wie spät ist es?." was the old front of
    every phrase that ends in a question or exclamation mark (fixed 2026-10-23)."""

    def test_one_end_mark(self):
        f = cs.generate._front
        self.assertEqual(f("🏰", "das Schloss"), "🏰 das Schloss.")
        self.assertEqual(f("⏰", "Wie spät ist es?"), "⏰ Wie spät ist es?")
        self.assertEqual(f("🍀", "Viel Glück!"), "🍀 Viel Glück!")
        self.assertEqual(f("❓", "Ich habe eine Frage."), "❓ Ich habe eine Frage.")
        self.assertEqual(f("🧭", "Entschuldigung, wo ist ...?"), "🧭 Entschuldigung, wo ist ...?")
        self.assertEqual(f("🙋", "Ich hätte gern …"), "🙋 Ich hätte gern …")

    def test_no_stray_space_and_escaped(self):
        f = cs.generate._front
        self.assertEqual(f("", "die Küche"), "die Küche.")
        self.assertEqual(f(None, "  die Küche  "), "die Küche.")
        self.assertEqual(f("💼", "Müller & Co"), "💼 Müller &amp; Co.")
        self.assertEqual(f("💼", "<b>x</b>"), "💼 &lt;b&gt;x&lt;/b&gt;.")


class CardRules(unittest.TestCase):
    """One test per scenario: the rules every stored card keeps."""


class GoldenCards(unittest.TestCase):
    """One test per scenario: the whole result against its golden file."""

    def test_no_stale_golden_cards(self):
        expected = ["cards/%s/%s.txt" % (s.language, s.name) for s in cs.SCENARIOS]
        self.assertEqual(golden.stale("cards", expected), [], "golden cards no scenario writes any more")

    def test_known_issues_name_real_scenarios(self):
        self.assertEqual(sorted(set(KNOWN_ISSUES) - set(cs.BY_NAME)), [])


_RESULTS = {}


def _result(s):
    if s.name not in _RESULTS:
        _RESULTS[s.name] = cs.run(s)
    return _RESULTS[s.name]


def _rules_test(s):
    def test(self):
        problems = card_problems(s, _result(s))
        known = KNOWN_ISSUES.get(s.name, [])
        unexpected = [p for p in problems if not any(p.startswith(k) for k in known)]
        gone = [k for k in known if not any(p.startswith(k) for p in problems)]
        self.assertEqual(unexpected, [], "%s breaks card rules" % s.name)
        self.assertEqual(gone, [], "%s: fixed, so remove these from KNOWN_ISSUES" % s.name)
    return test


def _golden_test(s):
    def test(self):
        golden.check(self, "cards/%s/%s.txt" % (s.language, s.name), cs.golden_text(s, _result(s)))
    return test


for _s in cs.SCENARIOS:
    setattr(CardRules, "test_%s" % _s.name, _rules_test(_s))
    setattr(GoldenCards, "test_%s" % _s.name, _golden_test(_s))


if __name__ == "__main__":
    unittest.main(verbosity=1)
