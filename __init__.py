"""Tarkib — Anki add-on entry point.

Registers the ways to open the Add-Card dialog: a Tools-menu item, a keyboard shortcut, and a
Tarkib button on the note-editor toolbar. The dialog + generation pipeline live in ui/ and pipeline/.
"""
import os

from aqt import mw, gui_hooks
from aqt.qt import QAction, QKeySequence
from aqt.utils import qconnect

from .ui.dialog import AddCardDialog

# Toolbar/editor icon — the Tarkib mark, shipped with the add-on (not user data).
_ICON = os.path.join(os.path.dirname(__file__), "icons", "tarkib.svg")

# Inline mark SVG for the deck-browser button — a webview can't reliably load a file:// icon, so
# we embed the markup directly. Falls back to an emoji if the file is missing (never break loading).
# Used ONLY in webview BODY HTML (the deck-browser button). The top-toolbar link must use a PLAIN
# TEXT label: Anki's create_link puts the label into an aria-label="..." attribute, so an SVG's
# quotes would break out of it and dump raw markup into the bar. Toolbar = text (matches Decks/Add/…).
try:
    with open(_ICON, encoding="utf-8") as _svg_f:
        _ICON_SVG = _svg_f.read().replace(
            'width="24" height="24"',
            'width="18" height="18" style="vertical-align:middle;flex:none"',
        )
except Exception:
    _ICON_SVG = "✨"

# Unique pycmd string for the deck-browser button (won't clash with other add-ons' webview messages).
_DECK_BROWSER_CMD = "german_ai_cards:open"

# Hold a reference so the dialog isn't garbage-collected when the handler returns (Qt gotcha).
_dialog = None

# Default shortcut; overridable via the add-on config (config.json -> "shortcut").
_DEFAULT_SHORTCUT = "Ctrl+Shift+G"


def _open_dialog() -> None:
    global _dialog
    # Every entry point (menu, shortcut, editor button, deck-browser button, toolbar link) funnels
    # here: re-focus an open dialog instead of stacking a second one on top of it.
    if _dialog is not None and _dialog.isVisible():
        _dialog.raise_()
        _dialog.activateWindow()
        return
    _dialog = AddCardDialog(mw)
    _dialog.show()
    _dialog.raise_()
    _dialog.activateWindow()


def _open_settings() -> None:
    """Anki's Add-ons > Config button. Without this it opens the raw JSON editor, which shows the
    API keys in clear and lets edits race the Settings dialog; route it to the real Settings UI."""
    from .ui.settings import SettingsDialog
    dlg = SettingsDialog(mw)
    accepted = dlg.exec()
    # A Tarkib window left open shows what was just saved without being reopened.
    if (accepted or getattr(dlg, "saved", False)) and _dialog is not None and _dialog.isVisible():
        try:
            _dialog._sync_from_config()
        except Exception:
            pass


def _shortcut() -> str:
    try:
        cfg = mw.addonManager.getConfig(__name__) or {}
        return cfg.get("shortcut") or _DEFAULT_SHORTCUT
    except Exception:
        return _DEFAULT_SHORTCUT


def _setup_menu() -> None:
    action = QAction("Add a card with Tarkib…", mw)
    sc = _shortcut()
    if sc:
        action.setShortcut(QKeySequence(sc))
    qconnect(action.triggered, _open_dialog)
    mw.form.menuTools.addAction(action)


def _add_editor_button(buttons, editor) -> None:
    """Add a Tarkib button to the note-editor toolbar (Add window + Browse), the same way
    AwesomeTTS adds its icon. Clicking it opens the Tarkib generator."""
    buttons.append(editor.addButton(
        icon=_ICON,
        cmd="german_ai_cards",
        func=lambda _editor: _open_dialog(),
        tip="Add a card with Tarkib (%s)" % _shortcut(),
    ))


def _add_deck_browser_button(deck_browser, content) -> None:
    """Add a prominent 'Generate cards with Tarkib' button to the deck overview, right under the
    'Studied today' line, so the generator is discoverable without the Tools menu / editor toolbar."""
    content.stats += (
        '<div style="text-align:center;margin:16px 0 4px;">'
        '<a href="#" title="Generate cards with Tarkib (%s)" '
        'onclick="pycmd(\'%s\'); return false;" '
        'style="display:inline-flex;align-items:center;gap:8px;padding:9px 18px;'
        'border-radius:10px;text-decoration:none;font-size:14px;font-weight:600;'
        'color:#fff;background:linear-gradient(135deg,#8b5cf6,#22d3ee);'
        'box-shadow:0 2px 8px rgba(0,0,0,.35);cursor:pointer;">'
        '%s<span>Generate cards with Tarkib</span></a></div>'
        % (_shortcut(), _DECK_BROWSER_CMD, _ICON_SVG)
    )


def _on_webview_message(handled, message, context):
    """Open the generator when the deck-browser button is clicked (the pycmd bridge). This hook fires
    for EVERY webview message, so act only on our own command and pass everything else through."""
    if message == _DECK_BROWSER_CMD:
        _open_dialog()
        return (True, None)
    return handled


def _add_toolbar_link(links, toolbar) -> None:
    """Add a 'Tarkib' link to the main top toolbar, right after 'Add'
    (Decks · Add · Tarkib · Browse · Stats · Sync) — an always-visible entry point that never
    scrolls away and doesn't compete with other add-ons for deck-overview space. `create_link`
    also registers the click handler, so no webview message hook is needed for this one."""
    links.insert(2, toolbar.create_link(
        "gac_generate",
        "Tarkib",  # PLAIN TEXT only — create_link puts this in an aria-label attr (no HTML/SVG).
        _open_dialog,
        tip="Generate cards with Tarkib (%s)" % _shortcut(),
        id="german_ai_cards_toolbar",
    ))


# Register once the main window exists; the editor hook fires for every note editor.
gui_hooks.main_window_did_init.append(_setup_menu)
gui_hooks.editor_did_init_buttons.append(_add_editor_button)
gui_hooks.deck_browser_will_render_content.append(_add_deck_browser_button)
gui_hooks.webview_did_receive_js_message.append(_on_webview_message)
gui_hooks.top_toolbar_did_init_links.append(_add_toolbar_link)
mw.addonManager.setConfigAction(__name__, _open_settings)
