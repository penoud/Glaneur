# Impact Map

<!--
Temporary scratchpad, one story at a time. Reset to this empty state
between two stories. Do not store copies of files, logs, bulky test
output, or information that already lives in CLAUDE.md. See CLAUDE.md
sections "Impact Map" and "Minimal context policy".
-->

## Task

**Lot 5.1 E3 part B step 3 — multi-profile persistence scaffolding.**

Adds the disk round-trip for **additional** profiles beyond the
single implicit default. The v2 schema landed in `ca187d5` already
declares `profiles` as a list; today we only ever write/read one
entry. This commit lets the same v2 file carry any number of
additional profiles: `Config.save()` emits every profile in the
list, and `Config.load()` reads them all back.

Nothing at runtime consumes the extra profiles yet — the engine
still runs the default profile only. But the persistence bones are
now in place, which unblocks:

- a future "Add profile" button in the Preferences dialog (E3
  part B step 4);
- multi-profile CLI `--profile <name|id>` (roadmap §5.3);
- the scheduler grid (`anchor + k × I/n + m × I`, lot 5.2).

No schema bump: the v2 format has always allowed multiple entries
in `profiles`. This is an additive change to how the loader/saver
walk the list.

### Storage

- `Config._extra_profiles: list[Profile]` — extra profiles beyond
  the default. Default empty; hidden from serialisation like
  `_profile_id` / `_path`.
- `Config.save()` writes `profiles: [default_profile, *extra_profiles]`.
- `Config.load()` reads all profiles; index 0 populates the flat
  fields as before, indices 1.. go into `_extra_profiles`.
- New `Config.profiles() -> list[Profile]` returns
  `[default_profile(), *_extra_profiles]` — the complete list a
  future UI or CLI can iterate.
- Round-trip byte stability preserved: `Config.load(x).save()` on
  a file with N profiles still reproduces the same file.

## Directly modified

- `Glaneur/config.py`:
  - `Config._extra_profiles` field added.
  - `_load_v2` extended to iterate `profiles[1..]` and build
    `Profile` instances.
  - `_to_v2_dict` extended to emit every extra profile after the
    default one.
  - New instance method `Config.profiles()`.
- `tests/test_config.py`:
  - `TestMultipleProfiles` — new class:
    - extra profiles survive a save → load round-trip;
    - `Config.profiles()` returns default + extra in order;
    - a fresh Config has zero extras;
    - an extra profile with `None` overrides inherits from
      `defaults` (same rule as the default profile);
    - v2 → v2 byte stability with N profiles.

## Direct dependencies

- Uses `Profile`, `_DEFAULT_FIELDS`, `_PROFILE_STATE_FIELDS`.
- No touch to `Config.load` / `save` outside the `_load_v2` /
  `_to_v2_dict` helpers.
- No caller migrated to iterate `Config.profiles()` yet — that
  belongs to E3 part B step 4 and beyond.

## Explicitly out of scope

- UI to add / edit / remove profiles — E3 part B step 4 / lot 5.3.
- Multi-profile scheduler grid — lot 5.2.
- CLI `--profile <name|id>` — lot 5.3.
- Engine changes to route runs per profile — E3 part B step 5.
- `__version__` — unchanged.

## Tests

- `TestMultipleProfiles`:
  - `test_fresh_config_has_no_extras`
  - `test_extra_profile_survives_round_trip`
  - `test_profiles_returns_default_first_then_extras`
  - `test_extra_profile_inherits_defaults_via_null_override`
  - `test_extra_profile_override_wins_over_defaults`
  - `test_multi_profile_v2_is_byte_stable_across_round_trip`
- Every existing v2 test still passes: single-profile files
  produce empty `_extra_profiles`, and `profiles[0]` handling is
  unchanged.

Verification:

- `pytest -q` → 578 + 6 new tests.
- `python tools/check_coverage.py` → floors held.
- `ruff check` clean on touched files.

## Invariants

- `__version__` unchanged.
- `SCHEMA_VERSION` unchanged (still 2). Multi-profile is an
  **additive** use of the existing schema; older Glaneur reading a
  multi-profile file gets `profiles[0]` and quietly drops the rest
  — expected, since older Glaneur has no runtime concept of extras.
- No cache/manifest/config key touched.
- `Config` runtime API of flat access (`cfg.site`, `cfg.min_width`,
  ...) unchanged; still driven by the default profile.
- Byte stability: `Config.load(x).save()` reproduces the input
  bytes across any number of profiles.
- No dispatch/CLI/Qt change.

## Validation

Level `subsystem` — persisted-format usage extended without
schema bump. `invariant-reviewer` not required for a purely
additive read/write of an already-declared list slot.

- `pytest -q --cov=Glaneur --cov-branch` green.
- `python tools/check_coverage.py` green.
- `ruff check` clean on touched files.
