# Changelog

All notable changes to **Tarkib** are listed here, newest first.
Versions follow [SemVer](https://semver.org/).

## [1.0.0], first public release

One typed German word or phrase becomes a complete Anki card.

- **The card:** meaning and a natural translation, a casual and a formal example sentence (each
  translated), a short explanation, a related image, memory emojis, and audio for the German and
  the translation.
- **Grammar that matters:** article, plural and genitive for nouns; correct strong-verb forms
  (fahren, fuhr, ist gefahren); and grammar patterns taken from the card's own sentences, with
  verb + preposition + case first, for example `warten auf (+Akk)`.
- **Levels:** A1, A2, B1, B2 and C1 with level-appropriate vocabulary and sentence length, plus
  a Native level for real spoken German.
- **Cloze companion:** an optional fill-in-the-blank card with a typing box, a Check button that
  shows which letters are right, and a hint for AnkiDroid users on turning on the keyboard.
- **Languages:** the helper text can be one of 24 languages, with an optional second language on
  every card. Arabic is always Modern Standard Arabic. Every language has a voice you can preview.
- **Bring your own key:** Groq (free, the default), OpenAI, Gemini, OpenRouter, Mistral, Anthropic,
  a local Ollama model, or any OpenAI-compatible server. Keys stay on your computer and go only to
  the provider you chose.
- **Images:** Pexels, Pixabay or Serper with an optional key, and free keyless Openverse images
  otherwise.
- **Safety nets:** input that is not German is refused, a typo asks "Did you mean ...?", unknown
  helper languages fall back to English with a notice, and a failed image, audio or translation
  never stops the card from being added.
- **Five ways in:** the Tools menu, `Ctrl+Shift+G`, the editor button, the Decks screen and the
  top toolbar.
- Works with Anki 23.10 and newer. Pure Python, nothing to install.

[1.0.0]: https://github.com/saadel123/tarkib/releases/tag/v1.0.0
