# Tarkib: AI German, English and Spanish flashcards for Anki

### One German, English or Spanish word. A complete, well-structured Anki card.

> A free, open-source Anki add-on that turns one typed word into a full language card: meaning and a natural translation, a related image, memory emojis, audio, a casual and a formal example sentence, and the grammar that actually matters.

[![AnkiWeb: 83323714](https://img.shields.io/badge/AnkiWeb-83323714-3f4d99)](https://ankiweb.net/shared/info/83323714)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Anki](https://img.shields.io/badge/Anki-%E2%89%A523.10%20%28PyQt6%29-5866c4)](https://apps.ankiweb.net/)
[![Support me on Ko-fi](https://img.shields.io/badge/%E2%99%A5-Support%20me%20on%20Ko--fi-ff5e5b)](https://ko-fi.com/tarkib)
[![Free A1 German deck](https://img.shields.io/badge/German%20decks-Free%20A1-3f4d99)](https://ko-fi.com/s/ab96fd15d8)

![Tarkib demo: type one word in German, English or Spanish, click Add, and study the finished card with its photo, sentences, grammar and audio](assets/demo.gif)

## The story

I've been using Anki for a few years to learn languages. I found a card format that works for me. **Front:** the word. **Back:** the meaning, a related image, a couple of emojis that help me remember it, audio, and two example sentences, one casual and one formal. Verbs always come with their preposition and case, like "warten auf" with the Akkusativ, because that is what you need when you speak.

The problem was making those cards. I typed everything in by hand, made the audio with a separate TTS tool, searched for an image and uploaded it, then asked an AI if my example sentence was even correct. One card took me ten to fifteen minutes.

As a developer, I wanted to use that skill to build something that helps me with this. So I started planning and thinking about a tool that could do the slow parts for me, and after a while it turned into this add-on.

Now I type one word, pick the level (A1 to C1, or Native for real spoken German) and the language I want for the translation on the back, even a second one if I like. Tarkib builds the whole card with the image, audio, example sentences and grammar, plus a cloze card where I type the missing word, if I want one. I still check each card myself.

## How it works

![The Tarkib window: type one word, pick the language, a deck and a level, and click Add](assets/tarkib-window.gif)

1. Install it from [AnkiWeb](https://ankiweb.net/shared/info/83323714): in Anki, **Tools → Add-ons → Get Add-ons**, paste the code `83323714` and restart Anki.
2. Add your free keys in **Settings**: a Groq key writes the cards (free, no credit card), and a Pixabay key adds the photos (free, optional, but without one many cards get no photo). The [setup guide](https://tarkib-anki.pages.dev/docs/addon-install) shows every step with screenshots, about five minutes.
3. Open Tarkib with **Tools → "Add a card with Tarkib"**, `Ctrl+Shift+G`, or the Tarkib button in the editor, the Decks screen or the top toolbar. Type one word or phrase, pick German, English or Spanish, a deck and a level, and click **Add**. About 15 to 20 seconds later the card (and the optional cloze companion) is in your collection, with image and audio.

Create on the desktop, study anywhere: the cards are normal Anki notes and media, so they sync and study fully on AnkiDroid and iOS like any other deck. The generator runs on Anki Desktop only (the mobile apps do not run add-ons).

## What you get

![A finished Tarkib card with its parts numbered and explained: the word, the meaning and level, article and plural, a photo, two example sentences, the grammar patterns, a short explanation and the translation](assets/card-explained.png)

Type one word, get a full card:

- **Meaning and a natural translation**, in your helper language.
- **A casual and a formal example sentence**, each translated, so you learn when to use the word, not just what it means.
- **The grammar learners actually trip on:** in German, article, plural, and (from B1) genitive for nouns, the correct past forms of strong verbs, and for verbs the preposition with its case, like `warten auf` with Akkusativ. In English, irregular verbs and plurals, uncountable nouns, and the patterns that come with a word, like `depend on`, `interested in` or `look forward to + -ing`. In Spanish, a noun with its article and plural, a verb with its yo form, preterite and participle, irregular ones included (tener, tengo, tuvo, tenido), and patterns like `pensar en`, `tener que + infinitivo` or `es importante que + subjuntivo`.
- **A real image and a couple of memory emojis** tied to the word, so it has something to hook onto.
- **Audio in the language you learn**, so you hear how the word and the sentences sound. The translations are read aloud only if you turn on their voices in **Settings, Languages**.
- **An optional fill-in-the-blank (cloze) companion card**, to practice producing the word, not just recognizing it.
- **Sentences that match your level:** A1 to C1, plus a "Native" style for real spoken German, English or Spanish.

## German, English and Spanish

Pick the language of the card in the **Language** row, above the deck. English cards go to their own deck, "Tarkib English", and Spanish cards to "Tarkib Spanish", unless you pick another, and every deck remembers the language of its cards: pick a deck where you made English cards, and the window switches to English. The window opens where you made your last card.

English cards contrast everyday words and contractions with formal words (get and receive), since English has one "you". They use American spelling, or British spelling when a British voice reads them. Spanish cards contrast tú with usted, and use the Spanish of Spain, or Latin American Spanish when a Latin American voice reads them. The cloze card can drill ser and estar, or por and para. In **Settings, Languages**, pick the language you learn first: its voice, its translation language and its second translation are kept separately, so German cards can stay in English while English cards come in Arabic.

## Translation languages

The translation under the word can be any of **24 languages**. German and Spanish cards start in English. English cards cannot be translated into English, so their list has German instead: they use your German cards' translation language until you pick their own, and if that is English, the window asks you to pick one. Optionally add a **second language** on every card, for example English plus Arabic for a bilingual learner.

Every language has a natural Microsoft voice. The translations stay silent until you pick their voices in **Settings, Languages**. Press **▶** next to a voice to hear a sample sentence before you decide.

The Microsoft Edge voices are free and need no key. If you prefer, **Settings, Voice** lets Azure AI Speech, ElevenLabs, OpenAI, Google Cloud or Gemini read your cards instead, with your own key, and each has a Test button. If your voice service fails, Tarkib tries your other services, then the free Edge voices, and tells you which one read the card.

In **Settings, Voice**, the speech speed can be slower, about 20 percent, at A1 and A2 or at every level. Only the language you learn is slowed, on new cards. The translations keep the normal speed.

## Your style

In **Settings, Cards**, you can write a few wishes in any language: the topics, names, tone or length you want, for example "examples about cooking and travel, short sentences". While **Use my style** is ticked in the Tarkib window, Tarkib sends them with every card, in every language. The level and the card's rules stay as they are.

## Ready-made German decks (A1 is free)

![Tarkib German decks, A1 to C1: word cards and typing cards](assets/decks.gif)

Rather not make the cards yourself? I made German decks, A1 to C1, in the same card format. Every word has a picture, German audio, casual and formal sentences, and the grammar pattern with its case when the sentence has one, like `fahren mit (+Dat)`. Nouns come with their article, and the plural when there is one. Nearly every word also has a typing card checked letter by letter. Meanings in English or Arabic. The cards were made with Claude, Anthropic's AI, then reviewed and fixed by a person, card by card, over several rounds. The audio comes from a licensed voice service, and the pictures are licensed too.

**[Get the whole A1 level for free](https://ko-fi.com/s/ab96fd15d8)** (305 word cards plus 304 typing cards). The English edition is also on [AnkiWeb Shared Decks](https://ankiweb.net/shared/info/255858872). Other levels are in [my Ko-fi shop](https://ko-fi.com/tarkib/shop). You could build them yourself with Tarkib, but A2 to C1 is 1,814 word cards: on the free Groq plan, which allows a few dozen cards a day, that takes well over a month, and every card still needs checking. The paid levels are those cards already made and reviewed.

## Cost, keys and privacy

Tarkib is free and open source, with no account and no server of mine in between. It runs on your own key. The default is a free model on Groq, enough for a few dozen cards a day, and OpenAI, Google Gemini, Anthropic, Mistral, OpenRouter or a local Ollama model work too.

Your keys stay on your computer, are never synced, and each one goes only to its own service. The words you learn, and a translation only when its voice is on, go to the voice service that reads them: Microsoft's Edge read-aloud service by default, or the one you set up in **Settings, Voice**. Nothing is sent to me. The Edge read-aloud service is not an official API, so it can change without notice. If it does, the card is still made, Tarkib tells you why it has no sound, and a voice service with your own key can take over.

## A note on quality

The cards are written by a language model, so they are occasionally wrong, mostly with rarer words. Treat each card as a draft you approve: look it over after it is added and edit it like any other note. That takes seconds. Building the card by hand took ten to fifteen minutes.

## Contributing

Contributions are welcome, **especially improving the cards for more languages and CEFR levels**. See **[CONTRIBUTING.md](CONTRIBUTING.md)** for the dev setup and where the prompt and level rules live (`pipeline/prompts.py`). Version history is in **[CHANGELOG.md](CHANGELOG.md)**, and what is planned next in **[ROADMAP.md](ROADMAP.md)**. The code was built with a lot of help from Claude, Anthropic's AI.

## Support

This add-on is free and stays free. If it saves you time, you can support its development:

**[♥ Support me on Ko-fi](https://ko-fi.com/tarkib)**

Buying one of the [ready-made decks](https://ko-fi.com/tarkib/shop) helps too.

Inside the add-on there is a small "♥ Support this add-on" link and a quiet "Free A1 deck" link in the window footer, which becomes "A1 to C1 decks" once you have one of the decks. A short thank-you appears three times, at 50, 200 and 500 cards, with a permanent "Don't show this again". After your fifth card, a short note about the ready-made decks appears inside the window on up to three openings, and its x hides it for good. At the bottom of the Settings "Cards" tab, one line points to the ready-made decks. While no AI key is set, the setup message also says that the free A1 deck needs no key. The decks teach German, so these deck pointers show only while the window or Settings is on German.

## License

[MIT](LICENSE) © 2026 saadel123. Free to use, modify, and share. One file is not MIT: `pipeline/edge_drm.py`, the token for the free Edge voices, comes from [edge-tts](https://github.com/rany2/edge-tts) and stays under the LGPL-3.0 (see [licenses](licenses/README.md)).
