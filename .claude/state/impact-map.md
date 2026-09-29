# Impact Map

<!--
Temporary scratchpad, one story at a time. Reset to this empty state
between two stories. Do not store copies of files, logs, bulky test
output, or information that already lives in CLAUDE.md. See CLAUDE.md
sections "Impact Map" and "Minimal context policy".
-->

## Task

**Lot 0.8 — CLI choices derived from `Glaneur/config.py` registries.**

Small independent fix from
`docs/design/roadmap.md` and
`docs/design/evolution-multi-sources.md` §2. Removes the last
hard-coded copy of the source-type / image-format / sort-mode lists
in `cli.py` and drives it from `SORT_MODES`, `SOURCE_TYPES` and
`DJANGOPLICITY_FORMATS` — the single source of truth per boundary 3.

Motivation: with profiles (lot 5) and filters (lot 11.2) coming
next, these lists will drift apart if two copies remain.

### Rename table

None. Argparse `choices=` on `--type`, `--format`, `--sort` /
`--classement` now iterate `dict.values()` on the config registries
instead of listing the literals inline.

## Directly modified

- `cli.py::_build_parser` — `choices=list(SOURCE_TYPES.values())`
  for `--type`, `choices=list(DJANGOPLICITY_FORMATS.values())` for
  `--format`, `choices=list(SORT_MODES.values())` for `--sort` and
  its FR alias `--classement`. Imports come from
  `Glaneur.config`.
- `tests/test_cli.py` — new focused test locking the boundary:
  argparse rejects `--type flickr` because `flickr` is not in
  `SOURCE_TYPES.values()`, and if a new registry entry is added the
  parser accepts it without a code change to `cli.py`.

## Direct dependencies

- `Glaneur/config.py` — read only; `SORT_MODES`, `SOURCE_TYPES`
  and `DJANGOPLICITY_FORMATS` already exported (imported by
  `app.py`).

## Explicitly out of scope

- Lot 0.9 (contract test on `min_width` re-run after loosening) —
  separate small fix, gets its own commit.
- Any lot 5.x work (profiles) — depends on lots 3–4 and is much
  bigger.
- `__version__` — unchanged.

## Tests

- Existing `TestOptionsFromCli::test_invalid_source_type_choice`,
  `::test_invalid_format_choice` and
  `::test_invalid_sort_mode_choice` still pass — they exercise the
  same rejection surface.
- New `TestChoicesTrackConfig` (or extension of TestOptionsFromCli):
  monkey-patches a new key into `SOURCE_TYPES` and asserts the
  parser accepts it, without touching `cli.py`.

Verification:

- `pytest -q` → still 507+ passed / 2 skipped.
- `python tools/check_coverage.py` → floors held.
- `ruff check cli.py tests/test_cli.py` clean on baseline.

## Invariants

- `__version__` unchanged.
- No engine / source / config / persisted-format change.
- CLI flag names unchanged; only their `choices=` argument moves
  from a literal list to `dict.values()`.
- Argparse's rejection of unknown values still fires; the runtime
  behaviour is unchanged for every value already accepted before
  this commit.

## Validation

Level `local` per the roadmap's lot 0 footprint.

- `pytest -q` green.
- `ruff check cli.py tests/test_cli.py` clean on baseline.
