# Impact Map

<!--
Temporary scratchpad, one story at a time. Reset to this empty state
between two stories. Do not store copies of files, logs, bulky test
output, or information that already lives in CLAUDE.md. See CLAUDE.md
sections "Impact Map" and "Minimal context policy".
-->

## Task

**US-EN-02 — Rename French test names and test classes to English.**

Second story of the sprint
`docs/sprints/2026-09-french-to-english-complete.md`.

The test suite has 445 test functions; 219 of them use French words in
their names (`test_erreur_reseau`, `test_deux_processus_second_leve_folder_busy`,
`test_aucune_image`, …), and a handful of test classes are French too
(`TestExecuter`, `TestChargerManifeste`, `TestTelecharger`,
`TestCoupeCircuit`, `TestSauverManifesteFusion`, `TestExecuterExtra`).

Objective: rewrite these names in English, preserving test bodies,
docstrings, fixtures, parametrize IDs, class ordering, and file
structure. Zero behaviour change; the test suite output must remain
identical.

## Directly modified

Every `tests/test_*.py` file with a French test name or test class:

- `tests/test_bug_report.py` (7 FR names)
- `tests/test_cli.py` (9)
- `tests/test_config.py` (17)
- `tests/test_core.py` (55, plus FR classes)
- `tests/test_folder_lock.py` (5)
- `tests/test_i18n.py` (10)
- `tests/test_logsetup.py` (2)
- `tests/test_scheduler.py` (10)
- `tests/test_source_base.py` (15)
- `tests/test_source_djangoplicity.py` (11)
- `tests/test_sources_edges.py` (25)
- `tests/test_source_wordpress.py` (13)
- `tests/test_system.py` (12)
- `tests/test_updater_downloader.py` (10)
- `tests/test_updater_threads.py` (3)
- `tests/test_updater_threads_run.py` (3)
- `tests/test_updater_version.py` (12)

Class renames (case by case):

- `TestExecuter` → `TestRun`
- `TestExecuterExtra` → `TestRunExtra`
- `TestChargerManifeste` → `TestLoadManifest`
- `TestSauverManifesteFusion` → `TestSaveManifestMerge`
- `TestTelecharger` → `TestDownload`
- `TestCoupeCircuit` → `TestCircuitBreaker`

Any other French class name discovered during the pass gets the same
treatment; the naming above is the pattern (English noun clause,
`Test` + PascalCase behaviour tested).

## Direct dependencies

- `conftest.py` and `tests/conftest.py`: **read only**. If any fixture
  is referenced by name in a docstring, it stays; fixture names
  themselves are not French.
- Production code: **not modified**. This US is test-file names only.
- `tools/check_coverage.py`: **read only**. Coverage floors do not
  change; renaming test functions cannot change coverage.

## Explicitly out of scope

- **Test bodies**: assertions, fixtures, mocks, parametrize values —
  untouched. Only the `def test_xxx` line (and its docstring `noun`
  where the docstring restates the French test name) may change.
- **Docstrings**: kept as is if already English. If a French docstring
  literally repeats the test name in French, translate it inline; do
  not otherwise translate docstrings (that was US-EN-01's job and is
  already done for the load-bearing docs).
- **Test files' module docstring**: untouched (already English).
- **Fixture names**: no renames.
- **Parametrize `id=` values**: no renames.
- **Class attributes** and helper functions inside test modules:
  untouched.
- **Production code identifiers**: US-EN-03.
- **Dispatch values referenced in tests**: US-EN-04.
- **Manifest keys in fixtures**: US-EN-05.
- **`__version__`**: unchanged.

## Tests

No test added or removed. Nothing structural changes. The full suite
must remain green with the same 495 passed / 2 skipped counts.

Verification steps:

- `pytest -q` → 495 passed, 2 skipped (identical to US-VERIF-04 and
  US-EN-01 baseline).
- `pytest --collect-only -q | wc -l` — collected-test count must be
  stable across the rename.
- `ruff check tests/` on the touched files.

## Invariants

- `__version__` unchanged.
- Zero production line modified.
- Number of collected tests unchanged (445 test functions plus
  parametrization).
- Test outputs unchanged (no assertion touched, no fixture reordered).
- Coverage floors held (renaming has no effect on line/branch
  coverage of the production package).

## Validation

Level `local`. Test-file text-only rename.

- `pytest -q` green.
- `pytest --collect-only -q` yields the same test count.
- `ruff check tests/` clean on the touched files (pre-existing
  warnings unchanged).
- No `invariant-reviewer` (no invariant touched).
