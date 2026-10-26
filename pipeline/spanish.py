"""Spanish as a learning language: what its cards need beyond the generic set.

Two parts, both read by the tables keyed by the registry (pipeline/languages.py):

    NOTE     the Spanish pieces of the generic prompts (prompts.generic_prompts fills its slots)
    CHECKS   the Spanish checks and card parts (generate.generic_rules takes them over the generic ones)

The Spanish of Spain by default; a Latin American voice gets Latin American Spanish with the words of its
country (the voice decides, like American and British English). No imports from the add-on, so prompts.py and generate.py can both
import this file.
"""
import html
import re
import unicodedata


def _esc(s):
    return html.escape(str(s or ""), quote=False)


def _plain(s):
    """Lower case without accents (canción -> cancion), for comparing forms."""
    s = unicodedata.normalize("NFD", str(s or "").lower())
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")


# ── the prompt pieces ────────────────────────────────────────────────────────────────────────
_LEVELS = {
    "A1": (
        ' # LEVEL A1 (beginner): use ONLY the ~600 most common everyday words. MAXIMUM 6 words per sentence, count them. '
        'ONE simple main clause, exactly ONE action. The present tense only ("ir a + infinitivo" for the future is fine), '
        'with ser, estar, tener, hay, querer and poder. FORBIDDEN at A1: the subjunctive, past tenses, clauses with porque, '
        'cuando, si or que, relative clauses, idioms, slang. '
        'REGISTER AT THIS LEVEL: example_casual uses tú, plain and friendly, never slang; example_formal uses usted, a polite '
        'sentence that makes sense on its own ("¿Puede usted ...?", "por favor"). '
        'VOCABULARY: apart from the target word, EVERY other word in both sentences must be basic beginner vocabulary a learner '
        'meets in the first weeks (family, home, food, shopping, school, work, time, weather, transport, greetings). Never formal '
        'or office words (solicitar, gestionar, efectuar). If the target word itself is harder, keep every other word trivial. '
        'grammar_patterns: look first for a verb, adjective or noun with its preposition, then ser or estar with an adjective, '
        'tener que + infinitivo, me gusta + infinitivo.'
    ),
    "A2": (
        ' # LEVEL A2 (elementary): ~1200 common words. MAXIMUM ~10 words per sentence. At most ONE simple clause with porque, '
        'cuando, si or que (never nested). The pretérito perfecto, the pretérito indefinido and the imperfecto of common verbs, '
        'ir a + infinitivo, reflexive verbs. FORBIDDEN at A2: the subjunctive (except fixed phrases like "que te vaya bien"), '
        'relative clauses beyond "que", idioms, slang. Make it CLEARLY a step above A1: use a clause OR a past tense. '
        'REGISTER AT THIS LEVEL: example_casual uses tú, never slang; example_formal uses usted. '
        'VOCABULARY: apart from the target word, every other word basic A1 or A2 vocabulary, never formal or office words. '
        'grammar_patterns: look first for a verb, adjective or noun with its preposition, then the past of an irregular verb, '
        'a reflexive verb, ir a or tener que + infinitivo.'
    ),
    "B1": (
        ' # LEVEL B1 (intermediate): ~2500 common words. Medium sentences; clauses with porque, aunque, cuando and relative '
        'clauses are fine. The present subjunctive after common triggers (quiero que, es importante que, para que, cuando + '
        'subjuntivo for the future), the conditional (me gustaría, podría), the preterite against the imperfect, por and para. '
        'At most ONE well-known idiom (note its meaning in the explanation). Light register contrast. '
        'grammar_patterns: look first for a verb, adjective or noun with its preposition, then a subjunctive trigger, a '
        'periphrasis (acabar de, volver a, seguir + gerundio), ser or estar, por or para.'
    ),
    "B2": (
        ' # LEVEL B2 (upper-intermediate): wide everyday and common professional words. Longer, more complex sentences, the '
        'imperfect subjunctive, conditional sentences (si tuviera ...), the passive with se, reported speech, a wide range of '
        'verbs with prepositions; common idioms are fine. A clear but MODERATE casual style (no heavy slang). '
        'grammar_patterns: look first for a verb, adjective or noun with its preposition, then a subjunctive trigger, a '
        'conditional sentence, the passive with se, a periphrasis.'
    ),
    "C1": (
        ' # LEVEL C1 (advanced): rich, near-native Spanish across registers. The formal example shows genuine C1 range where it '
        'sounds natural: the subjunctive in its finer uses, the pluperfect subjunctive, a precise formal style, connectors '
        '(no obstante, por consiguiente, a pesar de que); never forced or bookish. Idioms used naturally. Still REAL, '
        'everyday-useful Spanish, NEVER rare words. The casual example may be genuinely colloquial. '
        'grammar_patterns: look first for a verb, adjective or noun with its preposition and idiomatic collocations, then the '
        'subjunctive, conditional sentences, connectors that change the mood.'
    ),
}

_CLOZE_LEVELS = {
    "A1": ('\n\nLEVEL A1: use ONLY case "single_word"; a SHORT present-tense sentence (3 to 7 words) with the most common '
           'words; no idioms, no clause.'),
    "A2": ('\n\nLEVEL A2: prefer case "single_word"; a short sentence (present or a common past tense), common words, at '
           'most one porque, cuando or si clause; no idioms.'),
    "B1": ('\n\nLEVEL B1: use case "single_word", "verb_prep", "ser_estar" or "por_para"; a medium everyday sentence with '
           'common words.'),
}

_CLOZE_CASES = (
    'A. "single_word": one content word. For a noun, cloze the noun WITH its article, so the gender is part of the answer '
    '("la mesa", "el problema"); for a verb, the conjugated form; for an adjective, the form that agrees.\n'
    'B. "verb_prep": a verb, adjective or noun with its fixed preposition at its end. Cloze JUST the preposition '
    '("pensar en" -> answer "en", "depender de" -> "de", "soñar con" -> "con", "harto de" -> "de"). A fixed phrase '
    'with the preposition inside it ("echar de menos", "llevar a cabo") is "long_phrase".\n'
    'C. "ser_estar": the input is ser or estar, or an expression with one of them. Cloze JUST the form of ser or estar '
    '("estar cansado" -> "está", "ser de Madrid" -> "es").\n'
    'D. "por_para": the input is por or para, or a phrase with one of them. Cloze JUST por or para.\n'
    'E. "collocation": a verb + noun pair. Cloze JUST the verb ("tomar una decisión" -> "tomar" or its conjugated form).\n'
    'F. "long_phrase": a phrase of more than 3 words that is not an idiom, or a fixed phrase with a preposition inside '
    'it; cloze the whole phrase, its verb in the form the sentence uses ("echo de menos").\n'
    'G. "idiom": cloze 2 to 3 key content words, comma-separated.'
)


def _variety(voice):
    """The Spanish of Spain or of Latin America follows the voice that reads the card: a Spain voice (es-ES) gets
    the Spanish of Spain, every other Spanish voice Latin American Spanish."""
    return "Spain" if str(voice or "").startswith("es-ES") else "Latin America"


# The Latin American voices Settings offers: the country whose words the cards use, and some of them. The
# country matters for a few everyday words: "chaqueta" is a jacket in most countries and vulgar in Mexico,
# where the jacket is a "chamarra" (the Mexican voice wrote "chaqueta" in a test run). The main call followed
# the system prompt's words for Spain but not for Mexico ("ponerse la chaqueta" again, while the cloze call, which
# gets the country at the end of its user message, wrote "chamarra"), so the main user message ends with the
# country too. The vulgar word itself is never named: naming it invited it.
_COUNTRIES = {
    "es-MX": ("Mexico", "carro, computadora, celular, jugo, manejar, chamarra for a jacket", "carro, computadora, chamarra"),
    "es-US": ("the United States", "carro, computadora, celular, jugo, manejar", "carro, computadora"),
    "es-AR": ("Argentina", "auto, computadora, celular, jugo, manejar, colectivo", "auto, computadora"),
    "es-CO": ("Colombia", "carro, computador, celular, jugo, manejar", "carro, computador"),
}


def _country(voice):
    """(country, its words, a few of them) for a Latin American voice Settings offers, else None (any other
    voice of a Latin American country gets the words used across Latin America)."""
    return _COUNTRIES.get(str(voice or "")[:5])


def _standard(voice):
    if _variety(voice) == "Spain":
        words = ('the Spanish of Spain: vosotros for the casual plural, and the words used in Spain (coche, ordenador, '
                 'móvil, zumo, conducir)')
    elif _country(voice):
        words = ('neutral Latin American Spanish as spoken in %s: ustedes for every plural, never vosotros, and the words '
                 'used there (%s), never a word that is rude or vulgar there' % _country(voice)[:2])
    else:
        words = ('neutral Latin American Spanish: ustedes for every plural, never vosotros, and the words used across '
                 'Latin America (carro, computadora, celular, jugo, manejar)')
    return ('# STANDARD SPANISH (these are CEFR levels A1 to C1, used by learners preparing for official Spanish exams): '
            'write standard Spanish as taught to learners, %s. Every accent and the opening ¿ and ¡ are written. No slang, '
            'no text-speak (q, xq, tb), no swear words, and no English words where Spanish has its own (reunión, not '
            'meeting). (The separate "Native" style is the only place for slang.) ' % words)


def _variety_line(voice):
    if _variety(voice) == "Spain":
        return "\n\nUse the Spanish of Spain (vosotros, coche, ordenador)."
    if _country(voice):
        return "\n\nUse the Latin American Spanish of %s (ustedes, %s), never vosotros." % _country(voice)[::2]
    return "\n\nUse Latin American Spanish (ustedes, carro, computadora), never vosotros."


def _main_variety_line(voice):
    """The country of a Latin American voice once more at the end of the main user message (Spain and a voice
    of no listed country: nothing, their system prompt words are followed)."""
    return " " + _variety_line(voice).strip() if _country(voice) else ""


NOTE = {
    "input_examples": ('Words Spanish has taken from other languages (fútbol, wifi, chat), names, and a Spanish word with '
                       'a small typo or a missing accent COUNT AS SPANISH (fix the typo, add the accent).'),
    "word_rule": ('If the input is a bare noun, add its article, like a dictionary entry: mesa -> la mesa, problema -> el '
                  'problema. Never add an article to a verb, an adjective or a phrase. Phrases and sentences stay as '
                  'they are.'),
    "register_pair": (
        'example_casual is everyday spoken Spanish with tú, the way friends and family talk; example_formal uses usted, with '
        'its verb forms (usted tiene, ¿podría usted ...?), the way you speak to a stranger, an office or a doctor. The verb '
        'form carries the person, so leave out yo and tú as native speakers do ("¿Tienes tiempo?", never "¿Tienes tú '
        'tiempo?"; "Siempre pienso en ti", never "Yo siempre pienso en ti"); usted may stay where it makes the sentence '
        'polite. Casual may use everyday words and formal more formal ones where they fit (conseguir and obtener, empezar '
        'and comenzar). '),
    "self_check": (
        'gender and number agree (la casa blanca, los coches nuevos); ser against estar (es médico, está cansado, está en '
        'casa); por against para; the right preposition after a verb, adjective or noun (pensar en, depender de, soñar con, '
        'harto de); the subjunctive after wishes, doubts, feelings and para que (quiero que vengas), the indicative after '
        'facts (creo que viene); the preterite for a finished event and the imperfect for background or a habit; the '
        'personal "a" before a person as the object (veo a María); the order of object pronouns (te lo doy); every accent '
        '(está, más, también, qué and cómo in questions); questions and exclamations open with ¿ and ¡. '),
    "standard": _standard,
    "levels": _LEVELS,
    "native": (
        ' # NATIVE: real spoken Spanish of people aged 20 to 40 today, in the variety the voice sets: colloquial words, '
        'idioms and slang where it is natural (vale, qué guay, tío in Spain; qué padre, chévere, che across Latin America, '
        'each only where it belongs). Casual can sound like a text message; formal sounds like a competent work email. '
        'Casual is 5 to 12 words, formal 8 to 18. Vary how sentences start. NEVER stack fillers. '),
    "register_examples": ('"casual" = slang or very informal words (curro, guay, flipar, currar). "neutral" = works in both '
                          '(trabajo, comprar, ver). "formal" = official or written words not used in casual speech (no '
                          'obstante, efectuar, solicitar, cursar, por consiguiente). '),
    "ranked": ('a verb + preposition ("pensar en algo", "depender de algo", "soñar con algo", "acordarse de algo"), an '
               'adjective or noun + preposition ("harto de algo", "interesado en algo", "la razón de algo"), a periphrasis '
               'or a verb + infinitive ("tener que + infinitivo", "ir a + infinitivo", "acabar de + infinitivo", "volver a '
               '+ infinitivo"), a subjunctive trigger ("quiero que + subjuntivo", "es importante que + subjuntivo", "esperar '
               'que + subjuntivo"), ser or estar in a fixed phrase ("estar de acuerdo con algo", "ser capaz de + '
               'infinitivo"), por or para frames ("gracias por algo", "por la mañana"), verbs like gustar ("me gusta + '
               'infinitivo", "le duele algo"), reflexive verbs ("darse cuenta de algo", "quedarse con algo"), collocations '
               '("tomar una decisión", "hacer una pregunta"), a verb that opens a clause ("decir que", "preguntar si"), '
               'then level structures (the preterite and the imperfect, the conditional, the passive with se)'),
    "pattern_rule": ('At EVERY level, including A1: a verb, adjective or noun with its fixed preposition in a sentence '
                     '(pensar en, depender de, harto de, la razón de) MUST appear as a pattern.'),
    "pattern_format": ('Write each pattern as a frame a learner can reuse in a new sentence: "algo" where a thing goes, '
                       '"alguien" where a person goes, "+ infinitivo" or "+ subjuntivo" for verb patterns, a reflexive verb '
                       'with its se. GOOD: "pensar en algo", "tener que + infinitivo", "es importante que + subjuntivo", '
                       '"darse cuenta de algo". BAD: "pienso en mi madre" (a piece cut out of the sentence), "comprar '
                       'algo" (a bare object), "en algo" (a preposition alone).'),
    "morphology": (
        'NOUN -> {"pos":"noun","article":"el or la","gender":"m or f","noun":"<singular, without the article>",'
        '"plural":"<plural with its article, e.g. los lápices, las canciones>"}; a feminine noun that takes el in the '
        'singular (el agua) has "article":"el","gender":"f" and "plural":"las aguas"; a noun that does not change in the '
        'plural (la crisis, el lunes) gives the same form ("las crisis"). '
        'VERB -> {"pos":"verb","infinitive":"<infinitive, with se for a reflexive verb>","yo":"<yo form of the present, '
        'with me for a reflexive verb>","preterite":"<él form of the pretérito indefinido, with se for a reflexive verb>",'
        '"participle":"<participio>"}. Anything else -> {"pos":"other"}. Be 100% correct: gender (el problema, la mano, el '
        'día), plurals with their accents (canción, canciones; examen, exámenes; lápiz, lápices), stem-changing verbs (pensar, '
        'pienso; volver, vuelvo; pedir, pido), irregular verbs (tener, tengo, tuvo, tenido; hacer, hago, hizo, hecho; ir, '
        'voy, fue, ido) and irregular participles (abierto, escrito, visto, vuelto, roto). NEVER a regularized form '
        '(tení, hací, abrido, ponido).'),
    "tags": ("Cotidiano", "Trabajo", "Casa", "Transporte", "Dinero", "Salud", "Comida", "Cocina", "Ropa", "Compras",
             "Tecnología", "Sentimientos", "Educación", "Deporte", "Viajes", "Coche", "Tiempo", "Cualidades",
             "Comunicación", "Relaciones"),
    "tags_native": ("Cotidiano", "Trabajo", "Modismo", "Casa", "Transporte", "Dinero", "Salud", "Comida", "Cocina", "Ropa",
                    "Compras", "Tecnología", "Sentimientos", "Gramática", "Educación", "Deporte", "Viajes", "Coche",
                    "Tiempo", "Cualidades", "Jerga", "Comunicación", "Relaciones", "Formal"),
    "explanation": ('1 short, simple Spanish sentence that explains the word, like a learner\'s dictionary, in words easier '
                    'than the word itself, e.g. for comprar the explanation is "Dar dinero para tener algo." (at A1 and A2 only '
                    'the most common words; never a translation, never the word explained by itself, never starting '
                    'with the word and a colon)'),
    "cloze_cases": _CLOZE_CASES,
    "cloze_case_names": ("single_word", "verb_prep", "ser_estar", "por_para", "collocation", "long_phrase", "idiom"),
    "cloze_levels": _CLOZE_LEVELS,
    "contexts": {
        "Default": ('CONTEXT: Important everyday Spanish. Formal: office, appointment or email scenario (usted). Casual: '
                    'chat with friends or family (tú, messaging tone). Prefer situations people meet every week: work, '
                    'shopping, health, travel, home.'),
    },
    "variety_line": _variety_line,
    "main_variety_line": _main_variety_line,
    "arabic_address": (' Usted speaks to ONE person: translate it with the Arabic singular (يمكنك، لديك، تقريرك), never '
                       'with the plural (يمكنكم، لديكم، تقريركم), even in the most polite sentence.'),
}


# ── the checks and card parts ────────────────────────────────────────────────────────────────
# Irregular and stem-changing verbs: infinitive -> (yo present, él preterite, participle) as the card shows them.
# Used to RESCUE a real pattern whose verb appears in an irregular form ("tuvo" for tener) and to repair a
# regularized form on the word line ("tení"); a verb missing here costs a pattern at most, never a card.
IRREGULAR = {
    "ser": ("soy", "fue", "sido"), "estar": ("estoy", "estuvo", "estado"), "ir": ("voy", "fue", "ido"),
    "tener": ("tengo", "tuvo", "tenido"), "hacer": ("hago", "hizo", "hecho"), "decir": ("digo", "dijo", "dicho"),
    "poder": ("puedo", "pudo", "podido"), "querer": ("quiero", "quiso", "querido"), "venir": ("vengo", "vino", "venido"),
    "poner": ("pongo", "puso", "puesto"), "saber": ("sé", "supo", "sabido"), "salir": ("salgo", "salió", "salido"),
    "ver": ("veo", "vio", "visto"), "dar": ("doy", "dio", "dado"), "haber": ("he", "hubo", "habido"),
    "traer": ("traigo", "trajo", "traído"), "conducir": ("conduzco", "condujo", "conducido"),
    "traducir": ("traduzco", "tradujo", "traducido"), "producir": ("produzco", "produjo", "producido"),
    "conocer": ("conozco", "conoció", "conocido"), "parecer": ("parezco", "pareció", "parecido"),
    "ofrecer": ("ofrezco", "ofreció", "ofrecido"), "nacer": ("nazco", "nació", "nacido"), "crecer": ("crezco", "creció", "crecido"),
    "agradecer": ("agradezco", "agradeció", "agradecido"), "aparecer": ("aparezco", "apareció", "aparecido"),
    "oír": ("oigo", "oyó", "oído"), "caer": ("caigo", "cayó", "caído"), "leer": ("leo", "leyó", "leído"),
    "creer": ("creo", "creyó", "creído"), "construir": ("construyo", "construyó", "construido"),
    "incluir": ("incluyo", "incluyó", "incluido"), "destruir": ("destruyo", "destruyó", "destruido"),
    "huir": ("huyo", "huyó", "huido"), "seguir": ("sigo", "siguió", "seguido"), "conseguir": ("consigo", "consiguió", "conseguido"),
    "pedir": ("pido", "pidió", "pedido"), "servir": ("sirvo", "sirvió", "servido"), "repetir": ("repito", "repitió", "repetido"),
    "elegir": ("elijo", "eligió", "elegido"), "corregir": ("corrijo", "corrigió", "corregido"),
    "vestirse": ("me visto", "se vistió", "vestido"), "reír": ("río", "rio", "reído"),
    "dormir": ("duermo", "durmió", "dormido"), "morir": ("muero", "murió", "muerto"), "sentir": ("siento", "sintió", "sentido"),
    "preferir": ("prefiero", "prefirió", "preferido"), "pensar": ("pienso", "pensó", "pensado"),
    "empezar": ("empiezo", "empezó", "empezado"), "entender": ("entiendo", "entendió", "entendido"),
    "perder": ("pierdo", "perdió", "perdido"), "despertarse": ("me despierto", "se despertó", "despertado"),
    "sentarse": ("me siento", "se sentó", "sentado"), "volver": ("vuelvo", "volvió", "vuelto"),
    "devolver": ("devuelvo", "devolvió", "devuelto"), "resolver": ("resuelvo", "resolvió", "resuelto"),
    "mover": ("muevo", "movió", "movido"), "jugar": ("juego", "jugó", "jugado"), "encontrar": ("encuentro", "encontró", "encontrado"),
    "contar": ("cuento", "contó", "contado"), "recordar": ("recuerdo", "recordó", "recordado"),
    "acordarse": ("me acuerdo", "se acordó", "acordado"), "probar": ("pruebo", "probó", "probado"),
    "costar": ("cuesto", "costó", "costado"), "oler": ("huelo", "olió", "olido"), "adquirir": ("adquiero", "adquirió", "adquirido"),
    "abrir": ("abro", "abrió", "abierto"), "escribir": ("escribo", "escribió", "escrito"), "romper": ("rompo", "rompió", "roto"),
    "cubrir": ("cubro", "cubrió", "cubierto"), "descubrir": ("descubro", "descubrió", "descubierto"),
    "andar": ("ando", "anduvo", "andado"), "caber": ("quepo", "cupo", "cabido"), "valer": ("valgo", "valió", "valido"),
    "mantener": ("mantengo", "mantuvo", "mantenido"), "obtener": ("obtengo", "obtuvo", "obtenido"),
    "contener": ("contengo", "contuvo", "contenido"), "proponer": ("propongo", "propuso", "propuesto"),
    "suponer": ("supongo", "supuso", "supuesto"), "dirigir": ("dirijo", "dirigió", "dirigido"),
    "coger": ("cojo", "cogió", "cogido"), "escoger": ("escojo", "escogió", "escogido"), "recoger": ("recojo", "recogió", "recogido"),
}
# Forms that are just as right (older accents): accepted, never "repaired".
_ALSO = {"reír": ("rió",), "freír": ("frió", "frio")}
# Stems of irregular forms (yo, preterite, future, imperfect) that anchor a pattern naming the infinitive, past the
# ones a form in IRREGULAR already gives. Three letters or more, so a stem never matches half the dictionary.
_STEMS = {
    "ser": ("soy", "eres", "es", "somos", "sois", "son", "era", "fu", "sea", "sere"),
    "ir": ("voy", "vas", "va", "vamos", "vais", "van", "iba", "fu", "vay", "ire"),
    "tener": ("teng", "tien", "tuv", "tendr"), "hacer": ("hag", "hic", "hiz", "har"), "decir": ("dig", "dic", "dij", "dir"),
    "poder": ("pued", "pud", "podr"), "querer": ("quier", "quis", "querr"), "venir": ("veng", "vien", "vin", "vendr"),
    "poner": ("pong", "pus", "pondr"), "saber": ("sé", "sep", "sup", "sabr"), "salir": ("salg", "saldr"),
    "dar": ("doy", "das", "da", "dan", "dio", "di", "dimos", "diste", "dieron", "dé"), "haber": ("he", "has", "ha", "hay", "hemos", "han", "hub", "habr", "hay"),
    "estar": ("estoy", "estuv"), "ver": ("veo", "ves", "ve", "vemos", "ven", "vi", "vio", "vist", "veía"),
    "caber": ("quep", "cup", "cabr"), "andar": ("anduv",), "traer": ("traig", "traj"),
    "oír": ("oig", "oyes", "oye", "oyen", "oimos", "ois", "oyendo", "oyeron", "oia", "oian"),
    "caer": ("caig", "cay"), "valer": ("valg", "valdr"),
}
_SEP = re.compile(r"\s*,\s*")
# The tables' keys without accents, as the matching sees them (oir -> oír).
_PLAIN_KEYS = {_plain(k): k for k in list(IRREGULAR) + list(_ALSO)}
_PARTICIPLES = {_plain(v[2].split()[-1]) for v in IRREGULAR.values()}
_STEMS_PLAIN = {_plain(k): v for k, v in _STEMS.items()}


def _forms(inf):
    """Every form the table lists for an infinitive, accents dropped (me acuerdo -> acuerdo); oir finds oír."""
    forms = set()
    inf = inf if inf in IRREGULAR else _PLAIN_KEYS.get(_plain(inf), inf)
    for f in IRREGULAR.get(inf, ()) + _ALSO.get(inf, ()):
        for part in _SEP.split(f):
            words = part.split()
            if words:
                forms.add(_plain(words[-1]))
    return forms


def _base(inf):
    """The infinitive without its reflexive se (acordarse -> acordar, irse -> ir)."""
    inf = _plain(inf)
    if inf.endswith("se") and inf[:-2].endswith(("ar", "er", "ir")):
        return inf[:-2]
    return inf


def _regular(inf):
    """The regular yo, él preterite and participle of an infinitive, accents dropped."""
    b = _base(inf)
    stem, end = b[:-2], b[-2:]
    if end == "ar":
        return stem + "o", stem + "o", stem + "ado"
    if end in ("er", "ir"):
        return stem + "o", stem + "io", stem + "ido"
    return "", "", ""


def _last(form):
    words = str(form or "").split()
    return _plain(words[-1]) if words else ""


def morphology_html(m, level=None):
    """The word line, only where Spanish has something to learn: a noun's article in its gender's colour (the
    German classes: blue el, red la), with the plural when it is not simply -s or -es (las canciones, los
    lápices, las crisis, las aguas); an irregular or stem-changing verb as "tener · yo tengo · él tuvo ·
    tenido". A regular verb shows nothing. A regularized form ("tení") is replaced from IRREGULAR."""
    if not isinstance(m, dict):
        return ""
    pos = m.get("pos")
    if pos == "noun":
        art = str(m.get("article") or "").strip().lower()
        if art not in ("el", "la"):
            return ""
        gender = str(m.get("gender") or "").strip().lower()[:1]
        gender = gender if gender in ("m", "f") else ("m" if art == "el" else "f")
        bits = ['<span class="%s">%s</span>' % ("g-der" if gender == "m" else "g-die", art)]
        noun = str(m.get("noun") or "").strip()
        plural = str(m.get("plural") or "").strip()
        p_words = plural.split()
        if noun and len(p_words) >= 2:
            p_art, p_noun = p_words[0].lower(), " ".join(p_words[1:])
            expected = "los" if gender == "m" else "las"
            n, p = noun.lower(), p_noun.lower()
            if n.endswith("z") and p == n + "es":          # z becomes c before e: los lápices, never lápizes
                p_noun, p = p_noun[:-3] + "ces", p[:-3] + "ces"
                plural = "%s %s" % (p_words[0], p_noun)
            regular = (p == n + "s" and n[-1:] in "aeiouáéó") or (p == n + "es" and n[-1:] not in "aeiouáéíóú")
            if p_art != expected or not regular or (art == "el" and gender == "f"):   # el agua, las aguas
                bits.append("Pl. " + _esc(plural))
        return '<div class="morph">%s</div>' % " · ".join(bits)
    if pos == "verb":
        inf = str(m.get("infinitive") or "").strip()
        yo, pret, part = (str(m.get(k) or "").strip() for k in ("yo", "preterite", "participle"))
        key = _plain(inf).replace(" ", "")
        if not (inf and yo and pret and part):
            return ""
        table = next((k for k in IRREGULAR if _plain(k) == key), None)
        if table:
            ok = _forms(table)
            if _last(yo) not in ok or _last(pret) not in ok or _last(part) not in ok:   # the table decides
                yo, pret, part = IRREGULAR[table]
        reg = _regular(inf)
        if not reg[0] or (_last(yo), _last(pret), _last(part)) == reg:
            return ""
        yo_show = yo if yo.lower().startswith(("me ", "yo ")) else "yo " + yo
        pret_show = pret if pret.lower().startswith(("se ", "él ")) else "él " + pret
        return '<div class="morph">%s</div>' % " · ".join(_esc(x) for x in (inf, yo_show, pret_show, part))
    return ""


def register_hint(word_display, alternatives):
    if not alternatives:
        return ""
    return ('<div class="register-hint"><span class="formal-mark">«%s» (Formal)</span> '
            '<span class="arrow">→</span> <span class="casual-alt">En el día a día:</span> '
            '<span class="alt-list">%s</span></div>' % (_esc(word_display), " · ".join(_esc(a) for a in alternatives)))


# Words of the other Latin-script translation languages that are NEVER Spanish words. Conservative on
# purpose (no "con", "les", "ve", "has", "a", "no"): a hit costs a strict retry.
_LEAK_WORDS = {
    "the", "and", "with", "you", "your", "this", "that", "is", "are", "was", "were", "have", "of", "to", "it", "for",
    "from", "they", "what", "my", "am", "be", "not", "very", "but", "we", "she", "his", "her", "in", "on", "at", "an",
    "will", "would", "there", "their", "them",
    "und", "nicht", "ich", "ist", "sind", "eine", "einen", "einem", "einer", "für", "sehr", "auch", "aber", "oder",
    "wir", "haben", "zum", "zur", "schon", "noch", "heute", "bitte", "danke",
    "avec", "très", "mais", "nous", "vous", "sont", "être", "une", "pour", "dans", "je", "suis", "est", "il", "elle",
    "et", "oui", "merci", "aussi", "beaucoup", "toujours", "chez", "qui", "cette", "votre", "leur",
    "não", "você", "muito", "uma", "obrigado", "obrigada", "também", "isso", "isto", "estou", "tenho", "ela",
    "gli", "sono", "perché", "molto", "anche", "della", "non", "questo", "questa", "grazie", "siamo",
    "bir", "çok", "değil", "için", "ile", "gibi", "daha", "een", "niet", "ook", "maar", "het", "ik", "zijn", "dat",
    "wat", "met", "voor", "heb", "hebben", "nie", "jest", "się", "że", "jak", "dla", "czy", "bardzo", "och", "jag",
    "är", "inte", "det", "som", "yang", "tidak", "ini", "itu", "dengan", "untuk", "și", "sunt", "pentru", "foarte",
    "nem", "hogy", "egy", "nagyon", "và", "không", "là",
}
# Never on the list, because Spanish has them too: a, de, en, me, he, has, le, no, con, ve, van, dan, este, mas, ale,
# che, des, saya, and short names or abbreviations (Ben, EU, .com).


def leak(*texts):
    """The first sign that the translation language leaked into the Spanish fields: a letter of another script
    (Arabic, Cyrillic, Chinese, ...) or a function word of another Latin-script language."""
    for t in texts:
        t = t or ""
        for ch in t:
            if ch.isalpha() and ord(ch) > 0x24F:          # beyond Latin Extended (ñ, á, ü are inside it)
                return ch
        for tok in re.findall(r"[^\W\d_]+", t.lower()):
            if tok in _LEAK_WORDS:
                return tok
    return None


_PLACEHOLDERS = {"algo", "alguien", "alguno", "alguna"}
_PREPS = {"a", "al", "ante", "bajo", "con", "contra", "de", "del", "desde", "durante", "en", "entre", "hacia", "hasta",
          "mediante", "para", "por", "según", "segun", "sin", "sobre", "tras"}
_ARTICLES = {"el", "la", "los", "las", "un", "una", "unos", "unas", "lo"}
_PRONOUNS = {"me", "te", "se", "nos", "os", "le", "les", "yo", "tú", "tu", "él", "ella", "usted", "ustedes"}
_LABELS = {"infinitivo", "subjuntivo", "indicativo", "gerundio", "participio", "sustantivo", "verbo", "adjetivo",
           "adverbio", "lugar", "tiempo", "persona", "cosa"}
_META_STRONG = {"subjuntivo", "indicativo", "imperativo", "condicional", "pretérito", "preterito", "imperfecto",
                "pluscuamperfecto", "pasiva", "gerundio", "participio", "infinitivo", "perífrasis", "perifrasis"}
_META_WEAK = {"presente", "pasado", "futuro", "perfecto", "simple", "compuesto", "indefinido", "estilo", "indirecto",
              "oración", "oracion", "relativa", "condicional", "forma"}
_META = _META_STRONG | _META_WEAK


def _is_label(words):
    return any(w in _META_STRONG for w in words) or sum(w in _META_WEAK for w in words) >= 2


def _stem_variants(stem):
    """The stems a conjugated form may start with: the stem itself, its stem changes (pens -> piens, volv ->
    vuelv, ped -> pid, dorm -> durm, jug -> jueg) and its spelling changes before e (busc -> busqu, lleg ->
    llegu, empez -> empec, cog -> coj, conoc -> conozc, segu -> sig)."""
    out = {stem}
    for i in range(len(stem) - 1, -1, -1):        # the last e, o or u of the stem changes (oler -> huel)
        ch = stem[i]
        if ch == "u" and i > 0 and stem[i - 1] in "gq":
            continue                                # the silent u of gu and qu (segu -> sig, not segue)
        if ch in "eou":
            head, tail = stem[:i], stem[i + 1:]
            if ch == "e":
                out |= {head + "ie" + tail, head + "i" + tail}
            elif ch == "o":
                out |= {head + "ue" + tail, head + "u" + tail, head + "hue" + tail}
            elif ch == "u":
                out |= {head + "ue" + tail}
            break
    for a, b in (("c", "qu"), ("g", "gu"), ("z", "c"), ("g", "j"), ("c", "zc"), ("gu", "g")):
        for s in list(out):
            if s.endswith(a):
                out.add(s[:-len(a)] + b)
    return {s for s in out if len(s) >= 2}


# ser and estar by their whole forms, with accents: a stem would take estudiar for estar, and without its accent
# "está" is the "esta" of "esta casa".
_ESTAR_FORMS = {"estar", "estoy", "estás", "está", "estamos", "estáis", "están", "estaba", "estabas", "estábamos",
                "estaban", "estuve", "estuviste", "estuvo", "estuvimos", "estuvieron", "esté", "estés", "estén",
                "estemos", "estuviera", "estuvieran", "estaré", "estará", "estarán", "estaría", "estarían", "estado",
                "estando"}
_SER_WORD_FORMS = {"ser", "soy", "eres", "es", "somos", "sois", "son", "era", "eras", "éramos", "eran", "fui",
                   "fuiste", "fue", "fuimos", "fueron", "sea", "seas", "sean", "seamos", "sería", "serían", "será",
                   "serán", "seré", "sido", "siendo"}
# Forms that lose their only difference with the accent: sé and se, dé and de, té and te. They never count.
_ACCENT_TWINS = {"se", "de", "te", "si", "el", "tu", "mi", "mas", "aun", "solo"}


def _word_matches(w, tokens, raw=None):
    """A pattern word is in the sentences: as is, as another form of the same noun or adjective (harto, harta,
    hartos), or as a form of the verb it names (pensar -> pienso, tuvimos for tener, me acuerdo for acordarse).
    tokens are the sentences' words without accents, raw the same words with them (for ser and estar)."""
    w = _plain(w)
    if w in tokens:
        return True
    base = _base(w)
    if base in _SERESTAR:
        forms = _ESTAR_FORMS if base == "estar" else _SER_WORD_FORMS
        if raw is not None:
            return bool(set(raw) & forms)
        return bool(set(tokens) & ({_plain(f) for f in forms} - {"esta", "estas", "seria"}))
    if base[-2:] in ("ar", "er", "ir") and (len(base) >= 3 or base in _STEMS_PLAIN or base in _PLAIN_KEYS):
        stems = _stem_variants(base[:-2])
        forms = (_forms(base) | _forms(w)) - _ACCENT_TWINS
        extra = {_plain(x) for x in _STEMS_PLAIN.get(base, ())} - _ACCENT_TWINS
        for t in tokens:
            if t in forms or t in extra:
                return True
            if any(t.startswith(s) and len(s) >= 3 for s in stems | {x for x in extra if len(x) >= 3}):
                return True
            if len(base) - 2 <= 2 and any(t.startswith(s) and len(t) <= len(s) + 4 for s in stems):
                return True                         # a short stem (ver, dar, leer): only short forms
        return False
    stem = w[:-1] if w[-1:] in "aeos" and len(w) > 4 else w
    return any(t.startswith(stem) and len(t) - len(stem) <= 3 for t in tokens)


def pattern_in_text(pattern, text_lower):
    """True when a pattern is really exemplified by the sentences: one of its content words is a word of the
    sentences, as is, in another form of a noun or adjective, or in a conjugated form of the verb it names
    (stem changes, spelling changes and the irregular verbs included). Whole words only. A pattern made only of
    short or grammar words ("por la mañana" aside) needs every word it names."""
    raw = set(re.findall(r"[^\W\d_]+", text_lower.lower()))
    frame = _FRAME.match(_plain(pattern).strip(" ¿¡?!.,"))
    if frame:
        return _frame_in_text(frame.group("verb"), frame.group("link"), frame.group("kind"), text_lower)
    words = re.findall(r"[^\W\d_]+", _plain(pattern))
    label = _is_label(words)
    never = _PLACEHOLDERS | {_plain(p) for p in _PREPS} | _ARTICLES | {_plain(p) for p in _PRONOUNS} | _LABELS | {"que", "si"}
    content = [w for w in words if len(w) >= 3 and w not in never and not (label and w in {_plain(m) for m in _META})]
    tokens = set(re.findall(r"[^\W\d_]+", _plain(text_lower)))
    if not content:
        anchors = [w for w in words if w not in _PLACEHOLDERS and w not in _LABELS and w not in {_plain(m) for m in _META}]
        verbs = set(_STEMS_PLAIN) | set(_PLAIN_KEYS)
        return bool(anchors) and all(w in tokens or (w in verbs and _word_matches(w, tokens, raw)) for w in anchors)
    return any(_word_matches(w, tokens, raw) for w in content)


# A frame of a verb (or another word) and its infinitive, gerund or participle: "tener que + infinitivo", "ir a +
# infinitivo", "me gusta + infinitivo", "seguir + gerundio", "haber + participio", "capaz de + infinitivo". The model
# offers such frames from the prompt's own examples, and the verb alone is often in the sentence for another reason
# ("la cita que tiene" is not "tener que"), so the frame must be there in order: a form of the word, its linking
# word right after it (a subject pronoun may stand between), and the infinitive within the next three words.
_FRAME = re.compile(r"(?:(?:me|te|se|le|nos|os|les)\s+)?(?P<verb>[^\W\d_]+)(?:\s+(?:usted|ustedes|tu|yo))?"
                    r"(?:\s+(?P<link>que|a|al|de|en|por|con|para))?\s*\+\s*(?P<kind>infinitivo|gerundio|participio)\s*$")
_CLITIC_END = re.compile(r"(?:me|te|se|lo|la|le|nos|os|los|las|les){1,2}$")


def _is_form(kind, tok):
    """tok (no accents) is an infinitive, a gerund or a participle, a clitic or two allowed at the end (hacerlo)."""
    bare = _CLITIC_END.sub("", tok) if kind != "participio" else tok
    bare = bare if len(bare) >= 2 else tok
    if kind == "infinitivo":
        return bare.endswith(("ar", "er", "ir")) and (len(bare) >= 3 or bare == "ir")
    if kind == "gerundio":
        return bare.endswith(("ando", "iendo", "yendo"))
    return tok.endswith(("ado", "ada", "ados", "adas", "ido", "ida", "idos", "idas")) or tok in _PARTICIPLES


def _frame_in_text(verb, link, kind, text_lower):
    raw = re.findall(r"[^\W\d_]+", text_lower.lower())
    toks = [_plain(t) for t in raw]
    for i, t in enumerate(toks):
        if not _word_matches(verb, {t}, {raw[i]}):
            continue
        j = i + 1
        if j < len(toks) and toks[j] in ("usted", "ustedes", "tu", "yo"):
            j += 1
        if link:
            if j >= len(toks) or toks[j] != link:
                continue
            j += 1
        if any(_is_form(kind, x) for x in toks[j:j + 3]):
            return True
    return False


_ADJ_ENDINGS = ("ado", "ada", "ido", "ida", "oso", "osa", "ble", "ivo", "iva", "ante", "ente")
_NOUN_ENDINGS = ("ción", "cion", "sión", "sion", "dad", "tad", "miento", "ncia", "eza", "ura", "aje", "umbre")
_ADJECTIVES = {"harto", "harta", "capaz", "seguro", "segura", "contento", "contenta", "orgulloso", "orgullosa", "listo",
               "lista", "lleno", "llena", "rico", "rica", "fácil", "difícil", "cansado", "cansada", "feliz", "triste",
               "preocupado", "preocupada", "enamorado", "enamorada", "acostumbrado", "acostumbrada", "consciente"}
_SERESTAR = {"ser", "estar"}
# Words that open a noun phrase like an article ("este fin de semana", "mi casa"); matched with accents.
_DETERMINERS = {"este", "esta", "estos", "estas", "ese", "esa", "esos", "esas", "aquel", "aquella", "mi", "mis", "tu",
                "tus", "su", "sus", "nuestro", "nuestra", "cada", "otro", "otra"}
# Adverbs that make a preposition with de or a (después de, junto a), written without accents like the tokens.
_PREP_ADVERBS = {"antes", "despues", "cerca", "lejos", "delante", "detras", "encima", "debajo", "dentro", "fuera",
                 "ademas", "alrededor", "enfrente", "junto", "acerca"}
_GUSTAR = {"gustar", "encantar", "doler", "importar", "interesar", "molestar", "parecer", "faltar", "quedar"}


# Whole forms only: a prefix would take estudiar or establecer for estar. Not "este", which starts a pattern as
# "this" ("este fin de semana") far more often than as the subjunctive of estar.
_SER_ESTAR_FORMS = {"es", "son", "soy", "eres", "somos", "era", "eras", "eramos", "eran", "fue", "fui", "fuiste",
                    "fuimos", "fueron", "sea", "seas", "sean", "seria", "serian", "sera", "seran", "sido", "siendo",
                    "esta", "estan", "estoy", "estas", "estamos", "estaba", "estabas", "estaban", "estuve", "estuvo",
                    "estuvieron", "esten", "estaria", "estara", "estado", "estando"}


def _verb_of(token):
    """ser, estar or a verb like gustar when the token is one of their forms (es, está, gusta, duele), else ""."""
    if token in _SERESTAR or token in _SER_ESTAR_FORMS:
        return "estar" if token.startswith("est") else "ser"
    for base in _GUSTAR:
        if token == base or any(token.startswith(st) for st in _stem_variants(base[:-2]) if len(st) >= 3):
            return base
    return ""


def pattern_rank(pat):
    """Where a Spanish pattern sits in the value order (1 = first), used to order the patterns and keep the best
    three: 1 verb + preposition, 2 adjective or noun + preposition (or a frame that starts with its preposition),
    3 a periphrasis, verb + infinitive or a subjunctive trigger, 4 ser or estar in a fixed phrase and verbs like
    gustar, 5 reflexive verbs and collocations, 6 a verb that opens a clause, 8 a named structure, 9 anything
    else. A first version: refine it from real cards, like the German one was. A bare object ("comprar algo") and
    a pattern of grammar words only ("+ infinitivo", "en algo") are dropped."""
    low = _plain(pat)
    toks = re.findall(r"[^\W\d_]+", low)
    if not toks:
        return None
    raw = re.findall(r"[^\W\d_]+", pat.lower())      # with accents: "esta noche" is not "está"
    preps = {_plain(p) for p in _PREPS}
    real = [t for t in toks if t not in _PLACEHOLDERS]
    if len(toks) == 2 and toks[1] in _PLACEHOLDERS | {"sustantivo", "nombre"}:
        return None                     # "comprar algo", "tener + sustantivo": a bare object teaches nothing
    grammar = preps | _ARTICLES | {_plain(p) for p in _PRONOUNS} | _LABELS | {"que", "si"}
    meta = {_plain(m) for m in _META}
    content = [t for t in real if t not in grammar and t not in meta]
    if not content:
        return 8 if _is_label(toks) else None   # "pretérito indefinido" names a structure; "en algo" teaches nothing
    if pat.count("+") >= 3:
        return 9                        # "llevar + sustantivo + por si acaso + verbo": the sentence's skeleton
    first = next((t for t in real if t not in _ARTICLES and t not in {"me", "te", "le", "nos", "os", "les", "se"}), real[0])
    if first in preps or (first in _PREP_ADVERBS and any(t in preps for t in toks[1:])):
        lead = "preposition"            # "después de algo", "antes de + infinitivo": a preposition of two words
    elif first in {_plain(a) for a in _ADJECTIVES} or first.endswith(_ADJ_ENDINGS):
        lead = "adjective"
    elif first.endswith(tuple(_plain(e) for e in _NOUN_ENDINGS)) or toks[0] in _ARTICLES or raw[0] in _DETERMINERS:
        lead = "noun"
    else:
        lead = "verb"
    if "subjuntivo" in toks and "que" in toks:
        return 3                        # a subjunctive trigger, also with ser: "es importante que + subjuntivo"
    special = _verb_of(first) if lead == "verb" else ""
    if special in _SERESTAR:
        if "gerundio" in toks or "participio" in toks:
            return 3                    # "estar + gerundio", "ser + participio": a periphrasis
        rest = toks[toks.index(first) + 1:]
        if rest[:1] and rest[0] in preps:
            rest = rest[1:]             # "estar de acuerdo": that preposition belongs to the phrase
        if any(t in preps for t in rest[1:]):
            return 2                    # "estar cansado de + infinitivo": the adjective or noun with its preposition
    if special:
        return 4
    if "subjuntivo" in toks or "infinitivo" in toks or "gerundio" in toks or "participio" in toks or re.search(
            r"\b(tener que|ir a|acabar de|volver a|dejar de|empezar a|ponerse a)\b", low):
        if lead == "verb" or "que" in toks:
            return 3
    if any(t in preps for t in toks[1:]):
        return 2 if lead in ("adjective", "noun", "preposition") else 1
    if lead == "preposition":
        return 2
    if re.search(r"\b(que|si)\s*$", re.sub(r"(\s*\+\s*[^\W\d_]+)+\s*$", "", low)):
        return 6                        # "decir que", "informar que + cláusula"
    if first.endswith("se") and _base(first) != first:
        return 5
    if 2 <= len(real) <= 4:
        return 5
    return 9


_NOUN_ARTICLES = ("el", "la", "los", "las", "un", "una", "unos", "unas")


def headword(word, m):
    """The word on the card: a bare noun with its article, like a dictionary entry ("mesa" becomes "la mesa"). The
    prompt asks for it and the model often keeps the input as typed, so the word line's article is put in front, with
    the word line's spelling of the noun (its accents)."""
    w = (word or "").strip()
    if not isinstance(m, dict) or m.get("pos") != "noun" or not w or " " in w:
        return word
    art = str(m.get("article") or "").strip().lower()
    noun = str(m.get("noun") or "").strip()
    if art in ("el", "la", "los", "las") and noun and " " not in noun and _plain(noun) == _plain(w):
        return "%s %s" % (art, noun)
    return word


def cloze_article(sentence, answer, card_case, user_input):
    """A noun's blank takes its article, so the gender is part of the answer: "mesa" right after "la" in the
    sentence becomes "la mesa". Only for a one-word answer right after an article, and only when the typed word
    is a noun with its article (la mesa) or that very word typed bare (mesa: the card adds the article)."""
    if card_case != "single_word" or not answer:
        return answer
    parts = answer.split()
    if len(parts) != 1 or parts[0].lower() in _NOUN_ARTICLES:
        return answer
    typed = (user_input or "").strip().split()
    noun_typed = bool(typed) and typed[0].lower() in ("el", "la", "los", "las")
    if not (noun_typed or (len(typed) == 1 and typed[0].lower() == answer.lower())):
        return answer
    m = re.search(r"(?:^|\s)(\S+)\s+" + re.escape(answer) + r"\b", sentence)
    if not m:
        return answer
    preceding = m.group(1).strip('¿¡,.!?;:"«»“”')
    return ("%s %s" % (preceding, answer)) if preceding.lower() in _NOUN_ARTICLES else answer


CLOZE_CASES = NOTE["cloze_case_names"]
# A word that is vulgar in one country, with that country's own word (both feminine, so the articles and the
# adjectives around it still agree). The Mexican voice's prompt names Mexico twice, yet a live card still
# wrote "¿Podría usted ponerse la chaqueta ...?" in its formal sentence: the code makes sure.
_COUNTRY_SWAPS = {"es-MX": {"chaqueta": "chamarra", "chaquetas": "chamarras"}}


def country_words(text, voice, word=""):
    """The Spanish text with the country's own word where the general one is vulgar there ("chaqueta" becomes
    "chamarra" for a Mexican voice). A card that teaches the word itself keeps it."""
    swaps = _COUNTRY_SWAPS.get(str(voice or "")[:5])
    if not swaps or not text:
        return text
    typed = _plain(word)
    swaps = {k: v for k, v in swaps.items() if k not in typed}
    if not swaps:
        return text

    def swap(m):
        new = swaps[m.group(0).lower()]
        return new[0].upper() + new[1:] if m.group(0)[0].isupper() else new
    return re.sub(r"(?<!\w)(%s)(?!\w)" % "|".join(sorted(swaps, key=len, reverse=True)), swap, text, flags=re.IGNORECASE)


CHECKS = {
    "leak": leak,
    "pattern_in_text": pattern_in_text,
    "pattern_rank": pattern_rank,
    "cloze_cases": CLOZE_CASES,
    "cloze_no_hint": ("verb_prep", "ser_estar", "por_para", "collocation"),   # one short word: a hint gives it away
    "cloze_article": cloze_article,
    "headword": headword,
    "placeholders": ("algo", "alguien", "alguno", "alguna"),           # "tomar el pelo a alguien" adds to the headword
    "morphology": morphology_html,
    "register_hint": register_hint,
    "country_words": country_words,
}
