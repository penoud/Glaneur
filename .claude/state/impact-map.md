# Impact Map

<!--
Temporary scratchpad, one story at a time. Reset to this empty state
between two stories. Do not store copies of files, logs, bulky test
output, or information that already lives in CLAUDE.md. See CLAUDE.md
sections "Impact Map" and "Minimal context policy".
-->

## Task

**Lot 5.1 E3 part B (step 1) — `Config.default_profile()` builder.**

Forward-compat step between the just-landed
`Profile.effective_*(defaults)` resolvers and the real per-profile
list at runtime described in
`docs/design/evolution-multi-sources.md` §3.1/§3.2.

Adds two builders on :class:`Config`:

- `Config.default_profile() -> Profile` builds a :class:`Profile`
  from the current flat state — the same single implicit profile the
  UI already shows in its one-row table.
- `Config.defaults() -> dict` returns the ``defaults`` block —
  today, the current effective values of the inheritable settings
  (`min_width`, `verify_integrity`), matching what
  `Config.save()` writes on disk.

Callers can start reading `cfg.default_profile().effective_min_width(cfg.defaults())`
now; the answer matches `cfg.min_width` under the current single-
profile layout, but the API is stable across E3 part B step 2,
which will flip `Config`'s storage from flat per-profile fields to
a real `list[Profile]`.

## Directly modified

- `Glaneur/config.py`:
  - New `Config.default_profile()` instance method.
  - New `Config.defaults()` instance method.
- `tests/test_config.py`:
  - `TestConfigDefaultProfile` — new class covering both builders.

## Direct dependencies

- Uses `Profile`, `_DEFAULT_FIELDS`, and `_PROFILE_STATE_FIELDS`.
- No touch to `Config.load` / `Config.save`.
- No caller migrated yet — this commit only exposes the API.

## Explicitly out of scope

- Migrating `app.py`, `cli.py`, `engine`, `sources` to consume
  `default_profile()` / `defaults()` — E3 part B step 2.
- Storing `list[Profile]` on Config — E3 part B step 2.
- Multi-profile UI — E3 part B step 3.
- `__version__` — unchanged.

## Tests

- `TestConfigDefaultProfile`:
  - `test_default_profile_reflects_flat_state`
  - `test_default_profile_id_matches_stored_uuid`
  - `test_defaults_returns_inheritable_settings`
  - `test_effective_min_width_via_resolver_matches_flat`

Verification:

- `pytest -q` → 574 + 4 new tests.
- `python tools/check_coverage.py` → floors held.
- `ruff check Glaneur/config.py tests/test_config.py` clean.

## Invariants

- `__version__` unchanged.
- No engine, source, cache, manifest, or on-disk config format
  change.
- `Config` load/save behaviour unchanged.
- `Profile` field list unchanged.

## Validation

Level `local` — pure additions on `Config`, no caller touched.

- `pytest -q` green.
- `ruff check` clean on touched files.
