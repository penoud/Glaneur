# Impact Map

<!--
Temporary scratchpad, one story at a time. Reset to this empty state
between two stories. Do not store copies of files, logs, bulky test
output, or information that already lives in CLAUDE.md. See CLAUDE.md
sections "Impact Map" and "Minimal context policy".
-->

## Task

**US-EN-06 — CLI flags → English with hidden FR aliases.**

Sixth story of the sprint
`docs/sprints/2026-09-french-to-english-complete.md`. Independent of
US-EN-03/04/05 in principle; runs on top of the current tree.

### Rename table

| Old flag | New (canonical) flag | dest |
|---|---|---|
| `--dossier` | `--folder` (and `-d`) | `target_dir` |
| `--classement` | `--sort` | `sort_mode` |
| `--largeur-min` | `--min-width` | `min_width` |
| `--delai` | `--delay` | `delay` |
| `--verifier` | `--verify` | `verify` |
| `--pas-cache` | `--no-cache` | `no_cache` |
| `--depuis` | `--since` | `since` |
| `--jusqua` | `--until` | `until` |
| `--restaurer` | `--restore` | `restore` |

Unchanged: `--type`, `--format`, `--force` (already English).

### Alias mechanism

Each canonical EN flag registers via `add_argument("--folder", ...)`
with visible help text. The FR alias registers via a second
`add_argument("--dossier", dest="target_dir", help=argparse.SUPPRESS)`
so it stays hidden from `--help` but keeps existing scripts working.
Verified interactively: argparse accepts two `add_argument` calls
sharing the same `dest`, and `SUPPRESS` hides the FR row from help
output.

## Directly modified

- `cli.py` — the argparse block. Every visible help string and the
  parser `description` translated to English at the same time. Every
  `args.<fr_name>` reference (`args.dossier`, `args.classement`,
  `args.delai`, `args.verifier`, `args.pas_cache`, `args.depuis`,
  `args.jusqua`, `args.restaurer`, `args.largeur_min`) updated to
  `args.<en_dest>`.
- `tests/test_cli.py` — the `test_overrides_via_flags` scenario
  switches to the EN flag names; a new `test_fr_aliases_still_work`
  test locks the backwards-compat contract by driving the parser
  with the FR flags and asserting the same Options are built.
  `test_invalid_sort_mode_choice` swaps `--classement` → `--sort`.
  `TestRestore` switches `--dossier`/`--restaurer` → `--folder`/
  `--restore`.

## Direct dependencies

- `Config`, `Options`, `Engine`: unchanged. Flags map to their
  existing dataclass fields.
- No manifest, cache, or dispatch-value changes.

## Explicitly out of scope

- **Stdout summary lines** (`téléchargées`, `reprises`, `déjà à
  jour`, `inchangées`, `supprimées`, `ignorées`, `échecs`, `volume`)
  — user-visible French UI strings; belong to US-EN-08 residual FR
  text mop-up (or a locals-cleanup follow-up). Not touched here.
- **`--type` / `--format` / `--force`** — already English, kept
  as-is.
- **`Interrompu.` message** on Ctrl+C — French user-visible; US-EN-08.
- **`Dossier déjà en cours d'utilisation`** stderr message — French
  user-visible; US-EN-08.
- **CLI docstring examples** (`python cli.py --dossier ...`) — updated
  in lockstep with the flag rename, since they'd otherwise document
  a hidden alias.
- **`--largeur-min` dest was `min_width`** already; no dataclass
  rename here.
- **`__version__`** — unchanged.

## Tests

`tests/test_cli.py` covers:
- `test_overrides_via_flags` (renamed EN flags produce the same
  Options as before).
- **NEW** `test_fr_aliases_still_work` — same scenario but through
  every FR alias; asserts identical Options.
- `test_invalid_sort_mode_choice` uses the new EN name.
- `TestRestore.test_restore_with_explicit_ids` and
  `test_restore_without_ids_takes_all_deleted` use `--folder` and
  `--restore`.
- **NEW** `test_help_hides_fr_aliases` — captures `--help` output
  via `SystemExit` from `parser.parse_args(["--help"])` and asserts
  the EN names appear and no FR name is listed.

Verification:

- `pytest -q` → still passes, +2 new tests.
- `python tools/check_coverage.py` → floors still met.
- `ruff check` on touched files: no new warnings.

## Invariants

- `__version__` unchanged.
- Every pre-US-EN-06 FR flag still parses to the same `Options`.
- Help text lists only the canonical EN flags plus `-h`/`--help`.
- No config, manifest, cache, or dispatch value literal touched.
- No engine or source code touched.
- Coverage floors held.

## Validation

Level `module` — a single-file CLI change with parametrised argparse
plus its dedicated test module. `invariant-reviewer` not required
per the sprint doc's per-US validation column, and no boundary or
persisted format is crossed.

- `pytest -q --cov=Glaneur --cov-branch` green.
- `python tools/check_coverage.py` green.
- `ruff check` clean on `cli.py` and `tests/test_cli.py` (baseline
  preserved).
