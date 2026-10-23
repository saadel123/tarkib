#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Every golden card in one browser page, drawn with the real note types: out/card-preview.html.

    python3 tests/preview_cards.py              then open out/card-preview.html
    python3 tests/preview_cards.py noun_b1 ...  only the scenarios named

The tests check rules and catch changes; this page is for the eyes. Each scenario shows the main card
(front, then the answer side as Anki shows it) and the cloze card (front, then back), with a grey box
for the picture and Anki's play button for each sound. The Light and Dark buttons switch every card.
Add ?only=name1,name2 to the address to show some scenarios only. Look at it after any change to a
template, the CSS or the card HTML.
"""
import html
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import card_scenarios as cs  # noqa: E402

nt = cs.notetypes
OUT = os.path.join(cs.ROOT, "out", "card-preview.html")

_PLAY = ('<a class="replay-button soundLink" href="#"><svg class="playImage" viewBox="0 0 64 64">'
         '<circle cx="32" cy="32" r="29"></circle><path d="M56.502,32.301l-37.502,20.101l0.329,-40.804'
         'l37.173,20.703Z"></path></svg></a>')
# Close to Anki's reviewer: its page margin, the round play button, and the dark canvas.
_BASE_CSS = """
html { overflow: hidden; }
body { margin: 20px; overflow-wrap: break-word; background: #fff; color: #000; }
body.nightMode { background: #2c2c2c; color: #fff; }
.replay-button { display: inline-block; vertical-align: middle; margin: 0 4px; text-decoration: none; }
.replay-button svg { width: 40px; height: 40px; }
.replay-button svg circle { fill: #fff; stroke: #414141; }
.replay-button svg path { fill: #000; }
body.nightMode .replay-button svg circle { fill: #3a3a3a; stroke: #888; }
body.nightMode .replay-button svg path { fill: #fff; }
hr#answer { border: none; border-top: 1px solid #ccc; margin: 16px 0; }
"""


def _picture(name):
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="320" height="200"><rect width="320" height="200" '
           'rx="14" fill="#9aa3b5"/><text x="160" y="105" font-family="sans-serif" font-size="14" '
           'text-anchor="middle" fill="#fff">picture: %s</text></svg>' % html.escape(name))
    return "data:image/svg+xml;charset=utf-8," + svg.replace("#", "%23").replace('"', "'")


def _media(s, files):
    s = re.sub(r"\[sound:[^\]]*\]", _PLAY, s or "")
    for name in files:
        if not name.endswith(".mp3") and not name.endswith(".wav"):
            s = s.replace('src="%s"' % name, 'src="%s"' % _picture(name))
    return s


def _cloze(text, side):
    def one(m):
        answer, hint = m.group(1), m.group(2)
        if side == "front":
            return '<span class="cloze" data-cloze="%s" data-ordinal="1">[%s]</span>' % (
                html.escape(answer), hint if hint else "...")
        return '<span class="cloze" data-ordinal="1">%s</span>' % answer
    return re.sub(r"\{\{c1::(.*?)(?:::([^}]*))?\}\}", one, text or "")


def _template(tpl, fields, tags, side):
    """The few template features the Tarkib note types use: {{#F}}..{{/F}}, {{cloze:F}}, {{text:F}},
    {{Tags}} and {{F}}."""
    out = re.sub(r"\{\{#(\w+)\}\}(.*?)\{\{/\1\}\}",
                 lambda m: m.group(2) if (fields.get(m.group(1)) or "").strip() else "", tpl, flags=re.S)
    out = re.sub(r"\{\{cloze:(\w+)\}\}", lambda m: _cloze(fields.get(m.group(1), ""), side), out)
    out = re.sub(r"\{\{text:(\w+)\}\}", lambda m: re.sub(r"<[^>]+>", "", fields.get(m.group(1), "")), out)
    out = out.replace("{{Tags}}", " ".join(tags))
    return re.sub(r"\{\{(\w+)\}\}", lambda m: fields.get(m.group(1), ""), out)


def _frame(body, css, label):
    doc = ('<!doctype html><html><head><meta charset="utf-8"><style>%s</style><style>%s</style></head>'
           '<body class="card card1">%s</body></html>' % (_BASE_CSS, css, body))
    return ('<figure><figcaption>%s</figcaption><iframe srcdoc="%s"></iframe></figure>'
            % (label, html.escape(doc, quote=True)))


def scenario_html(s, r):
    parts = ['<section id="%s" data-name="%s"><h2>%s</h2><p class="about">%s</p>'
             % (s.name, s.name, html.escape(s.name), html.escape(s.about))]
    if r["error"]:
        parts.append('<p class="refused">Refused: %s</p></section>' % html.escape(r["error"]))
        return "".join(parts)
    parts.append('<div class="row">')
    files = r["files"]
    for note in r["notes"]:
        f = {k: _media(v, files) for k, v in note["fields"].items()}
        if note["type"] == "main":
            front = _template(nt.GERMAN_AI_FRONT, f, note["tags"], "front")
            back = _template(nt.GERMAN_AI_BACK.replace("{{FrontSide}}", front), f, note["tags"], "back")
            parts.append(_frame(front, nt.GERMAN_AI_CSS, "Main card, front"))
            parts.append(_frame(back, nt.GERMAN_AI_CSS, "Main card, answer"))
        else:
            parts.append(_frame(_template(nt.CLOZE_FRONT, f, note["tags"], "front"), nt.CLOZE_CSS, "Cloze, front"))
            parts.append(_frame(_template(nt.CLOZE_BACK, f, note["tags"], "back"), nt.CLOZE_CSS, "Cloze, back"))
    parts.append("</div></section>")
    return "".join(parts)


_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tarkib card preview</title>
<style>
:root { --bg: #f4f5f8; --ink: #1d2433; --soft: #5b6475; --line: #d9dde6; }
@media (prefers-color-scheme: dark) { :root { --bg: #11141c; --ink: #e8ebf2; --soft: #9aa3b5; --line: #2a3040; } }
body { margin: 0; padding: 16px; background: var(--bg); color: var(--ink); font: 14px/1.5 -apple-system, "Segoe UI", sans-serif; }
header { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; margin-bottom: 8px; }
header h1 { font-size: 18px; margin: 0 12px 0 0; }
button { font: inherit; padding: 6px 14px; border-radius: 8px; border: 1px solid var(--line); background: transparent; color: var(--ink); cursor: pointer; }
button[aria-pressed="true"] { background: #3f4d99; border-color: #3f4d99; color: #fff; }
section { border-top: 1px solid var(--line); padding: 14px 0 6px; }
h2 { font-size: 15px; margin: 0; font-family: ui-monospace, Menlo, monospace; }
.about { color: var(--soft); margin: 2px 0 10px; max-width: 900px; }
.refused { font-family: ui-monospace, Menlo, monospace; color: #c2410c; }
.row { display: flex; gap: 14px; flex-wrap: wrap; align-items: flex-start; }
figure { margin: 0; width: 380px; max-width: 100%; }
figcaption { font-size: 12px; color: var(--soft); margin-bottom: 4px; }
iframe { width: 100%; border: 1px solid var(--line); border-radius: 12px; background: #fff; height: 200px; display: block; }
</style></head><body>
<header><h1>Tarkib card preview</h1>
<button id="light" aria-pressed="true">Light</button><button id="dark" aria-pressed="false">Dark</button>
<span style="color:var(--soft)">{{COUNT}} scenarios, built by tests/preview_cards.py</span></header>
{{SECTIONS}}
<script>
(function () {
  var only = new URLSearchParams(location.search).get('only');
  if (only) {
    var keep = only.split(',');
    document.querySelectorAll('section').forEach(function (s) {
      if (keep.indexOf(s.dataset.name) < 0) s.remove();
    });
  }
  function fit(f) {
    try { f.style.height = (f.contentDocument.documentElement.scrollHeight + 2) + 'px'; } catch (e) {}
  }
  function setNight(on) {
    document.querySelectorAll('iframe').forEach(function (f) {
      try { f.contentDocument.body.classList.toggle('nightMode', on); f.contentDocument.body.classList.toggle('night_mode', on); } catch (e) {}
      fit(f);
    });
    document.getElementById('dark').setAttribute('aria-pressed', on ? 'true' : 'false');
    document.getElementById('light').setAttribute('aria-pressed', on ? 'false' : 'true');
  }
  document.querySelectorAll('iframe').forEach(function (f) {
    f.addEventListener('load', function () { fit(f); setTimeout(function () { fit(f); }, 300); });
  });
  document.getElementById('light').onclick = function () { setNight(false); };
  document.getElementById('dark').onclick = function () { setNight(true); };
  if (new URLSearchParams(location.search).get('dark')) window.addEventListener('load', function () { setNight(true); });
})();
</script>
</body></html>
"""


def main(names):
    chosen = [cs.BY_NAME[n] for n in names] if names else cs.SCENARIOS
    sections = "\n".join(scenario_html(s, cs.run(s)) for s in chosen)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(_PAGE.replace("{{COUNT}}", str(len(chosen))).replace("{{SECTIONS}}", sections))
    print(OUT)


if __name__ == "__main__":
    main(sys.argv[1:])
