# CLAUDE.md — Glaneur

This file is deliberately minimal for now: only the sections needed for
multi-agent work are in place. Boundaries, the invariants table, and the
conventions will be written in a dedicated story.

## Known gaps between this document and the code

This document describes the target state. As long as a gap is listed
here it is neither fixed outside its story nor reported as a regression,
unless it gets worse.

- The README still describes the `WINDOWS_PFX_BASE64` signing flow,
  which is obsolete (story 9).
- The README stays deliberately dual French/English by sprint decision;
  this is the only intentional French text left in the project.

Update this list whenever a story resolves a gap or you discover a new
one.

## Multi-agent work

- The main conversation frames, implements, and decides. It does not
  delegate the writing of production code.
- Sub-agents: `test-author` (tests only), `test-runner` (execution and
  summary), `invariant-reviewer` (review, read-only), `server-prober`
  (real servers, on demand). The full suite and coverage go through
  `test-runner`; an isolated test can be launched directly.
- Only one writer at a time on production code. Two independent
  stories run in parallel in two separate sessions, each in its own
  worktree and branch.
- Never push, never tag, never modify `__version__`: `main` publishes.
  Hooks block this. Do not work around them (another shell, other
  syntax): report the block.
- A sub-agent does not see this conversation. The delegation message
  provides the scope, the files, and the invariants at play.

## Minimal context policy

Each agent works with the smallest set of files that lets it correctly
answer the task.

- Never analyse the whole repository by default.
- Start from the diff and the files explicitly named.
- Only look for extra dependencies once a real dependency has been
  found.
- Do not re-read a file already analysed in the same task without a
  reason.
- `Glob` and `Grep` searches must be targeted.
- Do not explore directories outside the scope just to understand
  "the whole project".
- A local change does not trigger a global analysis.
- A documentation change does not trigger a code analysis.
- A test change does not automatically trigger an analysis of the
  entire production code.
- Tests are targeted before considering the full suite.
- An expensive check must be justified by the impact of the change.
- When an extra file is needed, briefly identify the link between that
  file and the change before continuing.
- A finished exploration must not be redone by another agent: its
  result must be passed on via the Impact Map or the delegation
  message.

## Impact Map

Every story that changes code must come with an Impact Map. The file
`.claude/state/impact-map.md` provides the template; it is temporary,
reset between two stories, and contains only what the current task
needs.

The Impact Map:

- defines the working scope;
- distinguishes directly modified files from dependencies;
- identifies the tests concerned;
- states explicitly what is out of scope;
- identifies the invariants actually concerned;
- determines the required validation level.

Sub-agents receive this information in their delegation.

A sub-agent must not rebuild an Impact Map already available.

If an agent discovers a new real dependency it may propose adding it
to the Impact Map and explain why it is needed.

A mere theoretical possibility is not enough to widen the scope.

## Conditional validation

The presence of a tool in the workflow does not mean it must be run on
every change.

The validation level is set by the Impact Map (`local`, `module`,
`subsystem`, `full`).

| Change type                              | Checks                                                                             |
| ---------------------------------------- | ---------------------------------------------------------------------------------- |
| Test only                                | tests concerned + targeted ruff                                                    |
| Local Python                             | tests concerned + targeted ruff                                                    |
| A source (`Glaneur/sources/…`)           | source's tests + relevant contract tests + targeted ruff + `invariant-reviewer` if a boundary or invariant is touched |
| Engine, scheduler, `config.py`           | tests concerned + targeted ruff + `invariant-reviewer`                             |
| Public API or persisted format           | tests concerned + full suite + coverage + `invariant-reviewer`                     |
| Packaging                                | tests concerned + packaging validation + `invariant-reviewer`                      |
| Sphinx documentation (`docs/sphinx/**`)  | `sphinx-build -W -n -b html docs/sphinx docs/sphinx/_build/html` (install `requirements-doc.txt` first) |
| Docstrings of a Python module            | `sphinx-build -W` on top of the usual checks for the change type                   |
| Cross-cutting                            | full pytest + coverage + full ruff + Sphinx + `invariant-reviewer`                 |

A full validation is reserved for cross-cutting changes, changes to the
public API or a persisted format, and steps explicitly planned by the
story.

After a local change, do not automatically run the full suite, full
coverage, or Sphinx.

## Docstrings and API documentation

API documentation lives in `docs/sphinx/`. It is generated by Sphinx
with `autodoc` + `napoleon` from the code's docstrings — the source of
truth is the code, not `.rst` files maintained by hand.

- Docstring style: **Napoleon (Google-style)**. Sections `Args:`,
  `Returns:`, `Yields:`, `Raises:`, `Attributes:` when they apply.
  Details, canonical example, and rationale in
  `docs/sphinx/README.md`.
- Dataclass fields: documented via inline `#:` comments, never in an
  `Attributes:` section — otherwise autodoc and Napoleon create two
  index entries for the same field and break `sphinx-build -W`.
- Internal references that do not resolve through autodoc (module
  constants, instance attributes, members of another undocumented
  package) are written with double backticks (```` ``foo`` ````), not
  with a Sphinx role like `:data:` or `:attr:`.
- Regenerate `docs/sphinx/api/*.rst` after a module is added, renamed,
  or removed: `make -C docs/sphinx apidoc` (or `make.bat` on Windows).
  The Makefile's post-processing removes the "Module contents" blocks
  that would produce duplicates at the package level.
- `sphinx-build -W -n -b html docs/sphinx docs/sphinx/_build/html`
  must stay green. A warning is handled before commit, not after.

## Delegation policy

An agent is launched only when it brings a capability distinct from
that of the main conversation or another agent.

- Do not launch several agents to analyse the same problem.
- Do not launch a reviewer for a trivial change that touches no
  invariant.
- Do not launch `server-prober` if a local test is enough.
- Do not launch `test-runner` to execute a single trivial command that
  can be run directly.
- Do not launch an agent just to move work to another context.
- Parallelism is reserved for genuinely independent tasks.

### Model policy

| Role                            | Default model                                  |
| ------------------------------- | ---------------------------------------------- |
| Targeted exploration            | economical model (session default)             |
| Test execution                  | Haiku (`test-runner`)                          |
| Test writing                    | inherited model (`test-author`)                |
| Server probe                    | Sonnet (`server-prober`)                       |
| Standard review                 | Sonnet (`invariant-reviewer`)                  |
| Architecture review             | Opus, only if the Impact Map justifies it      |

Opus is reserved for changes touching architecture, persistence,
security, concurrency, complex packaging, or explicitly flagged as such
in the Impact Map. Request it from `invariant-reviewer` via the
delegation message ("review Opus"), without creating a second
reviewer.
