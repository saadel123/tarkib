"""The languages Tarkib makes cards for: the ONE place a learning language is declared.

A learning language is the one the learner studies: its words are typed into Tarkib and its sentences
fill the card. The translation (helper) language is a different list (prompts.translation_languages): every
learning language is also a translation language for the others, never for itself.

Pure data and two small helpers, no imports. What a language DOES lives in the module that does it,
keyed by the code below:

    pipeline/prompts.py    PROMPTS[code]: every prompt and user message (German: the tuned set; any
                           other language: the generic set, with its NOTE where it has one)
    pipeline/generate.py   RULES[code]: the checks on the AI's answer and the parts of the card
                           that depend on the language (German: its own guards; any other language:
                           the generic checks, with its CHECKS where it has them)
    pipeline/<language>.py NOTE and CHECKS of one language (pipeline/english.py)

tests/test_languages.py fails until every table has an entry for every language listed here, the way
a compiler points at each place a new value is missing. docs/languages.md walks through it.
"""

LANGUAGES = (
    {
        "code": "de",
        # English name: messages and prompts name the language with it
        "name": "German",
        # the language's own name
        "native_name": "Deutsch",
        # the heading of the card's section in this language
        "label": "🇩🇪 Deutsch",
        # the quotes around the explanation, which is written in this language
        "quotes": ("„", '"'),
        # the free Edge voice that reads this language until the learner picks one
        "default_voice": "de-DE-KatjaNeural",
        # words dropped from the front of a headword before the AI's word is compared with the typed one
        "headword_prefixes": ("der", "die", "das", "sich"),
        # the tag a formal word gets
        "formal_tag": "Formell",
        # the writing system (the first word of the letters' Unicode names): a letter of another script in
        # a sentence is a word of the translation language leaking in
        "script": "LATIN",
        # the Add window: the hint in the empty word box, and the deck new cards go to until the learner picks
        # another (German: the configured default deck, which is "Tarkib" unless changed)
        "example_word": "die Probe",
        "default_deck": "Tarkib",
        # Settings: the voices offered for this language
        "voice_locales": ("de-DE", "de-AT", "de-CH"),
    },
    {
        "code": "en",
        "name": "English",
        "native_name": "English",
        "label": "🇬🇧 English",
        "quotes": ("“", "”"),
        # US by default: the spelling follows the voice (a British voice gets British English)
        "default_voice": "en-US-JennyNeural",
        "headword_prefixes": ("the", "a", "an", "to"),
        "formal_tag": "Formal",
        "script": "LATIN",
        "example_word": "give up",
        "default_deck": "Tarkib English",
        "voice_locales": ("en-US", "en-GB"),
    },
)

# A saved config without "learning_language" is German: every install made before there were
# other languages.
DEFAULT = "de"

_BY_CODE = {entry["code"]: entry for entry in LANGUAGES}


def codes():
    return tuple(_BY_CODE)


def get(code):
    """The registry entry for a code. A code that is not listed is a KeyError: the pipeline only ever
    holds codes that came out of resolve()."""
    return _BY_CODE[code]


def resolve(value):
    """(code, warning or None) for a config value: a code, an English or a native name, in any case.
    Empty means German without a warning (older configs), anything unknown means German with one,
    so a hand-edited config can never stop a card."""
    key = str(value or "").strip().lower()
    if not key:
        return DEFAULT, None
    for entry in LANGUAGES:
        if key in (entry["code"], entry["name"].lower(), entry["native_name"].lower()):
            return entry["code"], None
    return DEFAULT, 'learning language "%s" is not one Tarkib knows' % str(value).strip().replace('"', "'")
