"""System prompts for card generation.

The "Arabic" call is generalized: SYSTEM_ARABIC is used when the configured secondary
translation language is Arabic; any other language uses a generic translation prompt.
"""

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
# list (name + flavor description) AND the create-on-demand logic; _pick_context() routes these
# exact names to the CONTEXTS_* flavor above (Wichtig falls through to Default by design).
# v2 multi-language: each LanguageProfile supplies its own list of these entries.
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
# The LEVEL CODES are language-agnostic; the rule TEXT is German. A future LanguageProfile would
# swap SYSTEM_MAIN_LEVELED / LEVEL_RULES per target language (the seam is system_main_for_level()).
LEVELS = ["A1", "A2", "B1", "B2", "C1", "Native"]
DEFAULT_LEVEL = "B1"
LEVEL_LABELS = {  # dropdown display text
    "A1": "A1: Beginner", "A2": "A2: Elementary", "B1": "B1: Intermediate",
    "B2": "B2: Upper-intermediate", "C1": "C1: Advanced", "Native": "Native: real spoken German",
}
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
    "chinese (simplified)": "🇨🇳 中文", "chinese": "🇨🇳 中文",
}


def is_english_language(lang):
    return (not lang) or lang.strip().lower() in ("english", "en", "englisch")


def language_label(lang):
    """(display label with flag, is_rtl) for the translation section header."""
    key = (lang or "").strip().lower()
    return _LANG_LABELS.get(key, "🌐 %s" % (lang or "English")), key in _RTL_LANGS


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
