import difflib
"""The card-generation pipeline (network only — NO Anki access).

Built on the provider layer, the voice services (tts.py: the pure-Python Edge read-aloud client,
no edge-tts, pydub or ffmpeg, or a paid service with the user's key), and the period-split cloze
audio. Produces a "bundle" dict that anki_io writes into the collection.

Media is returned as {token: (filename, bytes)}; field strings contain the tokens, so anki_io
can write each blob, learn its real (possibly-renamed) filename, and substitute.
"""
import functools
import html
import json
import re
import time
import unicodedata

from . import prompts, providers, images, audio, tts, languages, english, spanish

# Media placeholder tokens (resolved to real filenames by anki_io after media.write_data).
IMG = "@@IMG@@"
TTS_DE = "@@TTS_DE@@"
TTS_EN = "@@TTS_EN@@"
TTS_SEC = "@@TTS_SEC@@"
CLOZE_FRONT = "@@CLOZE_FRONT@@"
CLOZE_BACK = "@@CLOZE_BACK@@"

_ARABIC = ("arabic", "msa", "fusha", "العربية", "ar")
_ARABIC_MARKS = re.compile(r"[ً-ْٰ]")     # the Arabic diacritics (tashkil), U+064B to U+0652 and U+0670
# A case marker the model copies into the translated pattern ("wait for (+Acc)") although the prompt says the case
# stays on the learning-language side: "(+Akk)", "(+Acc)", "(+Dat)", "(+Akk, +Dat)", "(+Dative)", "(+Akk/Dat)".
_CASE_NAME = r"(?:akk(?:usativ)?|acc(?:usative)?|dat(?:iv|ive)?|gen(?:itiv|itive)?|nom(?:inativ|inative)?)\.?"
_CASE_MARKER = re.compile(r"\s*\(\s*\+?\s*" + _CASE_NAME + r"(?:\s*(?:,|/|\+|&|and|und|or|oder)\s*\+?\s*" + _CASE_NAME
                          + r")*\s*\)", re.IGNORECASE)
# The same in frame notation, when the case is a whole element of the frame: "take + to + dative" (seen live).
# "verb + dative object" keeps its words: there the case word is not an element of its own.
_CASE_FRAME = re.compile(r"\s*\+\s*" + _CASE_NAME + r"(?:\s+case)?(?=\s*(?:$|\+|,|\)))", re.IGNORECASE)


def _without_case_markers(text):
    """A translated pattern without the case markers that belong to the learning-language side."""
    if not isinstance(text, str):
        return text
    return _CASE_FRAME.sub("", _CASE_MARKER.sub("", text)).strip()
# Native's separate grammar call. A reasoning model (gpt-oss) spends hidden tokens before the JSON, and with 800
# it used all of them first: the call failed and the card silently kept the main call's patterns (seen in the
# first live English run, completion exactly 800). Only the tokens used are counted, like the main call's 3000.
_GRAMMAR_MAX_TOKENS = 2000
# The second translation call, for the same reason: with 600, gpt-oss spent 576 tokens reasoning on a Spanish card
# with Arabic as its second translation, the JSON was cut off and the Arabic section silently missing. Every
# learning language, German included.
_SECONDARY_MAX_TOKENS = 2000
# The pictures put on cards since Anki started (sha256 of the bytes). images._pick walks down a result list past
# them, so a run of related cards does not get one photo three times (one test run had the same office photo
# on "advice", "look forward to" and "although"). In memory only: a restart starts afresh.
_USED_PICTURES = set()
_PICTURE_RETRY_PAUSE = 1.0      # seconds before the second picture search


# ── the headword ────────────────────────────────────────────────────────────────────────
# (The deck's prompt context moved to prompts.deck_context_de with the other prompt text.)
def _headword_stem(text, lang):
    """The headword in lower case without the words its language puts in front of it (German: der,
    die, das, sich), so the AI's word can be compared with the typed one."""
    prefixes = "|".join(re.escape(p) for p in languages.get(lang)["headword_prefixes"])
    return re.sub(r"^(%s)\s+" % prefixes, "", (text or "").strip().lower())


# ── safety nets (ported) ─────────────────────────────────────────────────────────────────
_GERMAN_ARTICLES = {
    "der", "die", "das", "den", "dem", "des", "ein", "eine", "einen", "einem", "einer", "eines",
    "mein", "meine", "meinen", "meinem", "meiner", "meines", "dein", "deine", "deinen", "deinem", "deiner", "deines",
    "sein", "seine", "seinen", "seinem", "seiner", "seines", "ihr", "ihre", "ihren", "ihrem", "ihrer", "ihres",
    "unser", "unsere", "unseren", "unserem", "unserer", "unseres", "euer", "eure", "euren", "eurem", "eurer", "eures",
    "diese", "dieser", "dieses", "diesen", "diesem", "jene", "jener", "jenes", "jenen", "jenem",
    "kein", "keine", "keinen", "keinem", "keiner", "keines",
    "im", "am", "zum", "zur", "beim", "vom", "ans", "ins", "übers", "fürs", "aufs", "durchs", "hinters", "unters", "vorm",
}

_EMOJI_SHORTCODE_MAP = {
    "thumbs_up": "👍", "thumbs_down": "👎", "briefcase": "💼", "shopping": "🛒", "shopping_cart": "🛒",
    "pencil": "📝", "memo": "📝", "clipboard": "📋", "calendar": "📅", "clock": "⏰", "phone": "📞",
    "computer": "💻", "laptop": "💻", "email": "✉️", "envelope": "✉️", "house": "🏠", "home": "🏠",
    "office": "🏢", "car": "🚗", "bus": "🚌", "train": "🚆", "food": "🍽️", "shrug": "🤷", "party": "🎉",
    "tada": "🎉", "laughing": "😂", "joy": "😂", "smile": "😊", "wave": "👋", "bulb": "💡", "fire": "🔥",
    "check": "✅", "x": "❌", "warning": "⚠️", "speech_balloon": "💬", "money": "💰", "euro": "💶",
    "star": "⭐", "sparkles": "✨", "rocket": "🚀", "eyes": "👀", "thinking": "🤔", "speaker": "🔊",
}
_PATTERN_STOP = {"sich", "jemand", "jemanden", "jemandem", "etwas", "akk", "dat", "gen", "nom",
                 "someone", "something", "somebody", "oneself", "each", "other"}


def _sanitize_emoji(s):
    if not s:
        return s
    return re.sub(r":([a-z_][a-z_0-9]*):", lambda m: _EMOJI_SHORTCODE_MAP.get(m.group(1).lower(), m.group(0)), s)


# An emoji-only field must not contain letters or digits. If it does, the model produced garbage
# (e.g. a mis-decoded escape like "Ἶ6") — blank it rather than render junk. Ranges: ASCII alnum +
# Greek/Greek-Extended/Cyrillic/Hebrew/Arabic letters. Real emoji live in the astral plane (U+1F3xx+)
# so this never strips a valid emoji.
_NOT_EMOJI = re.compile(r"[0-9A-Za-zͰ-Ͽἀ-῿Ѐ-ӿ֐-׿؀-ۿ]")


def _clean_emoji_field(s):
    s = _sanitize_emoji(s)
    if s and _NOT_EMOJI.search(s):
        return ""
    return (s or "").strip()


def _sanitize_card_emojis(card):
    for k in ("emoji", "emoji_formal", "emoji_casual"):  # emoji-only fields → strict validation
        if isinstance(card.get(k), str):
            card[k] = _clean_emoji_field(card[k])
    for k in ("example_casual", "example_formal", "example_casual_en", "example_formal_en",
              "secondary_casual", "secondary_formal"):  # text fields → only shortcode expansion
        if isinstance(card.get(k), str):
            card[k] = _sanitize_emoji(card[k])
    return card


_STR_FIELDS = ("word", "translation_en", "example_casual", "example_formal", "example_casual_en",
               "example_formal_en", "explanation_de", "imageKeyword", "register", "emoji", "emoji_formal",
               "emoji_casual")
_LIST_FIELDS = ("casual_alternatives", "casual_alternatives_en", "grammar_patterns", "grammar_patterns_en", "tags")
# Paired by position: the n-th gloss belongs to the n-th pattern. Dropping one entry (a pattern sent as
# an object, an empty string) shifted every later gloss onto the wrong pattern ("Erfahrung haben" next
# to "experience with"), so these keep every position and _validate_grammar_patterns drops the pairs.
_PAIRED_LIST_FIELDS = ("grammar_patterns", "grammar_patterns_en")


def _unstringify(v):
    """Some models (some structured-output modes, a few compat servers) return NESTED JSON
    as a string: '["a","b"]' or '{"pos":"noun",...}', or a one-element list holding such a string.
    Left alone this silently drops the morphology line and renders literal brackets as a badge."""
    if isinstance(v, str):
        t = v.strip()
        if (t.startswith("[") and t.endswith("]")) or (t.startswith("{") and t.endswith("}")):
            try:
                return json.loads(t)
            except ValueError:
                return v
        return v
    if isinstance(v, list) and len(v) == 1 and isinstance(v[0], str) and v[0].strip().startswith(("[", "{")):
        inner = _unstringify(v[0])
        return inner if isinstance(inner, list) else v
    return v


def _coerce_card_types(card):
    """Weaker / no-JSON-mode models drift from the schema (a dict where a string belongs, a bare
    string where a list belongs, nested JSON as a string). Normalize so rendering and TTS never
    TypeError after a card that the LLM already produced successfully (hard rule 2)."""
    if not isinstance(card, dict):
        return {}
    for k in _LIST_FIELDS + ("morphology",):
        if k in card:
            card[k] = _unstringify(card[k])
    for k in _STR_FIELDS:
        v = card.get(k)
        if v is None or isinstance(v, str):
            continue
        if isinstance(v, (int, float)):
            card[k] = str(v)
        elif isinstance(v, list):
            card[k] = " ".join(x for x in v if isinstance(x, str))
        elif isinstance(v, dict):
            card[k] = _coerce_pattern(v)          # {"value": "der Termin"} keeps its text
        else:
            card[k] = ""
    for k in _LIST_FIELDS:
        v = card.get(k)
        if v is None:
            continue
        if isinstance(v, str):
            card[k] = [v] if v.strip() else []
        elif isinstance(v, list) and k in _PAIRED_LIST_FIELDS:
            card[k] = ["" if x is None else _coerce_pattern(x) for x in v]
        elif isinstance(v, list):
            card[k] = [x for x in v if isinstance(x, str) and x.strip()]
        else:
            card[k] = []
    return card


def _normalize_word_field(card):
    raw = card.get("word")
    if isinstance(raw, dict):
        raw = raw.get("value") or raw.get("text") or ""
    if not isinstance(raw, str):
        raw = str(raw) if raw is not None else ""
    card["word"] = raw
    return raw


def _coerce_pattern(p):
    if isinstance(p, str):
        return p
    if isinstance(p, dict):
        for key in ("pattern", "de", "en", "text", "value"):
            if isinstance(p.get(key), str):
                return p[key]
        strs = [v for v in p.values() if isinstance(v, str)]
        return strs[0] if strs else ""
    if isinstance(p, (list, tuple)):
        return " ".join(_coerce_pattern(x) for x in p)
    return str(p)


# Strong / irregular verbs whose conjugated forms share no usable prefix with the infinitive
# (helfen -> hilft, geben -> gab, nehmen -> genommen). Keyed by the infinitive stem, valued by the
# other stems a sentence can show (Präsens 2/3 sg, Präteritum, Partizip II). Only used to RESCUE a
# real pattern the plain substring test would drop, so a missing verb costs one pattern, never a card.
_ABLAUT = {
    "helf": ("hilf", "half", "geholf"), "geb": ("gib", "gab", "gegeb"), "nehm": ("nimm", "nahm", "genomm"),
    "sprech": ("sprich", "sprach", "gesproch"), "seh": ("sieh", "sah", "geseh"), "fahr": ("fähr", "fuhr", "gefahr"),
    "lauf": ("läuf", "lief", "gelauf"), "ess": ("iss", "aß", "gegess"), "les": ("lies", "las", "geles"),
    "treff": ("triff", "traf", "getroff"), "werd": ("wird", "wurd", "geword"), "komm": ("kam", "gekomm"),
    "geh": ("ging", "gegang"), "steh": ("stand", "gestand"), "find": ("fand", "gefund"), "denk": ("dacht",),
    "bring": ("bracht",), "wiss": ("weiß", "wusst"), "kenn": ("kannt",), "nenn": ("nannt",), "biet": ("bot", "gebot"),
    "bleib": ("blieb",), "schreib": ("schrieb",), "zieh": ("zog", "gezog"), "lieg": ("lag", "geleg"),
    "sitz": ("saß", "gesess"), "tu": ("tat", "getan"), "halt": ("hält", "hielt"), "schlaf": ("schläf", "schlief"),
    "trag": ("träg", "trug"), "wasch": ("wäsch", "wusch"), "wachs": ("wächs", "wuchs"), "verlier": ("verlor",),
    "werf": ("wirf", "warf", "geworf"), "sterb": ("stirb", "starb", "gestorb"), "gelt": ("gilt", "galt", "gegolt"),
    "beginn": ("begann", "begonn"), "gewinn": ("gewann", "gewonn"), "schwimm": ("schwamm", "geschwomm"),
    "flieg": ("flog",), "fließ": ("floss",), "schließ": ("schloss",), "rat": ("rät", "riet"), "lass": ("läss", "ließ"),
    "fall": ("fäll", "fiel"), "fang": ("fäng", "fing"), "bitt": ("bat", "gebet"), "leid": ("litt",),
    "schneid": ("schnitt",), "greif": ("griff",), "steig": ("stieg",), "tret": ("tritt", "trat"),
    "vergess": ("vergiss", "vergaß"), "empfehl": ("empfiehl", "empfahl", "empfohl"),
    "bewerb": ("bewirb", "bewarb", "beworb"), "entscheid": ("entschied",), "sing": ("sang", "gesung"),
    "trink": ("trank", "getrunk"), "spring": ("sprang", "gesprung"), "bind": ("band", "gebund"), "heb": ("hob",),
    "schieb": ("schob",), "frier": ("fror",), "riech": ("roch",), "brech": ("brich", "brach", "gebroch"),
    "heiß": ("hieß",), "ruf": ("rief",), "stoß": ("stöß", "stieß"), "bieg": ("bog",), "schein": ("schien",),
    "leih": ("lieh",), "reit": ("ritt",), "streit": ("stritt",), "sink": ("sank", "gesunk"), "zwing": ("zwang", "gezwung"),
    "schmelz": ("schmilz", "schmolz"), "verschwind": ("verschwand", "verschwund"), "gieß": ("goss",),
    "sei": ("ist", "sind", "bist", "war", "gewes"), "hab": ("hat", "hatt", "hast", "habt"), "mög": ("mag", "mocht"),
    "könn": ("kann", "konnt"), "müss": ("muss", "musst"), "dürf": ("darf", "durft"), "woll": ("will", "wollt"),
    "wend": ("wandt",), "send": ("sandt",), "erschreck": ("erschrick", "erschrak"), "gebär": ("gebier", "gebar"),
    "gefall": ("gefäll", "gefiel"), "misslinge": ("misslang", "misslung"), "tu": ("tut", "tat", "getan"),
}
# Separable prefixes, longest first so "zurück" wins over "zu". teilnehmen -> nehmen -> nimmt ... teil.
_SEP_PREFIXES = ("auseinander", "gegenüber", "zusammen", "herunter", "hinunter", "entgegen", "überein", "zurecht", "herauf", "hinauf", "heraus", "hinaus", "herein", "hinein", "voraus", "nieder",
                 "zurück", "vorbei", "weiter", "wieder", "statt", "teil", "fest", "fort", "frei", "hoch", "fern",
                 "los", "weg", "weh", "gut", "dar", "her", "hin", "ab", "an", "auf", "aus", "bei", "ein", "mit", "nach", "vor", "zu", "um")
# Prepositions with their fused forms, so "beim" satisfies "bei" and "ins" satisfies "in".
_PREP_FORMS = {
    "an": ("an", "am", "ans"), "in": ("in", "im", "ins"), "zu": ("zu", "zum", "zur"), "bei": ("bei", "beim"),
    "von": ("von", "vom"), "auf": ("auf", "aufs"), "für": ("für", "fürs"), "über": ("über", "übers"),
    "um": ("um", "ums"), "durch": ("durch", "durchs"), "vor": ("vor", "vors"), "hinter": ("hinter", "hinters"),
    "unter": ("unter", "unters"), "mit": ("mit",), "nach": ("nach",), "aus": ("aus",), "gegen": ("gegen",),
    "ohne": ("ohne",), "seit": ("seit",), "während": ("während",), "wegen": ("wegen",), "trotz": ("trotz",),
    "statt": ("statt",), "zwischen": ("zwischen",), "neben": ("neben",), "ab": ("ab",),
}


_INSEP = ("be", "ge", "er", "ver", "zer", "ent", "emp", "miss")
_ABLAUT_REV = {}
for _k, _fs in _ABLAUT.items():
    for _f in (_k,) + tuple(_fs):
        _ABLAUT_REV.setdefault(_f, set()).update((_k,) + tuple(_fs))


def _family(base):
    """The ablaut family of a stem, also when the stem carries an inseparable prefix (empfinden ->
    emp + find -> empfand) or is itself a conjugated form (gibt -> gib -> gab)."""
    fam = set(_ABLAUT.get(base, ()))
    for pre in _INSEP:
        if base.startswith(pre) and base[len(pre):] in _ABLAUT:
            fam.update(pre + f for f in _ABLAUT[base[len(pre):]])
    for cand in (base, base[:-1], base[:-2]):
        if cand in _ABLAUT_REV:
            fam.update(_ABLAUT_REV[cand])
    return fam


def _verb_stems(w):
    """Every stem a German verb from a pattern may show in a sentence: the plain stem, its ablaut
    stems, the ge- participle (ändern -> geändert), and all of those again for the base verb of a
    separable compound (aufpassen -> pass ... auf, aufgepasst, aufzupassen)."""
    stems = set()
    base = w[:-2] if w.endswith("en") else (w[:-1] if w.endswith("n") else w)
    if len(base) >= 3:
        stems.add(base)
        stems.add("ge" + base)
    fam = _family(base)
    stems.update(fam)
    stems.update("ge" + f for f in fam if len(f) >= 3)      # gebracht, geworden, gesprochen
    for pre in _SEP_PREFIXES:
        if w.startswith(pre) and len(w) - len(pre) >= 3:
            rest = w[len(pre):]
            rb = rest[:-2] if rest.endswith("en") else (rest[:-1] if rest.endswith("n") else rest)
            if len(rb) >= 3:
                stems.add(rb)
            forms = set(_family(rb))
            stems.update(forms)
            # the participle keeps the prefix in front (aufgepasst, teilgenommen, wehgetan) and the
            # zu-infinitive puts zu between prefix and stem (anzubieten, auszudrücken)
            stems.update(pre + f for f in forms | {rb, "ge" + rb, "zu" + rb} if len(f) >= 2)
            break
    return stems


def _prep_in_text(words, text_words):
    return any(f in text_words for w in words for f in _PREP_FORMS.get(w, ()))


# Grammar META terms: words that DESCRIBE the pattern and are never expected in the sentence itself
# ("um ... zu + Infinitiv", "wo ist + Nominativ", "wenn-Satz: Verb am Ende"). A pattern made only of
# these is anchored by its short function words instead.
_META = {"infinitiv", "nominativ", "akkusativ", "dativ", "genitiv", "uhrzeit", "frage", "verb", "verben", "position",
         "nebensatz", "hauptsatz", "satz", "ende", "satzende", "imperativ", "perfekt", "partizip", "präteritum", "futur",
         "passiv", "konjunktiv", "possessivartikel", "possessivpronomen", "modalverb", "komparativ", "superlativ",
         "relativsatz", "präposition", "richtung", "bewegung", "zeitangabe", "indirekte", "höfliche", "bitte", "formell",
         "informell", "trennbar", "reflexiv", "adjektiv", "nomen", "artikel", "negation", "verneinung", "wortstellung",
         "endung", "deklination", "steigerung", "vergleich", "aufforderung", "höflichkeitsform", "anrede", "form",
         "rede", "infinitivsatz", "ort", "frage", "fragewort", "verbzweit", "verbletzt", "inversion", "zeit"}
# The function words such a pattern can be anchored on. Every one present in the pattern must be in the text.
# In a structural pattern the conjunctions, question words and Konjunktiv-I forms are what the
# sentence must contain; a preposition in such a pattern is descriptive ("mit wer") and is ignored.
_ANCHORS = {"um", "zu", "wo", "ob", "ist", "dass", "weil", "wenn", "als", "wie", "wer", "was", "wann", "warum", "wohin",
            "woher", "damit", "bevor", "nachdem", "obwohl", "seit", "bis", "während", "sobald", "falls", "sei", "habe",
            "werde", "könne", "müsse", "wolle", "solle", "dürfe", "kein", "nicht"}


def _structural_in_text(words, text_words):
    """'um ... zu + Infinitiv' passes when both um and zu are in the sentence; 'W-Frage: Verb auf Position 2'
    fails because it has nothing the sentence must contain. Strict on purpose: this is the door an invented
    pattern would try."""
    anchors = [w for w in words if w in _ANCHORS]
    return bool(anchors) and all(w in text_words for w in anchors)


def _pattern_in_text(pattern, text_lower):
    """True when the pattern is really exemplified by the sentences: a content word appears as is,
    with a common ending stripped, as an irregular / separated verb form (hilft for helfen, nimmt ...
    teil for teilnehmen), or, for a bare preposition frame like "um (+Akk)", as the preposition itself
    (fused forms included). Invented patterns, whose words are nowhere in the text, still fail."""
    if ":" in pattern:
        head, tail = pattern.split(":", 1)
        if _pattern_in_text(head, text_lower):
            return True                                # "in (+Dat): Ort ohne Bewegung" stands on its head
        # a literal example after the colon that occurs word for word: "Relativsatz mit Präposition: mit der"
        tw = [w for w in re.findall(r"[a-zäöüß]+", tail.lower()) if len(w) >= 2]
        if tw and all(w in set(re.findall(r"[a-zäöüß]+", text_lower)) for w in tw):
            return True
    words = re.findall(r"[a-zäöüß]+", pattern.lower())
    content = [w for w in words if len(w) >= 4 and w not in _PATTERN_STOP]
    text_words = set(re.findall(r"[a-zäöüß]+", text_lower))
    if not content:
        return _prep_in_text(words, text_words)
    for w in content:
        if w in text_lower:
            return True
        for suffix in ("en", "st", "et", "te", "ten", "ung"):
            if w.endswith(suffix) and len(w) - len(suffix) >= 3:
                if w[:-len(suffix)] in text_lower:
                    return True
                break
        for st in _verb_stems(w):
            if any(tw.startswith(st) for tw in text_words):
                return True
    if all(w in _META for w in content):
        return _structural_in_text(words, text_words)
    return False


def _self_referential(pat, word):
    """True when a MULTI-WORD taught phrase (idiom / Redemittel) is merely restated as its own
    'pattern', optionally with a label like '(Redewendung)' and no case information. Single words
    with an added verb/label ('Zeit haben', 'anrufen (trennbar)') are NOT self-referential."""
    w = re.sub(r"^(der|die|das|sich)\s+", "", (word or "").strip().strip(".!?…")).lower()
    nw = len(w.split())
    if nw < 2:
        return False
    p = (pat or "").strip().lower()
    m = re.match(r"^(.*?)\s*\(([^)]*)\)\s*$", p)
    core, paren = (m.group(1).strip(), m.group(2)) if m else (p, "")
    core_n = re.sub(r"^(sich|jemandem|jemanden)\s+", "", core)
    if nw == 2:                                    # two-word phrase: only the EXACT restatement counts
        contained = core_n == w or core == w
    else:                                          # longer phrase: full or near-full overlap
        wt = [t for t in w.split() if len(t) > 2]
        contained = w in p or (wt and sum(t in core.split() for t in wt) >= max(2, len(wt) - 1))
    if not contained:
        return False
    extra = core.replace(w, "") + " " + paren
    # real grammar info saves the pattern: a case marker or added preposition frame; labels like
    # "(Redewendung)" or "(Nomen-Verb-Verbindung)" do not (nomen != Nominativ).
    return not re.search(r"\+|\bakk\w*|\bdat\w*|nominativ|genitiv", extra)


def _input_not_german(card):
    """True only when the model explicitly said the input is not German. A missing key (older
    prompt, weaker model that dropped it) means the card goes through, never a refusal."""
    v = card.get("input_is_german", True)
    if isinstance(v, bool):
        return not v
    return str(v).strip().lower() in ("false", "0", "no", "nein")


def _looks_like_typo(typed, returned):
    """True when the model's word is a near miss of what the user typed: "benachrichtigong" vs
    "benachrichtigung". Such a card is kept and the dialog asks; a genuinely different word
    ("Tisch" vs "Fisch") also lands here, and asking is right there too."""
    a, b = (typed or "").lower(), (returned or "").lower()
    if len(a) < 4 or len(b) < 4:
        return False
    return difflib.SequenceMatcher(None, a, b).ratio() >= 0.75


def _refuse_if_not_language(card, call_main, word, force=False, name="German"):
    """Runs BEFORE the word-mismatch guard on purpose: for an input in another language the prompt tells
    the model to put the word it thinks was meant into "word", which would trip the mismatch guard
    first (a wasted strict call and the wrong message). One verdict is not enough to throw a finished
    card away, so a second strict call has to agree; a user who insists can force it
    (options["force_input"]). Returns the card to continue with. `name`: the learning language, which
    the message names ("not german: ...", "not english: ...")."""
    if force or not _input_not_german(card):
        return card
    try:
        confirm = call_main(True)
    except Exception:
        confirm = None
    if confirm is not None and not _input_not_german(confirm):
        return confirm                        # the first verdict was a hallucination; keep the good card
    src = confirm if confirm is not None else card
    sug = re.sub(r"\s+", " ", str(src.get("input_suggestion") or "")).strip().replace('"', "'")
    raise RuntimeError('not %s: "%s"; suggestion "%s"' % (name.lower(), str(word).replace('"', "'"), sug))


_refuse_if_not_german = _refuse_if_not_language   # German's name for it (RULES["de"], the tests)


_LANG_ALIASES = {"de": "German", "deutsch": "German", "allemand": "German",
                 "ar": "Arabic", "msa": "Arabic", "fusha": "Arabic", "العربية": "Arabic", "arabisch": "Arabic",
                 "fa": "Persian", "farsi": "Persian", "zh": "Chinese (Simplified)", "chinese": "Chinese (Simplified)",
                 "fr": "French", "français": "French", "franzoesisch": "French", "französisch": "French",
                 "es": "Spanish", "español": "Spanish", "tr": "Turkish", "türkçe": "Turkish", "ru": "Russian",
                 "uk": "Ukrainian", "it": "Italian", "pl": "Polish", "pt": "Portuguese", "nl": "Dutch", "el": "Greek",
                 "cs": "Czech", "ro": "Romanian", "hu": "Hungarian", "sv": "Swedish", "id": "Indonesian",
                 "vi": "Vietnamese", "hi": "Hindi", "ur": "Urdu", "ja": "Japanese", "ko": "Korean"}


def _known_language(lang, fallback, allowed=None):
    """Only the closed list from Settings may reach the prompts: an unknown name is handed to the model
    as an instruction to write in that language, and a model told to write in "Chihasa" will happily
    invent it. Aliases the rest of the code accepts (ar, farsi, français, ...) are canonicalised, not
    rejected. `allowed`: the learning language's translation languages (prompts.translation_languages),
    by default the common list, which is German's. The learning language itself is known but never
    allowed (English cards translated into English). Total on any config value.
    Returns (name, warning or None)."""
    allowed = prompts.COMMON_TRANSLATION_LANGS if allowed is None else allowed
    key = str(lang or "").strip()
    if not key:
        return fallback, None
    low = key.lower()
    if prompts.is_english_language(key):
        name = "English"
    else:
        name = next((k for k in prompts.TRANSLATION_LANGS_ALL if k.lower() == low), None) or _LANG_ALIASES.get(low)
    if name in allowed:
        return name, None
    if name:
        return fallback, 'translation language "%s" is the language the cards teach' % name
    return fallback, 'translation language "%s" is not in the supported list' % key.replace('"', "'")


def _contiguous(needle, hay):
    n = len(needle)
    return bool(n) and any(hay[i:i + n] == needle for i in range(len(hay) - n + 1))


def _subsequence(needle, hay):
    it = iter(hay)
    return all(w in it for w in needle)


_DE_TOKEN = r"[a-zäöüß]+"
_ANY_TOKEN = r"[^\W\d_]+"      # the letters of any language


def _sentence_like(pat, sentences, token=_DE_TOKEN):
    """A grammar pattern is a short reusable fragment. The Native grammar call has returned the whole
    example sentence, a sentence cut off with "...", and a sentence with the headword blanked out;
    all three teach nothing and are dropped here. Word sequences are compared, never characters, so
    punctuation cannot hide a sentence and the length of the sentence cannot decide the fate of a
    real opener such as "Es tut mir leid, dass". Real short patterns ("Wo ist ...?") pass."""
    raw = (pat or "").strip()
    truncated = bool(re.search(r"(\.\.\.|…)\s*[.?!]?$", raw))
    p = re.sub(r"\s*(\.\.\.|…)\s*[.?!]?$", "", raw).lower()
    words = re.findall(token, p)
    for s in sentences:
        sw = re.findall(token, (s or "").lower())
        if not sw:
            continue
        if len(words) >= 4 and len(words) >= 0.9 * len(sw) and _contiguous(words, sw):
            return True                                   # the sentence itself, punctuation irrelevant
        if truncated and len(words) >= 5 and sw[:len(words)] == words and len(words) >= 0.6 * len(sw):
            return True                                   # the sentence cut off with "..."
        if len(words) >= 5 and len(sw) >= 5 and words[:2] == sw[:2] and words[-1] == sw[-1]:
            return True                                   # the sentence with a gap punched in it
        if len(words) >= 5 and len(words) >= 0.6 * len(sw) and _subsequence(words, sw) and not _contiguous(words, sw):
            return True                                   # most of the sentence, with a gap somewhere
    return False


# Everyday transitive verbs whose accusative object teaches nothing on its own: "kaufen (+Akk)" is filler,
# "helfen (+Dat)" is not. Only a pattern that is exactly <verb> (+Akk) is affected.
_EVERYDAY_AKK = {"kaufen", "brauchen", "haben", "sehen", "machen", "essen", "trinken", "lesen", "finden", "nehmen",
                 "bekommen", "suchen", "kennen", "verstehen", "mögen", "möchten", "hören", "lernen", "wissen", "sagen",
                 "schreiben", "öffnen", "schließen", "bestellen", "bezahlen", "tragen", "holen", "bringen", "zeigen",
                 "besuchen", "vergessen", "probieren", "kochen", "putzen", "waschen", "spielen", "benutzen", "buchen"}
_PREPS = r"(?:an|auf|aus|bei|beim|für|gegen|in|im|ins|mit|nach|über|um|unter|von|vom|vor|zu|zum|zur|durch|ohne|seit|wegen|trotz|zwischen|neben|hinter|statt|während)"
_MARKER = re.compile(r"\(\s*\+\s*(Dat|Akk|Gen|Nom)\b", re.I)
_INF = r"(?:[a-zäöüß]+(?:en|ern|eln)|sein|tun)(?:/(?:[a-zäöüß]+(?:en|ern|eln)|sein|tun))?"     # infinitives, "erledigen/machen" allowed
_ART = r"(?:der|die|das|den|dem|des|ein|eine|einen|einem|einer|eines|zur|zum|ins|im|am|ans|beim|vom|kein|keine|keinen|seine|ihre|meine|deine|viel|viele|wenig|wenige|mehrere|zahlreiche|etwas|genug)"
# A named structure, a Konjunktiv form (inherently a structure), or an auxiliary followed by "+", a
# participle or "...". A bare "ist" followed by an adjective ("ist wirklich hervorragend") is NOT one.
_STRUCT = re.compile(r"\b(Perfekt|Präteritum|Plusquamperfekt|Passiv|Konjunktiv|Partizip|Imperativ|Komparativ|Superlativ|Modalverb|"
                     r"Deklination|Relativsatz|Nebensatz|Genitiv|Nominalisierung|indirekte Rede|Futur|Wechselpräposition)\b"
                     r"|\b(könnte|könnten|hätte|hätten|wäre|wären|würde|würden|sei|seien|möchte|möchten|sollte|sollten|müsste|dürfte)\b"
                     r"|\b(hat|ist|haben|sein|hatte|war|wird|wurde|werden|worden|sind)\b\s*(\+|ge[a-zäöüß]+\b|\.\.\.|…)", re.I)
_CONJ = r"(dass|ob|weil|wenn|wo|wie|wer|was|wann|warum|wohin|woher|damit|obwohl|bevor|nachdem|während|bis|falls|sobald|solange|seitdem|sodass|indem)"
_CLAUSE = re.compile(r"(,\s*" + _CONJ + r"\b|^" + _CONJ + r"(-satz)?\b|\b" + _CONJ + r"\b[\s-]*(satz|\+|:|\.\.\.|…|\())", re.I)
_MODAL = re.compile(r"\b(können|kann|kannst|müssen|muss|musst|wollen|will|willst|sollen|soll|sollst|dürfen|darf|darfst|mögen|möchte|möchten|möchtest|lassen|gern|lieber|werden|wird)\b\s*\+", re.I)


def _pattern_rank(pat):
    """Where a German pattern sits in the pattern value order (1 = highest), used to ORDER patterns
    and to pick the best three when a card has more. Almost everything anchored in the sentence is
    kept (rank 9 = other): a stricter shape filter was tried and rejected, because the patterns it
    dropped were still worth learning. Only these shapes return None and are dropped: a literal
    intensifier phrase ("ist wirklich hervorragend") and a clause tail that ends in
    its own finite auxiliary ("Arzttermin bestätigt ist"), plus a label made only of grammar words
    ("Verb an Position 2"). An infinitive haben/werden at the end is a collocation and stays."""
    p = (pat or "").strip()
    low = p.lower()
    if re.match(r"^(?:ist|sind|war|bin|bist|wird)\s+(?:sehr|wirklich|ganz|total|ziemlich|echt|richtig|absolut|extrem)\s+[a-zäöüß]+\.?$", low):
        return None                                                  # ist wirklich hervorragend (a bare "sehr groß" stays)
    if re.search(r"\b(ist|sind|war|waren|hat|hatte|hatten|wird|wurde|wurden)\.?$", low) and len(low.split()) >= 3 \
            and not re.search(r"[+(:,]", p):
        return None                                                  # Arzttermin bestätigt ist: a dass-clause tail. Infinitive haben/werden/sein
                                                                     # at the end is a collocation ("einen Termin haben") and stays
    has_marker = bool(_MARKER.search(p)) or bool(re.search(r"\+\s*(akkusativ|dativ|genitiv|akk|dat|gen)\b", low))
    core = re.sub(r"\s*\([^)]*\)", "", low).strip()                          # labels say something about the pattern, not the pattern
    core = re.sub(r"\b(jmdm|jdm|jmdn|jdn)\.?", lambda m: {"jmdm": "jemandem", "jdm": "jemandem", "jmdn": "jemanden", "jdn": "jemanden"}[m.group(1)], core)
    core = re.sub(r"\s*\+\s*(akkusativ|dativ|genitiv|akk|dat|gen)\b.*$", "", core).strip()
    words = re.findall(r"[a-zäöüß]+", core)
    if not words:
        return None
    has_prep = bool(re.search(r"\b" + _PREPS + r"\b", core))
    starts_verb = bool(re.match(r"^(?:sich\s+|jemandem\s+|jemanden\s+|jmdm\.?\s+|jmdn\.?\s+|etwas\s+|nicht\s+)*" + _INF + r"\b", core))
    objects = bool(re.match(r"^(?:sich|jemandem|jemanden|jmdm|jmdn|etwas)\b", core))
    # 1 / 2  something + preposition + case
    if has_marker and has_prep:
        return 1 if (starts_verb or objects) else 2
    # 3  a verb with its case; the plain accusative of an everyday verb, or an article + noun label, is filler
    if has_marker:
        verb = re.match(r"^(?:sich\s+|jemandem\s+|jemanden\s+|etwas\s+)*(" + _INF + r")$", core)
        only_akk = bool(re.search(r"\(\s*\+\s*akk\s*\)|\+\s*akkusativ\b|\+\s*akk\b", low)) and low.count("+") == 1
        if verb and verb.group(1) in _EVERYDAY_AKK and only_akk:
            return 9                                                 # kaufen (+Akk): kept, but never ahead of a real pattern
        if starts_verb or objects:
            return 3
        return 8
    # 5  a clause opener, alone ("weil-Satz") or after a verb ("mitteilen, dass")
    if _CLAUSE.search(p):
        return 5
    # 6  zu-infinitive frames
    if re.search(r"\bzu\b\s*(\+\s*infinitiv|\.\.\.|…)|\bum\s*(\.\.\.|…)\s*zu\b|\bohne\s*(\.\.\.|…)\s*zu\b|zu-infinitiv|zu \+ infinitiv", low):
        return 6
    # 7  separable verbs, shown split or labelled
    if "trennbar" in low or "getrennt" in low or re.search(r"\((?:[a-zäöüß]+\s+)+(an|auf|aus|ab|ein|mit|zu|vor|um|los|weg|zurück|her|hin|nach|bei|fest|statt|teil|dabei)\)", low) \
            or re.search(r"(\.\.\.|…)\s*(an|auf|aus|ab|ein|mit|zu|vor|um|los|weg|zurück|statt|teil)\b", low):
        return 7
    # 8  a named structure: Perfekt, Konjunktiv, Passiv, modal + Infinitiv, weak nouns, time accusative, two-part connectors
    struct = bool(_STRUCT.search(p)) or bool(_MODAL.search(low)) or bool(re.search(r"schwach|deklination|deklension|zeitangabe|\+\s*(infinitiv|verb)\b", low)) \
             or bool(re.search(r"(nicht nur|sowohl|weder|entweder|zwar|je|einerseits|zuerst)\b.*(sondern|als auch|noch|oder|aber|desto|andererseits|dann)", low))
    # 4 / 3  collocations: article, quantifier or possessive + noun + infinitive; Noun + infinitive; objects + infinitive
    if struct and len(words) <= 2:
        return 8                                                     # "den Kandidaten (n-Deklination)": a label names the structure
    noun_inside = bool(re.search(r"(^|\s)[A-ZÄÖÜ][a-zäöüß/]+", re.sub(r"\s*\([^)]*\)", "", p)))
    if re.match(r"^(?:" + _ART + r"\s+)?[a-zäöüß/]+(?:\s+[a-zäöüß/]+){0,2}\s+" + _INF + r"$", core) and \
            (re.match(r"^" + _ART + r"\b", core) or noun_inside or objects or "kollokation" in low) and \
            not re.match(r"^" + _ART + r"\s+[a-zäöüß]+\s+(?:sein|werden|bleiben)$", core):
        if objects and len(words) == 2:
            return 7                                                 # sich beeilen: reflexive, no object noun
        return 3 if objects else 4                                   # jemandem Bescheid geben / eine Entscheidung treffen
    if re.match(r"^" + _INF + r"\s+(gehen|lassen|bleiben|lernen)$", core):
        return 7                                                     # klettern gehen
    if starts_verb and re.search(r"\+\s*adjektiv", low) and words[0] not in ("sein", "werden"):
        return 3                                                     # klingen + Adjektiv
    if re.match(r"^da(für|gegen|mit|bei|von|zu)\s+sein$", core):
        return 7                                                     # dafür sein
    if struct:
        return 8
    if words[0] == "sich" and len(words) >= 2:
        return 7
    if all(w in _META or w in _PREP_FORMS or len(w) <= 2 for w in re.findall(r"[a-zäöüß]+", low)):
        return None                                                  # "Verb an Position 2": grammar words only, nothing from the sentence.
                                                                     # The example in parentheses counts: "Possessivartikel (Ihre/deine)" stays
    if has_prep and not re.search(r"\b(sehr|wirklich|ganz|total|ziemlich|echt)\b", low) and (starts_verb or p[:1].isupper() or len(words) >= 2):
        return 7                                                     # a preposition frame without its case (am Telefon)
    return 9                                                         # anything else that is anchored in the sentence stays


def _validate_grammar_patterns(card):
    """Keep only patterns that are anchored in the card's own sentences, are not the sentence itself,
    are not the headword restated, and have a shape worth teaching (_pattern_rank). Then keep the
    three best by rank. The English list follows the German list entry for entry, so the two boxes
    never disagree and an English-only box cannot appear."""
    de_text = ((card.get("example_casual") or "") + " " + (card.get("example_formal") or "")).lower()
    de = [_coerce_pattern(p) for p in (card.get("grammar_patterns") or [])]
    en = [_coerce_pattern(p) for p in (card.get("grammar_patterns_en") or [])]
    word = card.get("word", "")
    de_s = [card.get("example_casual"), card.get("example_formal")]
    kept = []
    for i, p in enumerate(de):
        if not p or not _pattern_in_text(p, de_text) or _self_referential(p, word) or _sentence_like(p, de_s):
            continue
        rank = _pattern_rank(p)
        if rank is None:
            continue
        kept.append((rank, i, p, en[i] if i < len(en) and en[i] else ""))
    kept.sort(key=lambda t: (t[0], t[1]))      # best rank first, original order as tie-break
    kept = kept[:3]
    card["grammar_patterns"] = [t[2] for t in kept]
    glosses = [_without_case_markers(t[3]) for t in kept]
    card["grammar_patterns_en"] = glosses if kept and all(glosses) else []
    return card


def _fix_double_determiner(sentence, answer):
    poss = ("mein", "meine", "meinen", "meinem", "meiner", "meines", "dein", "deine", "deinen", "deinem", "deiner",
            "deines", "sein", "seine", "seinen", "seinem", "seiner", "seines", "ihr", "ihre", "ihren", "ihrem",
            "ihrer", "ihres", "unser", "unsere", "unseren", "unserem", "unserer", "unseres", "euer", "eure",
            "euren", "eurem", "eurer", "eures")
    art = ("der", "die", "das", "den", "dem", "des", "ein", "eine", "einen", "einem", "einer", "eines")
    bad = re.compile(r"\b(" + "|".join(poss) + r")\s+(" + "|".join(art) + r")\s+([A-ZÄÖÜ][\w-]+)", re.IGNORECASE)
    new = bad.sub(r"\1 \3", sentence)
    if new == sentence:
        return sentence, answer
    parts = answer.split()
    return new, (" ".join(parts[1:]) if parts and parts[0].lower() in art else answer)


def _fix_german_cloze(sentence, answer):
    """German's cloze fix: the doubled determiner goes ("meine die Brille"), then an answer in small letters takes the
    sentence's capital ("morgen" in "Morgen gehe ich einkaufen."), which before lost the cloze card."""
    sentence, answer = _fix_double_determiner(sentence, answer)
    return _cloze_case_fix(sentence, answer)


def _extend_cloze_answer_with_article(sentence, answer, card_case, user_input):
    if card_case != "single_word" or not answer:
        return answer
    parts = answer.split()
    if parts and parts[0].lower() in _GERMAN_ARTICLES:
        return answer
    wp = user_input.strip().split()
    noun = " ".join(wp[1:]) if wp and wp[0].lower() in {"der", "die", "das"} else user_input.strip()
    if len(noun.split()) != 1 or not noun[:1].isupper():
        return answer
    m = re.search(r"(?:^|\s)(\S+)\s+" + re.escape(answer) + r"\b", sentence)
    if not m:
        return answer
    preceding = m.group(1).rstrip(',.!?;:"„“')
    return ("%s %s" % (preceding, answer)) if preceding.lower() in _GERMAN_ARTICLES else answer


def _letter_hint(w, beginner=False):
    """Letter hint shown in the cloze blank. Long words (6+) show 3 letters. Beginners (A1/A2) get
    2 letters for 4-5 letter words ("ko..." instead of "k...", which could be kommt/kocht/kauft/kennt);
    everyone else gets 1."""
    s = (w or "").strip()
    if len(s) >= 6:
        return s[:3] + "..."
    if beginner and len(s) > 3:
        return s[:2] + "..."
    return s[:1] + "..."


def _wrap_first(text, answer, replacement):
    """Wrap the first WHOLE-WORD occurrence of the answer; only if there is none, the first bare
    substring. "mit" in "Damit fahre ich mit dem Bus" must blank the preposition, not the inside of
    Damit (audio.split_for_cloze uses the same word-boundary rule, and the two must agree)."""
    out, n = re.subn(r"(?<![\wäöüÄÖÜß])" + re.escape(answer) + r"(?![\wäöüÄÖÜß])", lambda _m: replacement, text, count=1)
    if n:
        return out
    return re.sub(re.escape(answer), lambda _m: replacement, text, count=1)


_CLOZE_CASES = ("single_word", "noun_prep", "verb_prep_article", "nvv", "long_phrase", "idiom")


def build_cloze_text(sentence, answer_raw, card_case, idiom_meaning="", beginner=False, no_hint=("noun_prep", "nvv")):
    text = sentence
    if card_case == "idiom":
        # Letter hints like every other case. The old style put idiom_meaning_de into the FIRST
        # blank's hint (the visible blank then showed the whole German paraphrase, a give-away)
        # and left later blanks hintless (rendered as a bare "[...]"), which looked broken. The
        # meaning belongs on the back (GrammarHint) only.
        answers = [a.strip() for a in answer_raw.split(",") if a.strip()]
        for ans in answers:
            hint = " ".join(_letter_hint(w, beginner) for w in ans.split() if w)
            text = re.sub(r"\b" + re.escape(ans) + r"\b", "{{c1::" + ans + "::" + hint + "}}", text, count=1)
        return text
    if card_case in no_hint:    # one short word (a preposition, a particle): a letter hint would give it away
        return _wrap_first(text, answer_raw, "{{c1::" + answer_raw + "}}")
    hint = " ".join(_letter_hint(w, beginner) for w in answer_raw.split() if w)
    return _wrap_first(text, answer_raw, "{{c1::" + answer_raw + "::" + hint + "}}")


# ── HTML ─────────────────────────────────────────────────────────────────────────────────
def _esc(s):
    """Escape LLM/user text before it lands in permanent note HTML. Anki renders fields as HTML,
    so an unbalanced tag from a weak model (or anything hostile) would otherwise persist in the
    collection and re-execute on every device. quote=False keeps ordinary quotes readable."""
    if s is None:
        return ""
    return html.escape(str(s), quote=False)


# a word in double quotes inside the explanation: the AI's own quotes or plain ones, any language's
_QUOTED = re.compile(r'[„“”«»"]([^„“”«»"\n]+)[„“”«»"]')


def _nest_quotes(text, inner):
    """The explanation sits in the language's quotes, so a word quoted inside it takes the inner pair
    („‚obwohl‘ leitet einen Gegensatz ein.“), never a doubled mark („„obwohl“ ...)."""
    return _QUOTED.sub(lambda m: inner[0] + m.group(1) + inner[1], str(text or ""))


def _patterns_html(pats, label):
    if not pats:
        return ""
    badges = " ".join('<span class="pattern-badge">%s</span>' % _esc(p) for p in pats)
    return '<div class="patterns-box"><div class="patterns-label">💡 %s</div>%s</div>' % (label, badges)


def _register_hint_de(word_display, alternatives):
    if not alternatives:
        return ""
    return ('<div class="register-hint"><span class="formal-mark">„%s" (Formell)</span> '
            '<span class="arrow">→</span> <span class="casual-alt">Im Alltag:</span> '
            '<span class="alt-list">%s</span> <span class="casual-alt">(Casual)</span></div>'
            % (_esc(word_display), " · ".join(_esc(a) for a in alternatives)))


def _register_hint_en(translation_en, alternatives_en):
    if not alternatives_en:
        return ""
    return ('<div class="register-hint"><span class="formal-mark">"%s" (Formal)</span> '
            '<span class="arrow">→</span> <span class="casual-alt">Casual:</span> '
            '<span class="alt-list">%s</span></div>' % (_esc(translation_en), " · ".join(_esc(a) for a in alternatives_en)))


_GENDER_CLASS = {"der": "g-der", "die": "g-die", "das": "g-das"}


def _level_chip(level):
    if not level:
        return ""
    return '<span class="level-chip lvl-%s">%s</span> ' % (level.lower(), level)  # inline, sits before the translation


_NO_GENITIVE_LEVELS = ("A1", "A2")   # Genitiv is introduced at B1; showing it earlier only confuses


def _morphology_html(m, level=None):
    """Compact reference line. Noun → 'der · Pl. die Wörter · Gen. des Wortes' (article color-coded
    der=blue/die=red/das=green); verb → 'holt ab · holte ab · hat abgeholt · trennbar'.
    At A1/A2 the genitive is omitted (not part of those levels)."""
    if not isinstance(m, dict):
        return ""
    if m.get("pos") == "noun":
        bits = []
        art = (m.get("article") or "").strip().lower()
        if art in _GENDER_CLASS:
            bits.append('<span class="%s">%s</span>' % (_GENDER_CLASS[art], art))
        pl = (m.get("plural") or "").strip()
        if pl and pl != "—":
            bits.append("Pl. " + _esc(pl))
        gen = (m.get("genitive") or "").strip()
        if gen and level not in _NO_GENITIVE_LEVELS:
            bits.append("Gen. " + _esc(gen))
        return ('<div class="morph">%s</div>' % " · ".join(bits)) if bits else ""
    if m.get("pos") == "verb":
        forms = [_esc(x) for x in (m.get("present_3sg"), m.get("past_3sg"), m.get("perfect")) if x]
        if m.get("separable"):
            forms.append("trennbar")
        return ('<div class="morph">%s</div>' % " · ".join(forms)) if forms else ""
    return ""


# Common English words that are NOT German — catches gross code-switch leaks at A1–C1 (Native is
# exempt; authentic Denglisch is allowed there). Conservative: none of these collide with German words.
_ENGLISH_LEAK = {
    "the", "and", "with", "without", "because", "about", "would", "could", "should", "please",
    "sorry", "really", "very", "people", "help", "always", "never", "here", "there", "this", "that",
    "what", "when", "where", "which", "your", "you", "they", "somewhere", "anywhere", "everywhere",
    "something", "someone", "anyone", "everyone", "anything", "everything", "nothing",
    "interrupt", "interrupts", "interrupting",
}


def _has_english_leak(*texts):
    for t in texts:
        for tok in re.findall(r"[A-Za-z]+", (t or "").lower()):
            if tok in _ENGLISH_LEAK:
                return tok
    return None


# ── the generic checks: every learning language without German-style guards of its own ───────
def _anchored_generic(pattern, text_lower):
    """A content word of the pattern (3+ letters) appears in the sentences, as is or with its ending
    changed (the first letters match). A pattern of short words only needs all of them."""
    words = re.findall(_ANY_TOKEN, (pattern or "").lower())
    content = [w for w in words if len(w) >= 3]
    tokens = set(re.findall(_ANY_TOKEN, text_lower))
    if not content:
        return bool(words) and all(w in tokens for w in words)
    for w in content:
        stem = w[:max(3, len(w) - 3)]
        if w in text_lower or any(t.startswith(stem) for t in tokens):
            return True
    return False


def _rank_in_order(pattern):
    return 9          # no value order of its own: the model's order ("best first") stands


_PLACEHOLDERS_DEFAULT = ("someone", "something", "somebody", "sb", "sth")


def _self_referential_generic(pat, word, prefixes, placeholders=_PLACEHOLDERS_DEFAULT):
    """A multi-word headword restated as its own pattern, adding nothing: no placeholder (the language's own:
    "something", "algo"), no + frame."""
    pre = "|".join(re.escape(x) for x in prefixes)
    strip = (lambda t: re.sub(r"^(%s)\s+" % pre, "", t)) if pre else (lambda t: t)
    w = strip((word or "").strip().strip(".!?…").lower())
    nw = len(w.split())
    if nw < 2:
        return False
    p = (pat or "").strip().lower()
    m = re.match(r"^(.*?)\s*\(([^)]*)\)\s*$", p)
    core, paren = (m.group(1).strip(), m.group(2)) if m else (p, "")
    contained = strip(core) == w
    if not contained and nw > 2:
        wt = [t for t in w.split() if len(t) > 2]
        contained = w in p or bool(wt and sum(t in core.split() for t in wt) >= max(2, len(wt) - 1))
    if not contained:
        return False
    extra = core.replace(w, "") + " " + paren
    return not re.search(r"\+|" + "|".join(r"\b%s\b" % re.escape(x) for x in placeholders), extra)


def _extends_headword(pat, word, prefixes, placeholders=_PLACEHOLDERS_DEFAULT):
    """The card's own word in a frame ("no obstante + sustantivo", "aprovechar la oportunidad de + infinitivo",
    "give up + -ing"): the pattern most worth learning on its card, so it goes first."""
    pre = "|".join(re.escape(x) for x in prefixes)
    strip = (lambda t: re.sub(r"^(%s)\s+" % pre, "", t)) if pre else (lambda t: t)
    w = strip((word or "").strip().strip(".!?…").lower())
    p = strip((pat or "").strip().lower())
    here = r"(?<!\w)%s(?!\w)" % re.escape(w)
    if not w or not re.search(here, p):
        return False
    extra = re.sub(here, " ", p, count=1)
    return bool(re.search(r"\+|" + "|".join(r"\b%s\b" % re.escape(x) for x in placeholders), extra))


def _validate_patterns_generic(card, anchored, rank, prefixes, placeholders=_PLACEHOLDERS_DEFAULT):
    """Like German's _validate_grammar_patterns, with the language's own anchoring and value order: keep
    the patterns anchored in the card's sentences that are neither a sentence nor the headword restated,
    order them (rank None drops one), keep three; the translation list follows entry for entry."""
    text = ((card.get("example_casual") or "") + " " + (card.get("example_formal") or "")).lower()
    pats = [_coerce_pattern(p) for p in (card.get("grammar_patterns") or [])]
    glosses = [_coerce_pattern(p) for p in (card.get("grammar_patterns_en") or [])]
    word = card.get("word", "")
    sentences = [card.get("example_casual"), card.get("example_formal")]
    kept = []
    for i, p in enumerate(pats):
        if (not p or not anchored(p, text) or _self_referential_generic(p, word, prefixes, placeholders)
                or _sentence_like(p, sentences, token=_ANY_TOKEN)):
            continue
        r = rank(p)
        if r is None:
            continue
        if _extends_headword(p, word, prefixes, placeholders):
            r = 0           # the card's own word in a frame comes first (seen live: "no obstante + sustantivo" last)
        kept.append((r, i, p, glosses[i] if i < len(glosses) and glosses[i] else ""))
    kept.sort(key=lambda t: (t[0], t[1]))
    kept = kept[:3]
    card["grammar_patterns"] = [t[2] for t in kept]
    glosses = [_without_case_markers(t[3]) for t in kept]
    card["grammar_patterns_en"] = glosses if kept and all(glosses) else []
    return card


def _script_leak(script):
    """The leak check of a language without its own: the first letter of another writing system in its
    fields (an Arabic word in an English sentence)."""
    def leak(*texts):
        for t in texts:
            for ch in (t or ""):
                if ch.isalpha():
                    try:
                        if not unicodedata.name(ch).startswith(script):
                            return ch
                    except ValueError:
                        continue
        return None
    return leak


def _morphology_generic(m, level=None):
    """The word line of a language without its own: the article and plural of a noun, the forms of a verb."""
    if not isinstance(m, dict):
        return ""
    if m.get("pos") == "noun":
        art = str(m.get("article") or "").strip()
        pl = str(m.get("plural") or "").strip()
        bits = [_esc(art)] if art else []
        if pl and pl != "—":
            bits.append("Pl. " + _esc(pl))
    elif m.get("pos") == "verb":
        forms = str(m.get("forms") or "").strip()
        bits = [_esc(forms)] if forms else []
    else:
        return ""
    return ('<div class="morph">%s</div>' % " · ".join(bits)) if bits else ""


def _register_hint_generic(word_display, alternatives):
    if not alternatives:
        return ""
    return ('<div class="register-hint"><span class="formal-mark">"%s" (Formal)</span> '
            '<span class="arrow">→</span> <span class="casual-alt">Everyday:</span> '
            '<span class="alt-list">%s</span></div>' % (_esc(word_display), " · ".join(_esc(a) for a in alternatives)))


def _same_sentence(sentence, answer):
    return sentence, answer


def _cloze_case_fix(sentence, answer):
    """The generic cloze fix: an answer that is in the sentence with other capitals takes the sentence's spelling
    ("tengo" in "Tengo un coche nuevo."). Before, the answer was not found and the cloze card was lost."""
    if answer and answer not in sentence:
        m = re.search(r"(?<!\w)%s(?!\w)" % re.escape(answer), sentence, re.IGNORECASE)
        if m:
            return sentence, m.group(0)
    return sentence, answer


def _fold(s):
    """Lower case without accents: "Llevará" -> "llevara"."""
    return "".join(ch for ch in unicodedata.normalize("NFD", s.lower()) if not unicodedata.combining(ch))


def _fixed_phrase_cloze(sentence, answer, card_case, user_input):
    """(case, answer) for the cloze. A preposition INSIDE a fixed phrase is no verb_prep blank: "Yo echo {{c1::de}}
    menos" and "Se llevará {{c1::a}} cabo" ask for a word nobody forgets. When the answer is
    a word inside the typed phrase, neither its first nor its last, the whole phrase as the sentence has it becomes
    the blank, as a long_phrase: "echo de menos", "llevará a cabo". The words before the answer may be conjugated;
    each must start like the typed word (three letters, accents aside), else nothing changes ("tuve en cuenta" for
    "tener en cuenta" keeps the model's blank). A preposition that ends the phrase (pensar en, look forward to)
    stays a verb_prep blank."""
    if card_case != "verb_prep" or not answer:
        return card_case, answer
    typed = re.findall(r"\w+", (user_input or "").lower())
    ans = re.findall(r"\w+", answer.lower())
    inside = [i for i in range(1, len(typed) - len(ans)) if ans and typed[i:i + len(ans)] == ans]
    if not inside:
        return card_case, answer
    i = inside[0]
    m = re.search(r"(?<!\w)((?:\w+\s+){%d})%s(?!\w)" % (i, r"\s+".join(re.escape(w) for w in typed[i:])),
                  sentence, re.IGNORECASE)
    if not m or not all(_fold(said)[:3] == _fold(t)[:3] for said, t in zip(m.group(1).split(), typed[:i])):
        return card_case, answer
    return "long_phrase", m.group(0)


def _same_case(sentence, answer, card_case, user_input):
    return card_case, answer


def _same_text(text, voice, word=""):
    return text


def _same_word(word, morphology):
    return word


def _same_answer(sentence, answer, card_case, user_input):
    return answer


_GENERIC_CLOZE_CASES = ("single_word", "long_phrase", "idiom")


def generic_rules(code, checks=None):
    """RULES for a language without German-style guards: the generic checks above, with the language's
    own pieces from its CHECKS (pipeline/<language>.py) where it has them."""
    entry, c = languages.get(code), dict(checks or {})
    return {
        "input_check": functools.partial(_refuse_if_not_language, name=entry["name"]),
        "leak": c.get("leak") or _script_leak(entry["script"]),
        "patterns": functools.partial(_validate_patterns_generic,
                                      anchored=c.get("pattern_in_text") or _anchored_generic,
                                      rank=c.get("pattern_rank") or _rank_in_order,
                                      prefixes=entry["headword_prefixes"],
                                      placeholders=tuple(c.get("placeholders") or _PLACEHOLDERS_DEFAULT)),
        "cloze_cases": tuple(c.get("cloze_cases") or _GENERIC_CLOZE_CASES),
        "cloze_no_hint": tuple(c.get("cloze_no_hint") or ()),
        "cloze_fix": c.get("cloze_fix") or _cloze_case_fix,
        "cloze_case": _fixed_phrase_cloze,      # "echar de menos" is blanked whole, never as "de"
        "country_words": c.get("country_words") or _same_text,
        "headword": c.get("headword") or _same_word,
        # Native: the main prompt asks for frames too; the separate grammar call (which gave sentence pieces in every
        # live English and Spanish Native card) runs only when none of the main call's patterns survives the checks.
        "grammar_fallback": True,
        "cloze_article": c.get("cloze_article") or _same_answer,
        "morphology": c.get("morphology") or _morphology_generic,
        "register_hint": c.get("register_hint") or _register_hint_generic,
        # audio file names start with the clip's role: the learning language's code, "tts_tr" the translation
        "audio_names": {"target": "tts_%s" % code, "translation": "tts_tr"},
    }


# ── what each learning language checks, and how its card shows the language ───────────────
# German: the guards above, each one grown from a real bad card. build_card and build_back_html read
# nothing German-only outside this table and the registry (pipeline/languages.py). A new language adds
# its entry here, and tests/test_languages.py fails until it does.
RULES = {
    "de": {
        "input_check": _refuse_if_not_german,   # the AI says it is not German: one strict call more, then refuse
        "leak": _has_english_leak,              # A1 to C1: an English word in a German field, one strict retry
        "patterns": _validate_grammar_patterns,   # anchored in the sentences, ranked, the best three kept
        "cloze_cases": _CLOZE_CASES,
        "cloze_no_hint": ("noun_prep", "nvv"),  # the preposition or the verb alone, no letter hint
        "cloze_fix": _fix_german_cloze,         # "meine die Brille" loses the doubled determiner, "morgen" -> "Morgen"
        "cloze_article": _extend_cloze_answer_with_article,   # a noun's blank takes its article
        "cloze_case": _same_case,               # German has no verb_prep case (its idioms come as "idiom")
        "country_words": _same_text,            # Spanish: a Mexican voice never reads "chaqueta"
        "headword": _same_word,                 # the prompt adds der, die or das to a bare noun
        "grammar_fallback": False,              # Native always asks the separate grammar call, as it always did
        "morphology": _morphology_html,         # der/die/das in colour, Pl., Gen., trennbar
        "register_hint": _register_hint_de,     # „gegebenenfalls" (Formell) → Im Alltag: ...
        "audio_names": {"target": "tts_de", "translation": "tts_en"},   # the names in every German card so far
    },
    "en": generic_rules("en", english.CHECKS),   # pipeline/english.py: irregular verbs, phrasal verbs, ...
    "es": generic_rules("es", spanish.CHECKS),   # pipeline/spanish.py: gender, stem changes, irregular verbs, ...
}


def _strip_arabic_marks(card):
    """The card's translation fields without Arabic diacritics (when the translation language is Arabic)."""
    for k in ("translation_en", "example_casual_en", "example_formal_en"):
        if isinstance(card.get(k), str):
            card[k] = _ARABIC_MARKS.sub("", card[k])
    for k in ("casual_alternatives_en", "grammar_patterns_en"):
        card[k] = [_ARABIC_MARKS.sub("", x) if isinstance(x, str) else x for x in (card.get(k) or [])]


def _voice_speaks(voice, language_name):
    """True when an Edge/Azure voice name belongs to the language ("ar-SA-ZariyahNeural" speaks Arabic)."""
    voice = (voice or "").strip()
    return bool(voice) and any(voice.startswith(loc) for loc in audio.secondary_locale_prefixes(language_name))


def language_settings(cfg, lang):
    """What Settings keeps for one learning language: "voice" (reads the language), "translation" (the
    translation language) and "translation_voice", "secondary" (the second translation) and
    "secondary_voice". German's live in the keys every config has had since 1.0 (voices.target, .translation,
    .secondary, defaults.translation_language, .secondary_translation_language), so an older config and a
    return to 1.1.0 keep working; any other language's live in cfg["languages"][code]. A language not set up
    yet borrows German's translation language when it may use it (an Arabic speaker who learns German sees
    Arabic on English cards at once), with its voice only when that voice speaks it; with nothing allowed
    to borrow it has none, and the card asks for one. Shared by build_card, Settings and the Add window."""
    cfg = cfg or {}
    voices = cfg.get("voices") or {}
    defaults = cfg.get("defaults") or {}
    entry = languages.get(lang)
    legacy = {
        "voice": str((voices["target"] if "target" in voices else voices.get("de", "")) or "").strip(),
        "translation": str(defaults.get("translation_language") or "").strip(),
        "translation_voice": str((voices["translation"] if "translation" in voices else voices.get("en", "")) or "").strip(),
        "secondary": str(defaults.get("secondary_translation_language") or "").strip(),
        "secondary_voice": str(voices.get("secondary") or "").strip(),
    }
    if lang == languages.DEFAULT:
        out = dict(legacy)
        out["voice"] = out["voice"] or entry["default_voice"]
        out["translation"] = out["translation"] or prompts.DEFAULT_TRANSLATION_LANG
        return out
    own = (cfg.get("languages") or {}).get(lang)
    own = own if isinstance(own, dict) else {}
    out = {k: str(own.get(k) or "").strip()
           for k in ("voice", "translation", "translation_voice", "secondary", "secondary_voice")}
    out["voice"] = out["voice"] or entry["default_voice"]
    if "translation" not in own:
        german = legacy["translation"] or prompts.DEFAULT_TRANSLATION_LANG     # what German's cards really use
        borrowed, _ = _known_language(german, None, allowed=prompts.translation_languages(lang))
        if borrowed:
            out["translation"] = borrowed
            if "translation_voice" not in own and _voice_speaks(legacy["translation_voice"], borrowed):
                out["translation_voice"] = legacy["translation_voice"]
    return out


def build_back_html(card):
    g = card.get
    # A card dict made before there were other languages (the deck scripts) has no language: German.
    lang = g("language") or languages.DEFAULT
    entry, rules = languages.get(lang), RULES[lang]
    ef = g("emoji_formal") or "📝"
    ec = g("emoji_casual") or "💬"
    is_formal = (g("register") or "neutral").lower() == "formal"
    word_display = (g("word") or "").strip().rstrip(".")
    translation_en = g("translation_en") or ""
    e = lambda k: _esc(g(k) or "")   # escaped field accessor
    prim_label = g("primary_label") or "🇬🇧 English"
    prim_name = g("primary_lang_name") or "English"
    prim_rtl = bool(g("primary_is_rtl"))
    # Top word: keep it CENTERED (the .card-translation CSS) and only flip direction for RTL;
    # inline text-align:right used to shove it into the corner.
    trans_style = ' style="direction:rtl;"' if prim_rtl else ''
    # Primary section: reuse the .arabic CSS block (RTL sentences, flipped borders and emoji
    # margins) instead of a bare inline direction that left the bubbles styled LTR.
    prim_cls = "section arabic" if prim_rtl else "section"
    prim_label_style = ' style="direction:rtl;text-align:right;"' if prim_rtl else ''

    def has(k):
        return bool(str(g(k) or "").strip())

    def sentences(casual_key, formal_key):
        # A sentence the AI left out gets no box: a weak model that skips a field left an empty box
        # with only its emoji. A section without any sentence is left out whole (see below).
        return ['  <div class="sentence %s"><span class="emoji">%s</span>%s</div>' % (kind, _esc(emoji), e(key))
                for kind, key, emoji in (("casual", casual_key, ec), ("formal", formal_key, ef)) if has(key)]

    parts = [
        '<div class="card-translation"%s>%s%s %s</div>' % (trans_style, _level_chip(g("level")), e("emoji"), _esc(translation_en)),
        rules["morphology"](g("morphology"), g("level")),
        '<div class="card-image">{{IMAGE}}</div>',
    ]
    target = sentences("example_casual", "example_formal")
    if target:
        parts += ['<div class="section">', '  <div class="section-label">%s</div>' % entry["label"]]
        if is_formal:
            parts.append(rules["register_hint"](word_display, g("casual_alternatives", []) or []))
        parts += target + ["</div>"]
    parts.append(_patterns_html(g("grammar_patterns", []), "Grammar patterns"))
    if has("explanation_de"):
        parts.append('<div class="explanation">👉 %s%s%s</div>'
                     % (entry["quotes"][0], _esc(_nest_quotes(g("explanation_de"), entry["inner_quotes"])), entry["quotes"][1]))
    helper = sentences("example_casual_en", "example_formal_en")
    if helper:
        parts += ['<div class="%s">' % prim_cls, '  <div class="section-label"%s>%s</div>' % (prim_label_style, _esc(prim_label))]
        if is_formal:
            parts.append(_register_hint_en(translation_en, g("casual_alternatives_en", []) or []))
        parts += helper + ["</div>"]
    parts.append(_patterns_html(g("grammar_patterns_en", []), "%s patterns" % _esc(prim_name)))
    # Optional secondary-translation section (e.g. Arabic) — only if generated.
    if g("secondary_word"):
        is_ar = card.get("secondary_is_arabic")
        sec_cls = "section arabic" if is_ar else "section"
        second = sentences("secondary_casual", "secondary_formal")
        if second:
            parts += ['<div class="%s">' % sec_cls,
                      '  <div class="section-label"%s>%s</div>' % (
                          ' style="direction:ltr;text-align:left;"' if is_ar else "", e("secondary_label"))]
            parts += second + ["</div>"]
        # 'secondary-word' (was 'arabic-word'): this class is stored in every note forever, and
        # the block is used for EVERY secondary language, so it is named for its role.
        parts.append('<div class="secondary-word"%s>%s %s</div>' % (
            "" if is_ar else ' style="direction:ltr;"', e("emoji"), e("secondary_word")))
    return "\n".join(p for p in parts if p)


def _front(emoji, word):
    """The main card's front: the emoji, then the word with one full stop. A word that already ends a
    sentence keeps its own mark ("Wie spät ist es?", "Viel Glück!", "Ich habe eine Frage."), where the
    old front read "Wie spät ist es?.", and a card without an emoji starts with the word, not a space."""
    w = (word or "").strip()
    if w and w[-1] not in ".?!…":
        w += "."
    return " ".join(p for p in (_esc(emoji), _esc(w)) if p)


def _audio_name(prefix, label, text, clip):
    """Audio filename: prefix, a readable label, then a hash of the SPOKEN TEXT, the voice service
    and the voice (tts.audio_tag), with the service's own extension (Gemini gives WAV).

    _safe() truncates, so a name derived from the sentence is not unique: "Das Wetter ist heute
    schlecht." and "Das Wetter ist heute schön." both became cloze_back_Das_Wetter_ist_heute_sch,
    and one card played the other's audio — with the opposite meaning. Hashing the text means the
    filename always follows the audio: different speech gets a different file, and the same text in
    the same voice still shares one. The service and voice are in the hash too (1.0.3), so a clip
    read by a backup service, or after a voice change, never takes the name of an existing clip;
    and media.write_data renames rather than overwrites if the bytes ever differ."""
    return "%s_%s_%s.%s" % (prefix, _safe(label), tts.audio_tag(text, clip), clip.ext)


def _clean_tts(t):
    return re.sub(r"\s+", " ", re.sub(r"[()\[\]]", "", t or "")).strip()


# ── orchestration ─────────────────────────────────────────────────────────────────────────
def _same_language(a, b):
    a, b = (a or "").strip().lower(), (b or "").strip().lower()
    if prompts.is_english_language(a) and prompts.is_english_language(b):
        return True
    if a in _ARABIC and b in _ARABIC:
        return True
    return a == b


# The content rule lives in the prompt, and a prompt is a request rather than a guarantee. This is
# the guard that does not depend on the model obeying it. It exists because a photograph of a pub
# bar reached a card: every check at the time was scoped to the sentence text, and nothing
# looked at the image query.
_IMG_DENY = frozenset("""
bar pub pubs tavern kneipe brewery brauerei biergarten beer beers bier wine wein winery vineyard
champagne sekt prosecco cocktail cocktails whisky whiskey vodka rum liquor liqueur alcohol
alcoholic drinking toast toasting cheers oktoberfest
pork pig pigs piglet swine ham bacon sausage bratwurst salami prosciutto butcher metzgerei
""".split())


def _clean_image_keyword(keyword, word, fallback=""):
    """Replace the image query outright if it names something the content rule forbids.

    Deleting the offending word and keeping the rest produces junk: "man drinking beer at
    Oktoberfest" becomes "man at", which searches for nothing useful. So a denied query is dropped
    whole and we search the word itself instead, which is what the keyword should usually have been.

    A learner is entitled to a card for "das Bier" if that is the word they typed. The prompt's
    CONTENT rule grants that exception and so does this.
    """
    if not keyword:
        return keyword
    asked = set(re.findall(r"[a-zäöüß]+", (word or "").lower()))
    hits = [t for t in (x.strip(",.;:!?()").lower() for x in keyword.split())
            if t in _IMG_DENY and t not in asked]
    if not hits:
        return keyword
    return (word or "").strip() or fallback or keyword


def build_card(cfg, provider, deck, word, options):
    """Run the full pipeline. Returns a bundle dict (see anki_io.write_bundle).

    options: meaning, scenario, image_keyword, image_source, secondary_language, generate_cloze, level.
    cfg: voices{target,translation,secondary}, tts{service,order,<service>{...}} (see pipeline/tts.py),
    image{pexels_key,serper_key,pixabay_key}, timeouts{ai_seconds,image_seconds,tts_seconds}.
    """
    # Optional User-Agent override (default lives in providers; not per-user, not a secret).
    # Threaded explicitly into each provider call — no global mutation (avoids a cross-call race).
    ua = (cfg.get("user_agent") or "").strip() or providers.DEFAULT_USER_AGENT
    meta_warnings = {}  # best-effort enrichment failures (grammar/secondary); surfaced in the toast

    def _warn_lang(text):
        prev = meta_warnings.get("language_warning")
        meta_warnings["language_warning"] = (prev + "; " + text) if prev else text

    # The learning language: the card's own pick, else Settings, else German (every config saved
    # before there were other languages). Its rules and texts come from RULES, the registry and
    # prompts.PROMPTS; nothing below names German.
    lang, _ll = languages.resolve(options.get("language") or (cfg.get("defaults", {}) or {}).get("learning_language"))
    if _ll:
        _warn_lang("%s, %s was used" % (_ll, languages.get(lang)["name"]))
    entry, rules = languages.get(lang), RULES[lang]

    # The learning language's own settings (language_settings). Only the learning language is read aloud
    # by default: the translation gets audio only when the user picks a translation voice in Settings
    # ("" = text only, the default since 1.0.2).
    settings = language_settings(cfg, lang)
    voice_target = settings["voice"]
    voice_en = settings["translation_voice"]
    voice_sec = settings["secondary_voice"]
    img_cfg = cfg.get("image", {}) or {}
    to = cfg.get("timeouts", {}) or {}
    ai_to = int(to.get("ai_seconds", 60))
    img_to = int(to.get("image_seconds", 15))
    tts_to = int(to.get("tts_seconds", 30))
    progress = options.get("progress") or (lambda msg: None)

    meaning = options.get("meaning", "")
    scenario = options.get("scenario", "")
    image_keyword = options.get("image_keyword", "")
    secondary_lang = str(options.get("secondary_language") or "").strip()
    # CEFR level: per-card pick > config default > built-in default. Unknown values fall back so a
    # stale config can never break generation. "Native" = the original prompt verbatim (see prompts).
    level = options.get("level") or cfg.get("defaults", {}).get("level") or prompts.DEFAULT_LEVEL
    if level not in prompts.LEVELS:
        level = prompts.DEFAULT_LEVEL
    # Primary translation language (the helper shown under the learning language). Default English
    # keeps the main prompt byte-identical; any other language is injected via the prompt's override.
    helpers = prompts.translation_languages(lang)
    configured = settings["translation"]
    primary_lang, _lw = _known_language(configured, prompts.default_translation_language(lang), allowed=helpers)
    if not primary_lang:
        # A learner of English with English (the default) or an unknown name as translation language: no
        # language may stand in for the one they read, so they are asked to pick it (friendly_error).
        raise RuntimeError('no translation language: cards that teach "%s" need another translation language than "%s"'
                           % (entry["name"], str(configured or "").replace('"', "'") or entry["name"]))
    if _lw:
        _warn_lang("%s, %s was used" % (_lw, primary_lang))
    secondary_lang, _sw = _known_language(secondary_lang, "", allowed=helpers)
    if _sw:
        _warn_lang(_sw + ", the second translation was skipped")
    # Never translate into the same language twice, whatever the UI passed in (a stale checkbox
    # after changing languages in Settings used to yield e.g. FRANCAIS + FRENCH on one card).
    if secondary_lang and _same_language(secondary_lang, primary_lang):
        meta_warnings["secondary_warning"] = "skipped, it is the same as the main translation language"
        secondary_lang = ""

    word_stem = _headword_stem(word, lang)
    style = str(options.get("style") or "").strip()      # "Use my style": the wishes from Settings, Cards

    def _call_main(strict):
        # The user message labels the input explicitly, carries the deck's context and the hints.
        system = prompts.main_system(lang, level, primary_lang, scenario, voice=voice_target)
        user = prompts.main_user(lang, word, deck, meaning, scenario, image_keyword, strict, options.get("exact_word"),
                                 style=style, voice=voice_target)
        # 3000 (was 1500): gpt-oss "reasoning" models spend HIDDEN reasoning tokens from the same
        # budget before emitting the JSON, and the amount varies per call. With the longer
        # rule set a reasoning spike could eat the whole 1500 and return an empty/truncated reply
        # (the intermittent 'Unreadable response' dialog). Cheap insurance: pay only for what is used.
        answer = providers.complete_json(provider, system, user, temperature=0.4, max_tokens=3000, timeout=ai_to, user_agent=ua)
        return _coerce_card_types(prompts.read_answer(lang, "main", answer))

    progress("generating card content")
    card = _call_main(options.get("strict", False))
    card = rules["input_check"](card, _call_main, word, options.get("force_input", False))
    raw_word = _normalize_word_field(card)
    got_stem = _headword_stem(raw_word, lang)
    if word_stem and got_stem and word_stem not in got_stem and got_stem not in word_stem:
        if not options.get("exact_word") and _looks_like_typo(word_stem, got_stem):
            # The model fixed a typo ("benachrichtigong" -> "die Benachrichtigung"). The card it made
            # is good, so keep it and let the dialog ask "Did you mean ...?"; a No re-runs with
            # options["exact_word"], which makes the prompt keep the input verbatim.
            meta_warnings["typo"] = {"input": word, "word": raw_word}
        else:
            card = _call_main(True)
            raw_word = _normalize_word_field(card)
            got_stem = _headword_stem(raw_word, lang)
            if word_stem and got_stem and word_stem not in got_stem and got_stem not in word_stem:
                raise RuntimeError('word mismatch: expected "%s", got "%s"' % (word.replace('"', "'"), raw_word.replace('"', "'")))

    # Exam-clean gate for A1–C1: if a word of another language leaked into the learning language's
    # fields (German: an English word), regenerate once. Native is exempt (Denglisch is allowed there).
    leak = (rules["leak"](card.get("example_casual"), card.get("example_formal"), card.get("explanation_de"))
            if level in ("A1", "A2", "B1", "B2", "C1") else None)
    if leak:
        # Best-effort (hard rule 2): a valid card already exists, so a 429/timeout on this second
        # back-to-back call must never throw it away. Keep the original and flag the leak instead.
        try:
            retry = _call_main(True)
            rstem = _headword_stem(_normalize_word_field(retry), lang)
            word_ok = not (word_stem and rstem and word_stem not in rstem and rstem not in word_stem)
            clean = not rules["leak"](retry.get("example_casual"), retry.get("example_formal"), retry.get("explanation_de"))
        except Exception:
            retry, word_ok, clean = None, False, False
        if retry is not None and word_ok and clean:
            card = retry            # regenerated card is clean AND still the right word
        else:
            meta_warnings["english_leak"] = leak   # keep original; surface the leak in the toast

    _sanitize_card_emojis(card)
    for k in ("example_casual", "example_formal", "explanation_de"):     # before the patterns and the audio
        if isinstance(card.get(k), str):
            card[k] = rules["country_words"](card[k], voice_target, word)
    for k in ("grammar_patterns", "casual_alternatives"):
        if isinstance(card.get(k), list):
            card[k] = [rules["country_words"](p, voice_target, word) if isinstance(p, str) else p for p in card[k]]
    card["word"] = rules["headword"](card.get("word", ""), card.get("morphology"))   # Spanish: "mesa" -> "la mesa"
    # Arabic without diacritics (a content rule) is enforced in code on every Arabic translation, the first
    # one, the grammar call's glosses and the cloze sentence's too, not only on the second one: a model adds a
    # shadda or a tanween now and then (the first live English run had both).
    arabic_plain = primary_lang.lower() in _ARABIC
    if arabic_plain:
        _strip_arabic_marks(card)
    # Label/direction for the primary-translation section (English default → "🇬🇧 English", LTR).
    card["primary_label"], card["primary_is_rtl"] = prompts.language_label(primary_lang)
    card["primary_lang_name"] = primary_lang
    card["level"] = level  # rendered as a chip on the card
    card["language"] = lang  # build_back_html takes the section label and the language's parts from it

    # Dedicated grammar-extraction call — now ONLY for Native. A1–C1 get level-appropriate
    # grammar_patterns straight from the main call (per-level focus in LEVEL_RULES), so no extra
    # call (faster, fewer rate-limit skips). The dedicated call gives Native its richer patterns.
    grammar_needed = level in prompts.GRAMMAR_LEVELS and bool(card.get("example_casual") or card.get("example_formal"))
    if grammar_needed and rules["grammar_fallback"]:
        probe = dict(card)
        rules["patterns"](probe)
        grammar_needed = not probe.get("grammar_patterns")     # the main call's own frames stand: no extra call
    if grammar_needed:
        progress("extracting grammar patterns")
        try:
            gout = prompts.read_answer(lang, "grammar", providers.complete_json(
                provider, prompts.grammar_system(lang, primary_lang), prompts.grammar_user(lang, card, primary_lang),
                temperature=0.2, max_tokens=_GRAMMAR_MAX_TOKENS, timeout=ai_to, user_agent=ua))
            card["grammar_patterns"] = gout.get("grammar_patterns") or []
            card["grammar_patterns_en"] = gout.get("grammar_patterns_en") or []
        except Exception as e:
            # The main call already fills grammar_patterns as a fallback — only warn if BOTH ended up
            # empty, so a rate-limited dedicated call doesn't show a misleading "grammar skipped" toast.
            if not (card.get("grammar_patterns") or card.get("grammar_patterns_en")):
                meta_warnings["grammar_warning"] = str(e)
    if arabic_plain:
        _strip_arabic_marks(card)          # again: the grammar call's glosses
    rules["patterns"](card)
    # Morphology (gender/plural/genitive · verb principal parts) is produced INSIDE the main call's
    # JSON for A1–C1 — folded in to avoid a 5th LLM call, which kept tripping the free-tier
    # tokens-per-minute limit. Native keeps its verbatim prompt and simply shows no morphology line.
    # A missing/invalid value just renders nothing (see _morphology_html).

    # Optional secondary translation (generalized "Arabic" call)
    if secondary_lang:
        progress("translating (%s)" % secondary_lang)
        try:
            sout = providers.complete_json(provider, prompts.secondary_system(lang, secondary_lang),
                                           prompts.secondary_user(lang, secondary_lang, card, level, primary_lang),
                                           temperature=0.2, max_tokens=_SECONDARY_MAX_TOKENS, timeout=ai_to,
                                           user_agent=ua)
            is_ar = secondary_lang.lower() in _ARABIC
            vals = {k: (_ARABIC_MARKS.sub("", v) if (is_ar and isinstance(v, str)) else v) for k, v in sout.items()}
            card["secondary_word"] = _sanitize_emoji(vals.get("word_translation", ""))
            card["secondary_casual"] = _sanitize_emoji(vals.get("casual", ""))
            card["secondary_formal"] = _sanitize_emoji(vals.get("formal", ""))
            card["secondary_is_arabic"] = is_ar
            card["secondary_label"] = "🇸🇦 العربية" if is_ar else prompts.language_label(secondary_lang)[0]
        except Exception as e:
            meta_warnings["secondary_warning"] = str(e)  # card still lands; translation just skipped

    # Tags
    tags = list(card.get("tags", []) or [])
    if (card.get("register") or "").lower() == "formal" and entry["formal_tag"] not in tags:
        tags.append(entry["formal_tag"])
    tags.append("Level::%s" % level)  # hierarchical → Anki shows a "Level" group to filter by (A1..Native)

    # Build main fields
    front = _front(card.get("emoji", ""), card.get("word", ""))
    back = build_back_html(card)

    media = {}
    # Per-clip audio resilience: each clip is attempted independently and failures are recorded
    # (never raised), so the card still lands with whatever audio succeeded. One Speaker per card
    # walks the voice-service chain (the chosen service, the backups that are set up, then Edge)
    # and skips a service for the remaining clips once it failed hard, so a broken service costs
    # one wait, not one per clip. Its summary goes into meta so the dialog can say exactly why a
    # clip is missing, or which service read it instead (tts.Speaker.summary).
    audio_status = {"ok": 0, "total": 0, "category": None}
    try:
        speaker = tts.Speaker(cfg.get("tts") or {}, timeout=tts_to)
    except Exception:
        speaker = tts.Speaker({}, timeout=tts_to)   # a broken tts config falls back to free Edge
    # Settings, Voice, Speech speed: the language you learn (the word with its sentences and the cloze
    # clips) may be read slower, at every level or at A1 and A2; the translations keep the normal speed.
    slow = tts.speech_rate(cfg.get("tts"), level)

    def _try_audio(text, voice, rate=1.0):
        audio_status["total"] += 1
        try:
            clip = speaker.speak(text, voice, rate)
        except Exception:
            return None                      # recorded in speaker.failures, reported via summary
        audio_status["ok"] += 1
        return clip

    # Image
    progress("fetching image")
    # imageKeyword already reflects the user's image hint (folded into the MAIN call as a SAFE
    # English term), so no raw non-English override is sent to the providers. Fall back to the
    # primary translation only if the model emitted no keyword at all.
    keyword = card.get("imageKeyword") or (card.get("translation_en", "") or "").split("/")[0].strip()
    img_keys = {"pexels": img_cfg.get("pexels_key", ""), "serper": img_cfg.get("serper_key", ""),
                "pixabay": img_cfg.get("pixabay_key", "")}  # Openverse needs no key (keyless fallback)
    keyword = _clean_image_keyword(keyword, word, card.get("translation_en", ""))
    img_src = options.get("image_source", "auto")
    img = images.fetch_image(keyword, deck, img_src, img_keys, timeout=img_to, exclude=_USED_PICTURES)
    if not img and keyword:
        # Usually a passing failure: in one test run three cards got no picture while the same search worked a
        # minute later. One more try, then the dialog says the card has none.
        time.sleep(_PICTURE_RETRY_PAUSE)
        img = images.fetch_image(keyword, deck, img_src, img_keys, timeout=img_to, exclude=_USED_PICTURES)
    if not img:
        meta_warnings["image_warning"] = ('no picture found for "%s"' % keyword) if keyword else "no picture found"
    if img:
        media["IMG"] = img  # (filename, bytes)
        back = back.replace("{{IMAGE}}", '<img src="%s" style="max-width:280px;border-radius:8px;">' % IMG)
    else:
        back = back.replace('<div class="card-image">{{IMAGE}}</div>', "").replace("{{IMAGE}}", "")

    # Main audio (DE + EN) — each clip independent; a failure just leaves that clip out.
    progress("generating audio")
    de_text = _clean_tts(". ... ".join([card.get("word", ""), card.get("example_casual", ""), card.get("example_formal", "")]))
    de_clip = _try_audio(de_text, voice_target, slow)
    if de_clip is not None:
        media["TTS_DE"] = (_audio_name(rules["audio_names"]["target"], front, de_text, de_clip), de_clip.data)
    # Translation audio — only when a translation voice is set. "(none)" (voice_en == ""), the
    # default, keeps the translation as TEXT only, so we skip the clip entirely (no wasted call, no
    # "audio failed" noise in the toast).
    if voice_en:
        en_text = _clean_tts(" ... ".join([(card.get("translation_en", "") or "") + ".", card.get("example_casual_en", ""), card.get("example_formal_en", "")]))
        en_clip = _try_audio(en_text, voice_en)
        if en_clip is not None:
            media["TTS_EN"] = (_audio_name(rules["audio_names"]["translation"], front, en_text, en_clip), en_clip.data)
    # Secondary-language audio (5th clip) — only when a secondary voice is configured AND the
    # secondary translation was produced. Reads the translation aloud in the secondary language.
    if voice_sec and (card.get("secondary_casual") or card.get("secondary_formal") or card.get("secondary_word")):
        sec_text = _clean_tts(" ... ".join([card.get("secondary_word", ""),
                                            card.get("secondary_casual", ""), card.get("secondary_formal", "")]))
        sec_clip = _try_audio(sec_text, voice_sec)
        if sec_clip is not None:
            media["TTS_SEC"] = (_audio_name("tts_sec", front, sec_text, sec_clip), sec_clip.data)
    audio_tags = ""
    if "TTS_DE" in media:
        audio_tags += "[sound:%s]" % TTS_DE
    if "TTS_EN" in media:
        audio_tags += "[sound:%s]" % TTS_EN
    if "TTS_SEC" in media:
        audio_tags += "[sound:%s]" % TTS_SEC
    if audio_tags:
        back += "<br>" + audio_tags

    bundle = {
        "main": {"fields": {"Front": front, "Back": back}, "tags": tags, "deck": deck},
        "cloze": None,
        "media": media,
        "meta": {"word": card.get("word", word), "translation_en": card.get("translation_en", ""),
                 "audio": audio_status, **meta_warnings},
    }

    # Cloze companion
    if options.get("generate_cloze", True):
        try:
            progress("generating cloze companion")
            cu = prompts.cloze_user(lang, word, deck, card.get("translation_en", ""), level, primary_lang, voice_target,
                                    style=style)
            cz = prompts.read_answer(lang, "cloze", providers.complete_json(
                provider, prompts.cloze_system(lang), cu, temperature=0.3, max_tokens=1600, timeout=ai_to, user_agent=ua))
            sentence = rules["country_words"]((cz.get("sentence") or "").strip(), voice_target, word)
            answer_raw = rules["country_words"]((cz.get("answer") or "").strip(), voice_target, word)
            card_case = str(cz.get("case") or "single_word").strip()
            if card_case not in rules["cloze_cases"]:
                card_case = "single_word"          # it becomes a tag, and tags are rendered on the card
            if not (sentence and answer_raw):
                bundle["meta"]["cloze_warning"] = "the model produced no usable cloze sentence"
            if sentence and answer_raw:
                card_case, answer_raw = rules["cloze_case"](sentence, answer_raw, card_case, word)
                working = answer_raw
                if card_case != "idiom":
                    sentence, working = rules["cloze_fix"](sentence, working)
                    while working and working not in sentence:
                        ws = working.split()
                        if len(ws) <= 1:
                            working = ""
                            break
                        working = " ".join(ws[1:])
                    if working:
                        working = rules["cloze_article"](sentence, working, card_case, word)
                if not (working or card_case == "idiom"):
                    bundle["meta"]["cloze_warning"] = "the cloze answer was not found in its sentence"
                if working or card_case == "idiom":
                    # Nest the cloze companion under whatever deck the user chose, regardless of
                    # namespace. For a flat "Deutsch::X" deck this yields the same "Deutsch::X::Cloze"
                    # path as before (existing cloze cards stay put); a non-German deck like
                    # "Tarkib German" now correctly gets "Tarkib German::Cloze".
                    cloze_deck = deck + "::Cloze"
                    deck_slug = deck.split("::")[-1] or deck or "Cards"  # leaf name for DeckOrigin/tags
                    answer_for_text = answer_raw if card_case == "idiom" else working
                    # Escape BEFORE building the {{c1::}} markup so the cloze syntax itself is untouched.
                    cloze_text = build_cloze_text(_esc(sentence), _esc(answer_for_text), card_case, _esc(cz.get("idiom_meaning_de", "")),
                                                  beginner=level in ("A1", "A2"), no_hint=rules["cloze_no_hint"])
                    if "{{c1::" not in cloze_text:
                        # Idiom answers are not substring-verified (dictionary form vs inflection): never
                        # bundle a cloze note with zero deletions.
                        raise ValueError("the cloze answer was not found in its sentence")
                    tts_answer = (",".join(a.strip() for a in answer_raw.split(",") if a.strip())
                                  if card_case == "idiom" else working)
                    progress("generating cloze audio")
                    front_audio = back_audio = ""
                    # Front (pause-drill) and back (full) are independent clips — one can land
                    # without the other.
                    split_text = audio.split_for_cloze(sentence, tts_answer)
                    # Whole-sentence blanks leave no words to speak ("Herzlich willkommen!" -> "!"):
                    # skip the pause-drill clip instead of burning 4 doomed TTS attempts.
                    fb = (_try_audio(split_text, voice_target, slow)
                          if re.search(r"[^\W\d_]", split_text) else None)
                    if fb is not None:
                        # The pause-drill clip depends on WHICH span is deleted, not just on the
                        # sentence — two cards sharing a sentence but deleting different words
                        # produce different audio. Naming it after the sentence alone made them
                        # collide, and one card then played the other's drill (19 cases across
                        # the catalogue). Hash the spoken text so the name follows the audio.
                        media["CLOZE_FRONT"] = (_audio_name("cloze_front", sentence, split_text, fb), fb.data)
                        front_audio = "[sound:%s]" % CLOZE_FRONT
                    bb = _try_audio(sentence, voice_target, slow)
                    if bb is not None:
                        media["CLOZE_BACK"] = (_audio_name("cloze_back", sentence, sentence, bb), bb.data)
                        back_audio = "[sound:%s]" % CLOZE_BACK
                    image_html = '<img src="%s">' % IMG if "IMG" in media else ""
                    cloze_translation = (cz.get("translation_en") or "").strip() or card.get("translation_en", "")
                    if arabic_plain:
                        cloze_translation = _ARABIC_MARKS.sub("", cloze_translation)
                    bundle["cloze"] = {
                        "deck": cloze_deck,
                        "fields": {
                            "Text": cloze_text,
                            # Full SENTENCE translation (in the primary language) — not the word's meaning.
                            "Translation": _esc(cloze_translation),
                            "Image": image_html, "FrontAudio": front_audio, "BackAudio": back_audio,
                            "GrammarHint": _esc(cz.get("grammar_hint", "") or ""),
                            "SourceWord": _esc(card.get("word", "")), "DeckOrigin": _esc(deck_slug),
                        },
                        # Anki splits tags on whitespace, so "1 Wortschatz" would silently become
                        # two tags ("1" and "wortschatz"). Collapse spaces before they ever ship.
                        "tags": ["cloze", re.sub(r"\s+", "_", deck_slug.lower().strip()),
                                 "case_%s" % card_case, "Level::%s" % level],
                    }
        except Exception as e:
            bundle["meta"]["cloze_warning"] = str(e)

    # Last, so it covers the cloze clips too: why clips are missing, who read them (ui/dialog.py).
    audio_status.update(speaker.summary())
    return bundle


def _safe(s):
    return re.sub(r"[^\w]", "_", s or "")[:24].strip("_") or "card"
