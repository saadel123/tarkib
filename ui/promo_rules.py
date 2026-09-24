"""When the add-on may show its quiet pointers to support and to the ready-made decks.

Pure functions with no Anki or Qt imports, so tests/test_guards.py can check them offline. The
widgets that use them live in ui/support.py and ui/dialog.py.

The rules, in one place:
  - the thank-you appears three times in the life of an install (THANK_AT), never on other cards,
    and never again after "Don't show this again";
  - the decks hint appears once the user has made HINT_AFTER cards, only when the Add dialog
    opens (never mid-session, while the user is typing), on at most HINT_MAX_SHOWS openings, and
    never after it was closed with x, never when the decks are already imported, and never while
    the red no-key banner is showing.
Nothing here is ever tied to a reward, and nothing asks for a rating in exchange for anything.
"""

THANK_AT = (50, 200, 500)
HINT_AFTER = 5
HINT_MAX_SHOWS = 3


def should_thank(cards_added, stats):
    """True when this card count is one of the thank-you milestones and the user has not opted out."""
    return cards_added in THANK_AT and not (stats or {}).get("hide_support_thanks")


def hint_should_show(stats, decks_imported, blocked):
    """True when the short decks hint may be shown now.

    stats: the add-on's "stats" config dict. decks_imported: the Tarkib German note type exists in
    the collection. blocked: another banner that matters more (no AI key) is showing."""
    stats = stats or {}
    if decks_imported or blocked or stats.get("decks_hint_done"):
        return False
    if int(stats.get("cards_added", 0) or 0) < HINT_AFTER:
        return False
    return int(stats.get("decks_hint_shows", 0) or 0) < HINT_MAX_SHOWS
