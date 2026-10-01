# Tarkib: configuration

You normally do not need this page. Anki's **Config** button for Tarkib opens its **Settings** dialog, a proper form with dropdowns and a key test, and so does **Settings…** in the add-on window (Tools, "Add a card with Tarkib"). This page documents the raw settings behind that dialog, for power users. The Settings dialog overwrites the keys it manages when you press Save there.

All values stay on your computer (Anki's add-on config, `meta.json`). They are never synced and never sent to the developer. Bring your own API keys.

- **providers**: one entry per AI service you have a key for. `type` is `openai_compatible` (Groq, OpenAI, OpenRouter, Gemini, Mistral, Ollama, and any compatible server, selected by `base_url`) or `anthropic`. Set `model` and `api_key`. A `base_url` must start with `https://`, plain `http://` is accepted only for a server on your own computer (localhost, for example Ollama). The first entry is the one the Settings dialog edits, and the engine picker in the Add dialog lists every provider that has a key.
- **image.pexels_key**: optional but recommended. Photos for your cards (free key at pexels.com/api). With no image key at all, the add-on tries free keyless Openverse images, which often find nothing, so many cards get no photo.
- **image.pixabay_key**: optional. Another free photo source (pixabay.com/api/docs).
- **image.serper_key**: optional. Google image results, better for IT and technical terms (serper.dev).
- **voices.target**: the German voice (Microsoft Edge read-aloud voice id, no key needed), default `de-DE-KatjaNeural`.
- **voices.translation**: the voice that reads the translation aloud. Default empty: the translation is text only, and only the German is read aloud. To hear it, pick a voice in Settings, Languages, Translation voice, or set a voice id here, for example `en-US-AriaNeural`.
- **voices.secondary**: the voice for the optional second translation. Empty, the default, means no audio: picking a second language keeps it silent until you choose its voice under Settings, Languages.
- **defaults.translation_language**: the helper language shown under the German. Default `English`. It must be one of the 24 languages offered in Settings, for example `Arabic` or `French`. Any other value falls back to English with a warning.
- **defaults.secondary_translation_language**: optional second translation per card, from the same list of 24 languages. Empty means none and the extra call is skipped.
- **defaults.generate_cloze**: default state of the "Generate cloze companion" toggle.
- **defaults.image_source**: `auto` (try the providers you have keys for, then Openverse) or one of `pexels`, `pixabay`, `serper`, `openverse` to try that one first.
- **defaults.default_deck**: deck offered on first run (created only when you add a card). **defaults.last_deck** remembers your last choice.
- **defaults.level**: default CEFR level for new cards: `A1`, `A2`, `B1`, `B2`, `C1`, or `Native`.
- **deck_levels**: optional map of deck name to level, so a deck can pin its own level, for example `{"Deutsch::A1": "A1"}`.
- **timeouts**: HTTP timeouts in seconds (`ai_seconds` 60, `image_seconds` 15, `tts_seconds` 30).
- **stats**: internal counters and switches: `cards_added`, `hide_support_thanks` (true turns off the thank-you shown at 50, 200 and 500 cards), `decks_hint_shows` and `decks_hint_done` (the short note about the ready-made decks, shown at most three times. `decks_hint_done: true` hides it for good). Safe to leave alone.
- **shortcut**: keyboard shortcut that opens the dialog (default `Ctrl+Shift+G`).
- **user_agent**: HTTP User-Agent sent to AI providers. Leave blank to use the built-in browser-like default (needed because Groq sits behind Cloudflare, which blocks the bare Python agent). It is a fixed header, the same for everyone, not a secret.

**Note types.** The add-on creates two note types, `Tarkib` and `Tarkib Cloze`. If your collection already has the `Tarkib German` note types from the ready-made decks, or the older `German AI` / `CustomClozeDE` types from an earlier version, it uses those instead of creating new ones. It manages their card templates and CSS and refreshes them when an update changes the design, so edits you make to those templates in Tools, Manage Note Types will be overwritten on the next update. Your fields and card contents are never touched. If you already had a note type with one of these names before installing, the add-on will ask you to rename it rather than change it.
