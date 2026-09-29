# Impact Map

<!--
Temporary scratchpad, one story at a time. Reset to this empty state
between two stories. Do not store copies of files, logs, bulky test
output, or information that already lives in CLAUDE.md. See CLAUDE.md
sections "Impact Map" and "Minimal context policy".
-->

## Task

**US-EN-04 — Internal dispatch values → English.**

Fourth story of the sprint
`docs/sprints/2026-09-french-to-english-complete.md`. Depends on
US-EN-03 (identifier renames landed in `62f6b52`).

Rename dispatch value string literals. No persistence shim per sprint
decision, except a small legacy sort-mode value alias in
`Config.load` so a user's `config.json` written before this US does
not silently reset to default when their sort_mode was
`"galerie"`/`"plat"`.

### Rename table

| Old value | New value | Where |
|---|---|---|
| `"transitoire"` | `"transient"` | `ErrorClassification.category` — sources/base.py + engine/core.py + tests |
| `"coupure"` | `"cut"` | same |
| `"definitif"` | `"definitive"` | same |
| `"galerie"` | `"gallery"` | sort mode — config.py, options.py, sources/*, engine/core.py, cli.py, app.py, tests |
| `"plat"` | `"flat"` | sort mode — same set of files |
| `"date"` | (unchanged) | — |
| `"repris"` | `"resumed"` | engine status — engine/core.py + tests |
| `"inchangé"` | `"unchanged"` | same |
| `"introuvable"` | `"not-found"` | same |
| `"erreur"` | `"error"` | same |

## Directly modified

- `Glaneur/sources/base.py` — `Literal["transitoire", "coupure", "definitif"]`
  in the `ErrorClassification` dataclass; every `ErrorClassification(...)`
  constructor in `classify_error`; the `if classification.category == "definitif"`
  branch. Docstring examples.
- `Glaneur/sources/wordpress.py` — `sort_modes = frozenset({"galerie", ...})`.
- `Glaneur/sources/djangoplicity.py` — `sort_modes = frozenset({"date", "plat"})`
  and its comment.
- `Glaneur/sources/__init__.py` — docstring `sort_modes_for` example.
- `Glaneur/engine/core.py` — `if self.o.sort_mode == "plat"`,
  `if self.o.sort_mode == "galerie"`, `"galerie" in self.source.sort_modes`;
  the `download()` return-tuple statuses `"inchangé"`, `"introuvable"`,
  `"repris"`, `"ok"`, `"erreur"` and the run-loop dispatch on them;
  the `ErrorClassification("definitif", ...)` construction; docstring
  in `Engine.download` listing status codes.
- `Glaneur/engine/options.py` — default `sort_mode: str = "galerie"`.
- `Glaneur/config.py` — `SORT_MODES` values `"galerie"`/`"plat"`;
  default `sort_mode: str = "galerie"`; validation default in
  `validate()`; the `sort_mode_label` fallback default. Add a
  `_LEGACY_SORT_MODE_ALIASES = {"galerie": "gallery", "plat": "flat"}`
  applied in `load()` before `validate()`, so a legacy config keeps
  its user choice.
- `cli.py` — `--classement` choices list `["galerie", "date", "plat"]`.
- `app.py` — `SORT_MODES.get(..., "galerie")` fallback default (line 540).
- `tests/test_*.py` — every test that constructs
  `ErrorClassification(...)` with FR categories, tuples returned by
  `download()` mocks, `sort_mode="galerie"`/`"plat"` in `_moteur(...)`
  helpers, or asserts `.category == "transitoire"` etc.

## Direct dependencies

- Config load path: legacy value shim added (single dict, no new
  module).
- `_render_ui` / `render_en` engine event templates — not touched.
  Engine events do NOT surface these status strings; the run loop
  emits structured events with their own codes.

## Explicitly out of scope

- **CLI flag `--classement`** name — US-EN-06.
- **Qt UI labels** ("Par galerie", "Tout dans un dossier", etc.) —
  US-EN-07. Only the SORT_MODES *values* change; the display labels
  (keys) stay French.
- **Manifest keys** (`"fichier"`, `"taille"`, `"modifie"`,
  `"supprime"`, `"restaure"`) — US-EN-05.
- **`Element` field renames** — landed in US-EN-03.
- **`Transport.get_json` params `essais`, `fin_si`** — deferred.
- **`__version__`** — unchanged.

## Tests

Every test constructing `ErrorClassification("transitoire"/"coupure"/"definitif", ...)`
or asserting `.category ==` on those literals, every
`download()` mock returning a status tuple with `"repris"`,
`"inchangé"`, `"introuvable"`, `"erreur"`, every `sort_mode="galerie"`
or `sort_mode="plat"` in `_moteur(...)`, and every CLI test that
passes `--classement galerie` gets the value rewritten.

Verification:

- `pytest -q` → still 495 passed, 2 skipped.
- `python tools/check_coverage.py` → floors still met.
- `ruff check` on touched files: no new warnings.
- One new focused test: a legacy `config.json` with
  `"sort_mode": "galerie"` loads to `"gallery"` (not default-reset).

## Invariants

- `__version__` unchanged.
- Manifest, cache, and config schema unchanged — only sort-mode
  *values* in config translate through the legacy alias on load,
  and are rewritten in English on next `Config.save`.
- No CLI flag renamed (only its value choices change).
- Engine event codes unchanged.
- Coverage floors (`sources/*` 98.0, `scheduler.py` 95.0,
  `config.py` 97.0, `engine/*` 98.5) held.

## Validation

Level `subsystem`. Widespread cascade across engine, sources, config,
UI, CLI, and tests. Persisted-format touched only through the
one-way legacy sort-mode value alias in config load, which is a
strict superset of the old behaviour (never emits FR values on save).

- `pytest -q --cov=Glaneur --cov-branch` green.
- `python tools/check_coverage.py` green.
- `ruff check` clean on touched files (baseline preserved).
- `invariant-reviewer` — dispatch-value boundary (source/engine
  contract) and the config-load legacy shim.
