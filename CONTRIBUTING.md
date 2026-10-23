# Contributing to Tarkib

Thanks for wanting to help. This is a **free** Anki add-on that turns a typed word into a rich,
level-appropriate flashcard (image, audio, example sentences) using an AI provider you bring your
own key for (BYOK). Contributions are very welcome, **especially making the cards better for more
languages and levels**.

## Ground rules (please read)
- **Never commit an API key.** Your keys live in `meta.json` (git-ignored). Don't paste a real key
  into code, tests, issues, or screenshots. If a key ever lands in a commit, rotate it immediately.
- **Card-adding must never break.** Grammar, translation, image and audio are *best-effort*: a
  failure there is recorded as a warning and the card still lands. Keep that contract when you
  change the pipeline.
- **Pure Python standard library only.** No `pip` dependencies, no compiled deps, no `ffmpeg`.
  It must run inside Anki's bundled Python on macOS, Windows and Linux out of the box.
- **Plain punctuation in text the user sees** (labels, dialogs, toasts, card text): no em or en
  dashes and no exclamation marks. Use a comma, a period, or a colon.
- Be kind and constructive in issues and reviews.

## Dev setup
1. Clone the repo.
2. Symlink this repository into Anki's `addons21/`. The repo root IS the add-on, so link the repo
   folder itself, and name the link after the manifest `package` (`tarkib`):
   - **macOS:** `ln -s "$(pwd)" ~/Library/Application\ Support/Anki2/addons21/tarkib`
   - **Linux:** `ln -s "$(pwd)" ~/.local/share/Anki2/addons21/tarkib`
   - **Windows:** `mklink /D "%APPDATA%\Anki2\addons21\tarkib" "%CD%"` (in a terminal run as
     administrator, or with Developer Mode switched on)

   If you move or rename the repo folder, the symlink breaks and Anki silently drops the add-on.
   Recreate the link after any such move.
3. Restart Anki, then **Tools, "Add a card with Tarkib"** (or the Tarkib button in the editor).
   Open **Settings**, paste a free **Groq** key (and optionally a free Pexels or Pixabay key), Save.
4. Add a card to test. On any error the add-on shows a **copyable** dialog: paste that into issues.

Anki loads add-on code at startup, so **restart Anki after every code change**.

## How the code is laid out
```
tarkib/                 (the repository root)
  __init__.py           Anki hooks: Tools menu, shortcut, editor button, Decks screen, top toolbar
  manifest.json         AnkiWeb manifest (package "tarkib", Anki 23.10 or newer)
  config.json           default settings, documented in config.md (Anki's Config button opens Settings)
  notetypes.py          creates and updates the note types (presentation only, never your fields)
  anki_io.py            writes a card into the collection (media and notes, one undo entry)
  build.py              packages out/tarkib.ankiaddon from an allowlist of runtime files
  icons/tarkib.svg      the toolbar icon
  ui/
    dialog.py           the Add-card dialog (the Language row, the deck, the level, the banners)
    settings.py         tabbed Settings (Provider, Images, Languages, Voice, Cards)
    lang_rules.py       which language and deck the window starts with, where a switch moves it (pure)
    support.py          the Support link, the footer decks link (Free A1, then A1 to C1), the thank-you, the decks text
    promo_rules.py      when those may show (pure functions, tested offline)
  pipeline/             pure, Anki-free, stdlib-only: the brains
    languages.py        the learning languages: one registry, every per-language table is keyed by it
    prompts.py          ALL prompts, CEFR levels, translation languages   <- most contributions land here
    english.py          English as a learning language: its prompt pieces (NOTE) and checks (CHECKS)
    generate.py         builds a card: LLM calls, guards, HTML, image and audio
    providers.py        OpenAI-compatible and Anthropic clients (urllib), friendly error messages
    images.py           Pexels, Serper, Pixabay and keyless Openverse, as a fallback chain
    audio.py            pure-Python Edge read-aloud client
    tts.py              the voice services (Edge, Azure, ElevenLabs, OpenAI, Google, Gemini) and their backups
    edge_drm.py         the token for the free Edge voices, from edge-tts (LGPL-3.0)
  tests/                offline tests (no Anki, no network, no key): guards, voices, golden cards and
                        prompts, the languages; ui_check.py opens the real windows under Anki's Python
  assets/               README images (demo GIF, Tarkib window, decks preview, cover), never packaged
  ROADMAP.md            what is planned, and the principles a new feature must keep
```
The `pipeline/` package never imports Anki, so you can test it standalone.

## How a card gets made
1. **The dialog** collects the word, the learning language, the level, the deck and the options,
   then runs the pipeline in a background `QueryOp` so Anki never freezes.
2. **`generate.build_card`** takes every prompt from `prompts.PROMPTS[language]` and every
   language-dependent check from `generate.RULES[language]`, and makes up to four LLM calls (plus one
   strict retry when a check fails):
   - **MAIN** (every level): translation, casual and formal example sentences, explanation,
     image keyword, emojis, and for A1 to C1 also the grammar patterns and morphology (article,
     plural, strong-verb past forms). Folding these into one call keeps free-tier rate limits happy.
   - **GRAMMAR** (Native level only): the grammar patterns.
   - **SECONDARY** (only when a second helper language is set): the second translation.
   - **CLOZE** (when the cloze toggle is on): the fill-in-the-blank companion card.
3. **Deterministic guards** re-check the model's output: the input must be in the card's language
   (a typo becomes a "Did you mean ...?" question), the helper language must be a known one, every grammar pattern
   must literally occur in the example sentences and must not be the sentence itself, patterns are
   ordered by teaching value (verb + preposition + case first), and from A1 to C1 the card's
   language is checked for words of the translation language leaking in. Every model string is HTML-escaped before it reaches the card, and tags are
   stripped of markup. API keys only travel over https (plain http only to localhost) and never
   follow a redirect to another host.
4. **Image and audio** are fetched (best-effort) and the card is returned as a plain *bundle*:
   field HTML with `@@TOKEN@@` placeholders plus the media bytes.
5. **`anki_io.write_bundle`** runs in a `CollectionOp`: it writes the media, swaps the placeholders
   for the real file names Anki chose, and adds the note(s) as a single undo step.

Rules that keep this stable:
- **Every main prompt returns the same JSON keys.** The renderer and the note types depend on
  them. Change the wording freely, but never rename or drop a key in one prompt only.
- **Template changes bump `TEMPLATE_VERSION`** in `notetypes.py`, so existing users get the new
  design once. Never touch fields or card contents from there.
- **Threading:** network and audio in `QueryOp(...).without_collection()`, collection writes in a
  `CollectionOp`, Qt only on the main thread.

## Content rules (every generated card)
These are deliberate product rules. A prompt change that breaks one of them is a regression.

1. **No alcohol or pork** in example sentences or emojis. Use neutral items instead (water, juice,
   coffee, tea, chicken, beef, vegetables). The only exception is when the user's word itself is
   such a term.
2. **Arabic is Modern Standard Arabic only**, never a dialect, without diacritics.
3. **Images are classroom-safe.** The image keyword describes a wholesome scene, and people are
   modestly dressed. For a person word ("die Frau") the search is an activity, not the bare
   person. Abstract words picture the example sentence.
4. **Preposition + case at every level.** Whenever a sentence uses a verb with a preposition or a
   case-governing preposition, the grammar patterns name it with its case, for example
   `warten auf (+Akk)`. The English patterns are English only and carry no case marker.
5. **Exam-clean German from A1 to C1.** No Denglisch (Besprechung, not Meeting). Established
   loanwords such as Computer or Bus are fine. Denglisch is expected only at the Native level.
6. **Correct strong-verb forms.** Präteritum uses the real ablaut (fahren gives fuhr, never fahrte).

English cards keep rules 1 to 3 and their own versions of 4 to 6: a verb, adjective or noun with its
fixed preposition is always a pattern, written as a frame ("depend on something", "look forward to +
-ing"), never a piece of the sentence; standard English that fits the level from A1 to C1, slang only
at Native, American or British as the voice decides; irregular verbs and plurals always right (buy,
bought, bought), never a regularized form.

## The best place to contribute: languages and level quality
This is where the card *quality* lives, and where help is most valuable. German's tuned prompts are
in `pipeline/prompts.py`, English's prompt pieces and checks in `pipeline/english.py`:

- **CEFR levels (A1 to C1, plus Native):** `LEVELS`, `LEVEL_RULES`, and
  `system_main_for_level(level)`. Each level is a block of constraints (vocabulary, sentence
  length, tenses, grammar). Improving a level means editing its rule string. Keep A1 and A2 short
  and simple.
- **Translation language (the helper shown under the German):** `translation_override(lang)`,
  `language_label(lang)`, `COMMON_TRANSLATION_LANGS`. To add a language, add it to
  `COMMON_TRANSLATION_LANGS` and `_LANG_LABELS` in `prompts.py` (and `_RTL_LANGS` if it is written
  right to left), give it voices in `audio._SECONDARY_LOCALES` and a sample sentence in
  `audio.VOICE_SAMPLES`, and optionally short names ("ar", "farsi") in `generate._LANG_ALIASES`.
- **Per-language correctness rules** are a great contribution: targeted instructions that catch
  that language's common AI mistakes. Pair the prompt change with example outputs in your PR.

When you change a prompt, **show before and after example cards** for a couple of words in the PR.
Nobody can eyeball every language, so concrete samples are how quality gets judged.

## Adding a learning language (`pipeline/languages.py`)
A learning language is the one the cards teach (German, English). It is declared once:

1. **Its registry entry** in `pipeline/languages.py`, every field filled: names, the card label, the
   quotes, the default voice and the voice locales, the words dropped from the front of a headword,
   the formal tag, the script, the example word and the default deck.
2. **Its tables:** `prompts.PROMPTS[code] = prompts.generic_prompts(code)` and
   `generate.RULES[code] = generate.generic_rules(code)`. Until both exist, `tests/test_languages.py`
   fails and names the missing table. With nothing more, the language already makes cards from the
   generic prompt set (a test builds a whole card for a made-up language this way).
3. **Make it good**, in `pipeline/<language>.py` like `pipeline/english.py`: a `NOTE` (the level rules,
   the casual and formal contrast, the pattern order and format, the word line, the cloze cases),
   registered in `prompts.NOTES`, and `CHECKS` (the word line renderer, the pattern ranking and
   anchoring, the leak check), passed to `generic_rules`. Write it from the mistakes learners of that
   language make, not from a grammar book: the model knows the grammar.
4. **Its tests:** scenarios with `language=<code>` in `tests/card_scenarios.py`, then
   `UPDATE_GOLDEN=1 python3 tests/test_cards.py` to write their golden files. Read every new golden
   file, and look at the cards in `tests/preview_cards.py`. Add its frozen prompts to
   `tests/test_prompts.py` and a `tests/test_<language>.py` for its checks.
5. **Real cards** before anything ships: about ten words over every level, checked by a person who
   knows the language. The Add window and Settings need nothing more: the registry fills them.

## Other good contributions
- **Image providers** (`pipeline/images.py`): add a `fetch_<provider>` (the provider must permit
  downloading and embedding the image), a `test_<provider>`, and slot it into the fallback chain.
  Reject non-photo content (see `_looks_like_raster`).
- **Bug fixes**, clearer error messages, accessibility, translations of the UI strings.
- **Features from the [roadmap](ROADMAP.md).** Open an issue first so the approach can be agreed
  before you build it.

## Testing before a PR
- `python3 -m unittest discover -s tests`: every offline test, about a second, no key needed. Run
  it with Anki's own Python too, which adds the check of the real windows (`tests/ui_check.py`).
- A card or prompt changed on purpose: `UPDATE_GOLDEN=1 python3 tests/test_cards.py` (or
  `tests/test_prompts.py`), then read `git diff tests/golden` line by line and commit it with the change.
- `python3 -m py_compile $(git ls-files '*.py')`: must be clean.
- Live-test with your own key: restart Anki and add a card at the level you changed.
- `python3 build.py` if you touched packaging, then check the file list it prints.
- Describe your **test steps** in the PR.

## Pull requests
- Keep PRs small and focused (one feature or fix).
- Explain *what* and *why*, and include example output for prompt or language changes.
- Match the surrounding style: 4-space indent, stdlib only, Qt touched only on the main thread.

By contributing, you agree your contributions are licensed under the project's [MIT License](LICENSE), except changes to `pipeline/edge_drm.py`, which stay under the LGPL-3.0 (see [licenses/README.md](licenses/README.md)).
