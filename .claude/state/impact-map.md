# Impact Map

<!--
Temporary scratchpad, one story at a time. Reset to this empty state
between two stories. Do not store copies of files, logs, bulky test
output, or information that already lives in CLAUDE.md. See CLAUDE.md
sections "Impact Map" and "Minimal context policy".
-->

## Task

**Lot 5.0 E2 — One-row profile list.**

Replaces the "Site / Folder" banner of the main window with a
`QTableView` fed by a small `QAbstractTableModel`. Columns: name,
type, site, folder, last run, status. With a single implicit
profile there is one row; the user sees no functional difference,
but the table is the shape lot 5.1 (profiles) will slot into.

The status column is built from the engine's structured events
(landed in US-VERIF-04) — "Idle" when the engine is quiet,
"Running…" while a `Travailleur` runs, then a summary derived from
`RunResult` when it finishes (`Done — N downloaded`,
`Deferred until <date>`, `Interrupted`, `Failed`).

### Model

Kept in `app.py` for now (no new module). Later, when `Profile`
lands (E3 / lot 5.1), the same model gains a real list of profiles
and the migration replaces the "row-from-config" helper with a
"row-per-profile" iterator.

- `ProfileRow` — plain dataclass, six string fields matching the
  columns.
- `ProfileTableModel(QAbstractTableModel)` — read-only, exposes a
  `set_row(row: ProfileRow)` mutator that emits `dataChanged` and
  replaces the sole row today. Kept intentionally minimal — future
  edits (multiple rows, editable cells, sort) come with lot 5.1/5.3.

### Columns

| # | Header (en) | Source |
|---|---|---|
| 0 | Name | derived from `cfg.site` netloc, or `Config.default` |
| 1 | Type | `cfg.source_type` via `SOURCE_TYPES` reverse lookup |
| 2 | Site | `cfg.site` |
| 3 | Folder | `cfg.target_dir` |
| 4 | Last run | `cfg.last_run` truncated to `YYYY-MM-DD HH:MM` |
| 5 | Status | in-memory, updated by `Fenetre` |

## Directly modified

- `app.py`:
  - New `ProfileRow` dataclass and `ProfileTableModel` at module top,
    just after `_render_ui`.
  - `Fenetre._construire` builds a `QTableView` in place of
    `label_site` / `label_dossier`.
  - `Fenetre._rafraichir_bandeau` becomes
    `_rafraichir_table_profils` — pushes a fresh `ProfileRow` into
    the model. Preserves the old name as an alias (single-line
    forwarder) so no callers break.
  - `_lancer` sets status to "Running…" before starting the worker.
  - `_terminer(res)` sets the terminal status from the `RunResult`.
- `tests/test_app_profile_table.py` — new pytest-qt module covering
  the model contract and the status pipeline.

## Direct dependencies

- `Glaneur.config.PROFILE_FIELDS` — not used yet at runtime, but the
  column list mirrors the app-level / profile-level split so lot
  5.1's migration slots in cleanly.
- `Glaneur.engine.RunResult` — read only, for status construction.

## Explicitly out of scope

- Multiple rows / real `Profile` list — E3 / lot 5.1.
- Editable cells or in-place profile editing — E3.
- Sort / filter / context menu on the table — lot 5.3.
- `label_site` / `label_dossier` removal — they stay on the class
  (as `None`) to keep `_rafraichir_bandeau` a legal single-line
  forwarder. A follow-up commit will delete them once no caller
  references them.
- `__version__` — unchanged.

## Tests

New pytest-qt module `tests/test_app_profile_table.py`:

- `TestProfileRowFromConfig`: `_profile_row(cfg)` populates every
  column from the seeded config; unknown source_type falls back to
  the raw value; empty site/target_dir/last_run display an em dash.
- `TestModelContract`: `rowCount == 1`, `columnCount == 6`, header
  labels match the design, `data(role=DisplayRole)` returns the row
  fields, editing/other roles return `None`.
- `TestStatusPipeline`: `Fenetre._status_from_result(res)` maps
  `RunResult` to the expected short status string across success,
  defer, interrupted, failure branches.

Verification:

- `pytest -q` → still passing; +new tests.
- `python tools/check_coverage.py` → floors held.
- `ruff check app.py tests/test_app_profile_table.py` clean on
  baseline.

## Invariants

- `__version__` unchanged.
- No engine, source, cache, manifest, or config format change.
- Widget attribute names of every existing widget survive.
- The old `_rafraichir_bandeau` name still exists (as a
  single-line forwarder), so `_ouvrir_preferences` and any other
  caller keeps working.
- Coverage floors held.

## Validation

Level `module` — UI-only refactor, self-contained test module.

- `pytest -q --cov=Glaneur --cov-branch` green.
- `ruff check` clean on touched files.
