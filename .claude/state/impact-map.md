# Impact Map

<!--
Temporary scratchpad, one story at a time. Reset to this empty state
between two stories. Do not store copies of files, logs, bulky test
output, or information that already lives in CLAUDE.md. See CLAUDE.md
sections "Impact Map" and "Minimal context policy".
-->

## Task

**US-EN-03 — Internal Python identifiers, `Element` fields, and
`Transport.arret` → English.**

Third story of the sprint
`docs/sprints/2026-09-french-to-english-complete.md`.

Rename the following identifiers (the explicit sprint-doc list). No
change to persisted formats, dispatch-value string literals, or Qt
translation sources.

### Rename table

| Old identifier | New identifier | Where |
|---|---|---|
| `Element.nom_fichier` | `Element.filename` | `sources/base.py` dataclass + all constructors and accessors |
| `Element.mois` | `Element.month` | same |
| `Element.largeur` | `Element.width` | same |
| `Element.taille` | `Element.size` | same (dataclass field only — manifest `"taille"` string keys are US-EN-05) |
| `Element.groupe` | `Element.group` | same |
| `Transport.__init__(arret=...)` and `self.arret` | `Transport.__init__(stop_event=...)` and `self.stop_event` | `sources/base.py` |
| `Engine.__init__(arret=...)` and `self.arret` | `Engine.__init__(stop_event=...)` and `self.stop_event` | `engine/core.py` |
| `Engine.dossier_pour` | `Engine.folder_for` | `engine/core.py` |
| `Engine._pause(secondes: float)` param | `Engine._pause(seconds: float)` param | `engine/core.py` |
| Local variable `fichier` (file-path) | `file_path` (or context-appropriate English name) | `engine/core.py` run loop |

## Directly modified

- `Glaneur/sources/base.py` — `Element` fields; `Transport.arret` →
  `Transport.stop_event`.
- `Glaneur/sources/wordpress.py` — reads `Element` fields via
  positional args in the constructor; if it uses keyword args
  (`nom_fichier=`, `groupe=`, `mois=`, `largeur=`), rename.
- `Glaneur/sources/djangoplicity.py` — same as wordpress.
- `Glaneur/engine/core.py` — `Engine.arret` → `Engine.stop_event`;
  `Engine.dossier_pour` → `Engine.folder_for`; `_pause(secondes)` →
  `_pause(seconds)`; local `fichier` names; `element.nom_fichier`
  reads become `element.filename`; `element.largeur` →
  `element.width`; `element.mois` → `element.month`; etc.
- `Glaneur/engine/_merge.py`, `Glaneur/engine/delete_image.py`,
  `Glaneur/engine/restore.py`, `Glaneur/engine/list_deleted.py`,
  `Glaneur/engine/sanitize.py` — if they access `Element` fields or
  `arret`, cascade. (Unlikely for these, but the fork should verify.)
- `cli.py` — passes `arret=` to `Engine` if it does; rename.
- `app.py` — `Travailleur` reads `arret`; rename.
- `tests/test_*.py` — every test that constructs `Element(...)` with
  the FR kwargs, or accesses `.nom_fichier`, `.mois`, `.largeur`,
  `.taille`, `.groupe`, or `.arret`, or calls `Engine.dossier_pour(...)`.

## Direct dependencies

- Manifest write path (`Engine.download`, `Engine._run_locked`): uses
  string keys like `"taille"`, `"fichier"`, `"modifie"`. **Not renamed
  here.** These are persisted keys, owned by US-EN-05.
- Options dataclass: already English.
- Scheduler, config, updater: **read only.** Do not use any of the
  renamed identifiers.
- Translations `.ts` files: **not touched.** The identifier renames
  never appear as translation sources.

## Explicitly out of scope

- **Manifest dict-key strings** (e.g. `infos["taille"] = dest.stat().st_size`,
  `etat["fichier"]`, `etat["modifie"]`, `etat["supprime"]`,
  `etat["restaure"]`) — US-EN-05, with a read shim.
- **Dispatch values** in strings (`"transitoire"`, `"coupure"`,
  `"definitif"`, `"galerie"`, `"date"`, `"plat"`, `"wordpress"`,
  `"djangoplicity"`, engine statuses `"repris"`, `"inchangé"`,
  `"introuvable"`, `"erreur"`, marks `"supprime"`/`"restaure"`) —
  US-EN-04.
- **CLI flags** (`--dossier`, `--classement`, …) — US-EN-06.
- **Qt translation sources** — US-EN-07.
- **Transport.get_json parameters `essais` and `fin_si`** — public API
  parameters used by tests and adapters. A rename here would cascade
  outside the sprint-doc's explicit US-EN-03 list; deferred to a
  separate "public API rename" US, which we can plan after US-EN-08.
- **Other FR local variables** (`dossier`, `derniere`, `entetes`,
  `reponse`, `reprise`, `tentative`, `depuis`, `sous`, `nom`,
  `pris`, etc.) — deferred to a "locals cleanup" follow-up US. This
  US only touches `fichier` locals that hold a file path in the
  engine run loop.
- **`_journal` attribute** — the name is already English (from
  "journal" = "log"). Not renamed.
- **`_pause` method name** — "pause" is English. Only the parameter
  `secondes` inside it gets renamed.
- **`__version__`** — unchanged.

## Tests

Every test that constructs `Element(nom_fichier=..., groupe=..., mois=..., largeur=...)`
or reads `element.nom_fichier` / `.mois` / `.largeur` / `.taille` /
`.groupe` must have those calls rewritten. Same for `arret=` and
`.arret`. Same for `dossier_pour(...)` calls.

The tests' behaviour is preserved; only the identifiers change.

Verification:

- `pytest -q` → **495 passed, 2 skipped** (same as US-EN-02 baseline).
- `pytest --collect-only -q` → **497 tests collected** (unchanged).
- `python tools/check_coverage.py` → all floors still met.
- `ruff check` on touched files: no new warnings.

## Invariants

- `__version__` unchanged.
- No persisted-format key renamed. Manifest, cache, config unchanged.
- No dispatch-value string renamed. `"repris"`, `"inchangé"`,
  `"introuvable"`, `"erreur"`, `"coupure"`, `"transitoire"`,
  `"definitif"`, `"galerie"`, `"date"`, `"plat"`, `"wordpress"`,
  `"djangoplicity"` all unchanged.
- No CLI flag renamed.
- Coverage floors (`sources/*` 98.0, `scheduler.py` 95.0,
  `config.py` 97.0, `engine/*` 98.5) held.
- `Transport.get_json`'s `essais` and `fin_si` parameter names
  unchanged (see out-of-scope).

## Validation

Level `subsystem`. Widespread cascade across engine, sources, and
tests, but no boundary crossed and no persisted format touched.

- `pytest -q --cov=Glaneur --cov-branch` green.
- `python tools/check_coverage.py` green.
- `ruff check` clean on touched files (pre-existing warnings
  unchanged).
- `sphinx-build -W -n -b html docs/sphinx docs/sphinx/_build/html`
  green — `Element` dataclass docstring changes may affect autodoc.
- `invariant-reviewer` — Transport frontier + Engine callback API
  change (signature).
