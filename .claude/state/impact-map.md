# Impact Map

<!--
Temporary scratchpad, one story at a time. Reset to this empty state
between two stories. Do not store copies of files, logs, bulky test
output, or information that already lives in CLAUDE.md. See CLAUDE.md
sections "Impact Map" and "Minimal context policy".
-->

## Task

**US-EN-01 — Comments, docstrings, sprint docs, impact-map template,
`CLAUDE.md` → English.**

First story of the sprint
`docs/sprints/2026-09-french-to-english-complete.md`.

The whole codebase already reached English for identifiers, module
docstrings, and configuration keys in earlier sprints. What is still
French, per `CLAUDE.md` "Écarts connus", is a scattered set of
comments, a few docstrings, plus every text-only artefact under
`docs/sprints/`, `.claude/state/impact-map.md`, and `CLAUDE.md` itself.
This US pulls all of them to English. **README.md keeps its dual
French/English layout.** Sphinx `docs/sphinx/**` is already English.

Nothing in this US touches production code semantics, tests, or
persisted formats. The commit is text-only.

## Directly modified

- `CLAUDE.md` — rewritten in English, matching the current project
  structure. The "Écarts connus" section is updated to remove the
  entries this sprint resolves, and to name the follow-up US that
  will resolve the rest.
- `.claude/state/impact-map.md` — the template comment (top of file)
  translated. The body of the map for the *current* US is already
  English (this document itself).
- `docs/sprints/*.md` — the four existing sprint docs
  (`2026-09-preparation-publication.md`,
  `2026-09-documentation-sphinx.md`,
  `sprint-ci-validation-avant-tag.md`,
  `sprint-ci-workflows.md`) and the current sprint doc
  (`2026-09-verifier-lots-1-4-avant-lot-5.md`) translated to English.
  Filenames are kept for `git blame` continuity.
- French **comments** in `.py` files across the tree — translated
  where they exist, kept on the same line.
- French **docstrings** in `.py` files — kept rare per the September
  "docstrings-en" sprint, but any that survived get translated.

Runtime French strings (`print`, `raise RuntimeError(...)`, `journal`
calls with literal FR, argparse `help=` text) are **out of scope** for
this US: changing them affects user-visible behaviour, and each of
their categories has its own US later in the sprint.

## Direct dependencies

- `README.md` — **not modified**. It stays dual per the sprint
  contract.
- `docs/design/*.md` (`roadmap.md`, `evolution-multi-sources.md`) —
  **already English** since the September design-docs sprint.
- `docs/sphinx/**` — **already English** (its README, `conf.py`
  comments, and `.rst` files were translated in the Sphinx sprint).
- Production code identifiers, dispatch values, manifest keys,
  `Element` fields, CLI flags — **not touched here**. Their US come
  next in the sprint.
- Qt translation source strings and `.ts` files — **not touched
  here**. Their US (US-EN-07) is the last big one.

## Explicitly out of scope

- **README.md** stays dual per the sprint decision.
- **Persisted manifest format** — US-EN-05.
- **Dispatch values, engine statuses, sort modes** — US-EN-04.
- **`Element` dataclass fields, `Transport.arret`, method names** —
  US-EN-03.
- **CLI flags** — US-EN-06.
- **Qt translations** — US-EN-07.
- **AppStream metainfo** — US-EN-08.
- **Test names** — US-EN-02.
- **`__version__`** — unchanged.
- **Any code semantics** — this US is text only. The test suite is
  expected to pass without a single change to any test.

## Tests

No new tests. No test rewritten. The full suite must remain green
because nothing about behaviour changes.

Two commands verify:

- `pytest -q` — 495 passed, 2 skipped (unchanged from US-VERIF-04).
- `python tools/check_coverage.py` — coverage floors unchanged.

## Invariants

- `__version__` unchanged.
- No production code semantics touched.
- No test file modified (US-EN-02 owns that).
- Coverage floors (from US-VERIF-01) remain at or above their current
  baseline; strictly, this US moves no line so no floor moves.
- README.md stays dual.

## Validation

Level `local`. Text-only change, no test suite dependency, no invariant
reviewer.

- `pytest -q` green.
- `ruff check` on any touched `.py` file (only affects comments and
  docstrings — no functional lines).
- `sphinx-build -W -n -b html docs/sphinx docs/sphinx/_build/html`
  green — docstrings changed, so autodoc/napoleon must still produce
  a warning-free build.
