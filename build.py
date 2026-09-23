#!/usr/bin/env python3
"""Build a clean, upload-ready `tarkib.ankiaddon`.

Zips the CONTENTS of this folder (NOT the top-level folder, per AnkiWeb's rule). Only an ALLOWLIST
of runtime files ships: the add-on's Python packages, its manifest, config and icon, and the
license. In a git checkout, files git does not track are left out too, so a stray local file can
never reach users. It refuses to run if a secret file would be included. Output: out/tarkib.ankiaddon.

Usage:  python3 build.py
Then:   upload the file at https://ankiweb.net/shared/addons  (Upload button), or double-click it to
        sideload into Anki Desktop.
"""
import json
import os
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "out")
OUT = os.path.join(OUT_DIR, "tarkib.ankiaddon")

# What an installed add-on needs, nothing else. Tests, docs, repo files and this script stay home.
SHIP_FILES = {"__init__.py", "anki_io.py", "notetypes.py", "manifest.json", "config.json", "config.md",
              "LICENSE"}
SHIP_DIRS = {"pipeline": {".py"}, "ui": {".py"}, "icons": {".svg"}}


def _tracked():
    """Files git tracks here, or None outside a git checkout (for example a downloaded ZIP)."""
    try:
        out = subprocess.run(["git", "ls-files"], cwd=HERE, capture_output=True, text=True, check=True).stdout
    except Exception:
        return None
    return {os.path.normpath(line) for line in out.splitlines() if line.strip()}


def _candidates():
    files = [f for f in SHIP_FILES if os.path.isfile(os.path.join(HERE, f))]
    for d, exts in SHIP_DIRS.items():
        for root, dirs, names in os.walk(os.path.join(HERE, d)):
            dirs[:] = [x for x in dirs if x != "__pycache__"]
            for n in names:
                if os.path.splitext(n)[1] in exts:
                    files.append(os.path.relpath(os.path.join(root, n), HERE))
    return files


def main():
    manifest_path = os.path.join(HERE, "manifest.json")
    if not os.path.exists(manifest_path):
        sys.exit("ERROR: manifest.json missing, required for a valid .ankiaddon.")
    try:
        with open(manifest_path, encoding="utf-8") as f:
            m = json.load(f)
    except Exception as e:
        sys.exit("ERROR: manifest.json is not valid JSON: %s" % e)
    for k in ("package", "name"):
        if not m.get(k):
            sys.exit('ERROR: manifest.json is missing required field "%s".' % k)

    files = _candidates()
    tracked = _tracked()
    if tracked is not None:
        skipped = sorted(f for f in files if os.path.normpath(f) not in tracked)
        files = [f for f in files if os.path.normpath(f) in tracked]
        if skipped:
            print("   left out (not tracked by git): %s" % ", ".join(skipped))

    # SAFETY: never ship a key/secret or runtime state, even if the rules above ever drift.
    leaked = [f for f in files
              if os.path.basename(f) == "meta.json" or f.split(os.sep)[0] == "user_files"]
    if leaked:
        sys.exit("ABORT: refusing to package secret/runtime files: %s" % leaked)

    os.makedirs(OUT_DIR, exist_ok=True)
    if os.path.exists(OUT):
        os.remove(OUT)
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in sorted(files):
            z.write(os.path.join(HERE, rel), arcname=rel)  # arcname = path at the ZIP ROOT

    size_kb = os.path.getsize(OUT) / 1024
    top = sorted({f.split(os.sep)[0] for f in files})
    print("✅ Wrote %s" % os.path.relpath(OUT, HERE))
    print("   %d files, %.1f KB" % (len(files), size_kb))
    print("   top-level entries: %s" % ", ".join(top))
    if not (m.get("min_point_version") or m.get("max_point_version")):
        print("   note: manifest has no min/max_point_version; set Anki compatibility on the upload form.")
    print("\nNext: upload it at https://ankiweb.net/shared/addons  (Upload button, logged in).")
    print("Verified: no meta.json / API key is inside (this build refuses to include them).")


if __name__ == "__main__":
    main()
