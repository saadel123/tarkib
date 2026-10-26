# Changelog

All notable changes to **Tarkib** are listed here, newest first.
Versions follow [SemVer](https://semver.org/).

## [1.3.0]

- **Spanish cards.** Pick Spanish in the Language row: the card gets a casual sentence with tú and a
  formal one with usted, the patterns Spanish learners need (pensar en, tener que + infinitivo, es
  importante que + subjuntivo), a noun with its article and plural, a verb with its yo form,
  preterite and participle, irregular ones included, Spanish audio and the optional cloze card,
  which can also drill ser and estar, or por and para. Spanish cards go to the deck "Tarkib Spanish"
  unless you pick another, with the same levels, A1 to C1 and Native.
- **The Spanish of Spain or of Latin America.** Spanish cards use the Spanish of Spain, or Latin
  American Spanish when a Latin American voice reads them (Settings, Languages, Spanish voice). A
  Mexican, Argentine, Colombian or US voice gets the everyday words of its country.
- **Your style.** In Settings, Cards, write a few wishes in any language: the topics, names, tone
  or length you want. While "Use my style" is ticked in the Tarkib window, they go with every card.
  The level and the card's rules stay as they are.
- **Speech speed.** In Settings, Voice, the language you learn can be read about 20 percent slower,
  at A1 and A2 or at every level. The translations keep the normal speed.
- **Photos with a Pixabay key.** Pexels has paused new keys, so Settings and the Tarkib window now
  suggest a free Pixabay key. A Pexels key you already have keeps working.
- The second translation could go missing on some cards, because its step ran out of room with the
  default AI model. It has enough room now.
- When Microsoft Edge is your only voice service and answers slowly once, the next clips ask again.
  Before, one slow answer left the rest of the card without audio.
- Cards made one after another no longer get the same photo when their picture searches are alike.
- When the picture search finds nothing, Tarkib tries once more and then says the card has no
  picture. Before, the picture was missing without a word.
- A cloze card for a fixed phrase with a small word inside it now blanks the whole phrase, not just
  the small word.
- Special hyphens from the AI are written as a normal hyphen, so Anki's search finds words like
  "rendez-vous".
- On a Native card for a slang word, the formal sentence is now a polite everyday sentence, not a
  formal letter that nobody would write with slang in it.
- A word quoted inside the explanation no longer doubles the opening quote, and German explanations
  close with the German closing quote.
- The casual words in a formal word's hint were hard to read in Anki's light mode. They are dark
  now. Your note types refresh once by themselves.
- A German cloze card whose answer is written in small letters but starts the sentence ("morgen" in
  "Morgen gehe ich einkaufen.") is no longer lost.
- The translated grammar patterns no longer carry case markers like "(+Acc)": the case stays on the
  German pattern.
- The second translation's heading shows its flag and its own name, like the first.
- The messages about a wrong key now name the "Test keys" button by its real name.

## [1.2.0]

- **English cards.** Tarkib now makes cards for learners of English too. Pick English in the new
  Language row above the deck: the card gets a casual and a formal English sentence, the patterns
  English learners need (depend on, interested in, look forward to + -ing, phrasal verbs), the
  irregular forms of verbs and plurals, English audio and the optional cloze card. English cards go
  to the deck "Tarkib English" unless you pick another, and they have the same levels, A1 to C1 and
  Native.
- **American or British English.** English cards use American spelling, or British spelling when
  a British voice reads them (Settings, Languages, English voice).
- **Each language keeps its own settings.** Settings, Languages now starts with "Language you
  learn". The voice, the translation language and the second translation below it belong to that
  language, so German cards can stay in English while English cards come in Arabic. English cards
  can be translated into any of 24 languages, German included. If your German cards are translated
  into English, the Tarkib window asks you to pick another language for your English cards first.
- **Decks remember their language.** Picking a deck where you made English cards switches the window
  to English, and the window opens where you made your last card.
- The link to the free A1 deck, the note about the ready-made decks and the starter decks show only
  while the window is on German, since those decks teach German.
- A phrase that ends in a question or exclamation mark keeps its own mark on the front of the card:
  "Wie spät ist es?" instead of "Wie spät ist es?.".
- When the AI leaves out a sentence or the explanation, the card no longer shows an empty box for it,
  and a card without an emoji no longer starts with a space.
- When the AI sends a grammar pattern in an unusual format, every pattern still sits next to its own
  translation.
- Native cards get their grammar patterns from their own step. With the default AI model that step could run
  out of room, and the card then quietly used the simpler patterns from the main step.
- On Native cards with a translation language other than English, the patterns are now translated into that
  language. Before, they came in English even when the box said Arabic.
- Arabic translations never show diacritics, on every part of the card. Before, only the second
  translation was cleaned.
- In Settings, a language changed while the voice list was still loading for the first time could
  get the previous language's voice back. It keeps its own now.

## [1.1.0]

- **Audio works again.** Since 13 October 2026, Microsoft refuses the old way the free Edge voices
  were asked for audio, so cards came out without sound. Tarkib now uses the new token. If your
  computer's clock is off, it corrects itself from Microsoft's answer and tries again.
- **A card never goes silent without telling you.** Each voice request has a time limit and one
  retry. When audio fails, the Add window says why, for example "Microsoft Edge refused the
  connection: HTTP 403 Forbidden", and keeps the reason on screen until a card gets all its audio
  again. The add-on log in Anki's logs folder has the details.
- **Choose who reads your cards aloud,** in the new Settings tab Voice: Microsoft Edge (free, no
  key, the default), Azure AI Speech (official Microsoft voices, same names, free tier), ElevenLabs,
  OpenAI, Google Cloud or Gemini, each with your own key. Every service has a Test button that plays
  a short sample. If your service fails, Tarkib tries the other services you set up, in your order,
  then Microsoft Edge, and tells you which one read the card.
- Audio file names now come from the spoken text, the voice service and the voice, so a re-added
  card reuses its file and a clip never takes another clip's name. Gemini audio is saved as WAV.
- The token code comes from edge-tts and keeps its LGPL-3.0 license, see `licenses/README.md`.
  Everything else stays MIT.

## [1.0.2]

- **Only the German is read aloud by default.** The translation and the optional second language
  start without a voice. Turn either on under Settings, Languages. If you already use Tarkib, your
  current setting is kept. A voice set to (none) now stays off when you change the language or
  refresh the voice list.
- Once a ready-made deck is in your collection, the "Free A1 deck" link next to "Support this
  add-on" becomes "A1 to C1 decks" and opens the shop with every level. It used to disappear.
- **The Tarkib window fits its content at once.** After you add your keys in Settings, set the
  second language to (none), or close the note about the ready-made decks with x, the window no
  longer keeps an empty band, so you do not have to close and reopen it. If you drag it taller,
  the extra space sits above the buttons, and a maximized window stays maximized.
- **Saved settings show up right away,** even when you close Settings with Cancel or x after the
  first Save (on a fresh install it stays open while models load), and when you save from Anki's
  Add-ons screen (Config) while the Tarkib window is open.
- **A new default level applies to the next card** right after "Change default", instead of after
  reopening the window. If the default stays the same, a level you picked by hand for the session
  is kept.
- The window opens with the cursor in the word field, also when the note about the ready-made
  decks is showing.
- Settings, Images: the note now says a free Pexels key gives photos on most cards. It no longer
  promises a photo on every card.

## [1.0.1]

- **Free A1 deck pointers, quiet by design.** A "Free A1 deck" link sits next to "Support this
  add-on" in the window footer and hides once the ready-made decks are imported. After your fifth
  card, a short note inside the window mentions the decks. It shows on at most three openings of
  the window, and x hides it for good. While no AI key is set, the setup banner mentions that the
  free A1 deck needs no key.
- **The thank-you now appears three times in total** (at 50, 200 and 500 cards) instead of every
  50 cards, without emoji, and offers a link to rate Tarkib on AnkiWeb. "Don't show this again"
  still turns it off for good.
- Settings, Cards: the decks line now says the other levels are paid and links to all of them.
- Wording: the no-image-key note no longer promises a photo on every card.

## [1.0.0], first public release

One typed German word or phrase becomes a complete Anki card.

On AnkiWeb: [83323714](https://ankiweb.net/shared/info/83323714) (Tools, Add-ons, Get Add-ons, paste the code).

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

[1.3.0]: https://github.com/saadel123/tarkib/releases/tag/v1.3.0
[1.2.0]: https://github.com/saadel123/tarkib/releases/tag/v1.2.0
[1.1.0]: https://github.com/saadel123/tarkib/releases/tag/v1.1.0
[1.0.2]: https://github.com/saadel123/tarkib/releases/tag/v1.0.2
[1.0.1]: https://github.com/saadel123/tarkib/releases/tag/v1.0.1
[1.0.0]: https://github.com/saadel123/tarkib/releases/tag/v1.0.0
