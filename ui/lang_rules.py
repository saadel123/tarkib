"""Which learning language and which deck the Add window starts with, where a switch moves it, and how
Settings stores what it keeps for each learning language.

Pure functions with no Anki or Qt imports (the registry and the prompt tables only), so
tests/test_lang_rules.py can check them offline. ui/dialog.py and ui/settings.py use them.

The rules, in one place:
  - the window starts in the language last chosen (in Settings, or by adding a card), in that language's
    last deck if it still exists, else its default deck ("Tarkib", "Tarkib English");
  - every deck remembers the language of the cards last added to it, and a language's default deck belongs
    to that language from the start;
  - picking a deck that belongs to another language switches the language to it;
  - switching the language in a deck that belongs to the old language moves to the new language's last
    deck (or its default deck); a deck that belongs to no language in particular stays;
  - after a card is added, the deck remembers its language and the language its deck, and that language
    becomes the one the window starts with next time.
"""
from ..pipeline import languages, prompts


def _defaults(cfg):
    d = (cfg or {}).get("defaults")
    return d if isinstance(d, dict) else {}


def default_deck(cfg, lang):
    """The deck a language's cards go to until the learner picks another. German keeps the configured
    default deck ("Tarkib" unless the config says otherwise)."""
    if lang == languages.DEFAULT:
        return str(_defaults(cfg).get("default_deck") or languages.get(lang)["default_deck"]).strip()
    return languages.get(lang)["default_deck"]


def last_deck(cfg, lang):
    """The deck the language's last card went to, or "" ("last_deck" is German's since 1.0)."""
    d = _defaults(cfg)
    last = (d.get("last_decks") or {}).get(lang) if isinstance(d.get("last_decks"), dict) else None
    if not last and lang == languages.DEFAULT:
        last = d.get("last_deck")
    return str(last or "").strip()


def deck_language(cfg, deck):
    """The language a deck belongs to: the one its last card was made in, else the language whose default
    deck it is, else None (a deck of no language in particular)."""
    deck = (deck or "").strip()
    if not deck:
        return None
    remembered = ((cfg or {}).get("deck_languages") or {})
    remembered = remembered.get(deck) if isinstance(remembered, dict) else None
    if remembered in languages.codes():
        return remembered
    for code in languages.codes():
        if deck == default_deck(cfg, code):
            return code
    return None


def start(cfg, existing_decks):
    """(language, deck) the Add window opens with."""
    lang, _ = languages.resolve(_defaults(cfg).get("learning_language"))
    last = last_deck(cfg, lang)
    deck = last if last in existing_decks else default_deck(cfg, lang)
    return deck_language(cfg, deck) or lang, deck


def deck_after_switch(cfg, deck, new_lang, existing_decks):
    """The deck after the learner switches to `new_lang`."""
    owner = deck_language(cfg, deck)
    if owner is None or owner == new_lang:
        return deck
    last = last_deck(cfg, new_lang)
    return last if last in existing_decks else default_deck(cfg, new_lang)


def remember(cfg, deck, lang):
    """After a card was added: the deck remembers its language, the language its last deck, and the window
    starts in this language next time. Changes `cfg` in place (the caller writes it)."""
    d = cfg.setdefault("defaults", {})
    if not isinstance(d.get("last_decks"), dict):
        d["last_decks"] = {}
    d["last_decks"][lang] = deck
    if lang == languages.DEFAULT:
        d["last_deck"] = deck                    # what 1.1.0 and older read
    d["learning_language"] = lang
    if not isinstance(cfg.get("deck_languages"), dict):
        cfg["deck_languages"] = {}
    cfg["deck_languages"][deck] = lang
    return cfg


def picker_label(code):
    """How the language pickers show a language: its flag and its English name ("🇩🇪 German")."""
    entry = languages.get(code)
    flag = entry["label"].split(" ", 1)[0]
    if any(ch.isalpha() for ch in flag):         # a label without a flag
        return entry["name"]
    return "%s %s" % (flag, entry["name"])


def store_language_settings(cfg, lang, values):
    """Write what Settings shows for one learning language into `cfg` (in place): the inverse of
    generate.language_settings, which reads it back. `values` has its keys ("voice", "translation",
    "translation_voice", "secondary", "secondary_voice").

    German keeps the keys every config has had since 1.0 (voices.target, .translation, .secondary,
    defaults.translation_language, .secondary_translation_language), so 1.1.0 still reads a config saved
    here. Any other language lives in cfg["languages"][code]; an empty translation language is left out,
    so the language keeps borrowing German's once German's becomes one it may use.

    Returns the notes for the user: ["secondary"] when the second translation equalled the first and was
    turned off (never two identical translation sections)."""
    entry = languages.get(lang)
    get = lambda k: str((values or {}).get(k) or "").strip()
    translation, secondary = get("translation"), get("secondary")
    if lang == languages.DEFAULT:
        translation = translation or prompts.DEFAULT_TRANSLATION_LANG
    notes = []
    if secondary and secondary.lower() == translation.lower():
        secondary, notes = "", ["secondary"]
    secondary_voice = get("secondary_voice") if secondary else ""
    if lang == languages.DEFAULT:
        voices = cfg.setdefault("voices", {})
        defaults = cfg.setdefault("defaults", {})
        voices["target"] = get("voice") or entry["default_voice"]
        voices["translation"] = get("translation_voice")          # "" = the translation is not read aloud
        voices["secondary"] = secondary_voice
        voices.pop("de", None)                                    # the names before 1.0, read as a fallback
        voices.pop("en", None)
        defaults["translation_language"] = translation
        defaults["secondary_translation_language"] = secondary
        return notes
    if not isinstance(cfg.get("languages"), dict):
        cfg["languages"] = {}
    own = cfg["languages"].get(lang)
    own = dict(own) if isinstance(own, dict) else {}
    own.update(voice=get("voice") or entry["default_voice"], secondary=secondary, secondary_voice=secondary_voice)
    if translation:
        own.update(translation=translation, translation_voice=get("translation_voice"))
    else:
        own.pop("translation", None)
        own.pop("translation_voice", None)
    cfg["languages"][lang] = own
    return notes
