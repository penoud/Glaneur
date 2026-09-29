# Impact Map

<!--
Temporary scratchpad, one story at a time. Reset to this empty state
between two stories. Do not store copies of files, logs, bulky test
output, or information that already lives in CLAUDE.md. See CLAUDE.md
sections "Impact Map" and "Minimal context policy".
-->

## Task

**Lot 5.0 E1 (part 1) — `PROFILE_FIELDS` in `config.py`.**

Preparatory step for the tabbed Preferences dialog and the v1 → v2
config migration described in `docs/design/roadmap.md` §5.0/§5.1 and
`docs/design/evolution-multi-sources.md` §3.1.

`PROFILE_FIELDS` is the single source of truth for the split
between "application" preferences and "per-profile" preferences.
Today, one profile is baked into the flat `Config` dataclass. Later,
E3/lot 5.1 promotes each per-profile field into a `Profile` entry;
this constant drives both the "Site" tab (the fields it holds) and
the migration (the fields it moves from `Config` into a profile).

### Fields

Per `evolution-multi-sources.md` §3.1 and roadmap §5.0:

```python
PROFILE_FIELDS: tuple[str, ...] = (
    "source_type", "site", "image_format", "target_dir",
    "sort_mode", "min_width", "verify_integrity",
)
```

## Directly modified

- `Glaneur/config.py` — add `PROFILE_FIELDS` next to the existing
  registries (`SORT_MODES`, `SOURCE_TYPES`, `DJANGOPLICITY_FORMATS`).
- `tests/test_config.py` — new focused test class
  `TestProfileFields` locking:
  - every value listed in `PROFILE_FIELDS` is a real
    :class:`Config` dataclass field;
  - the split has no overlap with private/underscore fields;
  - the tuple contents match the design doc's list, so a rename or
    reorder is a deliberate change.

## Direct dependencies

- No caller yet; `PROFILE_FIELDS` is a public constant for the next
  commit (DialoguePreferences tabs) and the future v2 migration to
  key off.

## Explicitly out of scope

- The tabbed Preferences dialog itself — part 2 of this US, next
  commit.
- `Glaneur/system.py` — the extraction called for in the roadmap is
  already done in an earlier lot; nothing to move here.
- The v2 migration (roadmap §5.1) — bigger, later commit.
- `__version__` — unchanged.

## Tests

- `TestProfileFields` — new, three focused assertions above.

Verification:

- `pytest -q` → 516 + new tests.
- `python tools/check_coverage.py` → floors held.
- `ruff check Glaneur/config.py tests/test_config.py` clean on
  baseline.

## Invariants

- `__version__` unchanged.
- `Config` dataclass fields, defaults, load/save, and
  `_LEGACY_FIELD_ALIASES` unchanged.
- `PROFILE_FIELDS` is a `tuple[str, ...]` — order matters for later
  migration.
- Every name in `PROFILE_FIELDS` is a real field on `Config`.

## Validation

Level `local` per E1's roadmap footprint.

- `pytest -q` green.
- `ruff check` clean on touched files.
