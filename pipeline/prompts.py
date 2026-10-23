"""System prompts for card generation.

The "Arabic" call is generalized: SYSTEM_ARABIC is used when the configured secondary
translation language is Arabic; any other language uses a generic translation prompt.
"""
import functools

from . import english, languages

_RANKED = ('verb+preposition+case ("warten auf (+Akk)"), noun/adjective+preposition+case ("Angst vor (+Dat)"), a verb with a case you cannot guess ("helfen (+Dat)", "jemandem etwas geben (+Dat, +Akk)"), noun+verb collocations ("eine Entscheidung treffen"), a verb that opens a clause ("mitteilen, dass"), zu-infinitive frames ("um ... zu"), reflexive/separable verbs, then level structures (Perfekt, Konjunktiv, Passiv, weak nouns)')

SYSTEM_MAIN = (
    'You create German Anki flashcards. Return ONLY valid JSON: '
    '{'
    '"emoji":"one emoji",'
    '"word":"<EXACT user input — copy from the user message, NEVER copy this placeholder>",'
    '"translation_en":"<English meaning — generate fresh, do NOT copy this placeholder>",'
    '"register":"neutral",'
    '"casual_alternatives":[],'
    '"casual_alternatives_en":[],'
    '"example_formal":"Formal German sentence.",'
    '"example_casual":"Casual German sentence.",'
    '"example_formal_en":"Natural English formal.",'
    '"example_casual_en":"Natural English casual.",'
    '"explanation_de":"1 sentence German explanation.",'
    '"tags":["Alltag"],'
    '"imageKeyword":"english search term for image",'
    '"emoji_formal":"context emoji for formal sentence",'
    '"emoji_casual":"context emoji for casual sentence",'
    '"grammar_patterns":["<pattern from YOUR example sentences>","<another>"],'
    '"grammar_patterns_en":["<pattern from YOUR English sentences>","<another>"],'
    '"morphology":{},'
    '"input_is_german":true,'
    '"input_suggestion":""'
    '} '
    '# INPUT CHECK: set input_is_german to false when the input is NOT a German word or phrase: another language, random letters, '
    'or Arabic/other speech written in Latin letters ("blorptex", "shukran"). Loanwords used in German (Computer, Handy, Meeting), names '
    'and a German word with a small typo COUNT AS GERMAN (fix the typo). If false, still fill every other field with your best guess and put '
    'the German word the user probably meant in input_suggestion, or "" if there is none. '
    '# WORD: MUST be EXACTLY the user input. Fix only obvious typos. Add an article only if input is a bare noun. Phrases/sentences kept as-is. '
    '# REGISTER: classify into "casual" / "neutral" / "formal". '
    '"casual" = Umgangssprache (Bock haben, checken, krass). '
    '"neutral" = works in both contexts (arbeiten, kaufen, sehen). '
    '"formal" = legal/bureaucratic, not in casual speech (gegebenenfalls, hiermit, anbei, infolgedessen, dergestalt). '
    '# IF register == "formal": '
    '(1) casual_alternatives = 2-4 native casual replacements (e.g. gegebenenfalls → ["wenn du willst","vorher"]). '
    '(2) casual_alternatives_en = 2-4 casual English replacements. '
    '(3) example_casual must NOT contain the original formal word — use one of the alternatives instead, so it reads as real casual speech. '
    '(4) example_casual_en mirrors: uses the English casual alternative, NOT the formal translation. '
    '(5) example_formal keeps the formal word. '
    '(6) explanation_de must note the word is Behörden-/Geschäftssprache and casual speakers prefer the alternatives. '
    '(7) Add "Formell" to tags. '
    '# IF register == "neutral" or "casual": casual_alternatives = []. example_casual uses the actual word. No "Formell" tag. '
    '# If input is a phrase (>2 words), BOTH examples use that exact phrase. NEVER substitute synonyms — the card teaches THAT word/phrase. '
    '# CASUAL = 25-40 working German, 2026. 5-12 words. Contractions (hab, machs, gibts, ins, aufm, is). '
    'Modal particles (halt, mal, eben, doch, eh, einfach, echt): use AT MOST ONE per sentence, and only where it sounds natural — zero is fine. A native speaker aged 20-40 uses these sparingly for flow, NOT as decoration. '
    'HARD LIMIT: never stack two or more particles in the same sentence. One short, clear, fluent sentence beats a particle-stuffed one. '
    'Casual verb swaps: bekommen→kriegen, benötigen→brauchen, sich befinden→sein, sehr gut→richtig gut/mega. '
    'Vary sentence starts across cards. Questions often verb-first ("Machst du mal?"). '
    'FORBIDDEN: stacking fillers ("Boah Alter Ey"); multiple modal particles in one sentence; run-on sentences; repeated templates ("Hab halt gerade ..."). '
    '# FORMAL = professional-neutral, like a competent German email. 8-18 words. Standard verbs fine (bekommen, brauchen, machen). Sachlich, direct, polite. '
    'FORBIDDEN: Amtsdeutsch clichés (hiermit teile ich Ihnen mit, in Kenntnis setzen, diesbezüglich) unless actually a Behörde context. No archaic verbs (erstehen, vollziehen, tätigen). '
    '# ANTI-TRANSLATIONESE: read each German sentence mentally — would a real German say this word-for-word? If it feels translated from English, rewrite with native structure (verb-second, separable splits, time-manner-place, modal particles). '
    '# CONTENT: example sentences and ALL emoji fields must NEVER reference alcohol (Bier, Wein, Sekt, Schnaps, cocktails, 🍺🍷🍸🥂) or pork (Schwein, Schweinefleisch, Schinken, Speck, Wurst aus Schwein, 🐖🥓). When a generic example would naturally use these, pick a neutral everyday alternative instead (Wasser, Saft, Kaffee, Tee, Geschirr, Einkäufe, Hähnchen, Rind, Gemüse). This is a hard rule, not a preference. It applies to imageKeyword TOO: never search for a bar, a pub, a Kneipe, a brewery, beer, wine, a toast, a butcher counter or any pork product, even when the example sentence mentions one. ONLY exception: if the user-requested WORD itself is one of these terms, you must still teach it — keep that word but keep the surrounding context neutral. '
    '# ENGLISH: natural conversational English, NOT mirror of German syntax (Ich freue mich darauf → "I am looking forward to it", NOT "I look forward on that"). '
    'NEVER use slashes "/" in ANY English field — write "cordless drill, cordless screwdriver" not "cordless drill / cordless screwdriver". TTS reads "/" aloud as "slash" and breaks audio. Use comma between alternatives; pick ONE best phrasing if you can. '
    'PUNCTUATION RULE (BOTH German and English examples): NEVER use em-dash "—" (U+2014) or en-dash "–" (U+2013) inside any example sentence — TTS does NOT pause on dashes. ALWAYS use a comma "," for a natural pause, or a period "." for a stronger break. '
    'ENGLISH ALSO CONTAINS NO GERMAN WORDS — translate German places/brands/bureaucratic terms naturally '
    '(Bürgeramt → city hall; WG → shared apartment; Pfand → bottle deposit; REWE/Edeka/Aldi → supermarket; Kassiererin → cashier; Krankenkasse → health insurance). '
    'EXCEPTIONS already English: kindergarten, schadenfreude, autobahn, Berlin/Munich. '
    '# EMOJIS (emoji, emoji_formal, emoji_casual): emit the actual emoji character directly (e.g. 👍 💼 🛒 📝 😂). FORBIDDEN: ":briefcase:"-style shortcodes; "\\uXXXX" JSON escapes. The JSON value must be the literal emoji glyph. emoji_formal/emoji_casual must fit their example scene and differ from the word emoji. '
    '# META: imageKeyword = 1-3 SAFE, wholesome, classroom-appropriate English search terms (all ages). ABSTRACT WORDS: if the word is not something you can photograph (an adjective, adverb, verb, abstract noun, or a phrase such as wichtig, richtig, der Termin, die Frage, Kein Problem), do NOT search the word: describe the concrete SCENE of example_casual (or example_formal) instead, so the picture matches the sentence the learner reads (e.g. wichtig + a doctor appointment sentence -> "calendar with appointment reminder"). For a photographable noun, name the object itself. NEVER a term that could return suggestive/swimwear/bikini/lingerie/glamour/model photos; MODESTY (hard rule): people in photos must be modestly dressed - no bare-skin close-ups (bare legs, shoulders, midriff), no tight or revealing clothing, no swimwear or sleeveless glamour shots. For body-part words (Knie, Arm, Ruecken) choose a CLOTHED context (person in jeans holding their knee, physiotherapy with clothing) instead of bare skin. for a person word (Mädchen/Frau/Mann/Junge/Kind) search a wholesome activity or scene (e.g. "girl reading a book", "woman cooking") instead of the bare person. Base it on the WORD\'s core meaning as a POSITIVE/NEUTRAL everyday scene; avoid dark/morbid/medical/distressing images (graves, hospitals, accidents, crying) unless the word is itself about that, and ignore any negative emotion in a meaning/scenario hint when choosing the image. '
    '# GRAMMAR PATTERNS: up to 3 short reusable fragments that LITERALLY occur in YOUR sentences, verb+preposition+case first, then collocations. Empty beats filler. '
    '# GRAMMAR SELF-CHECK (re-read EACH German sentence before returning, fix any error): a SEPARABLE verb is EITHER split (finite part + prefix at the end: "Ich kriege das hin") OR a full infinitive after a modal/auxiliary ("Ich kann das hinkriegen") — NEVER a finite form AND the full infinitive together (WRONG: "Ich krieg ... hinkriegen"); exactly ONE finite verb per clause, positioned correctly (verb-second in main clauses, verb-LAST in subordinate clauses); correct case and agreement. '
    '# TAGS from: Alltag, Arbeit, Redewendung, Haushalt, Verkehr, Finanzen, Gesundheit, Essen, Kueche, Kleidung, Shopping, Technik, Gefuehle, Grammatik, Bildung, Sport, Reisen, Auto, Zeit, Eigenschaften, Umgangssprache, Kommunikation, Beziehungen, Formell. '
    '# MORPHOLOGY: fill "morphology" for the headword. NOUN → {"pos":"noun","article":"der|die|das","plural":"die <Plural>" (use "—" if it has no plural),"genitive":"des/der <genitive singular>"}. VERB → {"pos":"verb","present_3sg":"<3rd-person sg present, e.g. holt ab>","past_3sg":"<Präteritum 3rd sg>","perfect":"<hat/ist + Partizip II>","separable":true_or_false}. Anything else → {"pos":"other"}. Be 100% correct: gender, umlaut plurals, genitive, the right auxiliary (haben/sein), separability. For STRONG/IRREGULAR verbs use the correct ablaut Präteritum (bewerben→bewarb, sprechen→sprach, gehen→ging, nehmen→nahm, fahren→fuhr) — NEVER a regularized "-te" form.'
)

SYSTEM_LOANWORDS_EXPANDED = (
    ' # EXTENDED GERMAN-LOANWORDS TRANSLATION TABLE (applies because the user provided a scenario hint that may contain German terms): '
    'Bürgeramt → "city hall" / "registration office"; Anmeldung (residency) → "address registration"; '
    'WG / Wohngemeinschaft → "shared apartment" / "flat-share"; Mensa → "university cafeteria"; '
    'Pfand → "bottle deposit"; Brötchen → "bread roll"; Feierabend → "end of the workday"; '
    'REWE / Edeka / Aldi / Lidl / Kaufland → "grocery store" / "supermarket" (unless the card is teaching the store name); '
    'Kassiererin → "cashier"; Kasse → "checkout"; Hauptbahnhof → "main train station"; S-Bahn → "city train"; U-Bahn → "subway"; '
    'Nebenkosten → "utility costs"; Kaution → "security deposit"; '
    'Krankenkasse → "health insurance"; Aufenthaltstitel → "residence permit"; Arbeitsamt → "employment office". '
    'If the hint mentions any German place/term, your English translation MUST convert it.'
)

SYSTEM_GRAMMAR = (
    'You extract reusable grammar patterns from the given sentences. Return ONLY valid JSON: {"grammar_patterns":[],"grammar_patterns_en":[]}. '
    'Up to 5 German fragments of 2 to 6 words that LITERALLY occur in the German sentences, best first: ' + _RANKED + '. '
    'Never a whole sentence, a sentence cut off with "...", a sentence with a gap, an adjective with an intensifier, a bare object of an everyday verb, '
    'or an invented textbook example. Empty beats filler. grammar_patterns_en glosses the same entries in the same order, ENGLISH ONLY: '
    'no German word, no German grammar term ("subjunctive II", not "Konjunktiv II"), no case marker; the case stays on the German side.'
)

SYSTEM_ARABIC = (
    'You are an expert translator into Modern Standard Arabic (الفصحى). '
    'ABSOLUTE RULES: '
    '(1) ONLY Modern Standard Arabic (Fusha). NEVER any dialect. '
    '(2) Output must be 100% Arabic letters and Arabic punctuation. NEVER any Latin characters. '
    '(3) NO diacritics (تشكيل) — plain unvocalized Arabic only. '
    '(4) Use proper hamza, proper ta marbuta (ة not ه), and full grammatical inflection. '
    '(5) FORBIDDEN dialect words: لازم، دلوقتي، عايز، بدي، هيكون، مافيه، شي، هلق، قبل ما، أتجاوز، مرا، بحين، هيك، زي، كده، أوي. '
    '(6) REQUIRED MSA equivalents: يجب، الآن، أريد، سيكون، لا يوجد، شيء، حالياً، قبل أن، أتخطى، مرة. '
    '(7) Style: Like an Al Jazeera news anchor or formal literary Arabic. '
    '(8) Both casual and formal sentences use MSA — they differ only in tone, still 100% Fusha grammar. '
    '(9) word_translation must MATCH WHAT THE GERMAN IS. A bare noun -> an Arabic noun phrase. '
    'An ADJECTIVE -> an Arabic adjective, never the related noun (alt -> قديم/عجوز, NOT العمر; '
    'fertig -> جاهز/منتهٍ, NOT انتهاء). A verb -> the masdar is fine as a dictionary form. '
    'A FULL PHRASE OR SENTENCE -> translate the WHOLE thing, never a one-word label naming its '
    'topic (Wie spät ist es? -> كم الساعة؟, NOT الوقت; Können Sie mir helfen? -> هل يمكنكم مساعدتي؟, '
    'NOT طلب المساعدة). Never describe the phrase; translate it. '
    '(10) FORMALITY: Arabic has NO plural-for-politeness convention. German Sie addressing ONE '
    'person is translated with the SINGULAR (لديك، يمكنك، معك). Formality is carried by register '
    'and word choice, and by honorifics which are themselves singular (حضرتك، سيادتك) — never by '
    'switching to أنتم, which reads as addressing a group. Use the plural ONLY when the German '
    'actually addresses several people. '
    'Return ONLY valid JSON: {"word_translation":"...","casual":"...","formal":"..."}'
)


def secondary_translation_system(language):
    """System prompt for the optional secondary-translation call.

    Arabic uses the strict MSA prompt; any other language uses a generic translator.
    Both return JSON: {word_translation, casual, formal}.
    """
    if (language or "").strip().lower() in ("arabic", "msa", "fusha", "العربية", "ar"):
        return SYSTEM_ARABIC
    return (
        "You are an expert translator into %s. Translate naturally and idiomatically (not "
        "word-for-word). No alcohol or pork in any example.\n"
        "word_translation must match what the German IS: an adjective stays an adjective (never the "
        "related noun), and a full phrase or sentence is translated WHOLE, never replaced by a "
        "one-word label naming its topic.\n"
        "FORMALITY: where the German uses Sie/Ihr/Ihnen, render the formal sentence with whatever "
        "polite address THAT language actually uses — and only if it has one. Turkish (siz) and "
        "Russian (\u0432\u044b) do use the plural for politeness, so use it. Arabic does NOT: it marks "
        "formality by register and by singular honorifics, and a plural there reads as addressing a "
        "group. Never impose a European politeness pattern on a language that lacks it.\n"
        'Return ONLY valid JSON: {"word_translation":"...","casual":"...","formal":"..."}' % language
    )


SYSTEM_CLOZE = (
    'You create cloze-deletion companion cards for German Anki flashcards.\n\n'
    'TOP PRIORITY: The generated sentence MUST be 100% grammatically correct and sound COMPLETELY '
    'natural — the way a native German speaker actually speaks. Stilted/textbook German is UNACCEPTABLE.\n\n'
    'RULES:\n'
    '1. NATURAL GERMAN ABOVE ALL: favor common everyday German; reread mentally — would a real German say this?\n'
    '2. PRESERVE CONTENT WORDS, NOT WORD ORDER: keep the target nouns/verbs/adjectives/prepositions; you MAY '
    'rearrange word order, adjust inflection, and add helper words (articles, auxiliaries, conjunctions). '
    'You may NOT add or remove content words.\n'
    '3. FIX FRAGMENT INPUTS: embed fragments in a natural complete sentence (direct or subordinate); the answer '
    'matches the final grammatical form.\n'
    '4. FORBIDDEN: mixed direct+subordinate word order; split compound words; wrong mid-sentence capitalization; '
    'broken verb position in subordinate clauses; English word order.\n'
    '5. CONTEXT SPECIFICITY: only the target fits naturally.\n'
    '5b. CONTENT RESTRICTION: NEVER reference alcohol (Bier, Wein, Sekt, Schnaps) or pork (Schwein, Schinken, '
    'Speck). Use neutral alternatives (Wasser, Saft, Kaffee, Geschirr, Einkäufe, Hähnchen, Gemüse). Hard rule. '
    'Only exception: if the user-requested word itself is one of these, keep it but make the rest neutral.\n'
    '6. ANSWER MUST MATCH SENTENCE EXACTLY: after ANY restructuring, the answer field MUST be a LITERAL substring '
    'of the sentence (same words/case/spelling). Verify before returning. This is the #1 rule.\n'
    '7. Classify the input into ONE of 6 cases and apply its cloze strategy.\n\n'
    'CASES:\n'
    'A. "single_word" — single content word. For NOUNS include the article matching the case used; pick varied '
    'cases across cards. NEVER both a possessive AND an article. For verbs/adjectives/adverbs: cloze just the word.\n'
    'B. "noun_prep" — cloze JUST the preposition. Keep noun visible. ("Frage zum Thema" → answer "zum")\n'
    'C. "verb_prep_article" — cloze PREP+ARTICLE (2 words). ("warten auf" → "auf den")\n'
    'D. "nvv" — pure Noun-Verb-Verbindung; cloze JUST the verb. ("Entscheidung treffen" → "treffen")\n'
    'E. "long_phrase" — multi-word phrase >3 words, not an idiom; cloze the whole phrase.\n'
    'F. "idiom" — cloze 2-3 key content words comma-separated.\n\n'
    'Return ONLY valid JSON:\n'
    '{\n'
    '  "case": "single_word" | "noun_prep" | "verb_prep_article" | "nvv" | "long_phrase" | "idiom",\n'
    '  "sentence": "Natural German sentence with answer present as plain text (no cloze syntax)",\n'
    '  "answer": "Exact substring from sentence. Max 3 words per blank (idiom: comma-separated).",\n'
    '  "translation_en": "Full English translation",\n'
    '  "grammar_hint": "Short pattern for back or empty",\n'
    '  "idiom_meaning_de": "For idiom >4 words: German paraphrase or empty"\n'
    '}\n\n'
    'CRITICAL: answer MUST appear EXACTLY in sentence. ANSWER PLACEMENT: the answer must appear as a STANDALONE '
    'word, NEVER inside a compound (hyphenated or glued). If the natural sentence would use a compound, rewrite '
    'so the answer stands alone. Short native sentences, verb-second.'
)

CONTEXTS_MAIN = {
    'IT': 'CONTEXT: Software developer / tech team in Germany, 2026. REAL DENGLISCH IS NORMAL: gemergt, gepusht, gereviewt, deployed; ein Ticket ziehen; im Standup; im Sprint; auf Prod; PR aufmachen; Pipeline; CI läuft durch; on-call. Scenarios: code review, bug fix, merge conflict, Slack-Nachricht, Jira-Ticket, Retro, Debugging. AVOID generic office vocabulary.',
    'Redewendungen': 'CONTEXT: This is a GERMAN IDIOM / REDEWENDUNG. Anchor meaning on NATIVE GERMAN USAGE (Duden/DWDS), never on English-looking component words. Beware false friends. Before translation_en, decide what a native German MEANS, then pick the closest English idiom with the SAME meaning. explanation_de describes the REAL meaning. Both examples put the idiom where the real meaning fits.',
    'Supermarkt': 'CONTEXT: Grocery shopping / cooking in Germany. Stores: REWE, Edeka, Aldi, Lidl, Kaufland, dm. Vocabulary: Pfand, Flaschen zurückgeben, Kassenzettel, an der Kasse, Bio, Angebot, reduziert, Obst- und Gemüseabteilung, Bäckerei, Tiefkühlregal. Actions: einkaufen, kochen, aufwärmen, braten, einfrieren.',
    'NVV': 'CONTEXT: German Nomen-Verb-Verbindung. Professional register: meeting, decision, project, email, Retrospektive. CRITICAL: do NOT replace the NVV with a single verb. The NVV is the learning target and must appear in both examples.',
    'Verben': 'CONTEXT: German everyday verb. (1) If past tense, casual uses Perfekt (ich hab gemacht), not Präteritum. (2) Separable verbs show separation. (3) Prefer one example with a modal. (4) Reflexive verbs show the pronoun.',
    'Alltagsdeutsch': 'CONTEXT: Textbook German vs real street German. The CONTRAST is the purpose: formal uses the Schuldeutsch word; casual uses what Germans actually say (erhalten→kriegen, verstehen→checken, funktionieren→klappen, sehr→mega, möchte→will). Formal sounds textbook-correct; casual sounds like WhatsApp.',
    'Behörden': 'CONTEXT: German bureaucracy / Behördengang. Real Behörden scenarios: Bürgeramt (Anmeldung, Ummeldung), Krankenkasse, Ausländerbehörde, Arbeitsamt, Finanzamt, Steuererklärung, Aufenthaltstitel, Wohnberechtigungsschein, einen Termin vereinbaren, verschieben oder absagen. Formal example: a polite in-person or written interaction with an official, full Sie-Form, precise vocabulary. Casual example: a friend giving advice about a Behördengang ("Geh früh hin", "Nimm dir einen Termin"). Both examples must reflect real German bureaucratic reality, not generic office vocabulary.',
    'Default': 'CONTEXT: Important everyday German for someone living in Germany. Formal: office/appointment/email scenario. Casual: chat with friends/family (WhatsApp tone). Prefer scenarios a foreigner meets weekly: Arzttermin, Wohnungssuche, Behördengang, Einkaufen, Arbeit, Feierabend zu Hause.',
}

CONTEXTS_CLOZE = {
    'IT': 'CONTEXT: developer/tech scenario (code review, deploy, bug fix, PR, standup, sprint, server, Jira, Slack, CI/CD). NOT generic everyday life.\n\nClassify and generate a NATURAL German cloze sentence. Restructure if needed.',
    'Redewendungen': 'CONTEXT: a German idiom used naturally in a real situation.\n\nClassify and generate a NATURAL German cloze sentence. Restructure if needed.',
    'Supermarkt': 'CONTEXT: grocery/food/shopping/cooking.\n\nClassify and generate a NATURAL German cloze sentence. Restructure if needed.',
    'NVV': 'CONTEXT: the NVV in professional/work scenarios.\n\nClassify and generate a NATURAL German cloze sentence. Restructure if needed.',
    'Verben': 'CONTEXT: the verb in everyday action with clear subject and object.\n\nClassify and generate a NATURAL German cloze sentence. Restructure if needed.',
    'Alltagsdeutsch': 'CONTEXT: casual/Alltagsdeutsch register, conversational.\n\nClassify and generate a NATURAL German cloze sentence. Restructure if needed.',
    'Behörden': 'CONTEXT: a real Behördengang / bureaucratic scenario (Bürgeramt, Anmeldung, Ummeldung, Krankenkasse, Ausländerbehörde, Termin vereinbaren). NOT generic office vocabulary.\n\nClassify and generate a NATURAL German cloze sentence. Restructure if needed.',
    'Default': '',
}

# Single source of truth for the optional starter-deck pack. Drives BOTH the Settings checkbox
# list (name + flavor description) AND the create-on-demand logic; deck_context_de() (end of this
# file) routes these exact names to the CONTEXTS_* flavor above (Wichtig falls through to Default by
# design). These are the German decks; another learning language brings its own.
STARTER_DECKS = [
    {'name': 'Deutsch::Alltagsdeutsch', 'description': 'everyday spoken German, casual vs formal contrast', 'default_checked': True},
    {'name': 'Deutsch::Verben', 'description': 'verbs (separable, reflexive, Perfekt rules)', 'default_checked': True},
    {'name': 'Deutsch::Redewendungen', 'description': 'idioms with native meaning anchoring (no false friends)', 'default_checked': True},
    {'name': 'Deutsch::Nomen-Verb-Verbindungen', 'description': 'NVV / professional collocations (educated register)', 'default_checked': True},
    {'name': 'Deutsch::Supermarkt', 'description': 'grocery, cooking, Pfand, REWE / Edeka / Aldi realism', 'default_checked': True},
    {'name': 'Deutsch::Behörden', 'description': 'bureaucracy: Anmeldung, Ummeldung, Bürgeramt, Krankenkasse', 'default_checked': True},
    {'name': 'Deutsch::Wichtig', 'description': 'important words for daily life in Germany (general)', 'default_checked': True},
    {'name': 'Deutsch::IT Wortschatz', 'description': 'tech German with Denglisch, dev scenarios', 'default_checked': True},
]


# ── CEFR level system ────────────────────────────────────────────────────────────────────
# A1..C1 = a difficulty ladder (each uses level-appropriate words + grammar). "Native" = the
# original SYSTEM_MAIN prompt, verbatim — real spoken German with the full register machinery,
# kept as its own choice so it's preserved exactly.
# The LEVEL CODES are language-agnostic; the rule TEXT is German. Another learning language gets its
# own rule text through PROMPTS at the end of this file, the one way the pipeline asks for a prompt.
LEVELS = ["A1", "A2", "B1", "B2", "C1", "Native"]
DEFAULT_LEVEL = "B1"
LEVEL_LABELS = {  # dropdown display text
    "A1": "A1: Beginner", "A2": "A2: Elementary", "B1": "B1: Intermediate",
    "B2": "B2: Upper-intermediate", "C1": "C1: Advanced", "Native": "Native: real spoken German",
}


def level_label(code, lang):
    """A level as the dropdowns show it: Native names the learning language ("Native: real spoken
    English"); German's labels are LEVEL_LABELS, byte for byte."""
    if code == "Native":
        return "Native: real spoken %s" % languages.get(lang)["name"]
    return LEVEL_LABELS.get(code, code)


GRAMMAR_LEVELS = ("Native",)  # only Native uses the separate grammar call; A1–C1 get grammar_patterns
#                               from the MAIN call (per-level focus in LEVEL_RULES) — no extra call

SYSTEM_MAIN_LEVELED = (
    'You create German Anki flashcards for a learner at a given CEFR level. Return ONLY valid JSON: '
    '{'
    '"emoji":"one emoji",'
    '"word":"<EXACT user input — copy from the user message, NEVER copy this placeholder>",'
    '"translation_en":"<English meaning — generate fresh>",'
    '"register":"neutral",'
    '"casual_alternatives":[],'
    '"casual_alternatives_en":[],'
    '"example_formal":"German Sie/standard sentence.",'
    '"example_casual":"German du/everyday sentence.",'
    '"example_formal_en":"Natural English.",'
    '"example_casual_en":"Natural English.",'
    '"explanation_de":"1 short, simple German sentence.",'
    '"tags":["Alltag"],'
    '"imageKeyword":"english image search term",'
    '"emoji_formal":"emoji for the formal scene",'
    '"emoji_casual":"emoji for the casual scene",'
    '"grammar_patterns":[],'
    '"grammar_patterns_en":[],'
    '"morphology":{},'
    '"input_is_german":true,'
    '"input_suggestion":""'
    '} '
    '# INPUT CHECK: set input_is_german to false when the input is NOT a German word or phrase: another language, random letters, '
    'or Arabic/other speech written in Latin letters ("blorptex", "shukran"). Loanwords used in German (Computer, Handy, Meeting), names '
    'and a German word with a small typo COUNT AS GERMAN (fix the typo). If false, still fill every other field with your best guess and put '
    'the German word the user probably meant in input_suggestion, or "" if there is none. '
    '# MORPHOLOGY: fill "morphology" for the headword. NOUN → {"pos":"noun","article":"der|die|das","plural":"die <Plural>" (use "—" if it has no plural),"genitive":"des/der <genitive singular>"}. VERB → {"pos":"verb","present_3sg":"<3rd-person sg present, e.g. holt ab>","past_3sg":"<Präteritum 3rd sg>","perfect":"<hat/ist + Partizip II, e.g. hat abgeholt / ist gegangen>","separable":true_or_false}. Anything else → {"pos":"other"}. Be 100% correct: gender, umlaut plurals, genitive, the right auxiliary (haben/sein), separability. For STRONG/IRREGULAR verbs use the correct ablaut Präteritum (bewerben→bewarb, sprechen→sprach, gehen→ging, nehmen→nahm, fahren→fuhr) — NEVER a regularized "-te" form. '
    '# WORD: EXACTLY the user input. Fix only obvious typos. Add an article only if input is a bare noun. Keep phrases/sentences as-is. '
    '# TWO EXAMPLES = a casual/formal PAIR that teaches the contrast: '
    'example_casual uses "du" and everyday/spoken wording; example_formal uses "Sie" and standard/polite wording. '
    'STRONGLY prefer this du-vs-Sie contrast — use it whenever the sentence addresses, asks something of, or could address a person (greetings, questions, requests, offers, instructions). '
    'If the word has a colloquial-vs-standard form (e.g. kriegen vs bekommen), casual uses the colloquial one and formal the standard one. '
    'If the word has NO real register difference, still give TWO useful, DIFFERENT everyday sentences at this level (casual = a bit more conversational, formal = a bit more polite). BOTH must teach the word. '
    '# USEFULNESS: every sentence must be REAL, natural German that people actually say in Germany, and genuinely useful to learn. NEVER use rare or bookish words almost nobody uses. '
    '# MATCH THE LEVEL: the LEVEL RULES below set vocabulary, sentence length, tenses and grammar. Lower levels = shorter sentences, more common words, fewer tenses, simpler grammar. Obey the word-count cap STRICTLY. '
    '# ONE sentence per example (no second sentence in the same field). '
    '# GRAMMAR SELF-CHECK (re-read EACH German sentence before returning and FIX any error — these cards teach learners, a wrong form must never appear): '
    'verb conjugation correct (du-form ends in -st: "spielst du?", NOT "spielt du"); '
    'a SEPARABLE verb is EITHER split (finite part + prefix at the end: "Ich kriege das hin") OR a full infinitive after a modal/auxiliary ("Ich kann das hinkriegen") — NEVER a finite form AND the full infinitive together (WRONG: "Ich krieg ... hinkriegen"); '
    'exactly ONE finite verb per clause, correctly positioned (verb-second in main clauses, verb-LAST in subordinate clauses); correct case and article/adjective agreement. '
    '# EXAM-CLEAN GERMAN (these are CEFR levels A1–C1, used by learners preparing for official German language exams): write standard German with NO trendy English or Denglisch — always use the German word (Besprechung not Meeting, Frist not Deadline, herunterladen not downloaden, unterbricht not interrupts). Only fully-naturalised words that ARE standard German (Computer, Auto, Bus, Hotel, Restaurant) are allowed. Never insert a raw or English-conjugated word into a German sentence. (The separate "Native" style is the only place that keeps everyday English/Denglisch.) '
    '# HINTS DO NOT RAISE THE LEVEL: a meaning or scenario hint only sets the sense or topic; keep the sentence within THIS level\'s word-count and grammar limits anyway. '
    '# CONTENT: examples and ALL emoji fields must NEVER reference alcohol (Bier, Wein, 🍺🍷) or pork (Schwein, Schinken, Speck, 🐖🥓); use neutral everyday alternatives (Wasser, Saft, Kaffee, Hähnchen, Gemüse). Hard rule, and it applies to imageKeyword too: never search for a bar, a pub, a brewery, beer, wine or any pork product, even when the sentence mentions one. Only exception: if the requested WORD itself is one of these, teach it but keep the rest neutral. '
    '# IMAGEKEYWORD must be SAFE, wholesome and classroom-appropriate (all ages). NEVER a term that could return suggestive, swimwear, bikini, lingerie, glamour or model photos. MODESTY (hard rule): people in photos must be modestly dressed - no bare-skin close-ups (bare legs, shoulders, midriff), no tight or revealing clothing, no swimwear or sleeveless glamour shots. For body-part words (Knie, Arm, Ruecken) choose a CLOTHED context (person in jeans holding their knee, physiotherapy with clothing) instead of bare skin. For a person word (Mädchen, Frau, Mann, Junge, Kind), search a WHOLESOME ACTIVITY or SCENE instead of the bare person — e.g. "girl reading a book", "woman cooking", "boy playing football", "child in a classroom". Base it on the WORD\'s core meaning as a POSITIVE/NEUTRAL everyday scene; ABSTRACT WORDS: if the word cannot be photographed (an adjective, adverb, verb, abstract noun or a phrase such as wichtig, richtig, der Termin, die Frage, Kein Problem), do NOT search the word itself: describe the concrete SCENE of example_casual (or example_formal) so the picture matches the sentence the learner reads (e.g. wichtig + a doctor appointment sentence -> "calendar with appointment reminder"); for a photographable noun, name the object itself. avoid dark/morbid/medical/distressing images (graves, hospitals, accidents, crying) unless the word is itself about that, and ignore any negative emotion in a meaning/scenario hint when choosing the image. '
    '# ENGLISH: natural conversational English, NOT a word-for-word mirror of the German. Translate German places/terms (Bürgeramt → city hall; Krankenkasse → health insurance). No German words left in the English. '
    '# NO SLASHES "/" in any English field (TTS reads it aloud as "slash"). No em-dash "—" or en-dash "–" in ANY example (TTS does not pause on them) — use a comma or a period. '
    '# EMOJIS: emit the literal emoji glyph (👍 🛒 📝), never ":name:" shortcodes or \\uXXXX escapes. emoji_formal/emoji_casual fit their scene and differ from the word emoji. '
    '# TAGS from: Alltag, Arbeit, Haushalt, Verkehr, Finanzen, Gesundheit, Essen, Kueche, Kleidung, Shopping, Technik, Gefuehle, Bildung, Sport, Reisen, Auto, Zeit, Eigenschaften, Kommunikation, Beziehungen. '
    '# grammar_patterns: up to 5 short reusable fragments that LITERALLY occur in YOUR sentences, best first: ' + _RANKED + '. '
    'At EVERY level, including A1: a verb+preposition or a case-governing preposition in a sentence MUST appear with its case. '
    'Never a whole sentence, an adjective with an intensifier, a bare object of an everyday verb, or the headword restated (a phrase, Redemittel or Redewendung teaches itself). Empty beats filler. '
    'grammar_patterns_en = the same entries, same order, glossed in ENGLISH ONLY: no German word, no German grammar term ("subjunctive II", not "Konjunktiv II"), '
    'no case marker; the case stays on the German side. '
)

LEVEL_RULES = {
    "A1": (
        ' # LEVEL A1 (beginner): use ONLY the ~600 most common everyday words. MAXIMUM 6 words per sentence — count them. '
        'ONE simple main clause (Subject-Verb-Object), exactly ONE action — do NOT join two actions with und/oder and no chained imperatives ("Komm und setz dich" is too much). '
        'PRESENT TENSE only (one very basic Perfekt is OK, e.g. "Ich habe gegessen."). '
        'FORBIDDEN at A1: Konjunktiv II / politeness forms (Könnten, würden, hätten, wäre) — use simple present instead ("Können Sie...?", not "Könnten Sie...?"); subordinate clauses (weil/dass/wenn); relative clauses (..., der/die/das ...); indirect questions (ob/wie/wo...). "möchte" is allowed. '
        'NO idioms, NO slang. Always use FULL verb forms (hole, not hol; gehe, not geh). For du/Sie use a SHORT present question: "Nimmst du...?" / "Nehmen Sie...?". '
        ' REGISTER AT THIS LEVEL: example_casual is a PLAIN informal du-sentence in standard German, NOT slang: no interjections (Hey, Na, Boah, Ey), no colloquial particles or intensifiers (echt, halt, mal, voll, total, mega, krass, eh), no colloquial verbs (kriegen), no Denglisch, no contractions. example_formal is the same idea with Sie. VOCABULARY: apart from the target word, EVERY other word in both sentences must be basic beginner vocabulary a learner meets in the first weeks (family, home, food, shopping, school, work, time, weather, transport, greetings). Never use office/bureaucracy or abstract words (Unterlagen, Bürgeramt, Behörde, Antrag, Vertrag, Verantwortung, Situation). If the target word itself is harder, keep every other word trivial.'
        'grammar_patterns: look first for a preposition with its case, then a separable or modal verb.'
    ),
    "A2": (
        ' # LEVEL A2 (elementary): ~1200 common words. MAXIMUM ~10 words per sentence. At most ONE simple subordinate '
        'clause with weil/dass/wenn (never nested). FORBIDDEN at A2: relative clauses, indirect questions (ob/wie/wo...), '
        'Konjunktiv II except "möchte". Make it CLEARLY a step above A1: use a simple weil/dass/wenn clause OR the Perfekt '
        'past (e.g. "Ich habe ... geholt"). Simple linkers (und, aber, oder, denn). NO idioms, NO slang. Prefer a du vs Sie pair. '
        ' REGISTER AT THIS LEVEL: example_casual is a PLAIN informal du-sentence in standard German, NOT slang: no interjections (Hey, Na, Boah, Ey), no colloquial particles or intensifiers (echt, halt, mal, voll, total, mega, krass, eh), no colloquial verbs (kriegen), no Denglisch, no contractions. example_formal is the same idea with Sie. VOCABULARY: apart from the target word, EVERY other word in both sentences must be basic A1/A2 vocabulary (family, home, food, shopping, school, work, time, weather, transport, greetings). Never use office/bureaucracy or abstract words (Unterlagen, Bürgeramt, Behörde, Antrag, Vertrag, Verantwortung, Situation). If the target word itself is harder, keep every other word trivial.'
        'grammar_patterns: look first for verb/preposition+case, then a weil/dass/wenn clause, a reflexive verb, the Perfekt.'
    ),
    "B1": (
        ' # LEVEL B1 (intermediate): ~2500 common words. Medium sentences; subordinate clauses are fine '
        '(weil, dass, wenn, obwohl, deshalb). All common tenses + polite Konjunktiv II (würde, könnte). '
        'At most ONE well-known idiom (briefly note its meaning in explanation_de). Light register contrast. '
        'grammar_patterns: look first for verb+preposition+case and Noun-Verb-Verbindungen, then Konjunktiv II, a relative clause, Genitiv.'
    ),
    "B2": (
        ' # LEVEL B2 (upper-intermediate): wide everyday + common professional words. Longer, more complex '
        'sentences; at most ONE modal particle (halt, mal, doch) where natural, separable verbs, common '
        'Noun-Verb collocations (NVV), Konjunktiv II, Passiv. Common idioms allowed. Clear but MODERATE casual '
        'style (not heavy street slang). '
        'grammar_patterns: look first for verb+preposition+case and Noun-Verb-Verbindungen, then Passiv, Konjunktiv II, nominalization.'
    ),
    "C1": (
        ' # LEVEL C1 (advanced): rich, near-native German across registers. The formal example should show genuine '
        'C1 range where it sounds natural — e.g. Konjunktiv I (reported speech), Passiv, NVV, or a precise nominal '
        'style — never forced or bookish. Idioms and advanced linkers used naturally. Still REAL, everyday-useful '
        'German, NEVER rare words. The casual example may be genuinely colloquial (du, particles). '
        'grammar_patterns: look first for verb+preposition+case and idiomatic collocations, then Konjunktiv I, Passiv, nominal style.'
    ),
}


def system_main_for_level(level):
    """Main-call system prompt for a level. 'Native' (and anything unknown) = the original verbatim
    SYSTEM_MAIN (today's behaviour). A1..C1 = the leveled base + that level's rule block."""
    if level in LEVEL_RULES:
        return SYSTEM_MAIN_LEVELED + LEVEL_RULES[level]
    return SYSTEM_MAIN


def cloze_level_note(level):
    """Extra constraint appended to the cloze user prompt so the puzzle matches the level."""
    if level == "A1":
        return ('\n\nLEVEL A1: use ONLY case "single_word"; a SHORT present-tense sentence (3-7 words) with the '
                'most common words; no idioms, no subordinate clause.')
    if level == "A2":
        return ('\n\nLEVEL A2: prefer case "single_word"; a short sentence (present or Perfekt), common words, '
                'at most one weil/dass/wenn clause; no idioms.')
    if level == "B1":
        return ('\n\nLEVEL B1: use case "single_word", "noun_prep" or "verb_prep_article"; a medium everyday '
                'sentence with common words.')
    return ''  # B2 / C1 / Native: full behaviour


# ── Translation language (the helper language shown under German) ──────────────────────────
# Default English; user-configurable. English keeps the MAIN prompt byte-identical
# (translation_override returns "") so Native/English output never changes. The "_en" JSON keys
# are kept as-is and simply hold the chosen language's text (no note-type/card-data change).
# Closed list: every entry has a flag label here, voice locales in audio._SECONDARY_LOCALES and a
# preview sentence in audio.VOICE_SAMPLES. The Settings dropdowns are NOT editable, so nothing
# outside this list can reach the prompt (free text produced silently wrong cards).
COMMON_TRANSLATION_LANGS = ["English", "Arabic", "French", "Spanish", "Turkish", "Russian",
                            "Ukrainian", "Italian", "Polish", "Portuguese", "Persian",
                            "Dutch", "Greek", "Czech", "Romanian", "Hungarian", "Swedish",
                            "Indonesian", "Vietnamese", "Hindi", "Urdu",
                            "Japanese", "Korean", "Chinese (Simplified)"]
DEFAULT_TRANSLATION_LANG = "English"

_RTL_LANGS = {"arabic", "persian", "farsi", "hebrew", "urdu", "pashto"}
_LANG_LABELS = {
    "english": "🇬🇧 English", "arabic": "🇸🇦 العربية", "french": "🇫🇷 Français",
    "spanish": "🇪🇸 Español", "turkish": "🇹🇷 Türkçe", "russian": "🇷🇺 Русский",
    "ukrainian": "🇺🇦 Українська", "italian": "🇮🇹 Italiano", "polish": "🇵🇱 Polski",
    "portuguese": "🇵🇹 Português", "persian": "🇮🇷 فارسی", "farsi": "🇮🇷 فارسی",
    "hebrew": "🇮🇱 עברית", "urdu": "🇵🇰 اردو",
    "dutch": "🇳🇱 Nederlands", "greek": "🇬🇷 Ελληνικά", "czech": "🇨🇿 Čeština", "romanian": "🇷🇴 Română",
    "hungarian": "🇭🇺 Magyar", "swedish": "🇸🇪 Svenska", "indonesian": "🇮🇩 Bahasa Indonesia",
    "vietnamese": "🇻🇳 Tiếng Việt", "hindi": "🇮🇳 हिन्दी", "japanese": "🇯🇵 日本語", "korean": "🇰🇷 한국어",
    "chinese (simplified)": "🇨🇳 中文", "chinese": "🇨🇳 中文", "german": "🇩🇪 Deutsch",
}


def is_english_language(lang):
    return (not lang) or lang.strip().lower() in ("english", "en", "englisch")


def language_label(lang):
    """(display label with flag, is_rtl) for the translation section header."""
    key = (lang or "").strip().lower()
    return _LANG_LABELS.get(key, "🌐 %s" % (lang or "English")), key in _RTL_LANGS


def grammar_override(lang):
    """Appended to SYSTEM_GRAMMAR (Native's separate pattern call) when the translation language is not
    English, so the glosses come in that language and match the card's translation box: the call used to ask
    for English glosses whatever the translation language was. "" for English, so that prompt stays
    byte-identical."""
    if is_english_language(lang):
        return ""
    extra = ""
    if (lang or "").strip().lower() in ("arabic", "العربية", "fusha", "msa"):
        extra = " Use Modern Standard Arabic (MSA / Fusha) ONLY, never any dialect, and no diacritics."
    return (
        ' # TRANSLATION LANGUAGE = %s (NOT English): write grammar_patterns_en in %s instead of English: the same '
        'entries in the same order, natural %s, with no German word, no German grammar term and no case marker. '
        'Keep the JSON key names exactly as given.%s' % (lang, lang, lang, extra)
    )


def translation_override(lang):
    """Appended to the MAIN system prompt ONLY when the primary translation language is not English.
    Returns "" for English so the English/Native prompt stays byte-identical."""
    if is_english_language(lang):
        return ""
    extra = ""
    if (lang or "").strip().lower() in ("arabic", "العربية", "fusha", "msa"):
        extra = " Use Modern Standard Arabic (MSA / Fusha) ONLY — never any dialect."
    return (
        ' # TRANSLATION LANGUAGE = %s (NOT English): the fields translation_en, example_casual_en, '
        'example_formal_en, casual_alternatives_en and grammar_patterns_en MUST be written in %s, not '
        'English. Keep the JSON key names exactly as given. Translate naturally and idiomatically into '
        '%s (never word-for-word); leave NO English or German words in them.%s'
        % (lang, lang, lang, extra)
    )


# ── One prompt set per learning language: the only way the pipeline gets a prompt ──────────────
# Everything above is the German set, tuned on real cards and kept byte for byte (the frozen copies
# in tests/golden/prompts/de/ fail on any change). generate.build_card asks for every system prompt
# and user message through the functions at the end, with the learning language's code from
# pipeline/languages.py, so the pipeline itself holds no German text. A code missing from PROMPTS is a
# KeyError, never a silent German card; tests/test_languages.py checks every language has every entry.

def deck_context_de(deck, kind):
    """The CONTEXT line for a German deck, picked by words in its name; kind is "main" or "cloze".
    The starter deck names (STARTER_DECKS) route here; Wichtig falls through to Default on purpose."""
    table = CONTEXTS_MAIN if kind == "main" else CONTEXTS_CLOZE
    if "IT Wortschatz" in deck:
        return table["IT"]
    if "Redewendungen" in deck:
        return table["Redewendungen"]
    if "Supermarkt" in deck:
        return table["Supermarkt"]
    if "Nomen Verb Verbindung" in deck or "Nomen-Verb-Verbindung" in deck:
        return table["NVV"]
    if "Verben" in deck:
        return table["Verben"]
    if "Alltagsdeutsch" in deck or "statt Schuldeutsch" in deck:
        return table["Alltagsdeutsch"]
    if "Behörden" in deck or "Behoerden" in deck:
        return table["Behörden"]
    return table["Default"]


def _main_system_de(level, helper, scenario, voice=""):
    return system_main_for_level(level) + translation_override(helper) + (SYSTEM_LOANWORDS_EXPANDED if scenario else "")


def _main_user_de(word, deck, meaning, scenario, image_keyword, strict, exact_word):
    # Label the input explicitly: a bare greeting like "Guten Tag!" or "Danke" was read by the model
    # as the user talking to it ("which word do you want?") instead of as the phrase to teach.
    u = 'WORD OR PHRASE TO TEACH: "%s". %s' % (word, deck_context_de(deck, "main"))
    u += _hint_lines(meaning, scenario, image_keyword)
    if strict:
        u += ' STRICT REQUIREMENT: the "word" field MUST be exactly "%s" (or with proper article).' % word
    if exact_word:
        u += (' The user confirmed this spelling. Do NOT correct it, even if it looks misspelled: '
              'teach "%s" exactly as written.' % word)
    return u


def _grammar_system_de(helper=""):
    return SYSTEM_GRAMMAR + grammar_override(helper)


def _grammar_user_de(card, helper=""):
    # The second pair of sentences is the translation: name its language (it was always called English).
    tr = "English" if is_english_language(helper) else helper
    return ('German casual: "%s"\nGerman formal: "%s"\n%s casual: "%s"\n%s formal: "%s"\n\n'
            "Extract REAL patterns from these sentences. Return ONLY JSON."
            % (card.get("example_casual", ""), card.get("example_formal", ""),
               tr, card.get("example_casual_en", ""), tr, card.get("example_formal_en", "")))


def _secondary_user_de(helper, card, level, primary=""):
    su = ("Translate into %s.\n\nGERMAN WORD: %s\nGERMAN CASUAL: %s\nGERMAN FORMAL: %s\n"
          "ENGLISH CASUAL: %s\nENGLISH FORMAL: %s\n\nGenerate word_translation, casual, formal. Return ONLY JSON."
          % (helper, card.get("word", ""), card.get("example_casual", ""), card.get("example_formal", ""),
             card.get("example_casual_en", ""), card.get("example_formal_en", "")))
    if level in ("A1", "A2"):
        su += " Keep the translation short and simple, matching a beginner."
    return su


def _cloze_system_de():
    return SYSTEM_CLOZE


def _cloze_user_de(word, deck, meaning, level, helper, voice=""):
    cu = ("Input: %s\nDeck: %s\nEnglish meaning: %s\n%s\n\nClassify and generate a NATURAL German cloze sentence. Restructure if needed."
          % (word, deck, meaning, deck_context_de(deck, "cloze")))
    cu += cloze_level_note(level)
    if not is_english_language(helper):
        cu += ('\n\nWrite "translation_en" as the FULL sentence translated naturally into %s '
               '(NOT English).' % helper)
    return cu


# ── The generic prompt set: every learning language without a tuned set of its own ─────────────
# The language's name and its NOTE (pipeline/<language>.py, e.g. pipeline/english.py) fill the slots;
# a language without a note gets _DEFAULT_NOTE, which names no other language, so the set works for any
# language the registry lists (tests/test_languages.py proves it with a made-up one). The JSON keys are
# neutral here ("translation", "explanation"): a key named explanation_de would pull the model toward
# German. read_answer() maps them back to the card's historical keys in ONE place (_GENERIC_KEYS).

NOTES = {"en": english.NOTE}

_GENERIC_KEYS = {
    "main": {"translation": "translation_en", "casual_alternatives_translation": "casual_alternatives_en",
             "example_formal_translation": "example_formal_en", "example_casual_translation": "example_casual_en",
             "explanation": "explanation_de", "grammar_patterns_translation": "grammar_patterns_en",
             "input_in_language": "input_is_german"},
    "grammar": {"grammar_patterns_translation": "grammar_patterns_en"},
    "cloze": {"translation": "translation_en", "idiom_meaning": "idiom_meaning_de"},
}

_DEFAULT_NOTE = {
    "input_examples": ("Loanwords used in {language}, names, and {a_language} word with a small typo COUNT AS "
                       "{LANGUAGE} (fix the typo)."),
    "word_rule": ("If {language} uses articles and the input is a bare noun, add its article, like a dictionary entry. "
                  "Phrases and sentences stay as they are."),
    "register_pair": ('example_casual is everyday spoken {language}, the way friends talk; example_formal is polite '
                      'standard {language}, the way you speak to a stranger, an office or a teacher. If {language} has an '
                      'informal and a polite way to say "you", casual uses the informal one and formal the polite one. '),
    "self_check": ("verb forms and agreement, word order, the right preposition, and (where {language} has them) the right "
                   "case, gender and article. "),
    "standard": ('# STANDARD {LANGUAGE} (these are CEFR levels A1 to C1, used by learners preparing for official exams): '
                 'standard {language} as taught to learners. No slang, no text-speak, and no words from other languages '
                 'where {language} has its own. (The separate "Native" style is the only place for them.) '),
    "levels": {
        "A1": (' # LEVEL A1 (beginner): use ONLY the ~600 most common everyday words. MAXIMUM 6 words per sentence, count '
               'them. ONE simple main clause, exactly ONE action. Present tense only. No subordinate or relative clauses, '
               'no idioms, no slang. Apart from the target word, EVERY other word must be basic beginner vocabulary '
               '(family, home, food, shopping, school, work, time, weather, transport, greetings).'),
        "A2": (' # LEVEL A2 (elementary): ~1200 common words. MAXIMUM ~10 words per sentence. At most ONE simple '
               'subordinate clause (because, when, if, that), never nested. The present and the most common past tense. '
               'No idioms, no slang. Apart from the target word, every other word basic A1 or A2 vocabulary.'),
        "B1": (' # LEVEL B1 (intermediate): ~2500 common words. Medium sentences; subordinate clauses are fine. All common '
               'tenses and polite conditional forms. At most ONE well-known idiom (note its meaning in the explanation). '
               'Light register contrast.'),
        "B2": (' # LEVEL B2 (upper-intermediate): wide everyday and common professional words. Longer, more complex '
               'sentences, the passive, conditionals, common idioms. A clear but MODERATE casual style (no heavy slang).'),
        "C1": (' # LEVEL C1 (advanced): rich, near-native {language} across registers, with reported speech, the passive '
               'and a precise formal style where natural. Idioms and advanced linkers used naturally. Still REAL, '
               'everyday-useful {language}, NEVER rare words. The casual example may be genuinely colloquial.'),
    },
    "native": (' # NATIVE: real spoken {language} of people aged 20 to 40 today, with the words, loanwords and slang they '
               'actually use. Casual is 5 to 12 words, formal 8 to 18. Vary how sentences start. '),
    "register_examples": ('"casual" = slang or very informal words. "neutral" = words that work in both. "formal" = legal, '
                          'official or written words not used in casual speech. '),
    "ranked": ("a verb, adjective or noun with its fixed preposition (and its case, where {language} has cases), a verb "
               "with a case or a pattern you cannot guess, collocations, a verb that opens a clause, then level structures"),
    "pattern_rule": ("At EVERY level: a verb, adjective or noun with a fixed preposition in a sentence MUST appear as a "
                     "pattern (with its case, where {language} has cases)."),
    "pattern_format": "Write each pattern as a short frame with placeholders where the object goes.",
    "morphology": ('NOUN -> {"pos":"noun","article":"<its article, or empty if {language} has none>","plural":"<plural>"}. '
                   'VERB -> {"pos":"verb","forms":"<the 2 or 3 forms a learner must know, comma-separated>"}. Anything '
                   'else -> {"pos":"other"}. Be 100% correct, with every irregular form.'),
    "tags": ("Everyday", "Work", "Home", "Transport", "Money", "Health", "Food", "Kitchen", "Clothes", "Shopping",
             "Technology", "Feelings", "Education", "Sport", "Travel", "Time", "Qualities", "Communication",
             "Relationships"),
    "tags_native": ("Everyday", "Work", "Idiom", "Home", "Transport", "Money", "Health", "Food", "Kitchen", "Clothes",
                    "Shopping", "Technology", "Feelings", "Grammar", "Education", "Sport", "Travel", "Time", "Qualities",
                    "Slang", "Communication", "Relationships", "Formal"),
    "explanation": "1 short, simple {language} sentence that explains the word (never a translation)",
    "cloze_cases": ('A. "single_word": one content word; cloze just the word.\n'
                    'E. "long_phrase": a phrase of more than 3 words that is not an idiom; cloze the whole phrase.\n'
                    'F. "idiom": cloze 2 to 3 key content words, comma-separated.'),
    "cloze_case_names": ("single_word", "long_phrase", "idiom"),
    "cloze_levels": {
        "A1": ('\n\nLEVEL A1: use ONLY case "single_word"; a SHORT present-tense sentence (3 to 7 words) with the most '
               'common words; no idioms.'),
        "A2": '\n\nLEVEL A2: prefer case "single_word"; a short sentence with common words; no idioms.',
        "B1": '\n\nLEVEL B1: a medium everyday sentence with common words.',
    },
    "contexts": {
        "Default": ("CONTEXT: Important everyday {language}. Formal: office, appointment or email scenario. Casual: chat "
                    "with friends or family (messaging tone)."),
    },
    "contexts_cloze": {"Default": ""},
    "variety_line": None,
}


def _merged(note):
    out = dict(_DEFAULT_NOTE)
    out.update(note or {})
    return out


def _fill(text, **slots):
    """Fill {name} slots. JSON braces stay as they are: a slot is only ever a bare {word}."""
    for key, value in slots.items():
        text = text.replace("{%s}" % key, value)
    return text


def _a(name):
    """ "a German", "an English": the article for the language's name."""
    return ("an " if name[:1].lower() in "aeiou" else "a ") + name


def _is_arabic(helper):
    return (helper or "").strip().lower() in ("arabic", "msa", "fusha", "العربية", "ar")


_GENERIC_SCHEMA = (
    'Return ONLY valid JSON: {'
    '"emoji":"one emoji",'
    '"word":"<EXACT user input, copy it from the user message, NEVER copy this placeholder>",'
    '"translation":"<the meaning in {helper}, generate it fresh>",'
    '"register":"neutral",'
    '"casual_alternatives":[],'
    '"casual_alternatives_translation":[],'
    '"example_formal":"{language} formal sentence.",'
    '"example_casual":"{language} casual sentence.",'
    '"example_formal_translation":"The formal sentence in {helper}.",'
    '"example_casual_translation":"The casual sentence in {helper}.",'
    '"explanation":"1 short {language} sentence.",'
    '"tags":["{tag0}"],'
    '"imageKeyword":"english image search term",'
    '"emoji_formal":"emoji for the formal scene",'
    '"emoji_casual":"emoji for the casual scene",'
    '"grammar_patterns":[],'
    '"grammar_patterns_translation":[],'
    '"morphology":{},'
    '"input_in_language":true,'
    '"input_suggestion":""'
    '} '
)

_GENERIC_SAFETY = (
    '# CONTENT: examples and ALL emoji fields must NEVER reference alcohol (beer, wine, 🍺🍷) or pork (pork, bacon, ham, '
    '🐖🥓); use neutral everyday alternatives (water, juice, coffee, chicken, vegetables). Hard rule, and it applies to '
    'imageKeyword too: never search for a bar, a pub, a brewery, beer, wine or any pork product, even when the sentence '
    'mentions one. Only exception: if the requested WORD itself is one of these, teach it but keep the rest neutral. '
    '# IMAGEKEYWORD: 1 to 3 SAFE, wholesome, classroom-appropriate ENGLISH search terms (the picture search is English, '
    'all ages). NEVER a term that could return suggestive, swimwear, bikini, lingerie, glamour or model photos. MODESTY '
    '(hard rule): people in photos must be modestly dressed, no bare-skin close-ups (bare legs, shoulders, midriff), no '
    'tight or revealing clothing, no swimwear or sleeveless glamour shots. For body-part words (knee, arm, back) choose a '
    'CLOTHED context (person in jeans holding their knee, physiotherapy with clothing) instead of bare skin. For a person '
    'word (girl, woman, man, boy, child) search a WHOLESOME ACTIVITY or SCENE instead of the bare person, e.g. "girl '
    'reading a book", "woman cooking", "boy playing football", "child in a classroom". Base it on the WORD\'s core meaning '
    'as a POSITIVE or NEUTRAL everyday scene. ABSTRACT WORDS: if the word cannot be photographed (an adjective, adverb, '
    'verb, abstract noun or a phrase), do NOT search the word itself: describe the concrete SCENE of example_casual (or '
    'example_formal), so the picture matches the sentence the learner reads (e.g. "important" with a doctor appointment '
    'sentence -> "calendar with appointment reminder"); for a photographable noun, name the object itself. Avoid dark, '
    'morbid, medical or distressing images (graves, hospitals, accidents, crying) unless the word is itself about that, '
    'and ignore any negative emotion in a meaning or scenario hint when choosing the image. '
    '# NO SLASHES "/" in any sentence or translation (the voice reads it as "slash"): put alternatives after a comma. No '
    'em-dash "—" or en-dash "–" in ANY example (the voice does not pause on them): use a comma or a period. '
    '# EMOJIS: emit the literal emoji glyph (👍 🛒 📝), never ":name:" shortcodes or \\uXXXX escapes. emoji_formal and '
    'emoji_casual fit their scene and differ from the word emoji. '
)


def _generic_main_system(entry, note, level, helper, scenario, voice):
    """The MAIN call for a language without a tuned set. A1 to C1: the CEFR ladder with the language's level
    rules; Native: real spoken language with the register machinery (formal word -> casual alternatives)."""
    n = _merged(note)
    leveled = level in LEVEL_RULES
    standard = n["standard"](voice) if callable(n["standard"]) else n["standard"]
    msa = (" Use Modern Standard Arabic (MSA, Fusha) ONLY, never any dialect, and no diacritics. Address one person in "
           "the singular, also in the formal sentence: Arabic shows politeness with words, never with the plural."
           if _is_arabic(helper) else "")
    tags = n["tags"] if leveled else n["tags_native"]
    parts = [
        "You create {language} Anki flashcards for a learner at a given CEFR level. " if leveled
        else "You create {language} Anki flashcards in real spoken {language}. ",
        _GENERIC_SCHEMA,
        '# INPUT CHECK: set input_in_language to false when the input is NOT {a_language} word or phrase: another '
        'language, random letters, or another language written in Latin letters ("blorptex", "shukran"). '
        + n["input_examples"] + ' If false, still fill every other field with your best guess and put the {language} '
        'word the user probably meant in input_suggestion, or "" if there is none. ',
        '# MORPHOLOGY: fill "morphology" for the headword. ' + n["morphology"] + ' ',
        '# WORD: EXACTLY the user input. Fix only obvious typos. ' + n["word_rule"] + ' ',
    ]
    if leveled:
        parts += [
            '# TWO EXAMPLES = a casual/formal PAIR that teaches the contrast: ' + n["register_pair"]
            + 'If the word has NO real register difference, still give TWO useful, DIFFERENT everyday sentences at this '
            'level (casual = a bit more conversational, formal = a bit more polite). BOTH must teach the word. ',
        ]
    else:
        parts += [
            '# REGISTER: classify the word as "casual", "neutral" or "formal". ' + n["register_examples"],
            '# IF register == "formal": (1) casual_alternatives = 2 to 4 casual {language} replacements. (2) '
            'casual_alternatives_translation = the same in {helper}. (3) example_casual must NOT contain the formal word: '
            'use one of the alternatives, so it reads as real casual speech. (4) example_casual_translation mirrors it. '
            '(5) example_formal keeps the formal word. (6) The explanation says that the word is formal or official '
            'language and that casual speakers prefer the alternatives. (7) Add "{formal_tag}" to tags. ',
            '# IF register == "neutral" or "casual": casual_alternatives = [] and example_casual uses the word itself. ',
            '# TWO EXAMPLES: ' + n["register_pair"],
            '# If the input is a phrase of more than 2 words, BOTH examples use that exact phrase. NEVER substitute '
            'synonyms: the card teaches THAT word or phrase. ',
        ]
    parts += [
        '# USEFULNESS: every sentence must be REAL, natural {language} that people actually say, and genuinely useful to '
        'learn. NEVER use rare or bookish words almost nobody uses. ',
    ]
    if leveled:
        parts += [
            '# MATCH THE LEVEL: the LEVEL RULES below set vocabulary, sentence length, tenses and grammar. Lower levels = '
            'shorter sentences, more common words, fewer tenses, simpler grammar. Obey the word-count cap STRICTLY. ',
        ]
    parts += [
        '# ONE sentence per example (no second sentence in the same field). ',
        '# GRAMMAR SELF-CHECK (re-read EACH {language} sentence before returning and FIX any error; these cards teach '
        'learners, a wrong form must never appear): ' + n["self_check"],
        '# ANTI-TRANSLATIONESE: would a native speaker say each sentence word for word? If it reads like a translation, '
        'rewrite it the way a native speaker would. ',
    ]
    if leveled:
        parts += [
            standard,
            "# HINTS DO NOT RAISE THE LEVEL: a meaning or scenario hint only sets the sense or topic; keep the sentence "
            "within THIS level's word-count and grammar limits anyway. ",
        ]
    parts += [
        _GENERIC_SAFETY,
        '# EXPLANATION: ' + n["explanation"] + '. ',
        '# TRANSLATION LANGUAGE = {helper}: translation, example_casual_translation, example_formal_translation, '
        'casual_alternatives_translation and grammar_patterns_translation are written in {helper}, natural and idiomatic, '
        'never word for word, with no {language} words left in them (translate names of places, institutions and shops '
        'naturally). The formal sentence uses the polite way of addressing someone that {helper} has, and only if it has '
        'one.' + msa + ' ',
        '# TAGS from: ' + ", ".join(tags) + '. ',
        '# grammar_patterns: up to 5 short reusable fragments that LITERALLY occur in YOUR {language} sentences, best '
        'first: ' + n["ranked"] + '. ' + (n["pattern_rule"] + ' ' if leveled else '') + n["pattern_format"]
        + ' Never a whole sentence, an adjective with an intensifier, a bare object of an everyday verb, or the headword '
        'restated (a phrase teaches itself). Empty beats filler. grammar_patterns_translation = the same entries, same '
        'order, glossed in {helper} only, with no {language} word: each gloss is correct, natural {helper}, with its own word '
        'order and prepositions. ',
        n["levels"][level] if leveled else n["native"],
    ]
    if not leveled and n["variety_line"]:
        parts.append("# SPELLING: " + n["variety_line"](voice).strip() + " ")
    name = entry["name"]
    return _fill("".join(parts), language=name, LANGUAGE=name.upper(), a_language=_a(name), helper=helper or "English",
                 formal_tag=entry["formal_tag"], tag0=tags[0])


def _hint_lines(meaning, scenario, image_keyword):
    """The user's hints, any language, as the MAIN user message carries them (German and generic alike)."""
    u = ""
    if meaning:
        u += (' MEANING DISAMBIGUATION: the user wants the specific meaning "%s" '
              "(may be written in any language; interpret it). "
              "Generate the card focused on THIS sense only." % meaning)
    if scenario:
        u += (' EXAMPLE SCENARIO HINT: "%s" (may be written in any language; interpret it). '
              "Use it as the setting for both example sentences; the deck rules still apply." % scenario)
    if image_keyword:
        # The user's image request (any language) is folded into the MAIN call so the model turns it
        # into a SAFE English imageKeyword, instead of sending raw non-English text to the
        # English-indexed image providers. No extra LLM call; image-safety rules still apply.
        u += (' IMAGE HINT: the user wants the picture to show "%s" (may be written in any '
              "language). Set imageKeyword to a SAFE, wholesome ENGLISH image search term for "
              "THIS, following the image rules." % image_keyword)
    return u


def _generic_context(note, deck, kind):
    n = _merged(note)
    table = n["contexts"] if kind == "main" else n["contexts_cloze"]
    return table.get("Default", "")


def _generic_main_user(entry, note, word, deck, meaning, scenario, image_keyword, strict, exact_word):
    u = 'WORD OR PHRASE TO TEACH: "%s". %s' % (word, _fill(_generic_context(note, deck, "main"), language=entry["name"]))
    u += _hint_lines(meaning, scenario, image_keyword)
    if strict:
        u += ' STRICT REQUIREMENT: the "word" field MUST be exactly "%s".' % word
    if exact_word:
        u += (' The user confirmed this spelling. Do NOT correct it, even if it looks misspelled: '
              'teach "%s" exactly as written.' % word)
    return u


def _generic_grammar_system(entry, note, helper):
    n = _merged(note)
    text = ('You extract reusable grammar patterns from the given sentences. Return ONLY valid JSON: '
            '{"grammar_patterns":[],"grammar_patterns_translation":[]}. Up to 5 {language} fragments of 2 to 6 words that '
            'LITERALLY occur in the {language} sentences, best first: ' + n["ranked"] + '. ' + n["pattern_format"]
            + ' Never a whole sentence, a sentence cut off with "...", a sentence with a gap, an adjective with an '
            'intensifier, a bare object of an everyday verb, or an invented textbook example. Empty beats filler. '
            'grammar_patterns_translation glosses the same entries in the same order, in {helper} only, with no {language} '
            'word: each gloss is correct, natural {helper}, with its own word order and prepositions.')
    return _fill(text, language=entry["name"], helper=helper or "English")


def _generic_grammar_user(entry, card, helper):
    name, helper = entry["name"], helper or "English"
    return ('%s casual: "%s"\n%s formal: "%s"\n%s casual: "%s"\n%s formal: "%s"\n\n'
            "Extract REAL patterns from these sentences. Return ONLY JSON."
            % (name, card.get("example_casual", ""), name, card.get("example_formal", ""),
               helper, card.get("example_casual_en", ""), helper, card.get("example_formal_en", "")))


_GENERIC_ARABIC = (
    'You are an expert translator into Modern Standard Arabic (الفصحى). '
    'ABSOLUTE RULES: '
    '(1) ONLY Modern Standard Arabic (Fusha). NEVER any dialect. '
    '(2) Output must be 100% Arabic letters and Arabic punctuation. NEVER any Latin characters. '
    '(3) NO diacritics (تشكيل): plain unvocalized Arabic only. '
    '(4) Use proper hamza, proper ta marbuta (ة not ه), and full grammatical inflection. '
    '(5) FORBIDDEN dialect words: لازم، دلوقتي، عايز، بدي، هيكون، مافيه، شي، هلق، قبل ما، أتجاوز، مرا، بحين، هيك، زي، كده، أوي. '
    '(6) REQUIRED MSA equivalents: يجب، الآن، أريد، سيكون، لا يوجد، شيء، حالياً، قبل أن، أتخطى، مرة. '
    '(7) Style: like an Al Jazeera news anchor or formal literary Arabic. '
    '(8) Both casual and formal sentences use MSA; they differ only in tone, still 100% Fusha grammar. '
    '(9) word_translation must MATCH WHAT THE {LANGUAGE} WORD IS. A bare noun -> an Arabic noun phrase. An ADJECTIVE -> an '
    'Arabic adjective, never the related noun. A verb -> the masdar is fine as a dictionary form. A FULL PHRASE OR '
    'SENTENCE -> translate the WHOLE thing, never a one-word label naming its topic. Never describe the phrase; '
    'translate it. '
    '(10) FORMALITY: Arabic has NO plural-for-politeness convention. A sentence that speaks to ONE person is translated '
    'with the SINGULAR (لديك، يمكنك، معك), also when it is polite. Formality is carried by register and word choice, and '
    'by honorifics which are themselves singular (حضرتك، سيادتك), never by switching to أنتم, which reads as addressing a '
    'group. Use the plural ONLY when the sentence actually addresses several people. '
    'Return ONLY valid JSON: {"word_translation":"...","casual":"...","formal":"..."}'
)


def _generic_secondary_system(entry, helper):
    if _is_arabic(helper):
        return _fill(_GENERIC_ARABIC, LANGUAGE=entry["name"].upper())
    return ("You are an expert translator into %s. Translate naturally and idiomatically (not word-for-word). No alcohol "
            "or pork in any example.\n"
            "word_translation must match what the %s word IS: an adjective stays an adjective (never the related noun), "
            "and a full phrase or sentence is translated WHOLE, never replaced by a one-word label naming its topic.\n"
            "FORMALITY: render the formal sentence with the polite form of address %s actually uses, and only if it has "
            "one. Never impose a politeness pattern on a language that lacks it.\n"
            'Return ONLY valid JSON: {"word_translation":"...","casual":"...","formal":"..."}'
            % (helper, entry["name"], helper))


def _generic_secondary_user(entry, helper, card, level, primary):
    name, primary = entry["name"].upper(), (primary or "English").upper()
    su = ("Translate into %s.\n\n%s WORD: %s\n%s CASUAL: %s\n%s FORMAL: %s\n%s CASUAL: %s\n%s FORMAL: %s\n\n"
          "Generate word_translation, casual, formal. Return ONLY JSON."
          % (helper, name, card.get("word", ""), name, card.get("example_casual", ""), name,
             card.get("example_formal", ""), primary, card.get("example_casual_en", ""), primary,
             card.get("example_formal_en", "")))
    if level in ("A1", "A2"):
        su += " Keep the translation short and simple, matching a beginner."
    return su


def _generic_cloze_system(entry, note):
    n = _merged(note)
    names = " | ".join('"%s"' % c for c in n["cloze_case_names"])
    text = (
        'You create cloze-deletion companion cards for {language} Anki flashcards.\n\n'
        'TOP PRIORITY: The generated sentence MUST be 100% grammatically correct and sound COMPLETELY natural, the way a '
        'native {language} speaker actually speaks. Stilted textbook {language} is UNACCEPTABLE.\n\n'
        'RULES:\n'
        '1. NATURAL {LANGUAGE} ABOVE ALL: favor common everyday {language}; reread mentally: would a native speaker say '
        'this?\n'
        '2. PRESERVE CONTENT WORDS, NOT WORD ORDER: keep the target nouns, verbs, adjectives and prepositions; you MAY '
        'rearrange word order, adjust inflection, and add helper words. You may NOT add or remove content words.\n'
        '3. FIX FRAGMENT INPUTS: embed fragments in a natural complete sentence; the answer matches the final grammatical '
        'form.\n'
        '4. CONTEXT SPECIFICITY: only the target fits naturally.\n'
        '5. CONTENT RESTRICTION: NEVER reference alcohol or pork. Use neutral alternatives (water, juice, coffee, chicken, '
        'vegetables). Hard rule. Only exception: if the user-requested word itself is one of these, keep it but make the '
        'rest neutral.\n'
        '6. ANSWER MUST MATCH SENTENCE EXACTLY: after ANY restructuring, the answer field MUST be a LITERAL substring of '
        'the sentence (same words, case and spelling). Verify before returning. This is the #1 rule.\n'
        '7. Classify the input into ONE of the cases below and apply its cloze strategy.\n\n'
        'CASES:\n' + n["cloze_cases"] + '\n\n'
        'Return ONLY valid JSON:\n'
        '{\n'
        '  "case": ' + names + ',\n'
        '  "sentence": "Natural {language} sentence with the answer present as plain text (no cloze syntax)",\n'
        '  "answer": "Exact substring from sentence. Max 3 words per blank (idiom: comma-separated).",\n'
        '  "translation": "The full sentence in the translation language",\n'
        '  "grammar_hint": "Short pattern for the back, or empty",\n'
        '  "idiom_meaning": "For an idiom of more than 4 words: {a_language} paraphrase, or empty"\n'
        '}\n\n'
        'CRITICAL: answer MUST appear EXACTLY in sentence, as a STANDALONE word, NEVER inside another word. Short, '
        'natural sentences.'
    )
    return _fill(text, language=entry["name"], LANGUAGE=entry["name"].upper(), a_language=_a(entry["name"]))


def _generic_cloze_user(entry, note, word, deck, meaning, level, helper, voice):
    n = _merged(note)
    helper = helper or "English"
    cu = ("Input: %s\nDeck: %s\nMeaning in %s: %s\n%s\n\nClassify and generate a NATURAL %s cloze sentence. Restructure "
          "if needed." % (word, deck, helper, meaning, _generic_context(note, deck, "cloze"), entry["name"]))
    cu += n["cloze_levels"].get(level, "")
    cu += '\n\nWrite "translation" as the FULL sentence translated naturally into %s.' % helper
    if _is_arabic(helper):
        cu += " Use Modern Standard Arabic only, without diacritics."
    if n["variety_line"]:
        cu += n["variety_line"](voice)
    return cu


def _generic_read_answer(kind, data):
    keys = _GENERIC_KEYS.get(kind, {})
    if not isinstance(data, dict):
        return data
    return {keys.get(k, k): v for k, v in data.items()}


def _read_answer_de(kind, data):
    return data          # the German prompts already use the card's keys


def generic_prompts(code):
    """The generic set for a registry language, with its NOTE where it has one."""
    entry, note = languages.get(code), NOTES.get(code, {})
    return {
        "main": functools.partial(_generic_main_system, entry, note),
        "main_user": functools.partial(_generic_main_user, entry, note),
        "grammar": functools.partial(_generic_grammar_system, entry, note),
        "grammar_user": functools.partial(_generic_grammar_user, entry),
        "secondary": functools.partial(_generic_secondary_system, entry),
        "secondary_user": functools.partial(_generic_secondary_user, entry),
        "cloze": functools.partial(_generic_cloze_system, entry, note),
        "cloze_user": functools.partial(_generic_cloze_user, entry, note),
        "read_answer": _generic_read_answer,
    }


# The same keys for every language: what each call is told, as functions of the card's facts.
PROMPTS = {
    "de": {
        "main": _main_system_de,                     # (level, helper, scenario, voice) -> MAIN system prompt
        "main_user": _main_user_de,                  # the word, the deck's context and the hints
        "grammar": _grammar_system_de,               # Native only: the separate pattern call
        "grammar_user": _grammar_user_de,
        "secondary": secondary_translation_system,   # (helper) -> the second translation's system prompt
        "secondary_user": _secondary_user_de,
        "cloze": _cloze_system_de,
        "cloze_user": _cloze_user_de,
        "read_answer": _read_answer_de,              # (kind, answer) -> the answer with the card's keys
    },
    "en": generic_prompts("en"),
}


# ── Translation (helper) languages per learning language ─────────────────────────────────────────
# The common list, plus every learning language that is not on it (German), so each learning language is
# a translation language for the others, never for itself. German learners get exactly the old list.
TRANSLATION_LANGS_ALL = COMMON_TRANSLATION_LANGS + [e["name"] for e in languages.LANGUAGES
                                                    if e["name"] not in COMMON_TRANSLATION_LANGS]


def translation_languages(lang):
    name = languages.get(lang)["name"].lower()
    return [t for t in TRANSLATION_LANGS_ALL if t.lower() != name]


def default_translation_language(lang):
    """English when the learner may pick it, else none: a learner of English must choose."""
    return DEFAULT_TRANSLATION_LANG if DEFAULT_TRANSLATION_LANG in translation_languages(lang) else None


def main_system(lang, level, helper, scenario=False, voice=""):
    """The MAIN call's system prompt. German: the level's prompt, the helper language's override, and the
    loanwords table when the user gave a scenario hint. Generic: one template, see _generic_main_system.
    voice: the voice reading the learning language (English: it decides US or UK spelling)."""
    return PROMPTS[lang]["main"](level, helper, bool(scenario), voice)


def main_user(lang, word, deck, meaning="", scenario="", image_keyword="", strict=False, exact_word=False):
    return PROMPTS[lang]["main_user"](word, deck, meaning, scenario, image_keyword, strict, exact_word)


def grammar_system(lang, helper=""):
    return PROMPTS[lang]["grammar"](helper)


def grammar_user(lang, card, helper=""):
    return PROMPTS[lang]["grammar_user"](card, helper)


def secondary_system(lang, helper):
    return PROMPTS[lang]["secondary"](helper)


def secondary_user(lang, helper, card, level, primary=""):
    """primary: the first translation language, which the card's *_en fields hold."""
    return PROMPTS[lang]["secondary_user"](helper, card, level, primary)


def cloze_system(lang):
    return PROMPTS[lang]["cloze"]()


def cloze_user(lang, word, deck, meaning, level, helper, voice=""):
    """meaning: the word's meaning in the helper language, as the MAIN call gave it."""
    return PROMPTS[lang]["cloze_user"](word, deck, meaning, level, helper, voice)


def read_answer(lang, kind, data):
    """An AI answer ("main", "grammar" or "cloze") with the card's own keys."""
    return PROMPTS[lang]["read_answer"](kind, data)
