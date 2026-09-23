"""Single source of truth for the optional "Support this add-on" bits.

Owns: the support URL, the every-N-cards interval, the footer link widget, and the periodic
thank-you dialog. Change the link or interval ONCE here. The add-on is and stays free — this is a
passive nudge only, with a permanent opt-out, and it must NEVER block or break card-adding.
"""
from aqt import mw
from aqt.qt import QLabel, QMessageBox, QCheckBox
from aqt.utils import openLink

# Single source of truth for the support link (footer + every-N-cards thank-you). Mirror any change in README.md.
SUPPORT_URL = "https://ko-fi.com/tarkib"
SUPPORT_EVERY_N = 50  # show a gentle thank-you every N cards added (0 disables)

# Where the ready-made decks are. EMPTY hides every element that points at it rather than showing a
# dead link.
#
# This is the only place in the add-on that mentions the decks, at the bottom of a Settings tab. The
# add-on stays fully useful without it: a link is fine, a nag is not.
DECKS_URL = "https://ko-fi.com/s/ab96fd15d8"   # the free A1 deck; the link text says the A1 level is free


def support_link(parent=None):
    """A small, unobtrusive '♥ Support this add-on' link for a dialog footer (opens the browser)."""
    lbl = QLabel('<a href="%s">♥ Support this add-on</a>' % SUPPORT_URL, parent)
    lbl.setOpenExternalLinks(True)
    lbl.setToolTip("This add-on is free. If it helps you, you can support its development. ♥")
    lbl.setStyleSheet("font-size: 12px;")
    return lbl


def note_card_added_and_maybe_thank(parent):
    """Count one added card; every SUPPORT_EVERY_N, show ONE dismissible thank-you with a Support
    button. Honors a permanent 'don't show again' opt-out. Wrapped so it can never break the add."""
    try:
        cfg = mw.addonManager.getConfig(__name__) or {}
        stats = cfg.setdefault("stats", {})
        n = int(stats.get("cards_added", 0) or 0) + 1
        stats["cards_added"] = n
        mw.addonManager.writeConfig(__name__, cfg)
        if (not SUPPORT_EVERY_N) or stats.get("hide_support_thanks") or (n % SUPPORT_EVERY_N != 0):
            return
        box = QMessageBox(parent)
        box.setWindowTitle("Thanks for using Tarkib")
        box.setText("🎉 You've created %d cards with Tarkib!\n\n"
                    "It's free and stays free. If it's saved you time, a small tip helps me keep "
                    "improving it. ♥" % n)
        support_btn = box.addButton("♥ Support", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Maybe later", QMessageBox.ButtonRole.RejectRole)
        opt_out = QCheckBox("Don't show this again")
        box.setCheckBox(opt_out)
        box.exec()
        if box.clickedButton() == support_btn:
            openLink(SUPPORT_URL)
        if opt_out.isChecked():
            cfg = mw.addonManager.getConfig(__name__) or {}
            cfg.setdefault("stats", {})["hide_support_thanks"] = True
            mw.addonManager.writeConfig(__name__, cfg)
    except Exception:
        pass  # a support nudge must NEVER interrupt or break adding cards


def decks_link(parent=None):
    """One quiet line pointing at the ready-made decks, or None when no shop URL is set.

    Returns None rather than an empty widget so the caller can skip the row entirely: an empty
    QLabel still takes vertical space and leaves an unexplained gap in the form.
    """
    if not DECKS_URL:
        return None
    lbl = QLabel(
        'Would rather not type? There are ready-made decks, A1 to C1. Every card has a picture, '
        'German audio and two example sentences with translations, in English or Arabic. '
        '<a href="%s">The whole A1 level is free.</a>' % DECKS_URL, parent)
    lbl.setOpenExternalLinks(True)
    lbl.setWordWrap(True)
    lbl.setStyleSheet("font-size: 11px; margin-top: 12px;")
    return lbl
