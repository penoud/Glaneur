# Impact Map

<!--
Temporary scratchpad, one story at a time. Reset to this empty state
between two stories. Do not store copies of files, logs, bulky test
output, or information that already lives in CLAUDE.md. See CLAUDE.md
sections "Impact Map" and "Minimal context policy".
-->

## Task

**fix(i18n): restore French UI post US-EN-07.**

US-EN-07 (commit `b4dd8ad`) flipped Qt's source language from French to
English across every `tr()` / `translate()` call and regenerated
`glaneur_fr.ts` as the (EN → FR) translation. Two bugs slipped through
and together caused the user-visible regression — "la traduction ne
fonctionne plus pour la majorité de l'UI, il y a bien certains qui
changent mais pas tous":

1. **`Glaneur/i18n.py` was never updated.** It still treats French as
   the source: when the configured or system language is `"fr"`,
   `install_translator` returns early without loading
   `glaneur_fr.qm`, so FR users see the raw English source strings
   instead of the French UI. Only hardcoded-FR dict labels in
   `Glaneur/config.py` (`SORT_MODES`, `SOURCE_TYPES`,
   `INTERVAL_LABELS`) still appear in French — those are the "some
   strings" the user noticed.

2. **`glaneur_fr.ts` carries a positional-pairing drift.** The
   US-EN-07 commit message describes how the regenerated .ts was
   populated by positional pairing against the old (FR-sourced) .ts.
   In two contexts the entry order changed between old and new .ts,
   so the pairing is off by one over a contiguous prefix:
   - `Fenetre`: entries 0..13 are cyclically rotated by one
     (translation at position *i* actually belongs to position
     *i+1*; the last entry wraps back to position 0). The main
     window title, every &File/&Update now/… menu item, and the
     tray menu top entries are affected.
   - `Updater`: entries 0..4 are cyclically rotated by one (same
     pattern). The "Update check failed", "Windows installer missing",
     "SHA-256 verification failed", "Update download failed", and
     "Invalid GitHub Releases response" messages are affected.

   Without fix 1 these pairings were never visible (no translator
   loaded). Shipping fix 1 alone would make the main menu read in
   wrong French. Both must land together.

The fixes:

- **i18n.py** — invert the special case: `langue == "en"` is the
  no-op (source language); any other language loads
  `glaneur_<code>.qm`; load failure falls back to the English source.
- **glaneur_fr.ts** — rotate the FR translations one position UP
  within the two affected blocks (``Fenetre`` first 14 entries;
  ``Updater`` first 5 entries), so FR[*i*] ends up on the EN
  source it semantically translates. Then regenerate
  `glaneur_fr.qm` via `pyside6-lrelease`.

## Directly modified

- `Glaneur/i18n.py` — invert the special case, update the module and
  function docstrings. `translations_dir()` and `resolve_language()`
  shape unchanged; `resolve_language`'s last-resort fallback moves
  from `"fr"` to `"en"` (the current source language).
- `tests/test_i18n.py` — flip `TestInstallTranslator` (`fr` now loads
  the real `glaneur_fr.qm`; `en` is the no-op) and
  `TestResolveLanguage::test_last_resort_is_fr` becomes
  `_is_en`.
- `translations/build_translations.py` — fix the stale comment that
  claims "FR est la langue source".
- `translations/glaneur_fr.ts` — rotate the FR translations in the
  `Fenetre` (14 entries) and `Updater` (5 entries) misaligned
  prefixes so each sits on its correct EN source. Nothing else in
  the file changes.

## Direct dependencies

- `glaneur_fr.qm` must be present at runtime. It is produced by
  `python translations/build_translations.py release`; the file is
  gitignored (per `.gitignore`) so dev/package builds already assume
  the release step runs. No change needed there.

## Explicitly out of scope

- The hardcoded French labels in `Glaneur/config.py`
  (`SORT_MODES`, `SOURCE_TYPES`, `INTERVAL_LABELS`) — US-EN-07
  explicitly left those for a later rename story; untouched here.
- `glaneur_en.ts` content (intentionally empty, Qt falls back to the
  source) — untouched.
- `__version__` — unchanged.
- README's i18n §4 wording — the policy sentence still reads "source
  = French"; a doc-only follow-up, not part of this fix.

## Tests

- `TestInstallTranslator::test_en_is_source_language_loads_nothing`
  — the new no-op case.
- `TestInstallTranslator::test_fr_loads_the_real_qm` — the real
  `glaneur_fr.qm` loads end-to-end.
- `TestInstallTranslator::test_unknown_language_falls_back_to_en`
  — unknown code → fallback to English source.
- `TestInstallTranslator::test_empty_language_delegated_to_resolve`
  — empty configured + system `fr_FR` → `fr` AND the fr translator is
  installed (previously asserted `assert_not_called`).
- `TestResolveLanguage::test_last_resort_is_en` — empty name →
  `"en"`.

Verification:

- `pytest -q tests/test_i18n.py` green.
- Full suite via `test-runner` to confirm no caller regressed.
- `ruff check` clean on touched files.

## Invariants

- `__version__` unchanged.
- The configured language code stored in `Config.language` keeps the
  same accepted values (`""`, `"fr"`, `"en"`); only runtime behavior
  changes.
- No boundary moved: the engine still emits structured events, the UI
  still owns rendering via `UiJournal`.

## Validation

Level `local` per CLAUDE.md's conditional-validation table (local
Python module, no boundary/invariant touched, no persisted format
changed, no public API shape changed).

- `pytest tests/test_i18n.py` green.
- Full suite via `test-runner` (one shot, to confirm no caller of
  `install_translator` depended on the old early-return).
- `ruff check Glaneur/i18n.py tests/test_i18n.py translations/build_translations.py`
  clean.
- No invariant-reviewer: no boundary, no invariant from the
  CLAUDE.md table touched.
