# Sprint — French → English, complete

Location in the repository:
`docs/sprints/2026-09-french-to-english-complete.md`.

## Goal

Bring the whole project to English: source code, docstrings, comments,
tests, sprint docs, CLAUDE.md, `.claude/state/impact-map.md` template,
CLI help, Qt UI source strings, engine dispatch values, manifest keys,
and metadata. The **README stays dual French/English**; every other
text-carrying artefact is English-only.

This sprint replaces the "Écarts connus" list in `CLAUDE.md`. Each item
in that list gets its own US below; when the last US lands, the list
shrinks to whatever is left (only README dual-language is expected to
remain, plus the AppStream file if Linux packaging is still on hold).

No US changes `__version__`. No US pushes or tags. All commits stay on
a working branch until the maintainer merges.

## Decisions (fixed at sprint start)

- **Manifest keys** rename with a one-way read shim. Old manifests keep
  working forever; new writes are English. Zero user disruption.
- **CLI flags** rename with French aliases kept as hidden `argparse`
  alternatives. Existing scripts using `--dossier` etc. still work; the
  `--help` output shows only the English forms.
- **Qt UI**: the `.ts` source language flips to `en`. Every current
  French source becomes the translation for the `fr` locale. Translators
  can review the new English source at will; runtime behaviour is
  unchanged for French users (Qt still shows French).
- **Engine dispatch values** rename with no persistence shim, because
  they are transient (`transitoire`/`coupure`/`definitif`), UI-only
  (`galerie`/`date`/`plat` — displayed but not stored), or already
  handled through the manifest read shim (`supprime`/`restaure`).
- **`Element` dataclass fields** rename: not persisted, only in-memory.
- **Sub-agents**: `test-author` for test rewrites, `invariant-reviewer`
  after each US touching engine or persisted format.

## Constraints (same as the previous sprint)

- `__version__` unchanged across the sprint.
- No new runtime dependency.
- One writer at a time on production code. Independent US may run in
  parallel worktrees (see the sequencing table).
- Each US resets `.claude/state/impact-map.md` at its start.
- Never push, tag, or bypass hooks.

## User stories

| # | Story | Cascade | Validation |
|---|---|---|---|
| 01 | Comments, docstrings, sprint docs, impact-map template, CLAUDE.md → EN. README kept dual. | none (text only) | `local` |
| 02 | Rename ~200 test names from FR patterns to EN. | none (pytest discovers by name) | `local` |
| 03 | Internal Python identifiers: `_journal`, `arret`, `_pause`, `dossier_pour`, `fichier` locals; `Element` fields (`nom_fichier`→`filename`, `mois`→`month`, `largeur`→`width`, `taille`→`size`, `groupe`→`group`); `Transport.arret`→`Transport.stop_event`. | engine + sources + tests | `subsystem` + `invariant-reviewer` |
| 04 | Internal dispatch values: `ErrorClassification.category` (`transitoire`/`coupure`/`definitif` → `transient`/`cut`/`definitive`); sort modes (`galerie`/`plat` → `gallery`/`flat`, `date` unchanged); engine statuses (`repris`→`resumed`, `inchangé`→`unchanged`, `introuvable`→`not-found`, `erreur`→`error`). | engine + sources + tests + UI status column | `subsystem` + `invariant-reviewer` |
| 05 | Manifest keys with read shim: `taille`→`size`, `fichier`→`filename`, `modifie`→`modified`, `supprime`→`deleted`, `restaure`→`restored`; `etag`, `url`, `extra` unchanged. Adds `_MANIFEST_KEY_ALIASES` in the manifest read path. | engine (read + write + merge) + tests, plus a migration integration test | `full` (persisted format touched) + `invariant-reviewer` |
| 06 | CLI flags with FR aliases: `--folder`, `--sort`, `--delay`, `--verify`, `--since`, `--until`, `--restore`, `--no-cache` canonical; FR names kept as hidden argparse alternatives. Help text updated. | `cli.py` + `tests/test_cli.py` | `module` |
| 07 | Qt UI re-sourced in English: `_render_ui` templates become English literals; `.ts` `sourcelanguage="en"`, `target-language="fr"` on `glaneur_fr.ts` (English → English on `glaneur_en.ts`); context `Planificateur` → `Scheduler`; regenerate `.ts` via `pyside6-lupdate` and rebuild `.qm`. Existing French user experience preserved because translations are populated in `glaneur_fr.ts`. | `app.py` + `Glaneur/scheduler_labels.py` + all `translate()` sites in the package + `translations/*.ts` | `subsystem` + `invariant-reviewer` + Sphinx |
| 08 | AppStream metainfo and any residual user-visible FR text (excluding README). | `packaging/linux/` | `local` |

## Sequencing

```
US-EN-01  (docs)  ──┐
US-EN-02  (tests) ──┤
US-EN-03  (idents) ──┤──►  US-EN-04  (dispatch) ──►  US-EN-05  (manifest)
US-EN-06  (CLI)   ──┘                                       │
                                                            ▼
                                                       US-EN-07  (Qt)  ──►  US-EN-08  (metainfo)
```

- **01/02/06** are independent of everything else. Do them in any order
  or in parallel worktrees.
- **03** must land before **04**, because dispatch values live inside
  the identifiers 03 renames.
- **04** must land before **05**, so the manifest write path emits the
  final English status codes.
- **07** should come after **04** (event codes are stable; some UI
  strings surface engine statuses).
- **08** is the mop-up.

## Out of scope for the whole sprint

- README format changes (stays dual, no restructure).
- Deleting `glaneur_en.ts` (keep both files; translators may still use
  either as the reference).
- Renaming any Windows registry key, scheduled task name, or
  installer product name (these live outside the code base).
- Any change to `__version__` or to the release workflow.

## Definition of Done

- [ ] Every US of the sprint has its PR fusionnée sur `main`.
- [ ] `__version__` unchanged.
- [ ] `pytest`, coverage floors, ruff, and Sphinx all green on `main`.
- [ ] `CLAUDE.md` "Écarts connus" section reduced to (at most) the
      README dual-language note and any deliberately deferred item.
- [ ] `docs/sprints/*.md` files in English (except archived FR docs
      marked read-only).
- [ ] `.claude/state/impact-map.md` template in English.
