# Impact Map

<!--
Temporary scratchpad, one story at a time. Reset to this empty state
between two stories. Do not store copies of files, logs, bulky test
output, or information that already lives in CLAUDE.md. See CLAUDE.md
sections "Impact Map" and "Minimal context policy".
-->

## Task

**US-EN-05 — Manifest keys → English with a one-way read shim.**

Fifth story of the sprint
`docs/sprints/2026-09-french-to-english-complete.md`. Depends on
US-EN-04 (dispatch values landed in `cb6b68b`).

### Rename table

| Old key | New key |
|---|---|
| `"taille"` | `"size"` |
| `"fichier"` | `"filename"` |
| `"modifie"` | `"modified"` |
| `"supprime"` | `"deleted"` |
| `"restaure"` | `"restored"` |

Unchanged: `"etag"`, `"url"`, `"extra"`.

### Read shim contract

`read_manifest.py` gains `_MANIFEST_KEY_ALIASES` and translates every
per-entry key found in the JSON before returning. A single pre-US-EN-05
manifest keeps loading forever, and the next `write_manifest` call
emits English keys. Only reads translate — writes stay literal.

## Directly modified

- `Glaneur/engine/read_manifest.py` — add `_MANIFEST_KEY_ALIASES`
  and translation loop over every entry.
- `Glaneur/engine/write_manifest.py` — no change (writes what's in
  memory, which is now English keys).
- `Glaneur/engine/_merge.py` — `"supprime"` → `"deleted"`,
  `"restaure"` → `"restored"` in the mark-merging logic and its
  docstring.
- `Glaneur/engine/core.py` — every `etat["fichier"]`, `etat.get("taille")`,
  `etat.get("modifie")`, `etat.get("supprime")`, `etat.get("restaure")`,
  `etat["supprime"] = ...`, `etat.pop("restaure", ...)`, `e["fichier"]`,
  and every `infos["fichier"]`, `infos["taille"]`, `infos["modifie"]`.
  Also the docstring in `Engine.download` that lists ``infos`` keys.
- `Glaneur/engine/delete_image.py` — `etat.get("fichier")`,
  `entree["supprime"] = ...`, `entree.pop("restaure", ...)`.
- `Glaneur/engine/list_deleted.py` — `etat.get("supprime")` filter,
  the two sort keys, and the docstring naming `supprime`.
- `Glaneur/engine/restore.py` — `etat.pop("supprime", ...)`,
  `etat["restaure"] = True` and its docstring.
- `app.py` — `DialogueSupprimees` reads `e.get("fichier", ...)` and
  `e.get("supprime", ...)`. Rename to `filename` and `deleted`. Qt
  translation placeholders (`{fichier}`) stay French (US-EN-07).
- `cli.py` — nothing beyond `list_deleted` still returns `e["id"]`
  (already English). Verify.
- `tests/test_*.py` — every fixture and assertion that constructs
  `write_manifest(..., {"1": {"fichier": ..., "taille": ...}})` or
  reads `m["1"]["fichier"]` / `.get("supprime")` etc. Batch replace.

## Direct dependencies

- `Options`, `Element`, engine events: unchanged.
- Cache format (`derniere_date_media`, `titres_parents`): unchanged
  — US-EN-05 is manifest only. A cache-key rename is a separate US.
- Config format: unchanged.

## Explicitly out of scope

- **Cache keys** (`derniere_date_media`, `titres_parents`) — separate
  US, not part of US-EN-05.
- **Config keys** — already renamed in an earlier batch; sort_mode
  values were handled by US-EN-04.
- **CLI flags** — US-EN-06.
- **Qt UI translation placeholders** (`{fichier}`, `{taille}`
  strings inside `tr(...)`) — US-EN-07.
- **`__version__`** — unchanged.

## Tests

Every test that seeds a manifest with FR keys or asserts on FR keys
gets the keys rewritten. A **new integration test** covers the read
shim end-to-end: seed a manifest file on disk with FR keys → call
`read_manifest` → assert the returned dict uses EN keys → run the
engine or `_merge_ui_marks` → assert the written file has EN keys.

Verification:

- `pytest -q` → passes with 500+ tests (from 499, at least one new
  migration test).
- `python tools/check_coverage.py` → floors still met.
- `ruff check` on touched files: no new warnings.
- `sphinx-build -W -n -b html docs/sphinx docs/sphinx/_build/html` if
  the docstring changes affect the API pages (Engine.download's
  `infos` list of keys).

## Invariants

- `__version__` unchanged.
- No cache or config key touched.
- No dispatch value literal touched.
- No CLI flag renamed.
- Read shim is strictly one-way (old → new). No new shim reads
  English → French. No English → French key emitted on write.
- After one round-trip (load an FR manifest, save without changes),
  the on-disk file uses EN keys — this is the intended migration
  path.
- Coverage floors held.

## Validation

Level `full` — persisted format touched.

- `pytest -q --cov=Glaneur --cov-branch` green.
- `python tools/check_coverage.py` green.
- Full `ruff check` no new warnings.
- `sphinx-build -W` green if docstrings changed.
- `invariant-reviewer` — persisted-format boundary, read shim
  correctness, backwards-compatibility guarantee.
