<!-- Thanks for contributing! Keep PRs small and focused. -->

## What & why
<!-- What does this change, and why? -->

## Type
- [ ] Bug fix
- [ ] Language / level prompt improvement
- [ ] New feature
- [ ] Docs / chore

## For prompt / language / level changes
<!-- Nobody can eyeball every language, so paste BEFORE/AFTER example cards for a couple of
     words so the quality is reviewable. -->

## Checklist
- [ ] `python3 tests/test_guards.py` passes
- [ ] `python3 -m py_compile $(git ls-files '*.py')` is clean
- [ ] Tested (offline and/or in Anki), test steps below
- [ ] **No API key / `meta.json` committed**
- [ ] Pure standard library only; Qt touched only on the main thread; card-adding never breaks
- [ ] Card fields/structure unchanged (or a migration is described)

## Test steps
<!-- How did you verify it? -->
