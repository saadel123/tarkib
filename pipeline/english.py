"""English as a learning language: what its cards need beyond the generic set.

Two parts, both read by the tables keyed by the registry (pipeline/languages.py):

    NOTE     the English pieces of the generic prompts (prompts.generic_prompts fills its slots)
    CHECKS   the English checks and card parts (generate.generic_rules takes them over the generic ones)

No imports from the add-on, so prompts.py and generate.py can both import this file.
"""
import html
import re


def _esc(s):
    return html.escape(str(s or ""), quote=False)


# ── the prompt pieces ────────────────────────────────────────────────────────────────────────
_LEVELS = {
    "A1": (
        ' # LEVEL A1 (beginner): use ONLY the ~600 most common everyday words. MAXIMUM 6 words per sentence, count them. '
        'ONE simple main clause, exactly ONE action. Present simple (present continuous is OK), "can" for ability and requests. '
        'FORBIDDEN at A1: clauses with because, when, if or that; relative clauses; the passive; conditionals; idioms; slang; '
        'phrasal verbs other than the most basic (get up, sit down, turn on). '
        'REGISTER AT THIS LEVEL: example_casual is plain informal English (contractions like I\'m and don\'t are fine), never slang, '
        'no interjections (hey, wow, yeah). example_formal is a polite sentence with the word that makes sense on its own '
        '(a polite question with "Could you ...?" or a sentence with "please"). '
        'VOCABULARY: apart from the target word, EVERY other word in both sentences must be basic beginner vocabulary a learner '
        'meets in the first weeks (family, home, food, shopping, school, work, time, weather, transport, greetings). Never formal '
        'or office words (ensure, require, provide, regarding, receive). If the target word itself is harder, keep every other '
        'word trivial. '
        'grammar_patterns: look first for a verb, adjective or noun with its preposition, then can + verb.'
    ),
    "A2": (
        ' # LEVEL A2 (elementary): ~1200 common words. MAXIMUM ~10 words per sentence. At most ONE simple clause with because, '
        'when, if or that (never nested). Past simple, going to and will for the future, comparatives, can, could, must and have to. '
        'FORBIDDEN at A2: relative clauses, the passive, conditionals beyond "if + present, will", idioms, slang. Make it CLEARLY a '
        'step above A1: use a because, when or if clause OR the past simple. '
        'REGISTER AT THIS LEVEL: example_casual is plain informal English, never slang; example_formal says the same politely. '
        'VOCABULARY: apart from the target word, every other word basic A1 or A2 vocabulary, never formal or office words '
        '(ensure, require, provide, regarding). '
        'grammar_patterns: look first for a verb, adjective or noun with its preposition, then verb + -ing or to + verb, '
        'the past simple of an irregular verb.'
    ),
    "B1": (
        ' # LEVEL B1 (intermediate): ~2500 common words. Medium sentences; clauses with because, although, when, if and relative '
        'clauses (who, which, that) are fine. The present perfect, the past continuous, used to, the first and second conditional, '
        'common phrasal verbs. At most ONE well-known idiom (note its meaning in the explanation). Light register contrast. '
        'grammar_patterns: look first for a verb, adjective or noun with its preposition, then phrasal verbs, verb + -ing or '
        'to + verb, collocations.'
    ),
    "B2": (
        ' # LEVEL B2 (upper-intermediate): wide everyday and common professional words. Longer, more complex sentences, the '
        'passive, reported speech, the third conditional, wish, a wide range of phrasal verbs and collocations; common idioms are '
        'fine. A clear but MODERATE casual style (no heavy slang). '
        'grammar_patterns: look first for a verb, adjective or noun with its preposition, then phrasal verbs, collocations, '
        'the passive or a conditional.'
    ),
    "C1": (
        ' # LEVEL C1 (advanced): rich, near-native English across registers. The formal example shows genuine C1 range where it '
        'sounds natural: inversion for emphasis, cleft sentences, mixed conditionals, nuanced modals, a precise formal style; never '
        'forced or bookish. Idioms and advanced linkers used naturally. Still REAL, everyday-useful English, NEVER rare words. The '
        'casual example may be genuinely colloquial. '
        'grammar_patterns: look first for a verb, adjective or noun with its preposition and idiomatic collocations, then '
        'inversion, cleft sentences, mixed conditionals.'
    ),
}

_CLOZE_LEVELS = {
    "A1": ('\n\nLEVEL A1: use ONLY case "single_word"; a SHORT present-tense sentence (3 to 7 words) with the most common '
           'words; no idioms, no clause.'),
    "A2": ('\n\nLEVEL A2: prefer case "single_word"; a short sentence (present or past simple), common words, at most one '
           'because, when or if clause; no idioms.'),
    "B1": ('\n\nLEVEL B1: use case "single_word", "verb_prep" or "phrasal_verb"; a medium everyday sentence with common '
           'words.'),
}

_CLOZE_CASES = (
    'A. "single_word": one content word. Cloze just the word, never a, an or the.\n'
    'B. "verb_prep": a verb, adjective or noun with its fixed preposition. Cloze JUST the preposition '
    '("depend on" -> answer "on", "interested in" -> "in", "the reason for" -> "for").\n'
    'C. "phrasal_verb": cloze JUST the particle ("give up" -> "up", "put off" -> "off"). The sentence may split the verb '
    '("We put the meeting off").\n'
    'D. "collocation": a verb + noun pair. Cloze JUST the verb ("make a decision" -> "make", "take a photo" -> "take").\n'
    'E. "long_phrase": a phrase of more than 3 words that is not an idiom; cloze the whole phrase.\n'
    'F. "idiom": cloze 2 to 3 key content words, comma-separated.'
)


def _variety(voice):
    """US or UK English follows the voice that reads the card: a British voice gets British spelling and
    words, every other voice American."""
    return "British" if str(voice or "").startswith(("en-GB", "en-IE")) else "American"


def _standard(voice):
    words = ("colour, centre, flat, holiday, biscuit" if _variety(voice) == "British"
             else "color, center, apartment, vacation, cookie")
    return ('# STANDARD ENGLISH (these are CEFR levels A1 to C1, used by learners preparing for official English exams): '
            'write standard %s English, with %s spelling and words (%s). No slang, no text-speak (gonna, wanna, u, lol) and '
            'no swear words; contractions are fine in casual sentences. (The separate "Native" style is the only place for '
            'slang.) ' % (_variety(voice), _variety(voice), words))


def _variety_line(voice):
    return "\n\nUse %s English spelling and words." % _variety(voice)


NOTE = {
    "input_examples": ('Words English has taken from other languages (café, kindergarten, karaoke), names, and an English word '
                       'with a small typo COUNT AS ENGLISH (fix the typo).'),
    "word_rule": 'Keep it as typed: never add "the", "a" or "to". Phrases and sentences stay as they are.',
    "register_pair": (
        'example_casual is everyday spoken English: contractions (I\'m, don\'t, it\'s), everyday words and phrasal verbs (get, '
        'find out, check). example_formal is polite or professional standard English: full forms (I am, do not) and more formal '
        'words where they fit (receive, discover, contact), the way you would write to an office or speak to a stranger. If the '
        'word has a casual and a formal form (get and receive, find out and discover, buy and purchase), casual uses the casual '
        'one and formal the formal one. English has one "you" for everyone, so the contrast comes from the words and the tone. '),
    "self_check": (
        'subject and verb agree (she works, they work); questions use do, does or did with the base form ("Did you go?", never '
        '"Did you went?"); the right tense (the past simple for a finished time, "I saw her yesterday"; the present perfect for '
        'experience up to now, "I have seen it"); the right preposition after a verb, adjective or noun (depend on, good at, '
        'reason for); a, an and the used correctly; question word order ("Where does it come from?") and embedded questions '
        '("I don\'t know where it is"); no double negatives. '),
    "standard": _standard,
    "levels": _LEVELS,
    "native": (
        ' # NATIVE: real spoken English of people aged 20 to 40 today: contractions, phrasal verbs, idioms and slang where it is '
        'natural (gonna, kinda, no worries). Casual can sound like a text message; formal sounds like a competent work email. '
        'Casual is 5 to 12 words, formal 8 to 18. Vary how sentences start. NEVER stack fillers ("like, you know, basically"). '),
    "register_examples": ('"casual" = slang or very informal words (gonna, chill out, a quid, awesome). "neutral" = works in both '
                          '(work, buy, see). "formal" = legal, official or written words not used in casual speech (hereby, '
                          'notwithstanding, henceforth, commence, purchase). '),
    "ranked": ('a verb + preposition ("depend on something", "wait for someone"), an adjective or noun + preposition '
               '("interested in something", "the reason for something"), verb + -ing or to + verb ("enjoy + -ing", "decide '
               'to + verb", "make someone do something"), phrasal verbs ("give up", "look after someone", "put something off"), '
               'collocations ("make a decision", "take a photo", "do homework"), a verb that opens a clause ("explain that", '
               '"wonder if"), then level structures (present perfect, conditionals, the passive, used to)'),
    "pattern_rule": ('At EVERY level, including A1: a verb, adjective or noun with its fixed preposition in a sentence (depend '
                     'on, interested in, good at, reason for) MUST appear as a pattern.'),
    "pattern_format": ('Write each pattern as a frame a learner can reuse in a new sentence: "someone" and "something" where '
                       'the object goes, "+ -ing" or "to + verb" for verb patterns. GOOD: "depend on something", "would like '
                       'to + verb", "be going to + verb", "give someone advice about something". BAD: "like to buy" (a piece '
                       'cut out of the sentence), "buy something" or "bring something" (a bare object), "at something" (a '
                       'preposition alone).'),
    "morphology": (
        'NOUN -> {"pos":"noun","singular":"<singular, without a, an or the>","plural":"<plural>","countable":true_or_false}; '
        'for an uncountable noun (information, advice, furniture, news) use "countable":false and "plural":"". '
        'VERB -> {"pos":"verb","base":"<base form without to>","past":"<past simple>","past_participle":"<past participle>",'
        '"phrasal":true_or_false,"separable":true_or_false}; for a phrasal verb give every form with its particle ("give up", '
        '"gave up", "given up"); "separable" is true when the object can go between the verb and its particle (separable: put the '
        'meeting off, pick the kids up, turn the light off; not separable: look after the kids, get on the bus). Anything else -> {"pos":"other"}. Be 100% correct: irregular verbs (go, went, gone; take, took, taken; buy, '
        'bought, bought), irregular plurals (child, children; person, people; mouse, mice), uncountable nouns. NEVER a '
        'regularized form (goed, buyed, childs).'),
    "tags": ("Everyday", "Work", "Home", "Transport", "Money", "Health", "Food", "Kitchen", "Clothes", "Shopping",
             "Technology", "Feelings", "Education", "Sport", "Travel", "Car", "Time", "Qualities", "Communication",
             "Relationships"),
    "tags_native": ("Everyday", "Work", "Idiom", "Home", "Transport", "Money", "Health", "Food", "Kitchen", "Clothes",
                    "Shopping", "Technology", "Feelings", "Grammar", "Education", "Sport", "Travel", "Car", "Time",
                    "Qualities", "Slang", "Communication", "Relationships", "Formal"),
    "explanation": ('1 short, simple English sentence that explains the word, like a learner\'s dictionary, in words easier '
                    'than the word itself, e.g. buy: "You give money and get something." (at A1 and A2 only the most '
                    'common words; never a translation, never the word explained by itself)'),
    "cloze_cases": _CLOZE_CASES,
    "cloze_case_names": ("single_word", "verb_prep", "phrasal_verb", "collocation", "long_phrase", "idiom"),
    "cloze_levels": _CLOZE_LEVELS,
    "contexts": {
        "Default": ('CONTEXT: Important everyday English. Formal: office, appointment or email scenario. Casual: chat with '
                    'friends or family (messaging tone). Prefer situations people meet every week: work, shopping, health, '
                    'travel, home.'),
    },
    "variety_line": _variety_line,
}


# ── the checks and card parts ────────────────────────────────────────────────────────────────
# Irregular verbs: base -> (past, past participle) as the card shows them. Only used to RESCUE a real
# pattern whose verb appears in an irregular form ("took" for "take") and to repair a regularized form
# on the word line ("buyed"); a verb missing here costs a pattern at most, never a card.
IRREGULAR = {
    "arise": ("arose", "arisen"), "awake": ("awoke", "awoken"), "be": ("was, were", "been"), "bear": ("bore", "borne"),
    "beat": ("beat", "beaten"), "become": ("became", "become"), "begin": ("began", "begun"), "bend": ("bent", "bent"),
    "bet": ("bet", "bet"), "bind": ("bound", "bound"), "bite": ("bit", "bitten"), "bleed": ("bled", "bled"),
    "blow": ("blew", "blown"), "break": ("broke", "broken"), "breed": ("bred", "bred"), "bring": ("brought", "brought"),
    "build": ("built", "built"), "burn": ("burned", "burned"), "buy": ("bought", "bought"), "catch": ("caught", "caught"),
    "choose": ("chose", "chosen"), "cling": ("clung", "clung"), "come": ("came", "come"), "cost": ("cost", "cost"),
    "creep": ("crept", "crept"), "cut": ("cut", "cut"), "deal": ("dealt", "dealt"), "dig": ("dug", "dug"),
    "do": ("did", "done"), "draw": ("drew", "drawn"), "dream": ("dreamed", "dreamed"), "drink": ("drank", "drunk"),
    "drive": ("drove", "driven"), "eat": ("ate", "eaten"), "fall": ("fell", "fallen"), "feed": ("fed", "fed"),
    "feel": ("felt", "felt"), "fight": ("fought", "fought"), "find": ("found", "found"), "flee": ("fled", "fled"),
    "fly": ("flew", "flown"), "forbid": ("forbade", "forbidden"), "forget": ("forgot", "forgotten"),
    "forgive": ("forgave", "forgiven"), "freeze": ("froze", "frozen"), "get": ("got", "gotten"), "give": ("gave", "given"),
    "go": ("went", "gone"), "grind": ("ground", "ground"), "grow": ("grew", "grown"), "hang": ("hung", "hung"),
    "have": ("had", "had"), "hear": ("heard", "heard"), "hide": ("hid", "hidden"), "hit": ("hit", "hit"),
    "hold": ("held", "held"), "hurt": ("hurt", "hurt"), "keep": ("kept", "kept"), "kneel": ("knelt", "knelt"),
    "know": ("knew", "known"), "lay": ("laid", "laid"), "lead": ("led", "led"), "lean": ("leaned", "leaned"),
    "leap": ("leaped", "leaped"), "learn": ("learned", "learned"), "leave": ("left", "left"), "lend": ("lent", "lent"),
    "let": ("let", "let"), "lie": ("lay", "lain"), "light": ("lit", "lit"), "lose": ("lost", "lost"),
    "make": ("made", "made"), "mean": ("meant", "meant"), "meet": ("met", "met"), "mistake": ("mistook", "mistaken"),
    "overcome": ("overcame", "overcome"), "pay": ("paid", "paid"), "prove": ("proved", "proven"), "put": ("put", "put"),
    "quit": ("quit", "quit"), "read": ("read", "read"), "ride": ("rode", "ridden"), "ring": ("rang", "rung"),
    "rise": ("rose", "risen"), "run": ("ran", "run"), "say": ("said", "said"), "see": ("saw", "seen"),
    "seek": ("sought", "sought"), "sell": ("sold", "sold"), "send": ("sent", "sent"), "set": ("set", "set"),
    "shake": ("shook", "shaken"), "shine": ("shone", "shone"), "shoot": ("shot", "shot"), "show": ("showed", "shown"),
    "shrink": ("shrank", "shrunk"), "shut": ("shut", "shut"), "sing": ("sang", "sung"), "sink": ("sank", "sunk"),
    "sit": ("sat", "sat"), "sleep": ("slept", "slept"), "slide": ("slid", "slid"), "smell": ("smelled", "smelled"),
    "speak": ("spoke", "spoken"), "spell": ("spelled", "spelled"), "spend": ("spent", "spent"), "spill": ("spilled", "spilled"),
    "spin": ("spun", "spun"), "spit": ("spat", "spat"), "split": ("split", "split"), "spoil": ("spoiled", "spoiled"),
    "spread": ("spread", "spread"), "spring": ("sprang", "sprung"), "stand": ("stood", "stood"), "steal": ("stole", "stolen"),
    "stick": ("stuck", "stuck"), "sting": ("stung", "stung"), "stink": ("stank", "stunk"), "strike": ("struck", "struck"),
    "swear": ("swore", "sworn"), "sweep": ("swept", "swept"), "swim": ("swam", "swum"), "swing": ("swung", "swung"),
    "take": ("took", "taken"), "teach": ("taught", "taught"), "tear": ("tore", "torn"), "tell": ("told", "told"),
    "think": ("thought", "thought"), "throw": ("threw", "thrown"), "understand": ("understood", "understood"),
    "undertake": ("undertook", "undertaken"), "upset": ("upset", "upset"), "wake": ("woke", "woken"),
    "wear": ("wore", "worn"), "weep": ("wept", "wept"), "win": ("won", "won"), "wind": ("wound", "wound"),
    "withdraw": ("withdrew", "withdrawn"), "write": ("wrote", "written"),
}
# Other forms that are just as right (British forms, older forms): accepted, never "repaired".
_ALSO = {
    "burn": ("burnt",), "dream": ("dreamt",), "get": ("got",), "kneel": ("kneeled",), "lean": ("leant",),
    "leap": ("leapt",), "learn": ("learnt",), "light": ("lighted",), "prove": ("proved",), "shine": ("shined",),
    "show": ("showed",), "smell": ("smelt",), "spell": ("spelt",), "spill": ("spilt",), "spoil": ("spoilt",),
    "bear": ("born",), "dive": ("dove", "dived"), "spit": ("spit",), "wake": ("waked",),
}
# Verbs with regular forms that are also right and common ("learned"): a line with those is a regular verb.
_REGULAR_TOO = {"burn", "dream", "kneel", "lean", "leap", "learn", "light", "prove", "smell", "spell", "spill", "spoil"}


def _forms(base):
    """Every past and participle form the table accepts for a base verb."""
    past, part = IRREGULAR.get(base, ("", ""))
    out = {f.strip() for f in past.split(",") + part.split(",") if f.strip()} | set(_ALSO.get(base, ()))
    if base in _REGULAR_TOO:
        out.add(_regular(base))
    return out


def _regular(base):
    if base.endswith("e"):
        return base + "d"
    if len(base) > 2 and base.endswith("y") and base[-2] not in "aeiou":
        return base[:-1] + "ied"
    return base + "ed"


def _is_regular_form(base, form):
    """walk -> walked, like -> liked, study -> studied, stop -> stopped (a doubled last consonant)."""
    return form in (_regular(base), base + base[-1:] + "ed")


_BASE_OF = {}
for _b in IRREGULAR:
    for _f in _forms(_b):
        _BASE_OF.setdefault(_f, set()).add(_b)


def _first(text):
    words = (text or "").strip().lower().split()
    return words[0] if words else ""


def morphology_html(m, level=None):
    """The word line, only where English has something to learn: an irregular verb ("buy · bought ·
    bought"), a phrasal verb that splits ("separable"), an irregular plural ("Pl. children") or an
    uncountable noun. A regular noun or verb shows nothing. A regularized irregular form ("buyed") is
    replaced from IRREGULAR, never shown."""
    if not isinstance(m, dict):
        return ""
    pos = m.get("pos")
    if pos == "noun":
        if m.get("countable") is False:
            return '<div class="morph">uncountable</div>'
        sing = str(m.get("singular") or "").strip()
        plural = str(m.get("plural") or "").strip()
        if not plural or not sing:
            return ""
        s, p = sing.lower(), plural.lower()
        if p in (s + "s", s + "es") or (s.endswith("y") and p == s[:-1] + "ies"):
            return ""
        return '<div class="morph">Pl. %s</div>' % _esc(plural)
    if pos == "verb":
        base = re.sub(r"^to\s+", "", str(m.get("base") or "").strip(), flags=re.I)
        past = str(m.get("past") or "").strip()
        part = str(m.get("past_participle") or "").strip()
        head, rest = _first(base), " ".join(base.split()[1:])
        bits = []
        if head and past and part:
            p1, p2 = _first(past), _first(part)
            if head in IRREGULAR:
                ok = _forms(head)
                if p1 not in ok or p2 not in ok:            # a regularized or wrong form: the table decides
                    p1, p2 = (f.strip() for f in IRREGULAR[head])
                    past = ("%s %s" % (p1, rest)).strip()
                    part = ("%s %s" % (p2, rest)).strip()
                irregular = not (_is_regular_form(head, p1) and _is_regular_form(head, p2))
            else:
                irregular = not (_is_regular_form(head, p1) and _is_regular_form(head, p2))
            if irregular:
                bits.append(" · ".join(_esc(x) for x in (base, past, part)))
        if m.get("phrasal") and m.get("separable"):
            bits.append("separable")
        return ('<div class="morph">%s</div>' % " · ".join(bits)) if bits else ""
    return ""


def register_hint(word_display, alternatives):
    if not alternatives:
        return ""
    return ('<div class="register-hint"><span class="formal-mark">“%s” (Formal)</span> '
            '<span class="arrow">→</span> <span class="casual-alt">Everyday:</span> '
            '<span class="alt-list">%s</span></div>' % (_esc(word_display), " · ".join(_esc(a) for a in alternatives)))


# Words of the other Latin-script translation languages that are NEVER English words. Conservative on
# purpose (no "die", "was", "hat", "mit", "con", "per", "los"): a hit costs a strict retry.
_LEAK_WORDS = {
    "und", "nicht", "ich", "ist", "sind", "eine", "einen", "einem", "einer", "für", "sehr", "auch", "aber", "oder",
    "wir", "haben", "zum", "zur", "schon", "noch", "heute", "bitte", "danke",
    "une", "avec", "très", "mais", "nous", "vous", "sont", "être",
    "una", "muy", "pero", "está", "también",
    "gli", "sono", "perché", "uma", "não", "muito", "você",
    "bir", "çok", "değil", "een", "niet", "ook", "maar",
}


def leak(*texts):
    """The first sign that the translation language leaked into the English fields: a letter of another
    script (Arabic, Cyrillic, Chinese, ...) or a function word of another Latin-script language."""
    for t in texts:
        t = t or ""
        for ch in t:
            if ch.isalpha() and not ("a" <= ch.lower() <= "z") and ord(ch) > 0x24F:   # beyond Latin Extended
                return ch
        for tok in re.findall(r"[^\W\d_]+", t.lower()):
            if tok in _LEAK_WORDS:
                return tok
    return None


_STOP = {"someone", "somebody", "something", "sb", "sth", "one's", "oneself", "yourself", "himself", "herself",
         "themselves", "ing", "the", "and", "verb", "noun", "adjective", "adverb"}
# Grammar words. Many are ordinary words too ("ask a question", "present something", "keep it simple"), so a
# pattern is a grammar LABEL only with a word from the first set or two words from the second.
_META_STRONG = {"passive", "conditional", "infinitive", "gerund", "subjunctive", "inversion", "cleft", "participle",
                "tense", "clause", "imperative", "comparative", "superlative", "modal", "progressive", "continuous"}
_META_WEAK = {"present", "past", "perfect", "simple", "future", "reported", "speech", "relative", "first", "second",
              "third", "zero", "mixed", "structure", "question", "form"}
_META = _META_STRONG | _META_WEAK


def _is_label(words):
    return any(w in _META_STRONG for w in words) or sum(w in _META_WEAK for w in words) >= 2


# The present forms and contractions of the three verbs a pattern often names: "be in something" is in
# "I'm in the kitchen".
_PRESENT = {"be": ("am", "is", "are", "was", "were", "been", "being", "'m", "'re", "'s"),
            "have": ("has", "had", "having", "'ve", "'d"), "do": ("does", "did", "done", "doing")}


def _word_present(w, text_words):
    if w in text_words:
        return True
    forms = _PRESENT.get(w)
    return bool(forms) and any(t in forms or t.endswith(tuple(f for f in forms if f.startswith("'")))
                               for t in text_words)


_ENDINGS = ("s", "es", "ed", "d", "ing", "er", "ers", "est", "ly")
# Words that never anchor a pattern on their own: a preposition, a particle, a modal or a frame label is in
# almost every sentence ("for" is even inside "before"). A pattern made only of them needs each of them.
_MODALS = {"can", "could", "will", "would", "shall", "should", "may", "might", "must"}
_LABELS = {"verb", "noun", "adjective", "adverb", "time", "place", "subject", "object"}


def _matches(w, tok):
    """`tok` is the word `w` with at most an ending: depends, waited, studies, making, stopped."""
    if tok == w:
        return True
    stems = {w}
    if w.endswith("e") and len(w) > 3:
        stems.add(w[:-1])                          # make -> making
    if w.endswith("y") and len(w) > 3:
        stems.add(w[:-1] + "i")                    # study -> studies, studied
    for st in stems:
        if tok.startswith(st):
            rest = tok[len(st):]
            if rest in _ENDINGS or (len(rest) >= 3 and rest[0] == st[-1] and rest[1:] in ("ed", "ing", "er")):
                return True                        # stop -> stopped, stopping
    return False


def pattern_in_text(pattern, text_lower):
    """True when a pattern is really exemplified by the sentences: one of its content words is a word of
    the sentences, as is, with an ending (depends, waited, studies), in an irregular form (took for take)
    or as a form of be, have or do ("I'm" for be). Whole words only. A pattern made only of grammar words
    ("present perfect") or of short words ("by + -ing", "can + verb") needs every word it names."""
    words = re.findall(r"[a-z']+", (pattern or "").lower())
    label = _is_label(words)
    never = _STOP | _PREPS | _PARTICLES | _MODALS | _LABELS
    content = [w for w in words if len(w) >= 3 and w not in never and not (label and w in _META)]
    text_words = set(re.findall(r"[a-z']+", text_lower))
    if not content:
        anchors = [w for w in words if w not in _STOP and w not in _META and w not in _LABELS]
        return bool(anchors) and all(_word_present(w, text_words) for w in anchors)
    for w in content:
        if _word_present(w, text_words) or any(_matches(w, t) for t in text_words):
            return True
        for suffix in ("ing", "ed", "es", "s"):    # the pattern itself carries an ending ("depends on")
            if w.endswith(suffix) and len(w) - len(suffix) >= 3 and any(_matches(w[:-len(suffix)], t) for t in text_words):
                return True
        family = _forms(w) | _BASE_OF.get(w, set())
        for b in _BASE_OF.get(w, ()):
            family |= _forms(b)
        if family & text_words:
            return True
    return False


_PREPS = {"about", "at", "by", "for", "from", "in", "into", "of", "on", "onto", "with", "without", "against",
          "among", "between", "after", "before", "through", "towards", "toward", "under", "over", "across",
          "around", "behind", "during", "upon", "within", "until", "till", "since", "despite", "except", "near"}
_PARTICLES = {"up", "out", "off", "down", "away", "back", "over", "around", "along", "forward", "apart", "together"}
_PLACEHOLDERS = {"someone", "somebody", "something", "sb", "sth", "one's", "oneself"}
# Words that name no word of the sentence: prepositions, "to", articles, pronouns and the word-class labels of a
# frame. "time" and "place" stay meaningful: "until + time" and "at + place" teach how the preposition is used.
_FUNCTION = _PREPS | {"to", "the", "a", "an", "i", "you", "he", "she", "it", "we", "they", "verb", "noun", "adjective",
                      "adverb"}
_ADJECTIVES = {"afraid", "aware", "fond", "good", "bad", "keen", "proud", "sure", "tired", "full", "ready", "able",
               "responsible", "interested", "worried", "angry", "happy", "sorry", "late", "different", "similar",
               "famous", "capable", "jealous", "nervous", "married", "used", "excited", "bored", "busy", "free",
               "close", "crazy", "fed", "familiar", "grateful", "guilty", "kind", "polite", "rude", "safe"}
_ADJ_ENDINGS = ("ed", "ful", "ous", "ive", "able", "ible", "ic", "ant", "ent", "less")
_NOUN_ENDINGS = ("tion", "sion", "ment", "ness", "ity", "ance", "ence", "ship", "dom", "ure")
_DETERMINERS = {"a", "an", "the", "my", "your", "his", "her", "our", "their", "its"}


def pattern_rank(pat):
    """Where an English pattern sits in the value order (1 = first), used to order the patterns and keep the
    best three: 1 verb + preposition, 2 adjective or noun + preposition, 3 verb + -ing or to + verb,
    4 phrasal verb, 5 collocation, 6 a verb that opens a clause, 8 a named structure, 9 anything else.
    A first version: refine it from real cards, like the German one was."""
    low = (pat or "").lower()
    toks = re.findall(r"[a-z']+", low)
    if not toks:
        return None
    real = [t for t in toks if t not in _PLACEHOLDERS]
    if len(real) == 1 and len(toks) == 2 and toks[1] in _PLACEHOLDERS:
        return None                     # "buy something": a bare object teaches nothing (the prompt forbids it too)
    if "ing" not in toks and not [t for t in real if t not in _FUNCTION]:
        return None                     # "to + verb", "at something": only grammar words, nothing of the sentence
    first = real[0] if real else toks[0]
    if first in _PREPS:
        lead = "preposition"            # a frame that starts with its preposition: "until + time", "by + -ing"
    elif first in _DETERMINERS and len(real) > 1:
        lead = "noun"
        first = real[1]
    elif first in _ADJECTIVES or first.endswith(_ADJ_ENDINGS):
        lead = "adjective"
    elif first.endswith(_NOUN_ENDINGS):
        lead = "noun"
    else:
        lead = "verb"
    nxt = {toks[i]: (toks[i + 1] if i + 1 < len(toks) else "") for i in range(len(toks))}
    to_as_prep = "to" in toks and (nxt.get("to") in _PLACEHOLDERS or nxt.get("to") in _DETERMINERS)
    has_prep = any(t in _PREPS for t in toks) or to_as_prep
    verb_pattern = ("-ing" in low or "+ ing" in low or re.search(r"\bto \+|\bto (do|be|verb)\b|\bdoing\b", low)
                    or re.search(r"\b(someone|somebody|sb) (do|to do)\b", low))
    if _is_label(toks):
        return 8
    if has_prep:
        return 2 if lead in ("adjective", "noun", "preposition") else 1
    if verb_pattern:
        return 3
    if len(real) >= 2 and any(t in _PARTICLES for t in real[1:]):
        return 4
    if re.search(r"\b(that|if|whether)\s*$", low) or re.search(r"\b(how|what|why|where|when|who)\s*(\.\.\.|…)", low):
        return 6
    if 2 <= len(real) <= 4:
        return 5
    return 9


CLOZE_CASES = NOTE["cloze_case_names"]
CHECKS = {
    "leak": leak,
    "pattern_in_text": pattern_in_text,
    "pattern_rank": pattern_rank,
    "cloze_cases": CLOZE_CASES,
    "cloze_no_hint": ("verb_prep", "phrasal_verb", "collocation"),   # a one-word preposition or particle: a hint gives it away
    "morphology": morphology_html,
    "register_hint": register_hint,
}
