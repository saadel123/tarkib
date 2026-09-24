"""Single source of truth for the optional support and ready-made decks pointers.

Owns: the support, decks, shop and AnkiWeb URLs, the footer links, the milestone thank-you, and the
decks text in Settings. When they show is decided in ui/promo_rules.py. The add-on is and stays
free: these are quiet pointers with a permanent opt-out, and they must NEVER block or break
card-adding.
"""
from aqt import mw
from aqt.qt import QLabel, QMessageBox, QCheckBox
from aqt.utils import openLink

from .promo_rules import should_thank

# Mirror any change in README.md, ANKIWEB_LISTING.md and SOURCE_OF_TRUTH.md.
SUPPORT_URL = "https://ko-fi.com/tarkib"
ANKIWEB_URL = "https://ankiweb.net/shared/info/83323714"   # where a rating helps other learners find it

# The ready-made Tarkib German decks. EMPTY hides every element that points at them rather than
# showing a dead link. DECKS_URL is the free A1 deck, SHOP_URL lists every level.
DECKS_URL = "https://ko-fi.com/s/ab96fd15d8"
SHOP_URL = "https://ko-fi.com/tarkib/shop"
DECKS_NOTETYPE = "Tarkib German"   # present once a ready-made deck is imported (notetypes.MAIN_NOTETYPE)


def decks_imported():
    """True when the collection already holds the ready-made decks, so pointing at them is noise."""
    try:
        return mw.col is not None and mw.col.models.by_name(DECKS_NOTETYPE) is not None
    except Exception:
        return False


def support_link(parent=None):
    """A small, unobtrusive '♥ Support this add-on' link for a dialog footer (opens the browser)."""
    lbl = QLabel('<a href="%s">♥ Support this add-on</a>' % SUPPORT_URL, parent)
    lbl.setOpenExternalLinks(True)
    lbl.setToolTip("This add-on is free. If it helps you, you can support its development.")
    lbl.setStyleSheet("font-size: 12px;")
    return lbl


def decks_footer_link(parent=None):
    """A quiet 'Free A1 deck' link for the Add dialog footer, or None when it would be noise: no
    decks URL, or the ready-made decks are already in the collection."""
    if not DECKS_URL or decks_imported():
        return None
    lbl = QLabel('<a href="%s">Free A1 deck</a>' % DECKS_URL, parent)
    lbl.setOpenExternalLinks(True)
    lbl.setToolTip("Ready-made cards in this format. The whole A1 level is free, the other levels are paid.")
    lbl.setStyleSheet("font-size: 12px;")
    return lbl


def note_card_added_and_maybe_thank(parent):
    """Count one added card. At the milestones in promo_rules.THANK_AT (three times in the life of
    an install) show ONE dismissible thank-you. Honors the permanent opt-out. Returns the new count.
    Wrapped so it can never break the add."""
    n = 0
    try:
        cfg = mw.addonManager.getConfig(__name__) or {}
        stats = cfg.setdefault("stats", {})
        n = int(stats.get("cards_added", 0) or 0) + 1
        stats["cards_added"] = n
        mw.addonManager.writeConfig(__name__, cfg)
        if not should_thank(n, stats):
            return n
        box = QMessageBox(parent)
        box.setWindowTitle("Thanks for using Tarkib")
        box.setText("You have made %d cards with Tarkib.\n\n"
                    "It is free and stays free. If it saves you time, a small tip helps me keep "
                    "improving it, and a rating on AnkiWeb makes it easier for other learners to "
                    "find." % n)
        support_btn = box.addButton("♥ Support on Ko-fi", QMessageBox.ButtonRole.AcceptRole)
        rate_btn = box.addButton("Rate on AnkiWeb", QMessageBox.ButtonRole.ActionRole)
        later_btn = box.addButton("Maybe later", QMessageBox.ButtonRole.RejectRole)
        # Enter out of habit (it is the Add key in the dialog behind) must not open a tip page.
        box.setDefaultButton(later_btn)
        opt_out = QCheckBox("Don't show this again")
        box.setCheckBox(opt_out)
        box.exec()
        if box.clickedButton() == support_btn:
            openLink(SUPPORT_URL)
        elif box.clickedButton() == rate_btn:
            openLink(ANKIWEB_URL)
        if opt_out.isChecked():
            cfg = mw.addonManager.getConfig(__name__) or {}
            cfg.setdefault("stats", {})["hide_support_thanks"] = True
            mw.addonManager.writeConfig(__name__, cfg)
    except Exception:
        pass  # a support nudge must NEVER interrupt or break adding cards
    return n


def decks_link(parent=None):
    """One quiet line pointing at the ready-made decks, or None when no shop URL is set.

    Returns None rather than an empty widget so the caller can skip the row entirely: an empty
    QLabel still takes vertical space and leaves an unexplained gap in the form.
    """
    if not DECKS_URL or not SHOP_URL:
        return None
    lbl = QLabel(
        'Rather not type? There are ready-made decks in this card format, A1 to C1. Every word has a '
        'picture, German audio and two example sentences with translations, in English or Arabic. '
        'The whole A1 level is free, the other levels are paid. '
        '<a href="%s">Get the free A1 deck</a> or <a href="%s">see all levels</a>.' % (DECKS_URL, SHOP_URL), parent)
    lbl.setOpenExternalLinks(True)
    lbl.setWordWrap(True)
    lbl.setStyleSheet("font-size: 11px; margin-top: 12px;")
    return lbl
