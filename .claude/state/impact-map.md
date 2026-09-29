# Impact Map

<!--
Temporary scratchpad, one story at a time. Reset to this empty state
between two stories. Do not store copies of files, logs, bulky test
output, or information that already lives in CLAUDE.md. See CLAUDE.md
sections "Impact Map" and "Minimal context policy".
-->

## Task

**Lot 5.1 (E3) part A — v2 config schema on disk.**

First half of E3 (roadmap §5.1). Introduces the v2 on-disk shape of
`config.json` — `schema_version: 2`, a top-level application block,
a `defaults` block for the inheritable settings, and a `profiles`
list containing one entry today.

Runtime behaviour is unchanged: `Config` stays a flat dataclass, and
every existing caller keeps reading `cfg.site`, `cfg.min_width`,
`cfg.last_run` etc. verbatim. The change happens at the load/save
boundary:

- `save()` writes v2 shape;
- `load()` accepts either v1 (no `schema_version` key) or v2, and on
  a v1 read it also **migrates the file in place**, copying the
  pre-migration bytes to `config.v1.json` for rollback.

The v1 → v2 promotion of per-profile state into a real `Profile` list
at the runtime level is deferred to E3 part B (next commit), where
None-inheritance and unique/non-nested folder rules land.

### v2 shape

```json
{
  "schema_version": 2,
  "language": "",
  "interval_hours": 24,
  "schedule_anchor": "14:30",
  "request_delay": 0.5,
  "run_at_startup": false,
  "close_to_tray": true,
  "notifications": true,
  "check_updates_on_start": true,
  "slideshow_dir": false,
  "defaults": {
    "min_width": 800,
    "verify_integrity": false
  },
  "profiles": [
    {
      "id": "<uuid4().hex>",
      "name": "default",
      "source_type": "wordpress",
      "site": "https://example.com",
      "target_dir": "/…",
      "image_format": "Large",
      "sort_mode": "gallery",
      "min_width": null,
      "verify_integrity": null,
      "last_run": "",
      "retry_after": "",
      "backoff_level": 0
    }
  ]
}
```

- `min_width` / `verify_integrity` at profile level = `null` means
  "inherit the `defaults` value". Since today there is one implicit
  profile, migration puts the current Config values into `defaults`
  and sets the profile overrides to `null`.
- `schedule_anchor` is `HH:MM` local time. Migration seeds it from
  the current `last_run`'s time-of-day, or from midnight when
  `last_run` is empty. That matches the roadmap's "keeps today's
  rhythm" requirement.
- `slideshow_profile` (a real profile id) is **not yet** written —
  today's flat `slideshow_dir` bool stays, and E3 part B swaps them
  when the runtime moves to per-profile state.

## Directly modified

- `Glaneur/config.py`:
  - New `SCHEMA_VERSION = 2` module constant.
  - New `Profile` dataclass (definitions only, no runtime use yet —
    it will hold per-profile state once part B lands).
  - New `_DEFAULT_FIELDS = ("min_width", "verify_integrity")` — the
    inheritable settings.
  - New `_PROFILE_STATE_FIELDS = ("last_run", "retry_after", "backoff_level")` —
    per-profile run state.
  - `Config` gains `schedule_anchor: str = ""` and
    a private `_profile_id: str = ""` attribute (uuid4 seeded on
    migration or on first save; hidden from serialisation, like `_path`).
  - `Config.save()` writes v2 shape.
  - `Config.load()` reads either v1 or v2; on a v1 read, copies the
    file to `config.v1.json` before returning.
- `tests/test_config.py`:
  - `TestSchemaVersion` — new class:
    - fresh save emits `schema_version: 2` and the expected top-level
      keys;
    - profile inherits `min_width` / `verify_integrity` from
      `defaults` via `None` overrides;
    - v1 → v2 migration copies to `config.v1.json` and rewrites the
      current file in v2 shape;
    - unknown v2 keys are ignored;
    - `_profile_id` is stable across save/load.

## Direct dependencies

- `PROFILE_FIELDS` — used as the source of truth for what moves to
  the profile block.

## Explicitly out of scope

- `None`-inheritance resolver (`Config.effective_min_width()` etc.)
  — E3 part B.
- Multiple profiles at runtime — E3 part B / E4.
- Unique/non-nested folder validation — E3 part B.
- `slideshow_profile` (id) — E3 part B or lot 5.3.
- `__version__` — unchanged.

## Tests

- Existing tests unaffected: v1 fixtures still load through the
  compatibility path, and `Config.save()` output is exercised
  through the round-trip tests (`TestLegacySortModeAliases`,
  the byte-for-byte guard in `TestConfigJsonIsUnchangedAfterEmptyOk`).
- `TestConfigJsonIsUnchangedAfterEmptyOk` will fail if the seed uses
  v1 shape — it will now be a v1 → v2 migration. The fixture
  gets adjusted to save() once (canonicalising to v2) before the
  dialog opens, so the invariant still checks a **stable** round-trip.

Verification:

- `pytest -q` → still passing; +new tests.
- `python tools/check_coverage.py` → floors held (persisted-format
  touch means `full` validation).
- `ruff check Glaneur/config.py tests/test_config.py` clean on
  baseline.

## Invariants

- `__version__` unchanged.
- No runtime API of `Config` changed: every attribute the codebase
  reads (`cfg.site`, `cfg.min_width`, `cfg.last_run`, `cfg.sort_mode`,
  `cfg.language`, ...) works identically.
- v1 → v2 migration is one-way (no reverse shim), matches the
  US-EN-05 manifest pattern.
- `config.v1.json` is written **before** the new file replaces the
  old one, and never overwritten if it already exists.
- v2 → v2 load is idempotent: load → save reproduces the same file
  byte for byte.
- `_profile_id` is stable across load/save cycles; a new one is only
  generated on the initial migration or on a first save without a
  prior load.

## Validation

Level `full` per the roadmap's E3 note (persisted format touched)
plus `invariant-reviewer` afterwards.

- `pytest -q --cov=Glaneur --cov-branch` green.
- `python tools/check_coverage.py` green.
- `ruff check` clean on touched files.
- `invariant-reviewer` — v1 → v2 boundary, one-way migration
  guarantee, `config.v1.json` semantics.
