# Impact Map

<!--
Temporary scratchpad, one story at a time. Reset to this empty state
between two stories. Do not store copies of files, logs, bulky test
output, or information that already lives in CLAUDE.md. See CLAUDE.md
sections "Impact Map" and "Minimal context policy".
-->

## Task

**Lot 5.0 E1 (part 2) — Preferences in tabs.**

Follows the just-landed `PROFILE_FIELDS` (part 1). Refactors
`DialoguePreferences.__init__` from a stack of QGroupBoxes into a
`QTabWidget` with four tabs, keyed off `Glaneur.config.PROFILE_FIELDS`
per `docs/design/evolution-multi-sources.md` §3.2 and
`docs/design/roadmap.md` §5.0.

### Tab layout

| Tab | Contents | Visibility |
|---|---|---|
| **General** | interval, autostart (Windows), slideshow (Windows), close-to-tray, updates-at-startup, language | visible |
| **Site** | type, URL, format, target_dir, sort, min_width, verify_integrity — every field in `PROFILE_FIELDS` | visible |
| **Filters** | placeholder — the fields land in E5 (lot 11.2) | hidden via `setTabVisible(idx, False)` |
| **Images** | placeholder — the fields land in E6 (lot 11.5, resizing) | hidden via `setTabVisible(idx, False)` |

Wording: the visible group titles (`Site`, `Options`, ...) go away —
tab labels replace them. The English tab labels are wrapped in
`tr()` so they translate.

### Rebuilding

`__init__` now delegates each tab to a `_build_<name>_tab()` helper
returning a `QWidget`. Nothing else about the dialog changes:

- widget names and public attributes stay identical (`combo_type`,
  `combo_classement`, `champ_dossier`, ...), so `appliquer` and
  `_sur_changement_type` still work verbatim;
- OK / Cancel buttons stay at the bottom, outside the tabs;
- default focus stays on the first field of the first visible tab
  (the "General" tab), which matches typical UX for a settings
  dialog.

## Directly modified

- `app.py::DialoguePreferences.__init__` — replaced the QVBoxLayout of
  groupboxes with a `QTabWidget`, and four `_build_*_tab()` helpers.
- `tests/test_app_preferences.py` — new file, pytest-qt based:
  - dialog opens with four tabs, first two visible, last two hidden;
  - the widget attributes callers rely on
    (`combo_type`, `champ_site`, `combo_format`, `champ_dossier`,
    `combo_intervalle`, `combo_classement`, `spin_largeur`,
    `case_verifier`, `case_diaporama`, `case_barre`,
    `case_demarrage`, `case_maj_demarrage`, `combo_langue`) all
    exist and hold the seeded values;
  - **byte-for-byte guard**: `Config.save()` → open dialog →
    `dialog.appliquer()` (OK without edits, on Linux where autostart
    and slideshow are no-ops) → `Path(config.json).read_bytes()` is
    unchanged.

## Direct dependencies

- `Glaneur/config.py::PROFILE_FIELDS` — used only conceptually here
  (the tab split matches the tuple). The migration test in
  `tests/test_config.py::TestProfileFields` already locks the tuple.
- No engine, source, cache, or manifest touched.

## Explicitly out of scope

- Actually placing widgets under the Filters / Images tabs —
  E5 (lot 11.2) and E6 (lot 11.5).
- The v1 → v2 config migration — E3 / lot 5.1.
- `Glaneur/system.py` extraction — already done in an earlier lot.
- `__version__` — unchanged.

## Tests

Existing tests unaffected. Three focused new tests in
`tests/test_app_preferences.py` cover the tabbed layout, the widget
attribute contract, and the byte-for-byte config-preservation
invariant.

Verification:

- `pytest -q` → 519 + 3 new tests.
- `python tools/check_coverage.py` → floors held.
- `ruff check app.py tests/test_app_preferences.py` clean on
  baseline.

## Invariants

- `__version__` unchanged.
- `Config` load/save behaviour unchanged.
- `PROFILE_FIELDS` unchanged.
- Public API of `DialoguePreferences` unchanged: attribute names of
  every widget survive, and `appliquer()` behaves the same as before.
- Filters/Images tabs stay hidden until E5/E6 place widgets in them.
- Coverage floors held.

## Validation

Level `module` (single-file UI refactor plus a dedicated test
module).

- `pytest -q --cov=Glaneur --cov-branch` green.
- `python tools/check_coverage.py` green.
- `ruff check` clean on touched files.
