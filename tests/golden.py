# -*- coding: utf-8 -*-
"""Golden files: the expected output of a test, kept in tests/golden/ and compared byte for byte.

    UPDATE_GOLDEN=1 python3 tests/test_cards.py     rewrite them after a change you meant,
                                                     then read `git diff tests/golden` before committing

A missing golden file fails (it never passes silently), a mismatch fails with a unified diff, and a
golden file that no test writes any more fails too, so the folder never keeps dead examples.
"""
import difflib
import os

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden")
UPDATE = os.environ.get("UPDATE_GOLDEN") == "1"
_MAX_DIFF_LINES = 160


def _read(path):
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def check(case, rel_path, text):
    """Compare `text` with golden/<rel_path>, or write it when UPDATE_GOLDEN=1."""
    path = os.path.join(ROOT, rel_path)
    if UPDATE:
        if not os.path.exists(path) or _read(path) != text:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(text)
        return
    if not os.path.exists(path):
        case.fail("no golden file tests/golden/%s yet: run UPDATE_GOLDEN=1 with this test, then read "
                  "what it wrote" % rel_path)
    want = _read(path)
    if want != text:
        diff = list(difflib.unified_diff(want.splitlines(True), text.splitlines(True),
                                         "golden/" + rel_path, "now", n=2))
        shown = "".join(diff[:_MAX_DIFF_LINES])
        more = "\n... %d more diff lines" % (len(diff) - _MAX_DIFF_LINES) if len(diff) > _MAX_DIFF_LINES else ""
        case.fail("tests/golden/%s changed. If the change is meant, run with UPDATE_GOLDEN=1 and review "
                  "the diff:\n%s%s" % (rel_path, shown, more))


def stale(rel_dir, expected):
    """Golden files under golden/<rel_dir> that no test expects (relative paths, sorted). With
    UPDATE_GOLDEN=1 they are deleted instead and nothing is reported."""
    base = os.path.join(ROOT, rel_dir)
    found = set()
    for folder, _dirs, files in os.walk(base):
        for name in files:
            if name.startswith("."):
                continue
            found.add(os.path.relpath(os.path.join(folder, name), ROOT).replace(os.sep, "/"))
    extra = sorted(found - set(expected))
    if UPDATE:
        for rel in extra:
            os.remove(os.path.join(ROOT, rel))
        return []
    return extra
