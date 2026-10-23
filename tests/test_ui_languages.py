#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Runs tests/ui_check.py (the real Add window and Settings dialog, offscreen) in its own process.

The other tests replace aqt with empty stand-ins, so the real one cannot be imported next to them. Under a
Python without Anki (aqt and PyQt6 missing) this is a skip, not a failure; under Anki's own Python it runs:

    "$HOME/Library/Application Support/AnkiProgramFiles/.venv/bin/python" -m unittest discover -s tests
"""
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))


class UiLanguages(unittest.TestCase):
    def test_add_window_and_settings(self):
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
        run = subprocess.run([sys.executable, os.path.join(HERE, "ui_check.py")], capture_output=True,
                             text=True, env=env, timeout=300)
        if run.returncode == 77:
            self.skipTest("aqt and PyQt6 are not installed for this Python")
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=1)
