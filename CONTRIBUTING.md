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
    dialog.py           the Add-card dialog
    settings.py         tabbed Settings (Provider, Images, Languages, Cards)
    support.py          the Support link, the footer decks link (Free A1, then A1 to C1), the thank-you, the decks text
    promo_rules.py      when those may show (pure functions, tested offline)
  pipeline/             pure, Anki-free, stdlib-only: the brains
    prompts.py          ALL prompts, CEFR levels, translation languages   <- most contributions land here
    generate.py         builds a card: LLM calls, guards, HTML, image and audio
    providers.py        OpenAI-compatible and Anthropic clients (urllib), friendly error messages
    images.py           Pexels, Serper, Pixabay and keyless Openverse, as a fallback chain
    audio.py            pure-Python Edge read-aloud client
  tests/test_guards.py  offline unit tests (no Anki, no network, no key)
  assets/               README images (demo GIF, Tarkib window, decks preview, cover), never packaged
  ROADMAP.md            what is planned, and the principles a new feature must keep
```
The `pipeline/` package never imports Anki, so you can test it standalone.

## How a card gets made
1. **The dialog** collects the word, level, deck and options, then runs the pipeline in a
   background `QueryOp` so Anki never freezes.
2. **`generate.build_card`** makes up to four LLM calls (plus one strict retry when a check fails):
   - **MAIN** (every level): translation, casual and formal example sentences, explanation,
     image keyword, emojis, and for A1 to C1 also the grammar patterns and morphology (article,
     plural, strong-verb past forms). Folding these into one call keeps free-tier rate limits happy.
   - **GRAMMAR** (Native level only): the grammar patterns.
   - **SECONDARY** (only when a second helper language is set): the second translation.
   - **CLOZE** (when the cloze toggle is on): the fill-in-the-blank companion card.
3. **Deterministic guards** re-check the model's output: the input must be German (a typo becomes
   a "Did you mean ...?" question), the helper language must be a known one, every grammar pattern
   must literally occur in the example sentences and must not be the sentence itself, patterns are
   ordered by teaching value (verb + preposition + case first), and A1 to C1 German is checked for
   English leaks. Every model string is HTML-escaped before it reaches the card, and tags are
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

## The best place to contribute: languages and level quality (`pipeline/prompts.py`)
This is where the card *quality* lives, and where help is most valuable:

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

## Other good contributions
- **Image providers** (`pipeline/images.py`): add a `fetch_<provider>` (the provider must permit
  downloading and embedding the image), a `test_<provider>`, and slot it into the fallback chain.
  Reject non-photo content (see `_looks_like_raster`).
- **Bug fixes**, clearer error messages, accessibility, translations of the UI strings.
- **Features from the [roadmap](ROADMAP.md).** Open an issue first so the approach can be agreed
  before you build it.

## Testing before a PR
- `python3 tests/test_guards.py`: the offline unit tests, about a second, no key needed.
- `python3 -m py_compile $(git ls-files '*.py')`: must be clean.
- Live-test with your own key: restart Anki and add a card at the level you changed.
- `python3 build.py` if you touched packaging, then check the file list it prints.
- Describe your **test steps** in the PR.

## Pull requests
- Keep PRs small and focused (one feature or fix).
- Explain *what* and *why*, and include example output for prompt or language changes.
- Match the surrounding style: 4-space indent, stdlib only, Qt touched only on the main thread.

By contributing, you agree your contributions are licensed under the project's [MIT License](LICENSE).
