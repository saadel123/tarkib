# -*- coding: utf-8 -*-
"""The card scenarios behind tests/test_cards.py and tests/preview_cards.py. No Anki, no network.

A scenario is one card request (word, deck, level, settings) plus what the outside world did: the
answers the AI gave, in call order, whether a picture was found, and what the voice services did.
run() builds the card with the real generate.build_card and stores it with the real
anki_io.write_bundle in a fake collection, so what comes out is the note a learner would study.

Fixture text follows the content rules like a real card: no alcohol or pork, Modern Standard Arabic
without diacritics (one scenario sends diacritics on purpose), and no dashes. A scenario that feeds a
broken answer says so in its `about`.
"""
import copy
import importlib
import json
import os
import re
import sys
import types

for _n in ("aqt", "aqt.qt", "aqt.utils", "aqt.operations", "anki", "anki.collection", "anki.notes", "anki.hooks"):
    sys.modules.setdefault(_n, types.ModuleType(_n))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from pipeline import generate, languages, prompts, providers, tts  # noqa: E402

# anki_io and notetypes import each other relatively, so load them as a package without running
# __init__.py (which needs a running Anki).
if "tarkib_under_test" not in sys.modules:
    _pkg = types.ModuleType("tarkib_under_test")
    _pkg.__path__ = [ROOT]
    sys.modules["tarkib_under_test"] = _pkg
anki_io = importlib.import_module("tarkib_under_test.anki_io")
notetypes = importlib.import_module("tarkib_under_test.notetypes")

with open(os.path.join(ROOT, "config.json"), encoding="utf-8") as _f:
    DEFAULT_CONFIG = json.load(_f)

PROVIDER = {"id": "groq", "type": "openai_compatible", "name": "Groq",
            "base_url": "https://api.groq.com/openai/v1", "model": "openai/gpt-oss-120b", "api_key": "test-key"}


class Scenario:
    def __init__(self, name, about, word, ai, level="B1", deck="Tarkib", options=None, settings=None,
                 picture=True, voices=None, cloze=True, language="de"):
        self.name, self.about, self.word, self.ai = name, about, word, ai
        self.level, self.deck, self.cloze, self.language = level, deck, cloze, language
        self.options = options or {}          # extra build options: hints, secondary_language, ...
        self.settings = settings or {}        # merged into config.json, like a user's saved config
        self.picture = picture                # False: every picture source finds nothing
        self.voices = voices or {}            # service -> results in order (an Exception = a failure)

    def config(self):
        return _merge(DEFAULT_CONFIG, self.settings)

    def build_options(self):
        # The Add window will pass the language; German scenarios leave it out, so they also prove that a
        # config without one still makes German cards.
        extra = {} if self.language == languages.DEFAULT else {"language": self.language}
        return dict(self.options, level=self.level, generate_cloze=self.cloze, **extra)


def _merge(base, extra):
    out = copy.deepcopy(base)
    for k, v in (extra or {}).items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else copy.deepcopy(v)
    return out


# ── fixtures: what the AI answered ─────────────────────────────────────────────────────────
def card(**fields):
    """A MAIN answer with every key the prompt asks for. Missing keys are a separate scenario."""
    out = {"emoji": "", "word": "", "translation_en": "", "register": "neutral",
           "casual_alternatives": [], "casual_alternatives_en": [],
           "example_formal": "", "example_casual": "", "example_formal_en": "", "example_casual_en": "",
           "explanation_de": "", "tags": [], "imageKeyword": "", "emoji_formal": "", "emoji_casual": "",
           "grammar_patterns": [], "grammar_patterns_en": [], "morphology": {},
           "input_is_german": True, "input_suggestion": ""}
    out.update(fields)
    return out


def cloze(case, sentence, answer, translation, hint="", meaning=""):
    return {"case": case, "sentence": sentence, "answer": answer, "translation_en": translation,
            "grammar_hint": hint, "idiom_meaning_de": meaning}


def noun(article, plural, genitive):
    return {"pos": "noun", "article": article, "plural": plural, "genitive": genitive}


def verb(present, past, perfect, separable):
    return {"pos": "verb", "present_3sg": present, "past_3sg": past, "perfect": perfect, "separable": separable}


OTHER = {"pos": "other"}

SCHLOSS = card(
    emoji="🏰", word="das Schloss", translation_en="castle",
    example_casual="Hast du das Schloss am Fluss schon gesehen?",
    example_formal="Das Schloss steht seit vielen Jahren auf dem Hügel.",
    example_casual_en="Have you seen the castle by the river yet?",
    example_formal_en="The castle has stood on the hill for many years.",
    explanation_de="Ein Schloss ist ein großes, altes Gebäude, in dem früher Könige wohnten.",
    tags=["Reisen"], imageKeyword="castle on a hill", emoji_formal="🏛️", emoji_casual="💬",
    grammar_patterns=["auf dem Hügel stehen (+Dat)", "seit (+Dat)"],
    grammar_patterns_en=["to stand on the hill", "for (a period of time)"],
    morphology=noun("das", "die Schlösser", "des Schlosses"))

ANRUFEN = card(
    emoji="📞", word="anrufen", translation_en="to call (on the phone)",
    example_casual="Kannst du mich heute Abend anrufen?",
    example_formal="Ich rufe Sie morgen früh an.",
    example_casual_en="Can you call me this evening?",
    example_formal_en="I will call you early tomorrow.",
    explanation_de="Man spricht mit jemandem am Telefon.",
    tags=["Kommunikation"], imageKeyword="person talking on the phone", emoji_formal="📅", emoji_casual="💬",
    grammar_patterns=["rufe ... an (trennbar)", "jemanden anrufen (+Akk)"],
    grammar_patterns_en=["separable verb: the prefix goes to the end", "to call someone"],
    morphology=verb("ruft an", "rief an", "hat angerufen", True))

TERMIN_STYLE = card(
    emoji="📅", word="der Termin", translation_en="appointment",
    example_casual="Hast du morgen einen Termin beim Kochkurs?",
    example_formal="Könnten wir den Termin für das Kochseminar verschieben?",
    example_casual_en="Do you have an appointment at the cooking class tomorrow?",
    example_formal_en="Could we move the appointment for the cooking seminar?",
    explanation_de="Ein Termin ist eine feste Zeit für ein Treffen.", tags=["Alltag"],
    imageKeyword="calendar with a cooking class marked", emoji_formal="🗓️", emoji_casual="🍳",
    grammar_patterns=["einen Termin haben", "einen Termin verschieben"],
    grammar_patterns_en=["to have an appointment", "to move an appointment"],
    morphology=noun("der", "die Termine", "des Termins"))

MORGEN = card(
    emoji="🌅", word="morgen", translation_en="tomorrow",
    example_casual="Morgen habe ich frei.", example_formal="Haben Sie morgen Zeit?",
    example_casual_en="I'm off tomorrow.", example_formal_en="Do you have time tomorrow?",
    explanation_de="Morgen ist der Tag nach heute.", tags=["Zeit"], imageKeyword="calendar page for tomorrow",
    emoji_formal="📅", emoji_casual="😌", morphology=OTHER)

TISCH_AR = card(
    emoji="🪑", word="der Tisch", translation_en="طاوِلة",
    example_casual="Siehst du den Tisch dort?",
    example_formal="Möchten Sie diesen Tisch?",
    example_casual_en="هل ترى الطاولةَ هناك؟",
    example_formal_en="هل ترغب في هذه الطاولة؟",
    explanation_de="Auf einem Tisch isst oder arbeitet man.",
    tags=["Haushalt"], imageKeyword="wooden table", emoji_formal="🍽️", emoji_casual="👀",
    morphology=noun("der", "die Tische", "des Tisches"))

GEGEBENENFALLS = card(
    emoji="📄", word="gegebenenfalls", translation_en="if necessary", register="formal",
    casual_alternatives=["falls nötig", "wenn es sein muss"],
    casual_alternatives_en=["if need be", "if we have to"],
    example_formal="Gegebenenfalls senden wir Ihnen die Unterlagen noch einmal zu.",
    example_casual="Falls nötig, schick ich dir die Sachen nochmal.",
    example_formal_en="If necessary, we will send you the documents again.",
    example_casual_en="If need be, I'll send you the stuff again.",
    explanation_de="Das Wort gehört zur Behörden- und Geschäftssprache, im Alltag sagt man lieber falls nötig.",
    tags=["Arbeit"], imageKeyword="documents in an envelope", emoji_formal="📨", emoji_casual="💬",
    grammar_patterns=["jemandem etwas zusenden (+Dat, +Akk)",
                      "Gegebenenfalls senden wir Ihnen die Unterlagen noch einmal zu."],
    grammar_patterns_en=["to send something to someone", "If necessary, we will send you the documents again."],
    morphology=OTHER)

BOCK = card(
    emoji="😎", word="Bock haben", translation_en="to feel like (doing something)", register="casual",
    example_casual="Hast du Bock auf Kino heute Abend?",
    example_formal="Ehrlich gesagt habe ich heute keinen Bock auf die Besprechung.",
    example_casual_en="Do you feel like going to the cinema tonight?",
    example_formal_en="To be honest, I really don't feel like the meeting today.",
    explanation_de="Umgangssprachlich für Lust auf etwas haben.",
    tags=["Umgangssprache", "Alltag"], imageKeyword="friends going to the cinema", emoji_formal="💼",
    emoji_casual="🎬", grammar_patterns=["Bock haben auf (+Akk)"], grammar_patterns_en=["to feel like something"],
    morphology=OTHER)

WIE_SPAET = card(
    emoji="⏰", word="Wie spät ist es?", translation_en="What time is it?",
    example_casual="Max, wie spät ist es?",
    example_formal="Entschuldigung, wie spät ist es?",
    example_casual_en="Max, what time is it?",
    example_formal_en="Excuse me, what time is it?",
    explanation_de="So fragt man nach der Uhrzeit.",
    tags=["Zeit", "Kommunikation"], imageKeyword="wall clock", emoji_formal="🙋", emoji_casual="💬",
    grammar_patterns=["Wie spät ist es? (Redemittel)"], grammar_patterns_en=["What time is it?"],
    morphology=OTHER)

DAUMEN = card(
    emoji="🤞", word="jemandem die Daumen drücken", translation_en="to keep your fingers crossed for someone",
    example_casual="Ich drücke dir für die Prüfung die Daumen.",
    example_formal="Wir drücken Ihnen für das Gespräch die Daumen.",
    example_casual_en="I'll keep my fingers crossed for you in the exam.",
    example_formal_en="We will keep our fingers crossed for your interview.",
    explanation_de="Man wünscht jemandem Glück für etwas Wichtiges.",
    tags=["Redewendung", "Gefuehle"], imageKeyword="fingers crossed for good luck", emoji_formal="💼",
    emoji_casual="📚", grammar_patterns=["jemandem die Daumen drücken (+Dat)", "für (+Akk)"],
    grammar_patterns_en=["to keep your fingers crossed for someone", "for (something)"], morphology=OTHER)

# A broken answer on purpose: markup and a script in the text, shortcodes, nested JSON as strings, the
# word as an object, emoji fields holding letters, and a picture query the content rule forbids.
ERFAHRUNG_MESSY = card(
    emoji=":briefcase:", word={"value": "die Erfahrung"}, translation_en="experience <b>bold</b>",
    example_casual="Ich habe <script>alert(1)</script> viel Erfahrung mit Kindern.",
    example_formal="Sie haben viel Erfahrung mit Kunden :thumbs_up:",
    example_casual_en="I have a lot of experience with children <img src=x onerror=alert(1)>",
    example_formal_en="You have a lot of experience with customers.",
    explanation_de="Wissen aus der Praxis & aus der Übung.",
    tags='["Arbeit", "Bildung"]', imageKeyword="people drinking beer at a bar", emoji_formal="Ἶ6",
    emoji_casual="U+1F600", grammar_patterns=[{"pattern": "Erfahrung mit (+Dat)"}, "Erfahrung haben"],
    grammar_patterns_en='["experience with", "to have experience"]',
    morphology='{"pos": "noun", "article": "die", "plural": "die Erfahrungen", "genitive": "der Erfahrung"}')

BRILLE = card(
    emoji="👓", word="die Brille", translation_en="glasses",
    example_casual="Wo ist deine Brille?",
    example_formal="Bitte setzen Sie Ihre Brille auf.",
    example_casual_en="Where are your glasses?",
    example_formal_en="Please put on your glasses.",
    explanation_de="Mit einer Brille sieht man besser.",
    tags=["Gesundheit"], imageKeyword="glasses on a table", emoji_formal="📖", emoji_casual="🔎",
    grammar_patterns=["die Brille aufsetzen (+Akk)"], grammar_patterns_en=["to put on your glasses"],
    morphology=noun("die", "die Brillen", "der Brille"))

BESPRECHUNG = dict(
    emoji="🗓️", word="die Besprechung", translation_en="meeting",
    example_formal="Die Besprechung beginnt pünktlich um neun Uhr.",
    example_casual_en="We have the meeting tomorrow at ten.",
    example_formal_en="The meeting starts at nine o'clock sharp.",
    explanation_de="In einer Besprechung reden Kollegen über ein Thema.",
    tags=["Arbeit"], imageKeyword="colleagues in a meeting room", emoji_formal="🕘", emoji_casual="💬",
    grammar_patterns=["um ... Uhr (Uhrzeit)"], grammar_patterns_en=["at ... o'clock (time)"],
    morphology=noun("die", "die Besprechungen", "der Besprechung"))

UNTERBRECHEN = dict(
    emoji="✋", word="unterbrechen", translation_en="to interrupt",
    example_formal="Darf ich Sie kurz unterbrechen?",
    example_casual_en="He keeps interrupting me when I talk.",
    example_formal_en="May I interrupt you for a moment?",
    explanation_de="Wenn man unterbricht, stoppt man ein Gespräch für kurze Zeit.",
    tags=["Kommunikation"], imageKeyword="raised hand in a meeting", emoji_formal="🙋", emoji_casual="😤",
    grammar_patterns=["jemanden unterbrechen (+Akk)"], grammar_patterns_en=["to interrupt someone"],
    morphology=verb("unterbricht", "unterbrach", "hat unterbrochen", False))

BENACHRICHTIGUNG = card(
    emoji="🔔", word="die Benachrichtigung", translation_en="notification",
    example_casual="Hast du meine Benachrichtigung bekommen?",
    example_formal="Sie erhalten eine Benachrichtigung per E-Mail.",
    example_casual_en="Did you get my notification?",
    example_formal_en="You will receive a notification by email.",
    explanation_de="Eine Benachrichtigung ist eine kurze Nachricht über etwas Neues.",
    tags=["Technik"], imageKeyword="phone notification on a screen", emoji_formal="📧", emoji_casual="📱",
    grammar_patterns=["eine Benachrichtigung bekommen"], grammar_patterns_en=["to get a notification"],
    morphology=noun("die", "die Benachrichtigungen", "der Benachrichtigung"))

VERABREDUNG = card(
    emoji="🤝", word="die Verabredung", translation_en="arrangement to meet",
    example_casual="Ich habe heute Abend eine Verabredung mit Lisa.",
    example_formal="Wir haben eine Verabredung um acht Uhr.",
    example_casual_en="I'm meeting Lisa tonight.",
    example_formal_en="We have arranged to meet at eight o'clock.",
    explanation_de="Eine Verabredung ist ein geplantes Treffen mit jemandem.",
    tags=["Beziehungen"], imageKeyword="two friends meeting in a cafe", emoji_formal="🕗", emoji_casual="☕",
    grammar_patterns=["eine Verabredung mit jemandem haben (+Dat)"],
    grammar_patterns_en=["to have arranged to meet someone"],
    morphology=noun("die", "die Verabredungen", "der Verabredung"))

TERMIN = card(
    emoji="📅", word="der Termin", translation_en="appointment",
    example_casual="Ich habe morgen einen Termin beim Zahnarzt.",
    example_formal="Könnten Sie mir bitte einen neuen Termin geben?",
    example_casual_en="I have an appointment at the dentist tomorrow.",
    example_formal_en="Could you please give me a new appointment?",
    explanation_de="Ein Termin ist eine feste Zeit für ein Treffen.",
    tags=["Alltag", "Gesundheit"], imageKeyword="calendar with appointment reminder", emoji_formal="🗓️",
    emoji_casual="🦷", grammar_patterns=["einen Termin bei jemandem haben (+Dat)", "Könnten Sie ...? (höflich)"],
    grammar_patterns_en=["to have an appointment with someone", "Could you ...? (polite)"],
    morphology=noun("der", "die Termine", "des Termins"))

DANKE_NOT_GERMAN = card(
    emoji="🙏", word="danke", translation_en="thank you",
    example_casual="Danke für deine Hilfe.",
    example_formal="Vielen Dank für Ihre Unterstützung.",
    example_casual_en="Thanks for your help.",
    example_formal_en="Thank you very much for your support.",
    explanation_de="So sagt man, dass man dankbar ist.",
    tags=["Kommunikation"], imageKeyword="person saying thank you", emoji_formal="🤝", emoji_casual="😊",
    morphology=OTHER, input_is_german=False, input_suggestion="danke")

HANDY = card(
    emoji="📱", word="das Handy", translation_en="mobile phone",
    example_casual="Mein Handy ist schon wieder leer.",
    example_formal="Bitte schalten Sie Ihr Handy aus.",
    example_casual_en="My phone is dead again.",
    example_formal_en="Please switch off your mobile phone.",
    explanation_de="Ein Handy ist ein kleines Telefon für unterwegs.",
    tags=["Technik"], imageKeyword="smartphone on a desk", emoji_formal="🔕", emoji_casual="🔋",
    grammar_patterns=["etwas ausschalten (+Akk)"], grammar_patterns_en=["to switch something off"],
    morphology=noun("das", "die Handys", "des Handys"))

WARTEN_AUF = card(
    emoji="⏳", word="warten auf", translation_en="to wait for",
    example_casual="Ich warte schon seit zehn Minuten auf dich.",
    example_formal="Bitte warten Sie hier auf den Arzt.",
    example_casual_en="I've been waiting for you for ten minutes.",
    example_formal_en="Please wait here for the doctor.",
    explanation_de="Man bleibt an einem Ort, bis jemand kommt oder etwas passiert.",
    tags=["Alltag"], imageKeyword="person waiting at a bus stop", emoji_formal="🩺", emoji_casual="⌚",
    grammar_patterns=["warten auf (+Akk)", "seit (+Dat)"],
    grammar_patterns_en=["to wait for", "for (a period of time)"],
    morphology=verb("wartet", "wartete", "hat gewartet", False))

RUECKSICHT = card(
    emoji="🤝", word="die Rücksicht", translation_en="consideration",
    example_casual="Nimm bitte ein bisschen Rücksicht auf deine Nachbarn.",
    example_formal="Wir bitten Sie, Rücksicht auf die anderen Gäste zu nehmen.",
    example_casual_en="Please show a bit of consideration for your neighbours.",
    example_formal_en="We ask you to be considerate of the other guests.",
    explanation_de="Wer Rücksicht nimmt, achtet auf die Gefühle und Bedürfnisse anderer.",
    tags=["Beziehungen"], imageKeyword="quiet neighbours in an apartment building", emoji_formal="🏨",
    emoji_casual="🏠", grammar_patterns=["Rücksicht nehmen auf (+Akk)", "jemanden bitten, etwas zu tun"],
    grammar_patterns_en=["to show consideration for", "to ask someone to do something"],
    morphology=noun("die", "—", "der Rücksicht"))

ENTSCHEIDUNG = card(
    emoji="⚖️", word="eine Entscheidung treffen", translation_en="to make a decision",
    example_casual="Wir müssen heute endlich eine Entscheidung treffen.",
    example_formal="Der Vorstand wird die Entscheidung nächste Woche treffen.",
    example_casual_en="We finally have to make a decision today.",
    example_formal_en="The board will make the decision next week.",
    explanation_de="Man entscheidet sich nach dem Nachdenken für eine Möglichkeit.",
    tags=["Arbeit"], imageKeyword="team discussing options at a table", emoji_formal="🏢", emoji_casual="🤔",
    grammar_patterns=["eine Entscheidung treffen", "müssen + Infinitiv"],
    grammar_patterns_en=["to make a decision", "must + infinitive"], morphology=OTHER)

TERMIN_ARZT = card(
    emoji="📅", word="der Termin", translation_en="appointment",
    example_casual="Ich rufe beim Arzt an und mache einen Termin.",
    example_formal="Ich möchte bitte einen Termin bei Dr. Weber vereinbaren.",
    example_casual_en="I'll call the doctor's office and make an appointment.",
    example_formal_en="I would like to make an appointment with Dr. Weber, please.",
    explanation_de="Ein Termin ist eine feste Zeit, zum Beispiel beim Arzt.",
    tags=["Gesundheit"], imageKeyword="calendar", emoji_formal="🩺", emoji_casual="☎️",
    grammar_patterns=["einen Termin vereinbaren", "bei jemandem anrufen (+Dat)"],
    grammar_patterns_en=["to make an appointment", "to call someone's office"],
    morphology=noun("der", "die Termine", "des Termins"))

SCHRIPPE = card(
    emoji="🥖", word="die Schrippe", translation_en="bread roll",
    example_casual="Holst du mir zwei Schrippen vom Bäcker?",
    example_formal="Ich hätte gern vier Schrippen, bitte.",
    example_casual_en="Can you get me two bread rolls from the bakery?",
    example_formal_en="I would like four bread rolls, please.",
    explanation_de="In Berlin sagt man Schrippe für ein Brötchen.",
    tags=["Essen"], imageKeyword="fresh bread rolls in a bakery", emoji_formal="🧺", emoji_casual="🥐",
    grammar_patterns=["jemandem etwas holen (+Dat, +Akk)"], grammar_patterns_en=["to get something for someone"],
    morphology=noun("die", "die Schrippen", "der Schrippe"), input_is_german=False,
    input_suggestion="das Brötchen")

CHILLEN = card(
    emoji="😌", word="chillen", translation_en="يسترخي", register="casual",
    example_casual="Am Wochenende will ich einfach nur chillen.",
    example_formal="Nach der Arbeit möchte ich mich ein wenig entspannen.",
    example_casual_en="في عطلة نهاية الأسبوع أريدُ فقط أن أسترخي.",
    example_formal_en="بعد العمل أود أن أرتاح قليلا.",
    explanation_de="Umgangssprachlich für sich entspannen und nichts tun.",
    tags=["Umgangssprache"], imageKeyword="friends relaxing on a sofa", emoji_formal="🛋️", emoji_casual="🎮",
    grammar_patterns=["einfach nur + Infinitiv"], grammar_patterns_en=["فقط + فعل"],
    morphology=verb("chillt", "chillte", "hat gechillt", False))

EDGE_403 = tts.TTSError("edge", "auth", "Microsoft Edge refused the connection: HTTP 403 Forbidden", 403)


# ── the scenarios ──────────────────────────────────────────────────────────────────────────
SCENARIOS = [
    Scenario(
        "noun_b1", "A neuter noun at B1 with two patterns, a picture, only the German read aloud (the "
        "default) and a cloze card whose answer takes its article.",
        "das Schloss", [("main", SCHLOSS),
                        ("cloze", cloze("single_word", "Am Wochenende besuchen wir das Schloss.", "Schloss",
                                        "At the weekend we are visiting the castle."))]),
    Scenario(
        "verb_a2", "A separable verb at A2: the verb line with trennbar, patterns put in value order, "
        "and a beginner letter hint.",
        "anrufen", [("main", ANRUFEN),
                    ("cloze", cloze("single_word", "Kannst du mich später anrufen?", "anrufen",
                                    "Can you call me later?", hint="jemanden anrufen (+Akk)"))], level="A2"),
    Scenario(
        "noun_a1_arabic", "A1 with Arabic as the translation language: right to left, no genitive at A1, "
        "no patterns box when the AI gives none, and the diacritics the AI added to the translations removed.",
        "der Tisch", [("main", TISCH_AR),
                      ("cloze", cloze("single_word", "Der Tisch ist neu.", "Tisch", "الطاولةُ جديدةٌ."))],
        level="A1", settings={"defaults": {"translation_language": "Arabic"}}),
    Scenario(
        "formal_c1_french", "A formal word at C1: casual alternatives, the register hint on both sides, the "
        "Formell tag added by the code, a whole sentence dropped from the patterns, and French as a "
        "second translation with its own voice.",
        "gegebenenfalls",
        [("main", GEGEBENENFALLS),
         ("secondary", {"word_translation": "le cas échéant",
                        "casual": "Si besoin, je t'envoie les affaires encore une fois.",
                        "formal": "Le cas échéant, nous vous renverrons les documents."}),
         ("cloze", cloze("single_word", "Gegebenenfalls rufen wir Sie zurück.", "Gegebenenfalls",
                         "If necessary, we will call you back."))],
        level="C1", options={"secondary_language": "French"},
        settings={"voices": {"secondary": "fr-FR-DeniseNeural"}}),
    Scenario(
        "native_alltag", "Native in the Alltagsdeutsch deck: the original prompt, the separate grammar "
        "call (a whole sentence in its answer is dropped), the English read aloud too, and a cloze of "
        "the verb alone.",
        "Bock haben",
        [("main", BOCK),
         ("grammar", {"grammar_patterns": ["Bock auf etwas haben (+Akk)", "Hast du Bock auf Kino heute Abend?"],
                      "grammar_patterns_en": ["to feel like something",
                                              "Do you feel like going to the cinema tonight?"]}),
         ("cloze", cloze("nvv", "Ich habe heute echt keinen Bock.", "habe", "I really don't feel like it today.",
                         hint="Bock haben: Lust haben"))],
        level="Native", deck="Deutsch::Alltagsdeutsch",
        settings={"voices": {"translation": "en-US-AvaMultilingualNeural"}}),
    Scenario(
        "native_arabic", "Native with Arabic as the translation language: the grammar call is told to gloss in "
        "Arabic (it asked for English before, whatever the translation language), gets 2000 tokens, and the "
        "diacritics the AI added are removed from every Arabic text.",
        "chillen",
        [("main", CHILLEN),
         ("grammar", {"grammar_patterns": ["sich entspannen (reflexiv)", "will ... chillen (Modalverb + Infinitiv)"],
                      "grammar_patterns_en": ["يسترخي، فعلٌ انعكاسي", "يريد + فعل"]}),
         ("cloze", cloze("single_word", "Heute Abend will ich nur chillen.", "chillen", "الليلةَ أريد فقط أن أسترخي."))],
        level="Native", settings={"defaults": {"translation_language": "Arabic"}}),
    Scenario(
        "phrase_a2", "A whole phrase at A2: the AI restates the phrase as its own pattern (dropped, so no "
        "box) and the cloze blanks the phrase with a hint for each word.",
        "Wie spät ist es?",
        [("main", WIE_SPAET),
         ("cloze", cloze("long_phrase", "Entschuldigung, wie spät ist es?", "wie spät ist es",
                         "Excuse me, what time is it?"))], level="A2"),
    Scenario(
        "idiom_b2", "An idiom at B2 in the Redewendungen deck: two blanks with hints, and the patterns in "
        "value order (the preposition with its case first).",
        "jemandem die Daumen drücken",
        [("main", DAUMEN),
         ("cloze", cloze("idiom", "Ich drücke dir ganz fest die Daumen.", "drücke, Daumen",
                         "I'm keeping my fingers crossed for you.",
                         hint="jemandem die Daumen drücken: jemandem Glück wünschen",
                         meaning="jemandem Glück wünschen"))],
        level="B2", deck="Deutsch::Redewendungen"),
    Scenario(
        "messy_answer_b1", "A broken answer: markup and a script in the text, emoji shortcodes, a list and "
        "an object sent as strings, the word as an object, letters in emoji fields, a picture query the "
        "content rule forbids, and a cloze kind that does not exist.",
        "die Erfahrung",
        [("main", ERFAHRUNG_MESSY),
         ("cloze", cloze("weird_case", "Sie hat viel Erfahrung im Beruf.", "Erfahrung",
                         "She has a lot of experience at work.", hint="<i>Erfahrung</i> im Beruf"))]),
    Scenario(
        "no_picture_no_audio_a2", "No picture found and Edge refusing the audio: the card still lands, with "
        "no picture box and no sound, and the cloze answer loses a doubled determiner.",
        "die Brille",
        [("main", BRILLE),
         ("cloze", cloze("single_word", "Ich suche meine die Brille.", "die Brille", "I am looking for my glasses."))],
        level="A2", picture=False, voices={"edge": [EDGE_403]}),
    Scenario(
        "leak_retry_b1", "An English word in a German sentence at B1: one strict retry, and the clean card "
        "is used.",
        "die Besprechung",
        [("main", card(example_casual="Wir haben the Besprechung morgen um zehn.", **BESPRECHUNG)),
         ("main", card(example_casual="Wir haben die Besprechung morgen um zehn.", **BESPRECHUNG)),
         ("cloze", cloze("single_word", "Die Besprechung dauert eine Stunde.", "Besprechung",
                         "The meeting lasts one hour."))]),
    Scenario(
        "leak_kept_b2", "The English word survives the retry: the first card is kept and the warning goes "
        "to the dialog. The cloze answer is not in its sentence, so there is no cloze card.",
        "unterbrechen",
        [("main", card(example_casual="Er interrupts mich ständig, wenn ich rede.", **UNTERBRECHEN)),
         ("main", card(example_casual="Bitte interrupts mich nicht immer.", **UNTERBRECHEN)),
         ("cloze", cloze("single_word", "Bitte lass mich ausreden.", "unterbrechen",
                         "Please let me finish speaking."))], level="B2"),
    Scenario(
        "typo_b1", "A typo the AI fixed: the card is kept and the dialog will ask Did you mean. The "
        "translation language in the saved settings is not one Tarkib knows, so English is used with a "
        "warning.",
        "benachrichtigong",
        [("main", BENACHRICHTIGUNG),
         ("cloze", cloze("single_word", "Ich habe keine Benachrichtigung bekommen.", "Benachrichtigung",
                         "I didn't get a notification."))],
        settings={"defaults": {"translation_language": "Chihasa"}}),
    Scenario(
        "other_word_retry_b1", "The AI answered a different word: one strict retry brings the right one.",
        "der Termin",
        [("main", VERABREDUNG), ("main", TERMIN),
         ("cloze", cloze("single_word", "Ich muss den Termin leider absagen.", "Termin",
                         "Unfortunately I have to cancel the appointment.", hint="einen Termin absagen"))]),
    Scenario(
        "other_word_refused_b1", "The AI keeps answering a different word: the card is refused with a clear "
        "message, and no cloze call is made.",
        "der Termin", [("main", VERABREDUNG), ("main", VERABREDUNG)]),
    Scenario(
        "not_german_b1", "Arabic written in Latin letters: two calls agree it is not German, so the card is "
        "refused with the suggestion the AI made.",
        "shukran", [("main", DANKE_NOT_GERMAN), ("main", DANKE_NOT_GERMAN)]),
    Scenario(
        "not_german_overruled_b1", "The first call says the word is not German, the strict second call "
        "disagrees: the second card is used.",
        "das Handy",
        [("main", card(**dict(HANDY, input_is_german=False, input_suggestion=""))), ("main", HANDY),
         ("cloze", cloze("single_word", "Mein Handy ist leer.", "Handy", "My phone is dead."))]),
    Scenario(
        "verb_prep_b1", "A verb with its preposition in the Verben deck: the verb line, the preposition "
        "with its case, and a cloze of preposition plus article.",
        "warten auf",
        [("main", WARTEN_AUF),
         ("cloze", cloze("verb_prep_article", "Wir warten auf den Bus.", "auf den", "We are waiting for the bus.",
                         hint="warten auf (+Akk)"))], deck="Deutsch::Verben"),
    Scenario(
        "noun_prep_c1_arabic2", "A noun with its preposition at C1, Arabic as the second translation (the "
        "MSA prompt, diacritics removed, its own voice), and a cloze of the preposition alone.",
        "die Rücksicht",
        [("main", RUECKSICHT),
         ("secondary", {"word_translation": "مُراعاة", "casual": "من فضلك راعِ جيرانك قليلا.",
                        "formal": "نرجو منك مراعاة الضيوف الآخرين."}),
         ("cloze", cloze("noun_prep", "Bitte nimm Rücksicht auf die Kinder.", "auf",
                         "Please be considerate of the children.", hint="Rücksicht nehmen auf (+Akk)"))],
        level="C1", options={"secondary_language": "Arabic"},
        settings={"voices": {"secondary": "ar-SA-ZariyahNeural"}}),
    Scenario(
        "nvv_b2", "A noun and verb pair in the NVV deck: the pair restated as its own pattern is dropped, "
        "and the cloze blanks the verb alone.",
        "eine Entscheidung treffen",
        [("main", ENTSCHEIDUNG),
         ("cloze", cloze("nvv", "Bis Freitag müssen wir eine Entscheidung treffen.", "treffen",
                         "We have to make a decision by Friday.", hint="eine Entscheidung treffen"))],
        level="B2", deck="Deutsch::Nomen-Verb-Verbindungen"),
    Scenario(
        "hints_no_cloze_b1", "Meaning, scenario and picture hints (the scenario adds the loanwords table), a "
        "second translation language equal to the first (skipped with a warning), and no cloze card.",
        "der Termin", [("main", TERMIN_ARZT)],
        options={"meaning": "appointment at the doctor's", "scenario": "beim Arzt anrufen",
                 "image_keyword": "Kalender", "secondary_language": "English"}, cloze=False),
    Scenario(
        "missing_fields_b1", "A weak model that leaves fields out (no formal sentence, no explanation, no "
        "emojis, no word line): what the card shows then.",
        "die Küche",
        [("main", {"word": "die Küche", "translation_en": "kitchen", "example_casual": "Die Küche ist ganz neu.",
                   "example_casual_en": "The kitchen is brand new.", "tags": ["Haushalt"],
                   "imageKeyword": "modern kitchen"}),
         ("cloze", {"case": "single_word", "sentence": "Wir kochen heute in der Küche.", "answer": "Küche",
                    "translation_en": "We are cooking in the kitchen today."})]),
    Scenario(
        "user_insisted_b1", "The user insisted twice: on the spelling (the prompt says so) and on adding a "
        "word the AI called not German (no second call, no refusal).",
        "Schrippe",
        [("main", SCHRIPPE),
         ("cloze", cloze("single_word", "Ich kaufe zwei Schrippen.", "Schrippen", "I'm buying two bread rolls."))],
        options={"exact_word": True, "force_input": True}),
    Scenario(
        "style_b1", "The user's style wishes (Settings, Cards) ticked in the Tarkib window: they go into the main "
        "and the cloze request, nothing else changes.",
        "der Termin",
        [("main", TERMIN_STYLE),
         ("cloze", cloze("single_word", "Den Termin für den Kochkurs habe ich verschoben.", "Termin",
                         "I moved the appointment for the cooking class."))],
        options={"style": "Beispiele rund ums Kochen, kurze Saetze, ein freundlicher Ton."}),
    Scenario(
        "cloze_capital_a1", "The cloze answer written in small letters while the sentence starts with it: the blank "
        "takes the sentence's capital (before, the cloze card was lost).",
        "morgen",
        [("main", MORGEN),
         ("cloze", cloze("single_word", "Morgen gehe ich einkaufen.", "morgen", "I'm going shopping tomorrow."))],
        level="A1"),
    Scenario(
        "slow_speech_a1", "Speech speed \"Slower at A1 and A2\" (Settings, Voice) on an A1 card: the word, its "
        "sentences and both cloze clips are read slower, the translation at the normal speed.",
        "morgen",
        [("main", MORGEN),
         ("cloze", cloze("single_word", "Morgen gehe ich einkaufen.", "Morgen", "I'm going shopping tomorrow."))],
        level="A1", settings={"tts": {"speed": "slower_a1_a2"}, "voices": {"translation": "en-US-AvaMultilingualNeural"}}),
]

# ── English (the generic set: neutral JSON keys) ─────────────────────────────────────────────
def en_card(**fields):
    """A MAIN answer to the generic prompt, with its neutral keys."""
    out = {"emoji": "", "word": "", "translation": "", "register": "neutral",
           "casual_alternatives": [], "casual_alternatives_translation": [],
           "example_formal": "", "example_casual": "", "example_formal_translation": "", "example_casual_translation": "",
           "explanation": "", "tags": [], "imageKeyword": "", "emoji_formal": "", "emoji_casual": "",
           "grammar_patterns": [], "grammar_patterns_translation": [], "morphology": {},
           "input_in_language": True, "input_suggestion": ""}
    out.update(fields)
    return out


def en_cloze(case, sentence, answer, translation, hint="", meaning=""):
    return {"case": case, "sentence": sentence, "answer": answer, "translation": translation,
            "grammar_hint": hint, "idiom_meaning": meaning}


def en_noun(singular, plural, countable=True):
    return {"pos": "noun", "singular": singular, "plural": plural, "countable": countable}


def en_verb(base, past, participle, phrasal=False, separable=False):
    return {"pos": "verb", "base": base, "past": past, "past_participle": participle, "phrasal": phrasal,
            "separable": separable}


ARABIC = {"defaults": {"translation_language": "Arabic"}}

REASON = en_card(
    emoji="🤔", word="reason", translation="سَبَب",
    example_casual="What's the reason for the delay?",
    example_formal="There is no reason for concern at this stage.",
    example_casual_translation="ما سبب التأخير؟",
    example_formal_translation="لا يوجد سبب للقلق في هذه المرحلة.",
    explanation="A reason is the cause of something, or why it happens.",
    tags=["Communication"], imageKeyword="delayed train on a timetable board", emoji_formal="📄", emoji_casual="⏰",
    grammar_patterns=["the reason for something", "there is no + noun"],
    grammar_patterns_translation=["سبب شيء ما", "لا يوجد + اسم"],
    morphology=en_noun("reason", "reasons"))

BUY = en_card(
    emoji="🛍️", word="buy", translation="kaufen",
    example_casual="I bought new shoes yesterday.",
    example_formal="I would like to buy a present for my sister.",
    example_casual_translation="Ich habe gestern neue Schuhe gekauft.",
    example_formal_translation="Ich möchte ein Geschenk für meine Schwester kaufen.",
    explanation="To buy something means to pay money to get it.",
    tags=["Shopping"], imageKeyword="person buying shoes in a shop", emoji_formal="🎁", emoji_casual="👟",
    grammar_patterns=["buy something for someone", "would like to + verb"],
    grammar_patterns_translation=["etwas für jemanden kaufen", "möchte + Infinitiv"],
    morphology=en_verb("buy", "bought", "bought"))

INFORMATION = en_card(
    emoji="ℹ️", word="information", translation="معلومات",
    example_casual="I need more information.",
    example_formal="Can you give me some information?",
    example_casual_translation="أحتاج إلى معلومات أكثر.",
    example_formal_translation="هل يمكنك أن تعطيني بعض المعلومات؟",
    explanation="Information is facts about something.",
    tags=["Communication"], imageKeyword="information desk", emoji_formal="🙋", emoji_casual="📋",
    grammar_patterns=["give someone something"], grammar_patterns_translation=["يعطي شخصا شيئا"],
    morphology=en_noun("information", "", countable=False))

PUT_OFF = en_card(
    emoji="📅", word="put off", translation="reporter",
    example_casual="Can we put the meeting off until Friday?",
    example_formal="We regret that the launch has been put off until the autumn.",
    example_casual_translation="On peut reporter la réunion à vendredi ?",
    example_formal_translation="Nous regrettons que le lancement ait été reporté à l'automne.",
    explanation="To put something off means to decide to do it later.",
    tags=["Work"], imageKeyword="calendar with a meeting moved", emoji_formal="🚀", emoji_casual="🗓️",
    grammar_patterns=["put something off", "until + time"],
    grammar_patterns_translation=["reporter quelque chose", "jusqu'à + moment"],
    morphology=en_verb("put off", "put off", "put off", phrasal=True, separable=True))

CHILD = en_card(
    emoji="🧒", word="child", translation="طفل",
    example_casual="My sister looks after three children on weekends.",
    example_formal="Every child has the right to a good education.",
    example_casual_translation="تعتني أختي بثلاثة أطفال في عطلات نهاية الأسبوع.",
    example_formal_translation="لكل طفل الحق في تعليم جيد.",
    explanation="A child is a young person who is not an adult yet.",
    tags=["Relationships"], imageKeyword="child reading a book", emoji_formal="🎓", emoji_casual="👩‍👧",
    grammar_patterns=["look after someone", "the right to something"],
    grammar_patterns_translation=["يعتني بشخص ما", "الحق في شيء ما"],
    morphology=en_noun("child", "children"))

NEVERTHELESS = en_card(
    emoji="⚖️", word="nevertheless", translation="ومع ذلك", register="formal",
    casual_alternatives=["but still", "even so"], casual_alternatives_translation=["لكن مع ذلك", "حتى مع ذلك"],
    example_formal="The plan is risky, but we will nevertheless go ahead with it.",
    example_casual="It's a bit risky, but we're still gonna do it.",
    example_formal_translation="الخطة محفوفة بالمخاطر، لكننا سنمضي فيها مع ذلك.",
    example_casual_translation="الأمر فيه بعض المخاطرة، لكننا سنفعله على أي حال.",
    explanation="A formal word for despite what was just said; in casual speech people say but still.",
    tags=["Communication", "Formal"], imageKeyword="team deciding to go ahead with a plan", emoji_formal="📊",
    emoji_casual="🤷", grammar_patterns=["go ahead with something"],
    grammar_patterns_translation=["يمضي قدما في شيء ما"], morphology={"pos": "other"})

MAKE_A_DECISION = en_card(
    emoji="⚖️", word="make a decision", translation="يتخذ قرارا",
    example_casual="Honestly, I can't make a decision until I've slept on it.",
    example_formal="Only after reviewing all the evidence did the committee make a decision.",
    example_casual_translation="بصراحة، لا أستطيع أن أتخذ قرارا قبل أن أفكر في الأمر جيدا.",
    example_formal_translation="لم تتخذ اللجنة قرارا إلا بعد مراجعة جميع الأدلة.",
    explanation="To make a decision means to choose what to do after thinking about it.",
    tags=["Work"], imageKeyword="committee meeting around a table", emoji_formal="🏛️", emoji_casual="😴",
    grammar_patterns=["make a decision", "sleep on it", "only after + -ing, did + subject (inversion)"],
    grammar_patterns_translation=["يتخذ قرارا", "يفكر في الأمر قبل أن يقرر", "لم ... إلا بعد، مع تقديم الفعل للتوكيد"],
    morphology={"pos": "other"})

BREAK_THE_ICE = en_card(
    emoji="🧊", word="break the ice", translation="يكسر الجليد",
    example_casual="A funny story is a great way to break the ice.",
    example_formal="The host broke the ice by asking each guest to introduce themselves.",
    example_casual_translation="القصة المضحكة طريقة رائعة لكسر الجليد.",
    example_formal_translation="كسر المضيف الجليد عندما طلب من كل ضيف أن يعرف بنفسه.",
    explanation="To break the ice means to say or do something that helps people relax when they first meet.",
    tags=["Communication"], imageKeyword="people smiling at a meeting", emoji_formal="🎤", emoji_casual="😄",
    grammar_patterns=["break the ice (idiom)", "a way to + verb", "by + -ing"],
    grammar_patterns_translation=["يكسر الجليد", "طريقة ل + فعل", "عن طريق + مصدر"],
    morphology={"pos": "other"})

APPOINTMENT = dict(
    emoji="🩺", word="appointment", translation="موعد",
    example_formal="Please call us if you need to cancel your appointment.",
    example_casual_translation="لدي موعد عند الطبيب صباح الغد.",
    example_formal_translation="يرجى الاتصال بنا إذا كنت بحاجة إلى إلغاء موعدك.",
    explanation="An appointment is a fixed time to see someone, for example a doctor.",
    tags=["Health"], imageKeyword="calendar with appointment reminder", emoji_formal="📞", emoji_casual="🗓️",
    grammar_patterns=["need to + verb", "cancel an appointment"],
    grammar_patterns_translation=["يحتاج إلى + فعل", "يلغي موعدا"],
    morphology=en_noun("appointment", "appointments"))

DANKE_NOT_ENGLISH = en_card(
    emoji="🙏", word="thanks", translation="شكرا",
    example_casual="Thanks for your help.", example_formal="Thank you very much for your support.",
    example_casual_translation="شكرا على مساعدتك.", example_formal_translation="شكرا جزيلا على دعمك.",
    explanation="You say thanks when someone helps you.", tags=["Communication"],
    imageKeyword="person saying thank you", emoji_formal="🤝", emoji_casual="😊", morphology={"pos": "other"},
    input_in_language=False, input_suggestion="thanks")

DEADLINE = en_card(
    emoji="⏳", word="deadline", translation="الموعد النهائي",
    example_casual="The deadline for the project is Friday, right?",
    example_formal="Please submit the report before the deadline on Friday.",
    example_casual_translation="الموعد النهائي للمشروع يوم الجمعة، أليس كذلك؟",
    example_formal_translation="يرجى تقديم التقرير قبل الموعد النهائي يوم الجمعة.",
    explanation="A deadline is the latest time by which you must finish something.",
    tags=["Work"], imageKeyword="calendar", emoji_formal="📝", emoji_casual="📅",
    grammar_patterns=["the deadline for something", "before the deadline"],
    grammar_patterns_translation=["الموعد النهائي لشيء ما", "قبل الموعد النهائي"],
    morphology=en_noun("deadline", "deadlines"))

ENJOY = en_card(
    emoji="😊", word="enjoy", translation="يستمتع",
    example_casual="I really enjoy cooking for my friends.",
    example_formal="We hope you enjoyed your stay with us.",
    example_casual_translation="أستمتع حقا بالطبخ لأصدقائي.",
    example_formal_translation="نأمل أنك استمتعت بإقامتك معنا.",
    explanation="To enjoy something means to like it and have a good time doing it.",
    tags=["Feelings"], imageKeyword="friends cooking together", emoji_formal="🏨", emoji_casual="🍳",
    grammar_patterns=["enjoy + -ing", "look forward to + -ing", "We hope you enjoyed your stay with us."],
    grammar_patterns_translation=["يستمتع ب + مصدر", "يتطلع إلى + مصدر", "نأمل أنك استمتعت بإقامتك معنا."],
    morphology=en_verb("enjoy", "enjoyed", "enjoyed"))

# A regularized irregular verb on purpose: the word line must show the right forms.
TEACH_REGULARIZED = en_card(
    emoji="👩‍🏫", word="teach", translation="يعلم",
    example_casual="My mom taught me how to swim.",
    example_formal="Could you teach me a few words?",
    example_casual_translation="علمتني أمي السباحة.",
    example_formal_translation="هل يمكنك أن تعلمني بعض الكلمات؟",
    explanation="To teach means to help someone learn something.",
    tags=["Education"], imageKeyword="teacher helping a student", emoji_formal="📚", emoji_casual="🏊",
    grammar_patterns=["teach someone how to + verb"], grammar_patterns_translation=["يعلم شخصا كيف + فعل"],
    morphology=en_verb("teach", "teached", "teached"))

EN_SCENARIOS = [
    Scenario(
        "en_noun_prep_b1", "English at B1 with Arabic: a noun with its preposition first in the patterns, a regular "
        "plural (no word line), and a cloze of the preposition alone, without a letter hint.",
        "reason", [("main", REASON),
                   ("cloze", en_cloze("verb_prep", "Nobody knows the reason for his decision.", "for",
                                      "لا أحد يعرف سبب قراره.", hint="the reason for something"))],
        deck="Tarkib English", settings=ARABIC, language="en"),
    Scenario(
        "en_irregular_verb_a2_german", "English at A2 with German as the translation language: an irregular verb on "
        "the word line, patterns in value order, and a beginner letter hint.",
        "buy", [("main", BUY),
                ("cloze", en_cloze("single_word", "We bought bread at the market.", "bought",
                                   "Wir haben auf dem Markt Brot gekauft.", hint="buy, bought, bought"))],
        level="A2", deck="Tarkib English", settings={"defaults": {"translation_language": "German"}}, language="en"),
    Scenario(
        "en_uncountable_a1", "English at A1: an uncountable noun says so on the word line.",
        "information", [("main", INFORMATION),
                        ("cloze", en_cloze("single_word", "I need some information.", "information",
                                           "أحتاج إلى بعض المعلومات."))],
        level="A1", deck="Tarkib English", settings=ARABIC, language="en"),
    Scenario(
        "en_phrasal_b2_british", "A separable phrasal verb at B2 read by a British voice: British spelling in the "
        "prompts, French as the translation language, and a cloze of the particle alone.",
        "put off", [("main", PUT_OFF),
                    ("cloze", en_cloze("phrasal_verb", "We had to put the trip off because of the weather.", "off",
                                       "Nous avons dû reporter le voyage à cause du temps.", hint="put something off"))],
        level="B2", deck="Tarkib English", language="en",
        settings={"languages": {"en": {"voice": "en-GB-SoniaNeural", "translation": "French"}}}),
    Scenario(
        "en_irregular_plural_b1", "An irregular plural on the word line, and a verb with its preposition ranked first.",
        "child", [("main", CHILD),
                  ("cloze", en_cloze("single_word", "The children are playing in the garden.", "children",
                                     "الأطفال يلعبون في الحديقة.", hint="child, children"))],
        deck="Tarkib English", settings=ARABIC, language="en"),
    Scenario(
        "en_formal_native", "A formal word at Native: casual alternatives on both sides, the Formal tag (not doubled), "
        "the main call's own pattern kept so no separate grammar call, and the Arabic translation read aloud too.",
        "nevertheless",
        [("main", NEVERTHELESS),
         ("cloze", en_cloze("single_word", "It was raining, but we nevertheless went for a walk.", "nevertheless",
                            "كانت السماء تمطر، لكننا مع ذلك خرجنا في نزهة.", hint="nevertheless = but still (formal)"))],
        level="Native", deck="Tarkib English", language="en",
        settings={"defaults": {"translation_language": "Arabic"}, "voices": {"translation": "ar-SA-ZariyahNeural"}}),
    Scenario(
        "en_collocation_c1_german2", "A collocation at C1: the headword restated as a pattern is dropped, German as the "
        "second translation with its own voice, and a cloze of the verb alone.",
        "make a decision",
        [("main", MAKE_A_DECISION),
         ("secondary", {"word_translation": "eine Entscheidung treffen",
                        "casual": "Ehrlich gesagt kann ich mich erst entscheiden, wenn ich eine Nacht darüber geschlafen habe.",
                        "formal": "Erst nach Prüfung aller Beweise traf der Ausschuss eine Entscheidung."}),
         ("cloze", en_cloze("collocation", "We need to make a decision by Friday.", "make",
                            "يجب أن نتخذ قرارا بحلول يوم الجمعة.", hint="make a decision"))],
        level="C1", deck="Tarkib English", language="en", options={"secondary_language": "German"},
        settings={"languages": {"en": {"translation": "Arabic", "secondary": "German",
                                       "secondary_voice": "de-DE-KatjaNeural"}}}),
    Scenario(
        "en_idiom_b2", "An idiom at B2: the idiom restated as its own pattern is dropped, two cloze blanks with hints.",
        "break the ice",
        [("main", BREAK_THE_ICE),
         ("cloze", en_cloze("idiom", "Let's play a quick game to break the ice.", "break, ice",
                            "لنلعب لعبة سريعة لكسر الجليد.", hint="break the ice: help people relax"))],
        level="B2", deck="Tarkib English", settings=ARABIC, language="en"),
    Scenario(
        "en_leak_retry_b1", "An Arabic word in an English sentence at B1: one strict retry, and the clean card is used.",
        "appointment",
        [("main", en_card(example_casual="I have an appointment with the طبيب tomorrow.", **APPOINTMENT)),
         ("main", en_card(example_casual="I have a doctor's appointment tomorrow morning.", **APPOINTMENT)),
         ("cloze", en_cloze("single_word", "I have an appointment at ten.", "appointment", "لدي موعد في العاشرة."))],
        deck="Tarkib English", settings=ARABIC, language="en"),
    Scenario(
        "en_needs_translation_language", "English with the default settings, where the translation language is "
        "English: refused before any AI call, with a message that asks to pick one.",
        "window", [], deck="Tarkib English", language="en"),
    Scenario(
        "en_not_english_b1", "A German word typed as English: two calls agree it is not English, so the card is "
        "refused with the suggestion the AI made.",
        "danke", [("main", DANKE_NOT_ENGLISH), ("main", DANKE_NOT_ENGLISH)],
        deck="Tarkib English", settings=ARABIC, language="en"),
    Scenario(
        "en_hints_no_cloze_b1", "Meaning, scenario and picture hints (the scenario in German), a second translation "
        "language equal to the learning language (skipped with a warning), and no cloze card.",
        "deadline", [("main", DEADLINE)],
        deck="Tarkib English", settings=ARABIC, language="en", cloze=False,
        options={"meaning": "time limit at work", "scenario": "Projekt im Büro", "image_keyword": "calendar",
                 "secondary_language": "English"}),
    Scenario(
        "en_verb_pattern_b1", "A verb pattern with -ing ranked in, an invented pattern dropped (none of its words is in "
        "the sentences) and a whole sentence dropped; a regular verb shows no word line.",
        "enjoy", [("main", ENJOY),
                  ("cloze", en_cloze("single_word", "Did you enjoy the film?", "enjoy", "هل استمتعت بالفيلم؟"))],
        deck="Tarkib English", settings=ARABIC, language="en"),
    Scenario(
        "en_regularized_verb_a2", "The AI regularized an irregular verb (teached): the word line shows the right forms.",
        "teach", [("main", TEACH_REGULARIZED),
                  ("cloze", en_cloze("single_word", "She teaches math at a school.", "teaches",
                                     "هي تدرس الرياضيات في مدرسة."))],
        level="A2", deck="Tarkib English", settings=ARABIC, language="en"),
]

SCENARIOS += EN_SCENARIOS


# ── Spanish (the generic set with Spanish's note and checks) ─────────────────────────────────
es_card, es_cloze = en_card, en_cloze      # the same neutral keys


def es_noun(article, gender, noun, plural):
    return {"pos": "noun", "article": article, "gender": gender, "noun": noun, "plural": plural}


def es_verb(infinitive, yo, preterite, participle):
    return {"pos": "verb", "infinitive": infinitive, "yo": yo, "preterite": preterite, "participle": participle}


MESA = es_card(
    emoji="🪑", word="la mesa", translation="طاولة",
    example_casual="Pon la taza en la mesa.",
    example_formal="¿Puede usted limpiar la mesa?",
    example_casual_translation="ضع الكوب على الطاولة.",
    example_formal_translation="هل يمكنك أن تنظف الطاولة؟",
    explanation="Una mesa es un mueble para comer o trabajar.",
    tags=["Casa"], imageKeyword="wooden kitchen table", emoji_formal="🧽", emoji_casual="☕",
    grammar_patterns=["poner algo en algo", "¿Puede usted + infinitivo?"],
    grammar_patterns_translation=["يضع شيئا على شيء", "هل يمكنك + فعل؟"],
    morphology=es_noun("la", "f", "mesa", "las mesas"))

PENSAR_EN = es_card(
    emoji="💭", word="pensar en", translation="يفكر في",
    example_casual="Últimamente pienso mucho en mis padres.",
    example_formal="¿Ha pensado usted en nuestra propuesta?",
    example_casual_translation="أفكر كثيرا في والدي مؤخرا.",
    example_formal_translation="هل فكرت في اقتراحنا؟",
    explanation="Pensar en algo es tenerlo en la cabeza.",
    tags=["Sentimientos"], imageKeyword="person thinking at a window", emoji_formal="📄", emoji_casual="👨‍👩‍👦",
    grammar_patterns=["haber + participio", "pensar en algo"],
    grammar_patterns_translation=["الفعل المساعد + اسم المفعول", "يفكر في شيء"],
    morphology=es_verb("pensar", "pienso", "pensó", "pensado"))

TENER = es_card(
    emoji="⏱️", word="tener", translation="haben",
    example_casual="Ayer tuve que trabajar hasta tarde.",
    example_formal="¿Tiene usted un momento, por favor?",
    example_casual_translation="Gestern musste ich bis spät arbeiten.",
    example_formal_translation="Haben Sie bitte einen Moment Zeit?",
    explanation="Tener es cuando algo es tuyo.",
    tags=["Cotidiano"], imageKeyword="person working late at a desk", emoji_formal="🙋", emoji_casual="💼",
    grammar_patterns=["tener que + infinitivo", "hasta tarde"],
    grammar_patterns_translation=["müssen + Infinitiv", "bis spät"],
    morphology=es_verb("tener", "tengo", "tuvo", "tenido"))

# A regularized irregular verb on purpose: the word line must show the right forms.
HACER_REGULARIZED = es_card(
    emoji="🍳", word="hacer", translation="يفعل",
    example_casual="Hoy hago yo la cena.",
    example_formal="¿Qué hace usted los fines de semana?",
    example_casual_translation="اليوم أنا من يعد العشاء.",
    example_formal_translation="ماذا تفعل في عطلات نهاية الأسبوع؟",
    explanation="Hacer es crear algo o ocuparse de algo.",
    tags=["Cotidiano"], imageKeyword="person cooking dinner", emoji_formal="📅", emoji_casual="🍲",
    grammar_patterns=["hacer la cena", "los fines de semana"],
    grammar_patterns_translation=["يعد العشاء", "في عطلات نهاية الأسبوع"],
    morphology=es_verb("hacer", "hago", "hací", "hacido"))

ESTAR_CANSADO = es_card(
    emoji="😴", word="estar cansado", translation="to be tired",
    example_casual="Estoy cansado de esperar el autobús.",
    example_formal="¿Está usted cansado después del viaje?",
    example_casual_translation="I'm tired of waiting for the bus.",
    example_formal_translation="Are you tired after the trip?",
    explanation="Estar cansado es necesitar descansar.",
    tags=["Sentimientos"], imageKeyword="tired person waiting at a bus stop", emoji_formal="✈️", emoji_casual="🚌",
    grammar_patterns=["después de algo", "estar cansado de + infinitivo"],
    grammar_patterns_translation=["after something", "to be tired of + -ing"],
    morphology={"pos": "other"})

DARSE_CUENTA = es_card(
    emoji="⏰", word="darse cuenta", translation="se rendre compte",
    example_casual="Ni me di cuenta de que ya era tarde.",
    example_formal="Usted se dará cuenta de la diferencia enseguida.",
    example_casual_translation="Je ne me suis même pas rendu compte qu'il était déjà tard.",
    example_formal_translation="Vous remarquerez tout de suite la différence.",
    explanation="Darse cuenta es entender algo de repente.",
    tags=["Comunicación"], imageKeyword="person looking at a clock surprised", emoji_formal="🔍", emoji_casual="🌙",
    grammar_patterns=["darse cuenta de algo", "darse cuenta de que + indicativo"],
    grammar_patterns_translation=["se rendre compte de quelque chose", "se rendre compte que + indicatif"],
    morphology={"pos": "other"})

NO_OBSTANTE = es_card(
    emoji="⚖️", word="no obstante", translation="ومع ذلك", register="formal",
    casual_alternatives=["pero", "aun así"], casual_alternatives_translation=["لكن", "رغم ذلك"],
    example_formal="Es un plan arriesgado y, no obstante, lo vamos a intentar.",
    example_casual="Es arriesgado, pero aun así lo vamos a hacer.",
    example_formal_translation="إنها خطة محفوفة بالمخاطر، ومع ذلك سنحاول تنفيذها.",
    example_casual_translation="الأمر فيه مخاطرة، لكننا سنفعله على أي حال.",
    explanation="Palabra formal para decir que algo pasa a pesar de lo anterior. En el día a día se dice aun así.",
    tags=["Comunicación", "Formal"], imageKeyword="team deciding to go ahead with a plan", emoji_formal="📊",
    emoji_casual="🤷", grammar_patterns=["Es arriesgado, pero aun así lo vamos a hacer."],
    grammar_patterns_translation=["الأمر فيه مخاطرة، لكننا سنفعله على أي حال."], morphology={"pos": "other"})

TOMAR_UNA_DECISION = es_card(
    emoji="⚖️", word="tomar una decisión", translation="يتخذ قرارا",
    example_casual="Mira, no puedo tomar una decisión sin consultarlo con la almohada.",
    example_formal="Solo tras analizar todos los datos, la comisión tomó una decisión.",
    example_casual_translation="انظر، لا أستطيع أن أتخذ قرارا قبل أن أفكر في الأمر جيدا.",
    example_formal_translation="لم تتخذ اللجنة قرارا إلا بعد تحليل جميع البيانات.",
    explanation="Tomar una decisión es elegir qué hacer después de pensarlo.",
    tags=["Trabajo"], imageKeyword="committee meeting around a table", emoji_formal="🏛️", emoji_casual="😴",
    grammar_patterns=["tomar una decisión", "consultarlo con la almohada", "tomar una decisión sobre algo"],
    grammar_patterns_translation=["يتخذ قرارا", "يفكر في الأمر قبل أن يقرر", "يتخذ قرارا بشأن شيء"],
    morphology={"pos": "other"})

TOMAR_EL_PELO = es_card(
    emoji="😄", word="tomar el pelo", translation="يمزح مع شخص",
    example_casual="¿Me estás tomando el pelo?",
    example_formal="Le aseguro que no le estoy tomando el pelo.",
    example_casual_translation="هل تمزح معي؟",
    example_formal_translation="أؤكد لك أنني لا أمزح معك.",
    explanation="Tomar el pelo a alguien es engañarlo en broma.",
    tags=["Comunicación"], imageKeyword="friends laughing together", emoji_formal="🤝", emoji_casual="😂",
    grammar_patterns=["tomar el pelo (modismo)", "tomar el pelo a alguien", "estar + gerundio"],
    grammar_patterns_translation=["يمزح (تعبير اصطلاحي)", "يمزح مع شخص", "فعل مستمر"],
    morphology={"pos": "other"})

CITA = dict(
    emoji="🩺", word="la cita", translation="موعد",
    example_formal="Por favor, llame si necesita cancelar su cita.",
    example_casual_translation="لدي موعد مع الطبيب صباح الغد.",
    example_formal_translation="يرجى الاتصال إذا كنت بحاجة إلى إلغاء موعدك.",
    explanation="Una cita es una hora fija para ver a alguien, por ejemplo al médico.",
    tags=["Salud"], imageKeyword="calendar with appointment reminder", emoji_formal="📞", emoji_casual="🗓️",
    grammar_patterns=["tener una cita con alguien", "cancelar una cita"],
    grammar_patterns_translation=["لديه موعد مع شخص", "يلغي موعدا"],
    morphology=es_noun("la", "f", "cita", "las citas"))

GRACIAS_NOT_SPANISH = es_card(
    emoji="🙏", word="thanks", translation="شكرا",
    example_casual="Gracias por tu ayuda.", example_formal="Muchas gracias por su apoyo.",
    example_casual_translation="شكرا على مساعدتك.", example_formal_translation="شكرا جزيلا على دعمك.",
    explanation="Se dice gracias cuando alguien te ayuda.", tags=["Comunicación"],
    imageKeyword="person saying thank you", emoji_formal="🤝", emoji_casual="😊", morphology={"pos": "other"},
    input_in_language=False, input_suggestion="gracias")

PLAZO = es_card(
    emoji="⏳", word="el plazo", translation="الموعد النهائي",
    example_casual="El plazo del proyecto es el viernes, ¿no?",
    example_formal="Por favor, entregue el informe dentro del plazo.",
    example_casual_translation="الموعد النهائي للمشروع يوم الجمعة، أليس كذلك؟",
    example_formal_translation="يرجى تسليم التقرير ضمن المهلة المحددة.",
    explanation="El plazo es el tiempo que tienes para terminar algo.",
    tags=["Trabajo"], imageKeyword="calendar", emoji_formal="📝", emoji_casual="📅",
    grammar_patterns=["dentro del plazo", "el plazo de algo"],
    grammar_patterns_translation=["ضمن المهلة", "الموعد النهائي لشيء"],
    morphology=es_noun("el", "m", "plazo", "los plazos"))

AGUA = es_card(
    emoji="💧", word="agua", translation="ماء",
    example_casual="¿Me das un vaso de agua?",
    example_formal="¿Podría traerme agua, por favor?",
    example_casual_translation="هل تعطيني كوبا من الماء؟",
    example_formal_translation="هل يمكنك أن تحضر لي ماء من فضلك؟",
    explanation="El agua es lo que bebemos cuando tenemos sed.",
    tags=["Comida"], imageKeyword="glass of water on a table", emoji_formal="🙏", emoji_casual="🥛",
    grammar_patterns=["un vaso de algo", "¿Podría + infinitivo?"],
    grammar_patterns_translation=["كوب من شيء", "هل يمكنك + فعل؟"],
    morphology=es_noun("el", "f", "agua", "las aguas"))

ES_SCENARIOS = [
    Scenario(
        "es_noun_a1_arabic", "Spanish at A1 with Arabic: the article added to a bare noun, the article in red on the "
        "word line (a regular plural is not shown), and a noun cloze with its article.",
        "mesa", [("main", MESA),
                 ("cloze", es_cloze("single_word", "La mesa es nueva.", "La mesa", "الطاولة جديدة."))],
        level="A1", deck="Tarkib Spanish", settings=ARABIC, language="es"),
    Scenario(
        "es_verb_prep_b1", "A verb with its preposition at B1: ranked before a structure, the stem-changing verb on the "
        "word line, and a cloze of the preposition alone, without a letter hint.",
        "pensar en", [("main", PENSAR_EN),
                      ("cloze", es_cloze("verb_prep", "Siempre pienso en ti cuando llueve.", "en",
                                         "أفكر فيك دائما عندما تمطر.", hint="pensar en algo"))],
        deck="Tarkib Spanish", settings=ARABIC, language="es"),
    Scenario(
        "es_irregular_verb_a2_german", "An irregular verb at A2 with German as the translation language: the four forms "
        "on the word line, the card's own verb in a frame first (tener que + infinitivo, ahead of a preposition "
        "frame), and a beginner letter hint.",
        "tener", [("main", TENER),
                  ("cloze", es_cloze("single_word", "Mi hermana tiene dos hijos.", "tiene",
                                     "Meine Schwester hat zwei Kinder."))],
        level="A2", deck="Tarkib Spanish", settings={"defaults": {"translation_language": "German"}}, language="es"),
    Scenario(
        "es_regularized_verb_a2", "The AI regularized an irregular verb (hací, hacido): the word line shows the right "
        "forms from the table.",
        "hacer", [("main", HACER_REGULARIZED),
                  ("cloze", es_cloze("single_word", "Mi madre hace pan los domingos.", "hace",
                                     "تصنع أمي الخبز أيام الأحد."))],
        level="A2", deck="Tarkib Spanish", settings=ARABIC, language="es"),
    Scenario(
        "es_ser_estar_default", "Spanish with the default settings: the German cards' English is borrowed as the "
        "translation language, ser or estar ranked, and a cloze of the estar form alone, without a hint, its answer "
        "written in small letters at the start of the sentence (it takes the sentence's capital).",
        "estar cansado", [("main", ESTAR_CANSADO),
                          ("cloze", es_cloze("ser_estar", "Está muy cansado después del viaje.", "está",
                                             "He is very tired after the trip.", hint="estar + adjetivo"))],
        deck="Tarkib Spanish", language="es"),
    Scenario(
        "es_latam_voice_b2", "A Latin American voice at B2: Latin American Spanish in the prompts, French as the "
        "translation language, two verb + preposition patterns kept.",
        "darse cuenta", [("main", DARSE_CUENTA),
                         ("cloze", es_cloze("single_word", "No me di cuenta del error.", "cuenta",
                                            "Je ne me suis pas rendu compte de l'erreur."))],
        level="B2", deck="Tarkib Spanish", language="es",
        settings={"languages": {"es": {"voice": "es-MX-DaliaNeural", "translation": "French"}}}),
    Scenario(
        "es_formal_native", "A formal word at Native: casual alternatives, the Formal tag, the separate grammar call "
        "because the main call's one pattern was a whole sentence (dropped there and in the grammar call's answer), and "
        "the borrowed Arabic translation read aloud with the borrowed voice.",
        "no obstante",
        [("main", NO_OBSTANTE),
         ("grammar", {"grammar_patterns": ["ir a + infinitivo", "Es arriesgado, pero aun así lo vamos a hacer."],
                      "grammar_patterns_translation": ["سوف + فعل", "الأمر فيه مخاطرة، لكننا سنفعله على أي حال."]}),
         ("cloze", es_cloze("single_word", "Llovía mucho y, no obstante, salimos a pasear.", "no obstante",
                            "كانت تمطر كثيرا، ومع ذلك خرجنا للتنزه.", hint="no obstante = aun así (formal)"))],
        level="Native", deck="Tarkib Spanish", language="es",
        settings={"defaults": {"translation_language": "Arabic"}, "voices": {"translation": "ar-SA-ZariyahNeural"}}),
    Scenario(
        "es_collocation_c1_english2", "A collocation at C1: the headword restated is dropped, the headword with a "
        "placeholder (sobre algo) is kept, English as the second translation with its voice, a cloze of the verb alone.",
        "tomar una decisión",
        [("main", TOMAR_UNA_DECISION),
         ("secondary", {"word_translation": "to make a decision",
                        "casual": "Look, I can't make a decision until I've slept on it.",
                        "formal": "Only after analyzing all the data did the committee make a decision."}),
         ("cloze", es_cloze("collocation", "Tenemos que tomar una decisión antes del viernes.", "tomar",
                            "يجب أن نتخذ قرارا قبل يوم الجمعة.", hint="tomar una decisión"))],
        level="C1", deck="Tarkib Spanish", language="es", options={"secondary_language": "English"},
        settings={"languages": {"es": {"translation": "Arabic", "secondary": "English",
                                       "secondary_voice": "en-US-JennyNeural"}}}),
    Scenario(
        "es_idiom_b2", "An idiom at B2: the idiom restated is dropped, the idiom with a person (a alguien) is kept, "
        "estar + gerundio ranked after it, two cloze blanks with hints.",
        "tomar el pelo",
        [("main", TOMAR_EL_PELO),
         ("cloze", es_cloze("idiom", "No te creo, me estás tomando el pelo.", "tomando, pelo",
                            "لا أصدقك، أنت تمزح معي.", hint="tomar el pelo: engañar en broma"))],
        level="B2", deck="Tarkib Spanish", settings=ARABIC, language="es"),
    Scenario(
        "es_leak_retry_b1", "An English word in a Spanish sentence at B1: one strict retry, and the clean card is used.",
        "la cita",
        [("main", es_card(example_casual="Mañana tengo una cita con the médico.", **CITA)),
         ("main", es_card(example_casual="Mañana tengo una cita con el médico.", **CITA)),
         ("cloze", es_cloze("single_word", "Tengo una cita a las diez.", "una cita", "لدي موعد في العاشرة."))],
        deck="Tarkib Spanish", settings=ARABIC, language="es"),
    Scenario(
        "es_not_spanish_b1", "An English word typed as Spanish: two calls agree it is not Spanish, so the card is "
        "refused with the suggestion the AI made.",
        "thanks", [("main", GRACIAS_NOT_SPANISH), ("main", GRACIAS_NOT_SPANISH)],
        deck="Tarkib Spanish", settings=ARABIC, language="es"),
    Scenario(
        "es_hints_no_cloze_b1", "Meaning, scenario and picture hints (the scenario in Spanish), a second translation "
        "equal to the learning language (skipped with a warning), and no cloze card.",
        "el plazo", [("main", PLAZO)],
        deck="Tarkib Spanish", settings=ARABIC, language="es", cloze=False,
        options={"meaning": "time limit at work", "scenario": "proyecto en la oficina", "image_keyword": "calendar",
                 "secondary_language": "Spanish"}),
    Scenario(
        "es_style_b1", "Style wishes on a Spanish card: the same block in the generic main and cloze requests.",
        "pensar en", [("main", PENSAR_EN),
                      ("cloze", es_cloze("verb_prep", "Siempre pienso en ti cuando cocino.", "en",
                                         "أفكر فيك دائما عندما أطبخ.", hint="pensar en algo"))],
        deck="Tarkib Spanish", settings=ARABIC, language="es",
        options={"style": "Examples about cooking, short sentences."}),
    Scenario(
        "es_feminine_el_a2", "A feminine noun that takes el, typed bare and kept bare by the model: the card shows "
        "el agua (the word line's article in front), the article in red with the plural las aguas, and the noun cloze "
        "given its article from the sentence.",
        "agua", [("main", AGUA),
                    ("cloze", es_cloze("single_word", "El agua está muy fría.", "agua", "الماء بارد جدا."))],
        level="A2", deck="Tarkib Spanish", settings=ARABIC, language="es"),
]

SCENARIOS += ES_SCENARIOS

BY_NAME = {s.name: s for s in SCENARIOS}
assert len(BY_NAME) == len(SCENARIOS), "two scenarios share a name"


# ── the fakes ──────────────────────────────────────────────────────────────────────────────
def call_kind(system):
    """Which of the four calls a system prompt belongs to (German's tuned prompts or the generic ones)."""
    if system == prompts.SYSTEM_CLOZE or "cloze-deletion" in system[:80]:
        return "cloze"
    if system == prompts.SYSTEM_GRAMMAR or system.startswith("You extract reusable grammar patterns"):
        return "grammar"
    if system == prompts.SYSTEM_ARABIC or system.startswith("You are an expert translator into"):
        return "secondary"
    if system.startswith("You create ") and "flashcards" in system[:80]:
        return "main"
    return "unknown"


def _system_parts():
    parts = [("de/main_%s" % lv, prompts.system_main_for_level(lv)) for lv in prompts.LEVELS]
    parts += [("de/grammar", prompts.SYSTEM_GRAMMAR), ("de/cloze", prompts.SYSTEM_CLOZE),
              ("de/secondary_Arabic", prompts.SYSTEM_ARABIC)]
    return parts


def prompt_name(system, s=None):
    """The system prompt as the frozen parts it is made of (files in tests/golden/prompts/), e.g.
    "de/main_A1 + de/translation_override_Arabic", or None when it is not built from them. For a language on
    the generic set, the name says which prompt function made it and with which facts, e.g.
    "en/main_B1 [Arabic, en-US-JennyNeural]" (en/main_B1.txt freezes that one with Arabic and the US voice)."""
    if s is not None and s.language != "de":
        return _generic_prompt_name(system, s)
    for name, text in _system_parts():
        if system == text:
            return name
        if not (name.startswith("de/main_") and system.startswith(text)):
            continue
        rest, parts = system[len(text):], [name]
        m = re.match(r" # TRANSLATION LANGUAGE = (.+?) \(NOT English\)", rest)
        if m and rest.startswith(prompts.translation_override(m.group(1))):
            parts.append("de/translation_override_%s" % m.group(1))
            rest = rest[len(prompts.translation_override(m.group(1))):]
        if rest.startswith(prompts.SYSTEM_LOANWORDS_EXPANDED):
            parts.append("de/loanwords")
            rest = rest[len(prompts.SYSTEM_LOANWORDS_EXPANDED):]
        if not rest:
            return " + ".join(parts)
    if system.startswith(prompts.SYSTEM_GRAMMAR):
        m = re.match(r" # TRANSLATION LANGUAGE = (.+?) \(NOT English\): write grammar_patterns_en", system[len(prompts.SYSTEM_GRAMMAR):])
        if m and system == prompts.SYSTEM_GRAMMAR + prompts.grammar_override(m.group(1)):
            return "de/grammar + de/grammar_override_%s" % m.group(1)
    m = re.match(r"You are an expert translator into (.+?)\. ", system)
    if m and system == prompts.secondary_translation_system(m.group(1)):
        return "de/secondary_%s" % m.group(1)
    return None


def scenario_facts(s):
    """(translation language, voice of the learning language) as build_card will resolve them."""
    settings = generate.language_settings(s.config(), s.language)
    return settings["translation"] or prompts.DEFAULT_TRANSLATION_LANG, settings["voice"]


def _generic_prompt_name(system, s):
    lang, (helper, voice) = s.language, scenario_facts(s)
    for lv in prompts.LEVELS:
        if system == prompts.main_system(lang, lv, helper, bool(s.options.get("scenario")), voice=voice):
            return "%s/main_%s [%s, %s]" % (lang, lv, helper, voice)
    if system == prompts.grammar_system(lang, helper):
        return "%s/grammar [%s]" % (lang, helper)
    if system == prompts.cloze_system(lang):
        return "%s/cloze" % lang
    second = s.options.get("secondary_language")
    if second and system == prompts.secondary_system(lang, second):
        return "%s/secondary_%s" % (lang, second)
    return None


class _Note(dict):
    def __init__(self, model):
        super().__init__()
        self.model, self.tags, self.id = model, [], None


class _Media:
    def __init__(self):
        self.files = {}

    def write_data(self, name, data):
        self.files[name] = data
        return name


class _Decks:
    def __init__(self):
        self.ids = {}

    def id(self, name, create=True):
        return self.ids.setdefault(name, 1000 + len(self.ids))

    def name(self, did):
        return next(n for n, i in self.ids.items() if i == did)


class _Collection:
    """Just what anki_io.write_bundle touches."""
    def __init__(self):
        self.media, self.decks, self.models, self.added = _Media(), _Decks(), object(), []

    def add_custom_undo_entry(self, name):
        self.undo_name = name
        return 1

    def new_note(self, model):
        return _Note(model)

    def add_note(self, note, deck_id):
        note.id = 100 + len(self.added)
        self.added.append((note, deck_id))

    def merge_undo_entries(self, target):
        return "changes"


def run(s):
    """Build and store scenario `s`. Returns a dict: bundle, error, calls (every AI request), pictures,
    speech (every read-aloud attempt), notes (as stored), files (media as stored), violations (the
    scenario's script was not followed; always a test failure)."""
    calls, pictures, speech, violations = [], [], [], []
    answers = list(s.ai)

    def fake_json(provider, system, user, **kw):
        kind = call_kind(system)
        n = len(calls) + 1
        calls.append({"kind": kind, "system": system, "user": user,
                      "temperature": kw.get("temperature"), "max_tokens": kw.get("max_tokens")})
        if not answers:
            violations.append("AI call %d (%s) was not in the script" % (n, kind))
            raise RuntimeError("unexpected AI call")
        want, answer = answers.pop(0)
        if want != kind:
            violations.append("AI call %d was %s, the script expected %s" % (n, kind, want))
        if isinstance(answer, BaseException):
            raise answer
        return copy.deepcopy(answer)

    def fake_picture(keyword, deck, image_source, keys, timeout=15, exclude=None):
        name = "pexels_%s.jpg" % (re.sub(r"\W+", "_", (keyword or "").lower()).strip("_")[:40] or "x")
        pictures.append({"keyword": keyword, "deck": deck, "source": image_source,
                         "found": name if s.picture else None})
        return (name, b"\xff\xd8\xff\xe0 picture") if s.picture else None

    script = {k: list(v) for k, v in s.voices.items()}

    def adapter_for(service):
        def adapter(text, role_voice, sc, timeout, rate=1.0):
            out = script[service].pop(0) if script.get(service) else None
            speech.append({"service": service, "voice": role_voice, "text": text,
                           "failed": isinstance(out, BaseException)})
            if rate != 1.0:
                speech[-1]["rate"] = rate             # only a slowed clip says so: older goldens stay
            if isinstance(out, BaseException):
                raise out
            return tts.Clip(b"audio from " + service.encode(), "mp3", service, role_voice, rate)
        return adapter

    saved = (providers.complete_json, generate.images.fetch_image, dict(tts._ADAPTERS),
             anki_io.ensure_notetypes, anki_io.check_cloze_notetype, anki_io.find_main, anki_io.find_cloze)
    bundle = error = None
    notes, files = [], {}
    try:
        providers.complete_json = fake_json
        generate.images.fetch_image = fake_picture
        generate._PICTURE_RETRY_PAUSE = 0
        for service in tts.SERVICES:
            tts._ADAPTERS[service] = adapter_for(service)
        anki_io.ensure_notetypes = lambda col: None
        anki_io.check_cloze_notetype = lambda m: None
        anki_io.find_main = lambda mm: "main"
        anki_io.find_cloze = lambda mm: "cloze"
        try:
            bundle = generate.build_card(s.config(), PROVIDER, s.deck, s.word, s.build_options())
        except Exception as e:
            error = "%s: %s" % (type(e).__name__, e)
        if bundle is not None:
            col = _Collection()
            anki_io.write_bundle(col, bundle)
            for note, did in col.added:
                notes.append({"type": note.model, "deck": col.decks.name(did), "fields": dict(note),
                              "tags": list(note.tags)})
            files = dict(col.media.files)
    finally:
        (providers.complete_json, generate.images.fetch_image, adapters, anki_io.ensure_notetypes,
         anki_io.check_cloze_notetype, anki_io.find_main, anki_io.find_cloze) = saved
        tts._ADAPTERS.clear()
        tts._ADAPTERS.update(adapters)
        generate._PICTURE_RETRY_PAUSE = 1.0
        generate._USED_PICTURES.clear()
    if answers:
        violations.append("%d scripted AI answer(s) never asked for: %s"
                          % (len(answers), ", ".join(k for k, _ in answers)))
    return {"bundle": bundle, "error": error, "calls": calls, "pictures": pictures, "speech": speech,
            "notes": notes, "files": files, "violations": violations}


# ── the golden file of one scenario ────────────────────────────────────────────────────────
def _json(v):
    return json.dumps(v, ensure_ascii=False, sort_keys=True)


def golden_text(s, r):
    out = []
    w = out.append
    w('# Golden card "%s" (tests/card_scenarios.py)' % s.name)
    w("# %s" % s.about)
    w("# After a change you meant: UPDATE_GOLDEN=1 python3 tests/test_cards.py, then read the git diff.")
    w("")
    w("input: %s" % s.word)
    w("deck: %s | level: %s | cloze: %s" % (s.deck, s.level, "on" if s.cloze else "off"))
    if s.options:
        w("options: %s" % _json(s.options))
    if s.settings:
        w("settings: %s" % _json(s.settings))
    for i, c in enumerate(r["calls"], 1):
        name = prompt_name(c["system"], s)
        w("")
        w("== AI call %d: %s (temperature %s, max_tokens %s)" % (i, c["kind"], c["temperature"], c["max_tokens"]))
        w("system: %s" % (name or "NOT A FROZEN PROMPT, full text:"))
        if not name:
            w(c["system"])
        w("user:")
        w(c["user"])
    w("")
    w("== picture search")
    if not r["pictures"]:
        w("none")
    for p in r["pictures"]:
        w("keyword: %s | deck: %s | source: %s -> %s" % (p["keyword"], p["deck"], p["source"], p["found"] or "nothing found"))
    w("")
    w("== read aloud")
    if not r["speech"]:
        w("nothing")
    for i, sp in enumerate(r["speech"], 1):
        w("%d. %s %s%s%s: %s" % (i, sp["service"], sp["voice"], " at %sx speed" % sp["rate"] if "rate" in sp else "",
                                 " FAILED" if sp["failed"] else "", sp["text"]))
    if r["error"]:
        w("")
        w("== refused")
        w(r["error"])
    for note in r["notes"]:
        w("")
        w('== %s note in deck "%s"' % (note["type"], note["deck"]))
        w("tags: %s" % " ".join(note["tags"]))
        for k, v in note["fields"].items():
            w("-- %s" % k)
            w(v)
    if r["bundle"] is not None:
        w("")
        w("== media files")
        if not r["files"]:
            w("none")
        for name in sorted(r["files"]):
            data = r["files"][name]
            w("%s <- %s" % (name, data.decode("ascii") if data.startswith(b"audio from") else "picture"))
        w("")
        w("== for the dialog (bundle meta)")
        w(json.dumps(r["bundle"]["meta"], ensure_ascii=False, indent=2, sort_keys=True))
    return "\n".join(out) + "\n"


# ── a made-up language, the way a new one would be added ─────────────────────────────────────
ITALIAN = {"code": "it", "name": "Italian", "native_name": "Italiano", "label": "🇮🇹 Italiano", "quotes": ("«", "»"),
           "inner_quotes": ("“", "”"),
           "default_voice": "it-IT-ElsaNeural",
           "headword_prefixes": ("il", "lo", "la", "i", "gli", "le", "un", "uno", "una"),
           "formal_tag": "Formale", "script": "LATIN", "example_word": "il tavolo",
           "default_deck": "Tarkib Italian", "voice_locales": ("it-IT",)}


class MadeUpLanguage:
    """Adds Italian to the registry and gives it the generic prompts and rules, with no note and no checks
    of its own, for the length of a `with` block: what adding a language with nothing but its registry entry
    gives. tests/test_languages.py builds a whole card with it; tests/test_prompts.py freezes its prompts."""

    def __enter__(self):
        self._saved = (languages.LANGUAGES, dict(languages._BY_CODE))
        languages.LANGUAGES = languages.LANGUAGES + (ITALIAN,)
        languages._BY_CODE["it"] = ITALIAN
        prompts.PROMPTS["it"] = prompts.generic_prompts("it")
        generate.RULES["it"] = generate.generic_rules("it")
        return self

    def __exit__(self, *exc):
        languages.LANGUAGES, by_code = self._saved
        languages._BY_CODE.clear()
        languages._BY_CODE.update(by_code)
        prompts.PROMPTS.pop("it", None)
        generate.RULES.pop("it", None)


TAVOLO = {"emoji": "🪑", "word": "il tavolo", "translation": "table", "register": "neutral",
          "casual_alternatives": [], "casual_alternatives_translation": [],
          "example_casual": "Metti le chiavi sul tavolo, per favore.",
          "example_formal": "Il tavolo per quattro persone è pronto.",
          "example_casual_translation": "Put the keys on the table, please.",
          "example_formal_translation": "The table for four people is ready.",
          "explanation": "Un mobile con una superficie piana dove si mangia o si lavora.",
          "tags": ["Home"], "imageKeyword": "wooden table", "emoji_formal": "🍽️", "emoji_casual": "🔑",
          "grammar_patterns": ["mettere qualcosa su qualcosa"], "grammar_patterns_translation": ["to put something on something"],
          "morphology": {"pos": "noun", "article": "il", "plural": "i tavoli"},
          "input_in_language": True, "input_suggestion": ""}

ITALIAN_SCENARIO = Scenario(
    "it_made_up_language", "A language with nothing but its registry entry: the generic prompts and rules make the "
    "whole card.",
    "il tavolo", [("main", TAVOLO),
                  ("cloze", {"case": "single_word", "sentence": "Il gatto dorme sotto il tavolo.", "answer": "tavolo",
                             "translation": "The cat is sleeping under the table.", "grammar_hint": "",
                             "idiom_meaning": ""})],
    deck="Tarkib Italian", language="it")
