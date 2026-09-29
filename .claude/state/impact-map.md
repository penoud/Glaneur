# Impact Map

<!--
Temporary scratchpad, one story at a time. Reset to this empty state
between two stories. Do not store copies of files, logs, bulky test
output, or information that already lives in CLAUDE.md. See CLAUDE.md
sections "Impact Map" and "Minimal context policy".
-->

## Task

**Lot 5.1 E3/E4 — `Profile.effective(defaults)` and helpers.**

Small step between E3 part A (v2 schema landed) and E3 part B (real
per-profile list at runtime). Formalises the None-inheritance rule
from `docs/design/evolution-multi-sources.md` §3.2 and roadmap §5.1
as explicit API on the `Profile` dataclass, so when E3 part B moves
per-profile state off `Config` and into a `list[Profile]`, the
resolver is already tested and named.

### Rule (unchanged in scope)

> A profile field set to ``None`` inherits the default; a default is
> never copied into a profile.

### API added

- `Profile.effective_min_width(defaults)` — returns the profile's
  ``min_width`` when non-null, otherwise ``defaults.get("min_width")``,
  otherwise the Config default (800).
- `Profile.effective_verify_integrity(defaults)` — same rule.
- Module-level `_resolve(override, defaults, key, fallback)` helper
  covering the general case.

## Directly modified

- `Glaneur/config.py`:
  - New private `_resolve(override, defaults, key, fallback)` helper.
  - `Profile` gains two thin instance methods:
    `effective_min_width(defaults)` and
    `effective_verify_integrity(defaults)`.
- `tests/test_config.py`:
  - `TestProfileInheritance` — new class covering both methods
    across override + defaults + fallback branches.

## Direct dependencies

- Uses `_DEFAULT_FIELDS` implicitly through the semantic — order
  matters only in the way `_to_v2_dict` already lays them out.
- No touch to `Config`'s load/save behaviour.

## Explicitly out of scope

- Real per-profile list at runtime — E3 part B.
- Unique/non-nested folder validation — E3 part B.
- `slideshow_profile` (id) — E3 part B.
- CLAUDE.md invariants pointer — separate small commit.
- `__version__` — unchanged.

## Tests

- `TestProfileInheritance`:
  - `test_override_wins_over_defaults`
  - `test_defaults_used_when_override_is_none`
  - `test_fallback_used_when_both_missing`
  - `test_verify_integrity_semantics_mirror_min_width`

Verification:

- `pytest -q` → 570 + 4 new tests.
- `python tools/check_coverage.py` → floors held.
- `ruff check Glaneur/config.py tests/test_config.py` clean.

## Invariants

- `__version__` unchanged.
- No engine, source, cache, manifest, or on-disk config format
  change.
- `Config` load/save behaviour unchanged.
- `Profile` field list unchanged; only two new instance methods are
  added.

## Validation

Level `local` — pure additions on the `Profile` dataclass with
targeted tests.

- `pytest -q` green.
- `ruff check` clean on touched files.
