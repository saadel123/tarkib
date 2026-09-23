"""The Add-Card dialog: form -> QueryOp(pipeline) -> CollectionOp(write) -> done.

A hardcoded test word ("die Probe") is prefilled for the first-run end-to-end test.
Network/audio run off the UI thread (QueryOp); the collection write runs in a CollectionOp.
"""
import traceback

from aqt import mw
from aqt.qt import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, QComboBox,
    QCheckBox, QPushButton, QLabel, Qt,
)
from aqt.utils import qconnect, tooltip, showText, getText, askUser
from aqt.operations import QueryOp, CollectionOp

from .. import anki_io
from ..pipeline import generate, audio, providers, prompts
from .support import support_link, note_card_added_and_maybe_thank

FIELD_MIN_W = 340            # text inputs grow to at least this wide


def _cfg():
    return mw.addonManager.getConfig(__name__) or {}


class AddCardDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add a card with Tarkib")
        self.setMinimumWidth(560)
        self.cfg = _cfg()
        defaults = self.cfg.get("defaults", {}) or {}

        layout = QVBoxLayout(self)

        title = QLabel("Tarkib")
        title.setStyleSheet("font-size: 16px; font-weight: 700;")
        layout.addWidget(title)

        # First-run / misconfig banner.
        self.banner = QLabel()
        self.banner.setWordWrap(True)
        self.banner.setStyleSheet("background:#7f1d1d;color:#fff;padding:8px;border-radius:6px;")
        layout.addWidget(self.banner)
        # Informational notes (e.g. keyless image fallback) get a neutral look, so red stays
        # reserved for the one state that actually blocks adding (no AI key).
        self.info_banner = QLabel()
        self.info_banner.setWordWrap(True)
        self.info_banner.setStyleSheet("background:rgba(100,116,139,0.18);padding:8px;border-radius:6px;font-size:12px;")
        layout.addWidget(self.info_banner)

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        self.word_edit = QLineEdit()
        self.word_edit.setPlaceholderText("e.g. die Probe")
        self.word_edit.setMinimumWidth(FIELD_MIN_W)
        form.addRow("Word / phrase", self.word_edit)

        # Deck: editable combo + an "Add deck" button beside it (combo a bit narrower).
        # We list only the user's real decks — no taxonomy is imposed. The chosen deck is
        # created lazily at write time. Preselect the last-used deck; on first run fall back
        # to the single configured default (created only when the user actually adds a card).
        deck_row = QHBoxLayout()
        self.deck_combo = QComboBox()
        self.deck_combo.setEditable(True)
        decks = sorted({d.name for d in mw.col.decks.all_names_and_ids()})
        default_deck = (defaults.get("default_deck") or "Tarkib").strip()
        if default_deck and default_deck not in decks:
            decks.insert(0, default_deck)
        self.deck_combo.addItems(decks)
        last_deck = (defaults.get("last_deck") or "").strip()
        self.deck_combo.setCurrentText(last_deck if last_deck in decks else default_deck)
        add_deck_btn = QPushButton("Add deck")
        add_deck_btn.setToolTip("Create a new deck if the one you want isn't listed")
        qconnect(add_deck_btn.clicked, self._add_deck)
        deck_row.addWidget(self.deck_combo, 1)
        deck_row.addWidget(add_deck_btn, 0)
        form.addRow("Deck", deck_row)

        self.meaning_edit = QLineEdit()
        self.meaning_edit.setPlaceholderText("optional: which sense, e.g. to turn off (devices). Any language is fine")
        self.meaning_edit.setToolTip("Use this only when a word has several meanings, to pick the one you "
                                     "want taught. You can write it in any language.")
        self.meaning_edit.setMinimumWidth(FIELD_MIN_W)
        form.addRow("Meaning hint", self.meaning_edit)

        self.scenario_edit = QLineEdit()
        self.scenario_edit.setPlaceholderText("optional: scene for the example sentences. Any language is fine")
        self.scenario_edit.setToolTip("Sets the scene for the example sentences (work, travel, family, and "
                                      "so on). You can write it in any language.")
        self.scenario_edit.setMinimumWidth(FIELD_MIN_W)
        form.addRow("Scenario hint", self.scenario_edit)

        self.image_edit = QLineEdit()
        self.image_edit.setPlaceholderText("optional: describe the picture you want (any language)")
        self.image_edit.setToolTip("Describe the picture you want on the card. The app turns it into a safe "
                                    "image search for you, so any language works.")
        self.image_edit.setMinimumWidth(FIELD_MIN_W)
        form.addRow("Image keyword", self.image_edit)

        self.engine_combo = QComboBox()
        self.engine_form = form
        self._providers = [p for p in (self.cfg.get("providers") or []) if (p.get("api_key") or "").strip()]
        for p in self._providers:
            self.engine_combo.addItem(p.get("name") or p.get("id") or p.get("type"))
        form.addRow("Engine", self.engine_combo)
        self._set_engine_visible(len(self._providers) >= 2)  # only useful with 2+ providers

        # CEFR level: stores the language-agnostic code as item data; shows a friendly label.
        # Starts at the per-deck default if one is configured, else the global default.
        level_row = QHBoxLayout()
        self.level_combo = QComboBox()
        for code in prompts.LEVELS:
            self.level_combo.addItem(prompts.LEVEL_LABELS.get(code, code), code)
        self._set_level(self._resolve_level(self.deck_combo.currentText().strip()))
        qconnect(self.deck_combo.currentTextChanged, self._on_deck_changed)
        change_default_btn = QPushButton("Change default")
        change_default_btn.setToolTip("Set the default level for new cards in Settings")
        qconnect(change_default_btn.clicked, lambda: self._open_settings(initial_tab="Cards"))
        level_row.addWidget(self.level_combo, 1)
        level_row.addWidget(change_default_btn, 0)
        form.addRow("Level", level_row)

        layout.addLayout(form)

        self.cloze_check = QCheckBox("Generate cloze companion")
        self.cloze_check.setChecked(bool(defaults.get("generate_cloze", True)))
        layout.addWidget(self.cloze_check)

        # Secondary-translation toggle: created once, then re-synced from the saved config
        # (see _refresh_secondary) so a language changed in Settings shows up without reopening.
        self.secondary_lang = ""
        self.secondary_check = QCheckBox()
        layout.addWidget(self.secondary_check)
        self._refresh_secondary()

        # Buttons
        btn_row = QHBoxLayout()
        self.settings_btn = QPushButton("Settings…")
        qconnect(self.settings_btn.clicked, lambda: self._open_settings())
        btn_row.addWidget(self.settings_btn)
        btn_row.addSpacing(10)
        btn_row.addWidget(support_link(self))
        btn_row.addStretch()
        self.close_btn = QPushButton("Close")
        qconnect(self.close_btn.clicked, self.reject)
        btn_row.addWidget(self.close_btn)
        self.add_btn = QPushButton("Add")
        self.add_btn.setDefault(True)
        qconnect(self.add_btn.clicked, self._on_add)
        btn_row.addWidget(self.add_btn)
        layout.addLayout(btn_row)

        self._refresh_state()

    # ── state / validation ──
    def _refresh_state(self):
        if not self._providers:
            self.banner.setText("⚠ No AI provider with an API key yet. Click Settings, pick a provider, and paste your key (a free Groq key works).")
            self.banner.show()
        else:
            self.banner.hide()
        img = self.cfg.get("image", {}) or {}
        if not any((img.get(k) or "").strip() for k in ("pexels_key", "pixabay_key", "serper_key")):
            self.info_banner.setText("ℹ No image key yet, so many cards will have no photo. Add a free Pexels or Pixabay key in Settings for a photo on every card.")
            self.info_banner.show()
        else:
            self.info_banner.hide()
        # Block Add only when there's no usable provider; missing image key is non-fatal.
        self.add_btn.setEnabled(bool(self._providers))

    def _find_existing(self, deck, word):
        """Existing Tarkib notes for this word in this deck. Normalises the article so
        'die Frau' / 'Die Frau' / 'Frau' all match (Anki search is already case-insensitive)."""
        try:
            import re
            stem = re.sub(r"^(der|die|das|sich)\s+", "", word.strip(), flags=re.IGNORECASE)
            stem = (stem or word).replace('"', "").replace("*", "").strip()
            if not stem:
                return []
            from ..notetypes import find_main
            nt = find_main(mw.col.models)
            if nt is None:      # nothing generated yet, so nothing can be a duplicate
                return []
            q = 'deck:"%s" "note:%s" "Front:*%s*"' % (
                deck.replace('"', ""), nt["name"].replace('"', ""), stem)
            return list(mw.col.find_notes(q))
        except Exception:
            return []

    def _add_deck(self):
        """Prompt for a deck name, create it if missing, then select it in the combo."""
        name, ok = getText("New deck name (e.g. Deutsch::My Deck):", parent=self, default="")
        if not ok:
            return
        name = name.strip()
        if not name:
            return
        try:
            mw.col.decks.id(name, create=True)  # creates the deck if it doesn't exist
        except Exception as e:
            tooltip("Could not create deck: %s" % e)
            return
        if self.deck_combo.findText(name) == -1:
            self.deck_combo.addItem(name)
        self.deck_combo.setCurrentText(name)
        tooltip("Deck ready: %s" % name)

    def _resolve_level(self, deck):
        """Per-card default: the per-deck level if configured, else the global default."""
        defaults = self.cfg.get("defaults", {}) or {}
        deck_levels = self.cfg.get("deck_levels", {}) or {}
        lv = deck_levels.get(deck) or defaults.get("level") or prompts.DEFAULT_LEVEL
        return lv if lv in prompts.LEVELS else prompts.DEFAULT_LEVEL

    def _set_level(self, code):
        i = self.level_combo.findData(code)
        if i >= 0:
            self.level_combo.setCurrentIndex(i)

    def _on_deck_changed(self, deck):
        """Snap the level to a deck's configured default — only when one exists, so it never
        overrides a level the user picked by hand for an ordinary deck."""
        deck_levels = self.cfg.get("deck_levels", {}) or {}
        code = deck_levels.get(deck.strip())
        if code in prompts.LEVELS:
            self._set_level(code)

    def _set_engine_visible(self, visible):
        """The Engine picker only matters with 2+ providers; hide its row for the common
        single-provider case so the dialog stays uncluttered."""
        f = self.engine_form
        w = self.engine_combo
        if hasattr(f, "setRowVisible"):
            f.setRowVisible(w, visible)        # Qt >=6.4: collapses the row cleanly
        else:
            w.setVisible(visible)
            lbl = f.labelForField(w)
            if lbl is not None:
                lbl.setVisible(visible)

    def _selected_provider(self):
        i = self.engine_combo.currentIndex()
        if 0 <= i < len(self._providers):
            return self._providers[i]
        return None

    def _open_settings(self, initial_tab=None):
        from .settings import SettingsDialog
        if SettingsDialog(self, initial_tab=initial_tab).exec():
            # reload config + rebuild engine list
            self.cfg = _cfg()
            self._providers = [p for p in (self.cfg.get("providers") or []) if (p.get("api_key") or "").strip()]
            self.engine_combo.clear()
            for p in self._providers:
                self.engine_combo.addItem(p.get("name") or p.get("id") or p.get("type"))
            self._set_engine_visible(len(self._providers) >= 2)
            self._reload_decks()   # Settings can create starter decks; show them without reopening
            self._refresh_secondary()
            self._refresh_state()

    def _refresh_secondary(self):
        """Sync the 'Add <language> translation' checkbox with the saved config. Hidden (and
        ignored) when no secondary language is set, so it can never offer a stale language."""
        defaults = self.cfg.get("defaults", {}) or {}
        self.secondary_lang = (defaults.get("secondary_translation_language") or "").strip()
        if self.secondary_lang:
            self.secondary_check.setText("Add %s translation" % self.secondary_lang)
            self.secondary_check.setChecked(True)
            self.secondary_check.show()
        else:
            self.secondary_check.setChecked(False)
            self.secondary_check.hide()

    def _reload_decks(self):
        current = self.deck_combo.currentText().strip()
        decks = sorted({d.name for d in mw.col.decks.all_names_and_ids()})
        if current and current not in decks:
            decks.insert(0, current)
        self.deck_combo.blockSignals(True)
        self.deck_combo.clear()
        self.deck_combo.addItems(decks)
        self.deck_combo.setCurrentText(current)
        self.deck_combo.blockSignals(False)

    # ── run ──
    def _on_add(self):
        word = self.word_edit.text().strip()
        deck = self.deck_combo.currentText().strip()
        provider = self._selected_provider()
        if not word or not deck or not provider:
            tooltip("Need a word, a deck, and a configured engine.")
            return
        # Duplicate guard — checked BEFORE generating, so a dupe costs no tokens.
        existing = self._find_existing(deck, word)
        if existing and not askUser(
            'A card for "%s" already exists in "%s" (%d found).\nAdd another anyway?'
            % (word, deck, len(existing)),
            parent=self, defaultno=True, title="Possible duplicate"):
            return
        options = {
            "meaning": self.meaning_edit.text().strip(),
            "scenario": self.scenario_edit.text().strip(),
            "image_keyword": self.image_edit.text().strip(),
            "image_source": (self.cfg.get("defaults", {}) or {}).get("image_source", "auto"),
            "generate_cloze": self.cloze_check.isChecked(),
            "secondary_language": (self.secondary_lang if (self.secondary_check and self.secondary_check.isChecked()) else ""),
            "level": self.level_combo.currentData() or prompts.DEFAULT_LEVEL,
            "progress": self._progress,
        }
        self._start(word, deck, provider, options)

    def _start(self, word, deck, provider, options):
        """Kick off generation. Kept separate from _on_add so a refusal can re-run the same request
        with a flag (see _fail, "Add it anyway?") without re-reading the form."""
        cfg = self.cfg
        self._pending_deck = deck   # persisted as last_deck only after a successful write
        self._pending_model = provider.get("model", "")  # named in friendly error messages
        self._pending_run = {"word": word, "deck": deck, "provider": provider, "options": options}
        self.add_btn.setEnabled(False)

        def op(col):
            return generate.build_card(cfg, provider, deck, word, options)

        # without_collection(): the pipeline is network/audio only and must not occupy Anki's
        # single collection-worker thread (which would block other collection ops meanwhile).
        QueryOp(parent=self, op=op, success=self._on_built) \
            .without_collection().failure(self._fail).with_progress("Generating card…").run_in_background()

    def _progress(self, msg):
        def upd():
            try:
                if mw.progress.busy():
                    mw.progress.update(label=msg)
            except Exception:
                pass
        mw.taskman.run_on_main(upd)

    def _on_built(self, bundle):
        typo = (bundle.get("meta") or {}).get("typo")
        if typo:
            # The model corrected the spelling and the card is ready. Ask before writing anything:
            # Yes keeps the corrected card, No re-runs with the input kept exactly as typed.
            if not askUser('You typed "%s".\nThe card was made for "%s".\n\nUse "%s"?\n\n'
                           '(No makes a card for "%s" exactly as you typed it.)'
                           % (typo["input"], typo["word"], typo["word"], typo["input"]),
                           parent=self, title="Did you mean ...?", defaultno=False):
                pr = getattr(self, "_pending_run", None)
                if pr:
                    pr["options"]["exact_word"] = True
                    self._start(pr["word"], pr["deck"], pr["provider"], pr["options"])
                else:
                    self.add_btn.setEnabled(True)
                return
        out = {}

        def wop(col):
            return anki_io.write_bundle(col, bundle, out)

        def done(_changes):
            self.add_btn.setEnabled(True)  # re-enable FIRST, so nothing below can strand it disabled
            parts = ["main card"]
            if out.get("cloze_id"):
                parts.append("cloze")
            warn = bundle.get("meta", {}).get("cloze_warning")
            extra = " (cloze skipped: %s)" % warn if warn and not out.get("cloze_id") else ""
            msg = "✓ Added " + " + ".join(parts) + extra
            period = 4000
            # Audio is nice-to-have: the card already landed. Report partial/total audio loss.
            a = bundle.get("meta", {}).get("audio") or {}
            ok_n, total_n, cat = a.get("ok", 0), a.get("total", 0), a.get("category")
            if total_n and ok_n == 0:
                msg += ". Audio unavailable (%s). Re-add later for audio." % audio.tts_error_message(cat)
                period = 7000
            elif total_n and ok_n < total_n:
                msg += ". Note: %d of %d audio clips failed (%s). Re-add later to fill." % (
                    total_n - ok_n, total_n, audio.tts_error_message(cat))
                period = 7000
            # Best-effort enrichment steps that were skipped (recorded in meta by build_card).
            meta = bundle.get("meta", {})
            skipped = [name for key, name in (("grammar_warning", "grammar notes"),
                                              ("secondary_warning", "translation")) if meta.get(key)]
            if skipped:
                msg += ". Note: %s skipped (provider issue, e.g. rate limit)." % " and ".join(skipped)
                period = max(period, 6000)
            lw = meta.get("language_warning")
            if lw:
                msg += ". Note: %s. Fix it in Settings, Languages." % lw
                period = max(period, 7000)
            tooltip(msg, period=period)
            # Stay open for rapid multi-card entry (like Anki's own Add window): clear the
            # per-card inputs, keep deck/engine/cloze selections, re-enable, focus the word.
            for w in (self.word_edit, self.meaning_edit, self.scenario_edit, self.image_edit):
                w.clear()
            self.word_edit.setFocus()
            # Remember the deck for next time (mirrors Anki's own Add window).
            try:
                cfg = _cfg()
                cfg.setdefault("defaults", {})["last_deck"] = self._pending_deck
                mw.addonManager.writeConfig(__name__, cfg)
            except Exception:
                pass
            # Count the card; every 50, a gentle (dismissible) thank-you. Never blocks the add.
            note_card_added_and_maybe_thank(self)

        CollectionOp(parent=mw, op=wop).success(done).failure(self._fail).run_in_background()

    def _fail(self, exc):
        self.add_btn.setEnabled(True)
        title, body, kind = providers.friendly_error(exc, getattr(self, "_pending_model", ""))
        if kind == "settings":
            # Fixable in Settings (wrong/limited model, bad key). Offer a one-click jump.
            if askUser("%s\n\nOpen Settings now to change it?" % body,
                       parent=self, title=title, defaultno=False):
                self._open_settings()
            return
        if kind == "retry" and title.startswith("That does not look like German"):
            # The input check refused. The model can be wrong (a regional word, Native Denglisch,
            # a name), so the user gets the last word: the same request runs again with the check off.
            pr = getattr(self, "_pending_run", None)
            if pr and askUser("%s\n\nAdd it anyway?" % body, parent=self, title=title, defaultno=True):
                pr["options"]["force_input"] = True
                self._start(pr["word"], pr["deck"], pr["provider"], pr["options"])
            return
        if kind == "retry":
            # Transient (network / timeout / provider 5xx). Plain message, no scary traceback.
            showText("%s\n\n%s" % (title, body), parent=self, copyBtn=False)
            return
        # Unexpected — friendly headline + the copyable traceback for a bug report.
        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)) \
            if isinstance(exc, BaseException) else str(exc)
        showText("Tarkib: %s\n\n%s\n\n(Full details to copy if you report this:)\n%s"
                 % (title, body, tb), parent=self, copyBtn=True)
