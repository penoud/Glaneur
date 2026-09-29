# Impact Map

<!--
Temporary scratchpad, one story at a time. Reset to this empty state
between two stories. Do not store copies of files, logs, bulky test
output, or information that already lives in CLAUDE.md. See CLAUDE.md
sections "Impact Map" and "Minimal context policy".
-->

## Task

**US-EN-08 — AppStream metainfo and residual FR text mop-up.**

Eighth (and final) story of the sprint
`docs/sprints/2026-09-french-to-english-complete.md`.

Rewrites the three remaining French user-visible surfaces:

1. **CLI stdout summary** in `cli.py`: `téléchargées`, `reprises`,
   `déjà à jour`, `inchangées`, `supprimées`, `ignorées`, `échecs`,
   `volume`, `Interrompu.`, `Dossier déjà en cours d'utilisation`,
   `image(s) remise(s) en file` → English.
2. **AppStream metainfo** at `packaging/linux/org.glaneur.Glaneur.metainfo.xml`:
   summary + description flipped to English and updated from
   WordPress-only wording to include Djangoplicity, per CLAUDE.md's
   long-standing known gap.
3. **`Glaneur.desktop`** and **`bump-metainfo.sh`** comment strings.

Closes the "French → English" sprint. The only remaining intentional
French text is the dual-language README.

## Directly modified

- `cli.py` — stdout summary lines and `Interrupted` /
  `Folder already in use` messages.
- `tests/test_cli.py` — assertions on the CLI summary substrings and
  the `--restore` output line.
- `packaging/linux/org.glaneur.Glaneur.metainfo.xml` — `<summary>`,
  `<description>`, XML comment.
- `packaging/linux/Glaneur.desktop` — `Comment=`, `Keywords=`.
- `packaging/linux/bump-metainfo.sh` — script comment header, error
  message, success message.
- `CLAUDE.md` — Known gaps list pruned: dispatch values, manifest
  keys, CLI flags, Qt contexts, `.ts` source language, French
  docstrings, and the AppStream WordPress-only gap all closed; only
  the intentional dual-language README note remains, plus the
  independent WINDOWS_PFX_BASE64 signing note (story 9).

## Direct dependencies

- No engine, source, config, or persisted format touched.
- No new tests: `tests/test_cli.py` already covers the CLI stdout
  branches; only its French assertion substrings switch to EN.

## Explicitly out of scope

- README dual-language content — sprint decision.
- **`__version__`** — unchanged.

## Tests

- `tests/test_cli.py::TestReturnCodes::test_130_on_keyboard_interrupt`
  asserts on `"Interrupted"`.
- `tests/test_cli.py::TestStdoutOutput::test_summary_contains_the_counters`
  asserts on the new EN summary labels (`downloaded`, `resumed`,
  `up-to-date`, `unchanged`, `deleted`, `skipped`, `failures`).
- `tests/test_cli.py::TestRestore.*` asserts on `re-queued`.

Verification:

- `pytest -q` → still 507 passed / 2 skipped.
- `python tools/check_coverage.py` → floors held.
- `ruff check` on touched files: no new warnings.

## Invariants

- `__version__` unchanged.
- No engine/source/config change.
- No dispatch/manifest/cache key touched.
- CLI flag names unchanged (US-EN-06 owns those).
- Qt tr()/translate() sources unchanged (US-EN-07 owns those).
- Coverage floors held.

## Validation

Level `local` per sprint doc.

- `pytest -q` green.
- `python tools/check_coverage.py` green.
- `ruff check cli.py tests/test_cli.py packaging/` clean on baseline.
