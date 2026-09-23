"""Write a generated card bundle into the collection. Runs INSIDE a CollectionOp (so it's
on the right thread and produces an undo/refresh). No network here.

Media flow: generate.py returns media as {TOKEN: (filename, bytes)} and leaves "@@TOKEN@@"
placeholders in the field strings. We write each blob (media.write_data renames on collision
and returns the REAL filename), then substitute the real filename into the fields.
"""
import re

from .notetypes import ensure_notetypes, check_cloze_notetype, find_main, find_cloze



def _clean_tags(tags):
    """Anki stores tags space-separated, so a tag containing a space silently becomes two tags
    ("1 Wortschatz" -> "1" + "wortschatz"). Collapse whitespace, strip markup characters (the cloze
    template renders {{Tags}}, so a tag must never carry HTML) and drop blanks, keeping order."""
    out = []
    for t in (tags or []):
        t = re.sub(r"[<>&\"'`]", "", re.sub(r"\s+", "_", str(t or "").strip()))   # the cloze template prints {{Tags}}
        if t and t not in out:
            out.append(t)
    return out

def write_bundle(col, bundle, out=None):
    """Create the main (+ optional cloze) notes as ONE atomic, single-press-undo operation.
    Returns the merged OpChanges (required by CollectionOp). Populates `out` with note ids.

    Order matters: note types, media, and decks are created BEFORE the custom undo entry, so
    undoing the card removes only the two notes — not the note types/decks/media.
    """
    out = out if out is not None else {}
    ensure_notetypes(col)
    mm = col.models

    cloze = bundle.get("cloze")

    # Guard: a pre-existing CustomClozeDE (from a shared deck or another add-on) might lack
    # a field or not be a real cloze type. ensure_notetypes already fingerprinted 'German AI'
    # (fatal) but deliberately left a foreign CustomClozeDE alone so the main card still works;
    # here, where a cloze IS being written, fail with the friendly message BEFORE any media write.
    if cloze:
        check_cloze_notetype(find_cloze(mm))

    # Write media (not undoable) and map "@@TOKEN@@" -> real (possibly-renamed) filename.
    tokenmap = {}
    for token, blob in (bundle.get("media") or {}).items():
        if not blob:
            continue
        fname, data = blob
        tokenmap["@@%s@@" % token] = col.media.write_data(fname, data)

    def resolve(s):
        if not s:
            return s
        for ph, real in tokenmap.items():
            s = s.replace(ph, real)
        return s

    # Create decks up front (so undo doesn't remove them).
    main = bundle["main"]
    main_deck_id = col.decks.id(main["deck"], create=True)
    cloze_deck_id = col.decks.id(cloze["deck"], create=True) if cloze else None

    # One undo entry for the whole card.
    target = col.add_custom_undo_entry("Add a Tarkib card")

    note = col.new_note(find_main(mm))
    note["Front"] = resolve(main["fields"]["Front"])
    note["Back"] = resolve(main["fields"]["Back"])
    note.tags = _clean_tags(main.get("tags"))
    col.add_note(note, main_deck_id)
    out["main_id"] = note.id
    out["main_deck"] = main["deck"]

    if cloze:
        cnote = col.new_note(find_cloze(mm))
        for k, v in cloze["fields"].items():
            cnote[k] = resolve(v)
        cnote.tags = _clean_tags(cloze.get("tags"))
        col.add_note(cnote, cloze_deck_id)
        out["cloze_id"] = cnote.id
        out["cloze_deck"] = cloze["deck"]

    return col.merge_undo_entries(target)
