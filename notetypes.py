"""Dedicated note types + idempotent creation. We create our OWN note types
("Tarkib" + "Tarkib Cloze") and never touch the user's built-in "Basic".

Two families on purpose. The ready-made Tarkib decks carry "Tarkib German" (renamed from
"German AI Cards" before their first release, the only moment a rename is free); the add-on
creates the language-neutral "Tarkib" when no deck type is present. Distinct names matter:
the deck types have pinned ids, so a same-name type with a different id would collide on
import. The ownership marker in the CSS (_VPREFIX) is deliberately NOT renamed. It is invisible
to users and every note type already in the wild carries it; changing it would make the add-on
treat its own earlier work as a stranger's.
"""

GERMAN_AI_FRONT = "{{Front}}"
GERMAN_AI_BACK = "{{FrontSide}}\n\n<hr id=answer>\n\n{{Back}}"

GERMAN_AI_CSS = """.card {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Helvetica, Arial, sans-serif;
  font-size: 20px; text-align: center; line-height: 1.6; padding: 20px; max-width: 640px; margin: 0 auto;
}
.level-chip { display: inline-block; font-size: 11px; font-weight: 800; letter-spacing: 1px; padding: 2px 8px; border-radius: 999px; color: #fff; vertical-align: middle; position: relative; top: -2px; }
.lvl-a1 { background: #16a34a; } .lvl-a2 { background: #22c55e; } .lvl-b1 { background: #ca8a04; }
.lvl-b2 { background: #ea580c; } .lvl-c1 { background: #dc2626; } .lvl-native { background: #6d28d9; }
.card-translation { text-align: center; font-size: 22px; margin-bottom: 8px; font-weight: 500; }
.morph { text-align: center; font-size: 14px; color: #aaa; margin: 0 0 16px 0; }
.morph .g-der { color: #3b82f6; font-weight: 700; } .morph .g-die { color: #ef4444; font-weight: 700; } .morph .g-das { color: #22c55e; font-weight: 700; }
.card-image { text-align: center; margin: 0 0 20px 0; line-height: 0; }
.card-image img { max-width: 320px; max-height: 240px; width: auto; height: auto; border-radius: 14px; }
.section { margin-bottom: 24px; text-align: left; }
.section-label { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 1.5px; color: #888; margin-bottom: 10px; padding-left: 3px; }
.sentence { padding: 12px 14px; border-radius: 10px; margin-bottom: 8px; font-size: 16px; line-height: 1.5; text-align: left; }
.sentence .emoji { font-size: 20px; margin-right: 10px; }
.sentence.casual { background: rgba(255, 217, 61, 0.08); border-left: 3px solid #ffd93d; }
.sentence.formal { background: rgba(160, 196, 255, 0.08); border-left: 3px solid #a0c4ff; }
.patterns-box { margin: 22px 0; padding: 14px 16px; background: linear-gradient(135deg, #2d3561 0%, #3d4a8a 100%); border-radius: 12px; border: 1px solid rgba(138, 164, 255, 0.25); text-align: left; }
.patterns-label { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 1.5px; color: #a8b4ff; margin-bottom: 10px; }
.pattern-badge { display: inline-block; background: rgba(255, 255, 255, 0.14); color: #fff; padding: 6px 12px; border-radius: 8px; font-weight: 600; font-size: 14px; margin: 3px 6px 3px 0; border: 1px solid rgba(255, 255, 255, 0.15); }
.explanation { padding: 14px 16px; background: rgba(255, 186, 120, 0.08); border-left: 3px solid #ffba78; border-radius: 10px; font-size: 14px; line-height: 1.6; margin-top: 20px; margin-bottom: 32px; font-style: italic; text-align: left; }
.arabic .sentence { direction: rtl; text-align: right; border-left: none; border-right: 3px solid; }
.arabic .sentence.casual { border-right-color: #ffd93d; border-left: none; }
.arabic .sentence.formal { border-right-color: #a0c4ff; border-left: none; }
.arabic .sentence .emoji { margin-right: 0; margin-left: 10px; }
.arabic .section-label { direction: ltr; text-align: left; }
.secondary-word { display: flex; justify-content: center; align-items: center; gap: 10px; padding: 14px; background: rgba(46, 160, 100, 0.1); border-radius: 10px; font-size: 22px; font-weight: 700; color: #2d8f5e; margin: 20px 0; direction: rtl; }
.nightMode .secondary-word, .night_mode .secondary-word { color: #64dca0; }
.register-hint { background: linear-gradient(90deg, rgba(248,113,113,0.10), rgba(250,204,21,0.10)); border-left: 3px solid #f87171; border-radius: 8px; padding: 10px 14px; margin: 8px 0; font-size: 13px; line-height: 1.55; }
.register-hint .formal-mark { color: #f87171; font-weight: 600; }
.register-hint .arrow { color: #8a94b3; margin: 0 6px; }
.register-hint .casual-alt { color: #facc15; font-weight: 600; }
.register-hint .alt-list { color: #e2e6f0; font-style: italic; }
"""

CLOZE_FIELDS = ["Text", "Translation", "Image", "FrontAudio", "BackAudio", "GrammarHint", "SourceWord", "DeckOrigin"]

CLOZE_FRONT = r"""<div class="cloze-card">
  <div class="cloze-raw" style="display:none">{{text:Text}}</div>
  <div class="note-tags" style="display:none">{{Tags}}</div>
  {{#Image}}<div class="cloze-image">{{Image}}</div>{{/Image}}
  <div class="cloze-sentence">{{cloze:Text}}</div>
  <div class="cloze-type-wrapper">
    <input type="text" class="my-type-input tappable"
           autocomplete="off" autocorrect="off"
           autocapitalize="none" spellcheck="false"
           inputmode="text" placeholder="Type the answer…"
           ontouchend="this.focus()" onclick="this.focus()" />
    <div class="check-row">
      <button type="button" class="check-btn tappable" onclick="checkClozeAnswer(this)">Check</button>
    </div>
    <div class="check-feedback"></div>
    <div class="keyboard-hint" style="display:none">No keyboard? In AnkiDroid open Settings, then Advanced, and switch on "Type answer into the card". Restart AnkiDroid, then come back to this card.</div>
  </div>
  {{#FrontAudio}}<div class="cloze-audio">{{FrontAudio}}</div>{{/FrontAudio}}
</div>
<script>
(function(){
  if (window._checkClozeInstalled) return;
  window._checkClozeInstalled = true;
  function esc(s){return s.replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
  function norm(s){
    return (s||'').trim().toLowerCase().replace(/\s+/g,' ').replace(/[.,!?;:„""‚''«»]/g,'');
  }
  function decodeEntities(s){ const t=document.createElement('textarea'); t.innerHTML=s; return t.value; }
  // On an Arabic edition card the chrome is Arabic, full stop. Only the Android hint is bilingual,
  // and only because it quotes setting names that AnkiDroid writes in English.
  // window._tarkibAR is set per card by the block at the end of this script.
  function loc(en, ar){ return window._tarkibAR ? ar : en; }
  function extractAnswers(raw){
    const re = /\x7b\x7bc\d+::([^:}]+?)(?:::[^}]*?)?\x7d\x7d/g;
    const out=[]; let m;
    while ((m=re.exec(raw))!==null) out.push(m[1].trim());
    return out;
  }
  function renderDiff(typed, correct){
    let d=''; const max=Math.max(typed.length, correct.length);
    for (let i=0;i<max;i++){ const t=typed[i],c=correct[i];
      if (t!==undefined&&c!==undefined&&t===c){ d+='<span class="ok">'+esc(c)+'</span>'; }
      else if (t!==undefined&&c!==undefined){ d+='<span class="bad">'+esc(t)+'</span>'; }
      else if (c!==undefined){ d+='<span class="missing">_</span>'; }
      else { d+='<span class="extra">'+esc(t)+'</span>'; } }
    return d;
  }
  window.checkClozeAnswer = function(btn){
    const card=btn.closest('.cloze-card');
    const rawEl=card.querySelector('.cloze-raw');
    const raw=decodeEntities(rawEl?rawEl.textContent:'');
    const answers=extractAnswers(raw);
    const inputs=card.querySelectorAll('.cloze-type-wrapper .my-type-input');
    const fb=card.querySelector('.check-feedback');
    if (!answers.length){ fb.innerHTML='Could not extract answer. Raw: '+esc(raw.substring(0,100)); fb.className='check-feedback warn'; return; }
    const typedAll=[...inputs].map(i=>i.value||'');
    if (!typedAll.some(v=>v.trim())){ fb.innerHTML=loc('Type your answer first.','اكتب إجابتك أولا'); fb.className='check-feedback warn'; return; }
    if (answers.length===1 || inputs.length===1){
      const typed=norm(typedAll.join(' ')); const correct=norm(answers.join(' '));
      if (typed===correct){ fb.innerHTML='✓ '+loc('Correct!','صحيح'); fb.className='check-feedback good'; return; }
      fb.innerHTML='✗ '+loc('Not quite: ','ليس تماما: ')+'<span class="char-diff">'+renderDiff(typed,correct)+'</span>'; fb.className='check-feedback bad'; return;
    }
    const results=[]; let allCorrect=true;
    for (let i=0;i<Math.max(inputs.length,answers.length);i++){
      const t=norm(typedAll[i]||''); const c=norm(answers[i]||'');
      if (t===c&&t!==''){ results.push('<span class="ok">✓ '+esc(c)+'</span>'); }
      else { allCorrect=false; results.push('<span class="bad">'+esc(t||'(empty)')+'</span> → <span class="missing">'+esc(c)+'</span>'); }
    }
    if (allCorrect){ fb.innerHTML='✓ '+loc('All correct!','كله صحيح'); fb.className='check-feedback good'; }
    else { fb.innerHTML='✗ '+loc('Not quite:','ليس تماما:')+'<br>'+results.join('<br>'); fb.className='check-feedback bad'; }
  };
  // Typing a single character anywhere proves the keyboard works, so remember that and never nag
  // again. localStorage survives restarts; the window flag covers the session if storage is blocked.
  document.addEventListener('input', function(e){
    if (e.target && e.target.classList && e.target.classList.contains('my-type-input')){
      window._tarkibTyped = true;
      try { localStorage.setItem('tarkib.typed', '1'); } catch (err) { /* private mode, fine */ }
      document.querySelectorAll('.keyboard-hint').forEach(function(h){ h.style.display='none'; });
    }
  }, true);
  document.addEventListener('keydown', function(e){
    if (e.key==='Enter'){ const wrapper=e.target.closest?e.target.closest('.cloze-type-wrapper'):null;
      const btn=wrapper?wrapper.querySelector('.check-btn'):null; if (btn){ e.preventDefault(); btn.click(); } }
  }, true);
})();
// AnkiDroid does not hand keyboard focus to a plain HTML input during review until the user turns
// on Settings, Advanced, "Type answer into the card" AND restarts the app (the setting alone
// does not take effect in the open session). So
// Android users get told, and nobody else does: iPhone, iPad and desktop never match this test.
// This block sits OUTSIDE the install-once wrapper above on purpose. Inside it, the early return
// meant the hint appeared on the first card of a session and never again, which is exactly when a
// stuck user needs it most.
// On an Arabic edition card the hint is the ONE bilingual string, and the two lines are not
// translations of each other by accident: AnkiDroid translates its whole menu, so the Arabic line
// names the Arabic items (الإعدادات, خيارات متقدمة, إدخال الجواب في البطاقة) and the English line
// names the English ones. A reader follows whichever line matches the language their app runs in.
// Never collapse them to one line or translate one from the other.
(function(){
  // Which edition is this card from? Every note in the Arabic build carries edition::ar, and Anki
  // exposes {{Tags}} to the template, so the card can answer that without a new field or any change
  // to the data. An English-edition card has no such tag, so nothing below touches it.
  var tagEl = document.querySelector('.note-tags');
  var ar = !!(tagEl && /edition::ar/.test(tagEl.textContent || ''));
  window._tarkibAR = ar;
  if (ar){
    document.querySelectorAll('.my-type-input').forEach(function(i){
      i.placeholder = 'اكتب الإجابة'; });
    document.querySelectorAll('.check-btn').forEach(function(b){ b.textContent = 'تحقق'; });
  }
  if (!/Android/i.test(navigator.userAgent||'')) return;
  var typed = window._tarkibTyped === true;
  if (!typed){ try { typed = localStorage.getItem('tarkib.typed') === '1'; } catch (err) {} }
  if (typed) return;
  document.querySelectorAll('.keyboard-hint').forEach(function(h){
    h.style.display = '';
    if (ar && h.getAttribute('data-bilingual') !== '1'){
      h.setAttribute('data-bilingual', '1');
      h.innerHTML =
        '<span dir="rtl" style="display:block">لا تعمل لوحة المفاتيح؟ في AnkiDroid افتح الإعدادات ثم '
      + 'خيارات متقدمة، وقم بتفعيل خيار «إدخال الجواب في البطاقة»، ثم أعد تشغيل التطبيق وعد إلى هذه البطاقة.</span>'
      + '<span dir="ltr" style="display:block;margin-top:6px">No keyboard? In AnkiDroid open Settings, '
      + 'then Advanced, and switch on "Type answer into the card". Restart AnkiDroid, then come back '
      + 'to this card.</span>';
    }
  });
})();
</script>"""

CLOZE_BACK = r"""<div class="cloze-card cloze-back">
  {{#Image}}<div class="cloze-image">{{Image}}</div>{{/Image}}
  <div class="cloze-sentence cloze-revealed">{{cloze:Text}}</div>
  {{#Translation}}<div class="cloze-translation">{{Translation}}</div>{{/Translation}}
  {{#GrammarHint}}<div class="cloze-grammar">{{GrammarHint}}</div>{{/GrammarHint}}
  {{#BackAudio}}<div class="cloze-audio">{{BackAudio}}</div>{{/BackAudio}}
</div>"""

CLOZE_CSS = """.card { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; text-align: center; padding: 20px; background-color: #0a0e1a; color: #e4e4e7; }
.cloze-card { max-width: 640px; margin: 0 auto; padding: 24px; background: #171923; border-radius: 12px; border: 1px solid rgba(99, 102, 241, 0.15); }
.cloze-image img { max-width: 260px; max-height: 200px; border-radius: 8px; margin: 0 auto 16px auto; display: block; }
.cloze-sentence { font-size: 22px; line-height: 1.6; margin: 16px 0; color: #e4e4e7; font-weight: 500; }
.cloze { color: #818cf8; font-weight: 700; background: rgba(99, 102, 241, 0.15); padding: 2px 10px; border-radius: 4px; border-bottom: 2px solid #6366f1; font-style: normal; }
.cloze-revealed .cloze { color: #34d399; background: rgba(16, 185, 129, 0.12); border-bottom-color: #10b981; }
.cloze-translation { font-size: 15px; color: #a1a1aa; margin-top: 16px; padding: 12px; background: rgba(255,255,255,0.03); border-radius: 6px; line-height: 1.5; }
.cloze-grammar { font-size: 13px; color: #fbbf24; margin-top: 12px; padding: 10px 12px; background: rgba(251,191,36,0.08); border-radius: 6px; border-left: 3px solid #fbbf24; font-weight: 500; text-align: left; }
.cloze-audio { margin-top: 14px; }
.card:not(.nightMode) { background-color: #f8fafc; color: #1e293b; }
.card:not(.nightMode) .cloze-card { background: #fff; border-color: rgba(99,102,241,0.2); box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
.card:not(.nightMode) .cloze-sentence { color: #1e293b; }
.card:not(.nightMode) .cloze { color: #4f46e5; background: rgba(99,102,241,0.08); border-bottom-color: #4f46e5; }
.card:not(.nightMode) .cloze-revealed .cloze { color: #059669; background: rgba(16,185,129,0.08); border-bottom-color: #059669; }
.card:not(.nightMode) .cloze-translation { color: #64748b; background: rgba(0,0,0,0.03); }
.cloze-type-wrapper { margin: 14px auto 4px auto; text-align: center; }
.cloze-type-wrapper input[type="text"] { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; font-size: 17px; padding: 10px 14px; border: 2px solid rgba(99,102,241,0.4); background: rgba(99,102,241,0.08); color: #e4e4e7; border-radius: 8px; min-width: 260px; max-width: 80%; text-align: center; }
.cloze-type-wrapper input[type="text"]:focus { outline: none; border-color: #818cf8; background: rgba(99,102,241,0.14); }
.cloze-type-wrapper input[type="text"] { -webkit-user-select: text; user-select: text; -webkit-tap-highlight-color: transparent; touch-action: manipulation; }
.keyboard-hint { font-size: 12px; color: #9ca3af; margin-top: 8px; line-height: 1.4; }
.card:not(.nightMode) .cloze-type-wrapper input[type="text"] { color: #1e293b; border-color: rgba(99,102,241,0.3); background: rgba(99,102,241,0.04); }
.check-row { margin-top: 10px; }
.check-btn { padding: 8px 18px; background: #6366f1; color: #fff; border: none; border-radius: 6px; font-size: 14px; font-weight: 600; cursor: pointer; }
.check-btn:hover { background: #818cf8; }
.check-feedback { margin-top: 10px; min-height: 20px; font-size: 14px; padding: 8px 12px; border-radius: 6px; text-align: center; }
.check-feedback:empty { display: none; }
.check-feedback.good { color: #34d399; background: rgba(16,185,129,0.1); }
.check-feedback.bad { color: #f87171; background: rgba(248,113,113,0.1); }
.check-feedback.warn { color: #fbbf24; background: rgba(251,191,36,0.1); }
.char-diff { font-family: ui-monospace, Menlo, monospace; font-size: 17px; letter-spacing: 1px; margin-left: 6px; }
.char-diff .ok { color: #34d399; } .char-diff .bad { color: #f87171; text-decoration: line-through; }
.char-diff .missing { color: #fbbf24; } .char-diff .extra { color: #f87171; font-style: italic; }
"""


# Bump this whenever GERMAN_AI_CSS / CLOZE_CSS / the templates above change, so existing installs
# pick up the new look on their next card add. The marker is stored inside the note type's own CSS,
# so it travels with the collection (and across devices via sync). These note types are OURS, so
# this only ever restyles our own types — never the user's other note types.
TEMPLATE_VERSION = 9  # v9: the Arabic hint names AnkiDroid's Arabic menu items, not the English ones
                      # (v5: cloze input tappable + the hint; v4: .arabic-word -> .secondary-word)
_VTAG = "/* german-ai-cards:notetype-v%d */" % TEMPLATE_VERSION


# Ownership and freshness are two different questions and the marker answers both. _VPREFIX says
# "this type is ours, whatever version made it"; _VTAG says "it is at the current version". Testing
# only _VTAG conflates them: the day TEMPLATE_VERSION is bumped, a note type that carries an OLDER
# marker and one we have never seen both fail the same check. That matters because the ready-made
# decks carry the marker too, so a version bump here refreshes their templates on the next card add,
# outside the undo entry. Bump only for a template change that is safe to apply to those decks.
_VPREFIX = "/* german-ai-cards:notetype-v"


def _ours(m):
    """True only for a note type this add-on or the ready-made decks created, at any version."""
    return _VPREFIX in (m.get("css") or "")


def _current(m):
    return _VTAG in (m.get("css") or "")


def _versioned(css):
    return "%s\n%s" % (_VTAG, css)


def _field_names(m):
    return {f.get("name") for f in (m.get("flds") or [])}


# ── frozen note type names ──────────────────────────────────────────────────────────────────
# Two sources create note types for the same cards: the ready-made decks and this add-on.
# On import Anki matches note types by ID, never by name, and an add-on CANNOT choose an id — the
# Rust backend hard-asserts that a new note type's id is 0 and panics otherwise. So if the add-on
# created a type with the deck's NAME, a later deck import would land beside it as
# "Tarkib German+". Hence the split below:
#
#   the add-on ADOPTS the deck names (preferring them, so it converges onto one type after a deck
#   import) but only ever CREATES its own. Renaming these orphans existing cards, so the names are
#   frozen. The deck builder derives its schema ids from a separate frozen key, not from the
#   display name, which is what made the one rename from "German AI Cards" safe.
MAIN_NOTETYPE = "Tarkib German"            # ready-made decks: adopt, never create
CLOZE_NOTETYPE = "Tarkib German Cloze"
ADDON_MAIN = "Tarkib"                      # what the add-on creates when no deck type is present
ADDON_CLOZE = "Tarkib Cloze"
# Created under the old name before the add-on was renamed. Adopted so an existing collection keeps
# using the type its cards already point at; never created. Renaming a type in place would orphan
# every card on it, which is why the rename adds a name rather than replacing one.
LEGACY_MAIN = "German AI"
LEGACY_CLOZE = "CustomClozeDE"


def _first_existing(mm, names):
    for name in names:
        m = mm.by_name(name)
        if m is not None:
            return m
    return None


def find_main(mm):
    """The main note type to write to. The deck name first, so that once a user imports a deck the
    add-on starts adding to that same type instead of maintaining a second one forever."""
    return _first_existing(mm, (MAIN_NOTETYPE, ADDON_MAIN, LEGACY_MAIN))


def find_cloze(mm):
    return _first_existing(mm, (CLOZE_NOTETYPE, ADDON_CLOZE, LEGACY_CLOZE))


def check_main_notetype(m):
    """Fingerprint a pre-existing note type before we adopt it. We match note types by
    NAME only, so a same-named type from another source (a shared deck, another add-on) must not be
    silently rewritten: refreshing its templates would re-render every one of the user's existing
    cards with {{Front}}/{{Back}} references that may not exist. Raises a friendly RuntimeError
    (routed by providers.friendly_error) instead of a raw KeyError mid-write."""
    missing = [f for f in ("Front", "Back") if f not in _field_names(m)]
    if missing:
        raise RuntimeError(
            "Your collection already has a note type called '%s' that is missing field(s): %s.\n"
            "It was not created by this add-on, so it was left untouched.\n"
            "Fix: in Tools → Manage Note Types, rename that note type (e.g. '%s (old)') so the "
            "add-on can create its own, or add the missing field(s) to it."
            % (m["name"], ", ".join(missing), m["name"])
        )


def check_cloze_notetype(m):
    """Same fingerprint for a pre-existing 'CustomClozeDE': it needs all CLOZE_FIELDS AND must be a
    genuine cloze type (type == 1), otherwise {{c1::…}} never works and the cards are silently dead."""
    missing = [f for f in CLOZE_FIELDS if f not in _field_names(m)]
    if missing:
        raise RuntimeError(
            "Your existing '%s' note type is missing field(s): %s.\n"
            "Expected fields: %s.\n"
            "Fix: add the missing field(s) in Tools → Manage Note Types, or rename/delete the old note "
            "type so the add-on can recreate it."
            % (m["name"], ", ".join(missing), ", ".join(CLOZE_FIELDS))
        )
    if m.get("type") != 1:
        raise RuntimeError(
            "Your existing '%s' note type is not a cloze note type, so cloze cards cannot work.\n"
            "Fix: in Tools → Manage Note Types, rename or delete it so the add-on can recreate it as a "
            "cloze type." % m["name"]
        )


def _compatible(check, m):
    try:
        check(m)
        return True
    except RuntimeError:
        return False


def ensure_notetypes(col):
    """Create the two note types if missing; otherwise refresh their CSS + card templates when an
    OLDER add-on version created them. Idempotent and PRESENTATION-ONLY — it never adds/removes
    fields or touches card data, so existing cards simply re-render with the latest design.

    Collision safety: a same-named type we did NOT create is never modified. That is
    fatal for the add (raises a friendly RuntimeError, before any media is written). For
    'CustomClozeDE' we only skip the refresh here; write_bundle raises the friendly error only when a
    cloze card is actually being written, so the MAIN card keeps working (hard rule 2).
    """
    mm = col.models

    m = find_main(mm)
    if m is not None:
        check_main_notetype(m)   # raises before anything is touched
    if m is None:
        m = mm.new(ADDON_MAIN)
        for f in ("Front", "Back"):
            mm.add_field(m, mm.new_field(f))
        t = mm.new_template("Card 1")
        t["qfmt"] = GERMAN_AI_FRONT
        t["afmt"] = GERMAN_AI_BACK
        mm.add_template(m, t)
        m["css"] = _versioned(GERMAN_AI_CSS)
        mm.add(m)
    elif _ours(m) and not _current(m):
        _refresh(mm, m, GERMAN_AI_CSS, GERMAN_AI_FRONT, GERMAN_AI_BACK)

    m = find_cloze(mm)
    if m is None:
        m = mm.new(ADDON_CLOZE)
        m["type"] = 1  # cloze note type (enables {{cloze:Text}})
        for f in CLOZE_FIELDS:
            mm.add_field(m, mm.new_field(f))
        t = mm.new_template("Cloze")
        t["qfmt"] = CLOZE_FRONT
        t["afmt"] = CLOZE_BACK
        mm.add_template(m, t)
        m["css"] = _versioned(CLOZE_CSS)
        mm.add(m)
    elif _ours(m) and not _current(m) and _compatible(check_cloze_notetype, m):
        _refresh(mm, m, CLOZE_CSS, CLOZE_FRONT, CLOZE_BACK)   # never restyle a foreign type


def _refresh(mm, m, css, qfmt, afmt):
    """Best-effort: re-apply our latest CSS + first-template HTML to an existing note type. Wrapped
    so a refresh failure (e.g. a stale type whose fields the template references are missing) can
    NEVER block card creation — worst case the card just adds with the previous template."""
    try:
        m["css"] = _versioned(css)
        if m["tmpls"]:
            m["tmpls"][0]["qfmt"] = qfmt
            m["tmpls"][0]["afmt"] = afmt
        mm.update_dict(m)
    except Exception:
        pass
