# Sprint — Verify lots 1→4 before opening lot 5

Target location in the repository:
`docs/sprints/2026-09-verifier-lots-1-4-avant-lot-5.md`.

## Goal

Make lots 1 to 4 of `docs/design/roadmap.md` solid enough that lot 5
(profiles) can open without hidden debt. The sprint **verifies** what
already exists and **only fixes what blocks lot 5**. Everything else in
lots 1 to 4 stays where it is, in its own lot.

This sprint publishes nothing: `__version__` does not change.

## State observed on 2026-09-28 (starting state)

Recorded by reading the code on the `update-docs` branch. "Done" means
observed, "partial" means present but incomplete compared to
`docs/design/roadmap.md`, "missing" means absent.

| Item | State | Evidence |
|---|---|---|
| 1.1 Branch coverage + ratchet | partial | `pyproject.toml` (`branch = true`) and `tools/check_coverage.py` (per-module floors) exist, but **`.github/workflows/tests.yml` runs neither `--cov` nor `check_coverage.py`**. The ratchet is not guarded. |
| 1.2 Local fake HTTP server | missing | No `ThreadingHTTPServer` in `tests/`. |
| 1.3 Network tests `@pytest.mark.network` | missing | Marker not registered; no dedicated workflow. |
| 1.4 Ruff, pip-audit, Dependabot | partial | `ruff.toml` only enables `ARG, RUF` on top of the Ruff default. Ruff is not run in CI. `pip-audit` is not run. **Dependabot done** (`.github/dependabot.yml`). |
| 1.5 Sphinx + Google docstrings | partial | `docs/sphinx/conf.py` complete and `requirements-doc.txt` in place, but **Sphinx is not run in CI** and there are no pydocstyle `D` rules in Ruff. |
| 2 Identifiers and docstrings in English | done | Verified in `engine/core.py`, `sources/base.py`, `config.py`. |
| 2 French `tr()` sources | known | 17 occurrences of `QCoreApplication.translate("Moteur", <FR>)` in `engine/core.py`. |
| 2 `QCoreApplication` in the engine (boundary 1) | known | `Glaneur/engine/core.py:20`. |
| 2 Structured engine events | missing | The engine passes already-translated strings to the `journal(str)` callback. |
| 3.1 `Transport.get_json` retry policy | bug | `sources/base.py:264-275`: retries every `RequestException` (so **including 4xx**), waits `2×(attempt+1)` s (2/4/6 instead of 2/4), **`Retry-After` extracted but never used** in the loop. Cooperative stop OK. |
| 3.1 Retry shared with `Engine.download` | missing | `engine/core.py:302-339`: a single attempt, the failure surfaces to the circuit breaker of the `run` loop. |
| 3.2 Explicit fatal error on API root | partial | Classified as `definitif` by `classify_error`, but `get_json` surfaces a generic `RuntimeError`. |
| 3.3 Validation before renaming `.part` | missing | `engine/core.py:321` `tmp.replace(dest)` with no magic bytes, no size, no Checksum. |
| 3.4 Batched manifest | partial | Saves every 25 images + `finally:` on interruption. No time-based flush (30 s). |
| 4 Per-folder OS lock | missing | `engine/_locks.py` = a process-level `threading.Lock`, for manifest merging. No `fcntl.flock` and no `msvcrt.locking`. |

## What actually blocks lot 5

Three functional blockers, one safety-net blocker.

- **Lot 5.0 E2** — the profile-list "status" column reads **structured
  events** from the engine (`docs/design/evolution-multi-sources.md`
  §4). Without lot 2, we cannot build it.
- **Lot 5.2** — a single-worker queue processing one profile at a time,
  plus the catch-up after the PC has been off. Requires a **per-folder
  OS lock** (roadmap lot 4). A `threading.Lock` does not protect
  against the open UI application + scheduled task + leftover
  installation from an old version.
- **Lot 5.2** — the slot computation uses `retry_after`. If
  `Transport.get_json` retries 4xx and ignores `Retry-After`, we poison
  the I/2 rule (roadmap §5.2). Targeted fix from lot 3.1 required.
- **Lot 5.1** — v2 of `config.json` = **persisted format change**. The
  coverage ratchet must run in CI as a safety net (lot 1.1 tail).

The rest (1.2, 1.3, 1.4 ruff/pip-audit, 1.5 pydocstyle, 3.1 download,
3.2, 3.3, 3.4 timer) improves the project but does not prevent lot 5
from opening. Each stays where it is, in its own lot.

## Sprint constraints

- **`__version__` does not change.** No PR of this sprint publishes.
- No new runtime dependency. `pytest-cov` and `ruff` are already in
  `requirements-dev.txt`.
- Code comments, docstrings, and log messages **in English**. UI
  strings stay translated, but **the source is English** (starting
  point for the `.ts` conversion planned in the full lot 2).
- Only one writer at a time on production code. US-VERIF-01 and
  US-VERIF-03 are independent and can run in parallel in two separate
  worktrees; US-VERIF-02 then US-VERIF-04 run in series because they
  touch `sources/base.py` and `engine/core.py` respectively.
- Each user story opens its own draft PR, with a
  `.claude/state/impact-map.md` reset at start, as prescribed by
  `CLAUDE.md` section "Impact Map".
- Never push, never tag, never modify `__version__`. Hooks block; do
  not work around them.

## Decisions and their rationale

| Decision | Rationale |
|---|---|
| Do not cover all of lot 1 in this sprint | 1.2 (local fake server) and 1.3 (network tests) bring test quality, not a lot-5 unblock. Doing them here drags them into CI matrix questions that double the sprint's duration. |
| Fix `Transport.get_json` only, not `Engine.download` | Roadmap 3.1 wants them unified, but today the run loop's circuit breaker (5 consecutive failures → `defer`) already absorbs the missing retry inside `download`. Lot 5.2 does not depend on it. |
| US-VERIF-04 last | It is the largest change (all engine `translate()` calls, plus the UI layer that renders them). It benefits from having the safety net (US-VERIF-01) and the lock (US-VERIF-03) already green. |
| Do not touch the French manifest keys or the French `Element` fields | CLAUDE.md explicitly lists those gaps as deferred to their own lot. Reopening them here cascades to too many files. |
| Coverage ratchet wired only on modules already at their ceiling | The current ceilings (`sources/*` 100 %, `scheduler.py` 100 %, `config.py` 100 %, `engine/*` 95 %) are the ones measured today. We bake them into CI; we raise them in later lots following the rule "the ratchet never goes down". |

---

## US-VERIF-01 — Coverage ratchet wired in CI (lot 1.1, tail)

### Change 1 — `.github/workflows/tests.yml`

A single step added after "Run tests". Coverage is measured with
`--cov=Glaneur --cov-branch`, then `tools/check_coverage.py` compares
the result against the per-module ceilings.

```yaml
      - name: Run tests with coverage
        env:
          QT_QPA_PLATFORM: offscreen
        run: python -m pytest -q --cov=Glaneur --cov-branch

      - name: Check per-module coverage floors
        run: python tools/check_coverage.py
```

The old "Run tests" step disappears. The matrix stays unchanged
(`ubuntu-latest`, `windows-latest`, Python 3.11); the measurement
works identically on both OSes.

### Change 2 — `pyproject.toml`

Global `fail_under` stays at `0` (the per-module ceilings are what
matters). We do not touch this file in this story.

### Verified or assumed

- **Verified**: the current ceilings are the ones measured. A local run
  of `pytest --cov=Glaneur --cov-branch` then
  `python tools/check_coverage.py` must exit with 0 before the PR is
  merged.
- **Assumed**: on Windows, `coverage.Coverage.load()` correctly reads
  the `.coverage` file produced by pytest-cov. To be confirmed in CI at
  the first run.

### Acceptance criteria

- [ ] `tests.yml` runs `pytest --cov=Glaneur --cov-branch` then
      `tools/check_coverage.py`, on `ubuntu-latest` and `windows-latest`.
- [ ] A control PR that deliberately breaks a test (and its coverage)
      fails the `tests` job.
- [ ] A control PR that removes a tested branch in `sources/` (coverage
      goes from 100 % to 99 %) fails the "Check per-module coverage
      floors" job.
- [ ] The PR of this story is green on the first run after merge —
      that is, the ceilings recorded in `check_coverage.py` are met by
      the current suite.

---

## US-VERIF-02 — `Transport.get_json` retry policy (lot 3.1, core)

### Context

Today, `Glaneur/sources/base.py:264-275` (`Transport.get_json`) retries
every `requests.RequestException` — so 401, 403, 404 like a timeout.
The pause is `2 × (attempt + 1)` seconds (2, 4, 6). `Retry-After` is
indeed extracted by `_retry_after` but only consumed on the
`Engine.download` path, never inside the `get_json` loop.

### Change 1 — `Glaneur/sources/base.py`

`get_json` relies on `classify_error`:

- 3 total attempts. Wait between attempts = 2 s then 4 s (roadmap 3.1).
- On `classify_error` = `"definitif"` (400 outside `fin_si`, 401, 403,
  404, 405, 410, `MissingSchema`, `InvalidURL`…), re-raise the
  original exception immediately without retrying.
- On `"transitoire"` or `"coupure"`, retry. If `retry_after` is
  provided by the server (`Retry-After` in seconds or HTTP-date), use
  it, but **capped at 120 s**. Beyond that, retry without waiting
  indefinitely.
- Each wait stays `Event`-interruptible (already handled by
  `Transport.sleep`).

`fin_si` is applied **before** classification as today: a 400 with
`fin_si={400}` (WordPress pagination) stays a normal end, never a
failure.

### Change 2 — tests

The writer is the `test-author` sub-agent. Targets in
`tests/test_source_base.py`:

- 401, 403, 404 (outside `fin_si`): immediate raise, **a single**
  attempt, no `sleep`.
- 429 with `Retry-After: 3`: `Transport.sleep` called with 3 s, second
  attempt succeeds.
- 429 with `Retry-After: 300`: `Transport.sleep` called with **120 s**,
  not 300 s.
- Three consecutive 500 failures: observed pauses 2 s then 4 s (two
  pauses for three attempts). The old third 6 s pause must no longer
  appear.
- Cooperative stop: `Transport.arret.set()` during the pause raises
  `Interrupted` without a new request.
- `fin_si={400}` with a 400 response: returns `(None, headers)`, no
  retry.

Existing tests that relied on the 2/4/6 loop must be updated in the
same commit.

### Verified or assumed

- **Verified**: `classify_error` already exists (`sources/base.py:90`)
  and covers the necessary cases; the `_CUT_STATUSES` and
  `_DEFINITIVE_STATUSES` tables are exhaustive.
- **Verified**: `Transport.sleep` fragments the wait and cooperates
  with the stop.
- **Assumed**: no existing test verifies the third 6 s pause as
  desired behaviour. To be checked before switching.

### Acceptance criteria

- [ ] The existing suite stays green.
- [ ] The new tests listed above pass.
- [ ] No `sleep(6)` observed in `test_source_base.py` traces.
- [ ] The `Glaneur/sources/*` coverage ceiling stays at 100 %.
- [ ] `invariant-reviewer` review (`Transport` boundary).

---

## US-VERIF-03 — Per-folder OS lock (lot 4)

### Context

Today, `Glaneur/engine/_locks.py` = process-level `threading.Lock`,
for manifest merging UI ↔ engine. Lot 5.2 introduces a profile queue
then (lot 8) an hourly scheduled task. At that point, two triggers can
land at the same time on the same folder: open UI application and
scheduled task, or leftover installation of the old binary. A
`threading.Lock` does not protect between processes.

Choice: a per-folder OS lock, portable, no dependency.

### Change 1 — `Glaneur/engine/_folder_lock.py` (new)

Isolated module with a context manager:

```python
from contextlib import contextmanager
from pathlib import Path

@contextmanager
def folder_lock(target_dir: Path) -> Iterator[None]:
    """Hold an exclusive OS lock on ``target_dir/.glaneur.lock``.

    Uses ``fcntl.flock`` on POSIX and ``msvcrt.locking`` on Windows. The
    file body carries PID/host/UTC time for diagnostics only — the OS
    lock is the real gate, not the file's content. Raises
    :class:`FolderBusy` if the lock is already held.
    """
```

- POSIX: `fcntl.flock(fd, LOCK_EX | LOCK_NB)`. On `BlockingIOError`,
  raise `FolderBusy`. Released by `close()` on the descriptor, safe
  even if the process dies.
- Windows: `msvcrt.locking(fd, LK_NBLCK, 1)` on the first byte of the
  file. Same behaviour: on `OSError`, raise `FolderBusy`. The lock is
  released when the handle is closed.
- The `.glaneur.lock` file remains on disk after release — this is an
  implementation detail, not a lock-file in the historical sense. On
  the next acquisition we reuse the same file. A user who deletes the
  file "by hand" breaks nothing: the next acquisition recreates it.

### Change 2 — `Glaneur/engine/core.py`

Wrap the `Engine.run()` logic inside the context manager:

```python
def run(self) -> RunResult:
    try:
        with folder_lock(Path(self.o.target_dir)):
            return self._run_locked()
    except FolderBusy:
        return RunResult(
            message=<code busy>,   # via structured event, cf US-VERIF-04
            busy=True,
        )
```

`RunResult` gains a `busy: bool = False` boolean. No other engine
transformation in this story.

### Change 3 — `cli.py`

On `busy=True`, exit with **exit code 3** (roadmap lot 4). Short
message on `stderr`.

### Change 4 — tests

Targets in a new `tests/test_folder_lock.py`:

- Two successive acquisitions of the same folder in the same process:
  the second raises `FolderBusy`.
- Two successive acquisitions separated by the release of the first:
  the second acquisition succeeds.
- Two processes (`multiprocessing.Process`) running in parallel: the
  first gets the lock, the second raises `FolderBusy`.
- Manual deletion of the `.glaneur.lock` file between two runs: the
  reprise works.
- Integration: `Engine.run()` on an already-locked folder returns
  `RunResult(busy=True)`, with no side effects (no manifest written,
  no file downloaded).

### Verified or assumed

- **Verified**: `fcntl` is available on macOS and Linux. `msvcrt` is
  available in every CPython on Windows.
- **Assumed**: `msvcrt.locking(fd, LK_NBLCK, 1)` on a file opened in
  `r+b` mode does place a mandatory lock, not an advisory one. To be
  confirmed on `windows-latest` in CI.
- **Assumed**: on a mounted SMB share, the lock works. Not tested
  here. The roadmap does not require this case; keep as a note.

### Acceptance criteria

- [ ] The existing suite stays green.
- [ ] The new tests above pass on `ubuntu-latest` and
      `windows-latest`.
- [ ] `Engine.run()` on a locked folder returns `RunResult(busy=True)`,
      manifest not modified.
- [ ] `python -m cli` on a locked folder exits with exit code 3.
- [ ] The `Glaneur/engine/*` coverage ceiling (95 %) is maintained.
- [ ] `invariant-reviewer` review (new module in the engine;
      engine/OS boundary).

---

## US-VERIF-04 — Structured engine events (lot 2, tail, boundary 1)

### Context

`Glaneur/engine/core.py` imports `QCoreApplication` and makes 17
`translate("Moteur", <FR>)` calls. The consequences: the engine
depends on Qt (violation of boundary 1 documented in CLAUDE.md) and
the "status column" of the profile list in lot 5.0 E2 has nothing to
consume.

Target: the engine emits a `(code, params)` couple — a stable English
key and a dictionary of values — that the UI translates in its own
code.

### Change 1 — Event registry

New module `Glaneur/engine/events.py`:

```python
from dataclasses import dataclass
from typing import Mapping

@dataclass(frozen=True)
class EngineEvent:
    """A structured message emitted by the engine.

    ``code`` is a stable identifier (kebab-case) known to the UI mapper
    and to the file logger. ``params`` carries the values needed to
    render the message; the engine never formats a user-facing string.
    """
    code: str
    params: Mapping[str, object]
```

Codes to define (derived from the 17 `translate("Moteur", …)`
identified) — subject to adjustment when wiring:

| Code | Params | Current occurrence |
|---|---|---|
| `manifest-unreadable` | — | `core.py:113` |
| `download-error` | `{error}` | `core.py:336, 572` |
| `defer-with-time` | `{until}` | `core.py:362` |
| `defer-no-time` | — | `core.py:367` |
| `already-known` | `{count}` | `core.py:404` |
| `nothing-matches` | — | `core.py:437` |
| `known-and-todo` | `{known, todo}` | `core.py:468` |
| `all-up-to-date` | — | `core.py:476` |
| `identifying-galleries` | — | `core.py:488` |
| `n-new-images` | `{count, size}` | `core.py:551` |
| `interrupted` | — | `core.py:569` |
| `write-problem` | `{error}` | `core.py:574` |
| `not-found` | — | `core.py:531` |

The list is indicative: the writer of the story enumerates each
`translate()` at commit time and gives it a code at wiring time.

### Change 2 — `Glaneur/engine/core.py`

- Remove the `PySide6.QtCore.QCoreApplication` import.
- The `journal` callback changes signature:
  `Callable[[EngineEvent], None]`.
- Each `self._journal(QCoreApplication.translate("Moteur", …))`
  becomes `self._journal(EngineEvent(code, params))`.
- The file log writes the code + parameters in English (roadmap lot
  2).

### Change 3 — `app.py` (UI)

- A mapper `_render(event: EngineEvent) -> str` reproduces the 17
  current French strings and rewires them to the new codes. This is
  where — **and only here** — `QCoreApplication.translate` lives, with
  the `"UiJournal"` context (new context, separate from `"Moteur"`
  which no longer exists).
- The callback passed to `Engine` becomes
  `lambda ev: self.journal_widget.appendPlainText(self._render(ev))`.

### Change 4 — `translations/`

- Remove the `context="Moteur"` entries from the `.ts`.
- Add the new English sources under `context="UiJournal"`.
- Regenerate `translations/glaneur_fr.ts` with `lupdate`, keeping the
  other literal contexts as today.
- Recompile the `.qm` files with the existing script
  `translations/build_translations.py`.

### Change 5 — `Glaneur/logsetup.py` and file logs

The file log writes `event.code` +
`json.dumps(event.params, ensure_ascii=False)`. No translation on the
file side — roadmap lot 2: "The file log writes them in English."

### Change 6 — tests

- `tests/test_core.py`: every assertion that expected a specific
  French string now compares `event.code` and possibly a field of
  `event.params`. This is where most of the story's work hides.
- `tests/test_boundaries.py`: the `xfail(strict=True)` on the
  `QCoreApplication` import in the engine flips to `pass`. Remove the
  marker.
- New `tests/test_ui_journal_render.py`: every event code renders a
  non-empty string in French, and two calls to the same code produce
  the same rendering (determinism).

### Verified or assumed

- **Verified**: `test_boundaries.py` already marks the
  `QCoreApplication` import as a boundary to respect (CLAUDE.md).
- **Verified**: `Glaneur/i18n.py` already installs the translator with
  the expected context; adding a `"UiJournal"` context requires no
  new plumbing.
- **Assumed**: `lupdate` preserves the other contexts
  (`"Planificateur"`, `"Updater"`, `"BugReport"`) intact when
  regenerating. To be checked on the `.ts` diff before commit.
- **Assumed**: no module other than `engine/core.py` imports
  `QCoreApplication` outside the UI layer. To be checked with a grep
  at commit time.

### Acceptance criteria

- [ ] `Glaneur/engine/core.py` no longer imports `PySide6`.
- [ ] `test_boundaries.py`: the forbidden import becomes a `pass`
      without `xfail`.
- [ ] The full suite stays green, including the new rendering tests.
- [ ] The file log contains English codes + JSON params, no French
      strings.
- [ ] The `.qm` compiled by `translations/build_translations.py` is
      readable and covers every code.
- [ ] `sphinx-build -W -n -b html docs/sphinx docs/sphinx/_build/html`
      stays green (docstrings updated).
- [ ] **Opus** `invariant-reviewer` review (boundary 1 + structured
      events + translations).

---

## Order and parallelism

```
US-VERIF-01  ─┐
              ├─►  US-VERIF-02  ──►  US-VERIF-04  ──►  lot 5 opens
US-VERIF-03  ─┘
```

- US-VERIF-01 and US-VERIF-03 are independent (CI vs engine) and can
  run in parallel in two separate worktrees.
- US-VERIF-02 waits for US-VERIF-01 to be merged (the CI ratchet
  protects the retry-policy change).
- US-VERIF-04 closes the sprint. It waits for US-VERIF-02 to be merged
  (so the engine-tests refactor and the retry change do not mix in the
  same diff), and benefits from the US-VERIF-03 lock for its
  integration tests.

## Out of scope — explicitly

- Lot 1.2 (local fake server), lot 1.3 (network tests), lot 1.4 full
  Ruff ruleset + `pip-audit`, lot 1.5 pydocstyle in Ruff.
- Lot 3.1 on the `Engine.download` side (unified retry).
- Lot 3.2 typed fatal message on the API root.
- Lot 3.3 `.part` validation (magic bytes, size, checksum).
- Lot 3.4 time-based manifest flush.
- Remaining CLAUDE.md gaps: French manifest keys, French `Element`
  fields, French CLI flags, French dispatch values, `sourcelanguage="fr"`
  in `.ts`.

Each stays where it is, in its own lot.

## Definition of Done

- [ ] The four user stories each have their PR merged on `main`.
- [ ] `__version__` unchanged.
- [ ] The full suite and `python tools/check_coverage.py` pass on
      `main` at the end of the sprint.
- [ ] `sphinx-build -W -n -b html docs/sphinx docs/sphinx/_build/html`
      stays green.
- [ ] The `xfail(strict=True)` on the `QCoreApplication` import has
      been removed from `tests/test_boundaries.py`.
- [ ] `CLAUDE.md` "Known gaps" section is updated: the two gaps
      "`engine/core.py` imports `QCoreApplication`" and
      "`_locks.py` = `threading.Lock`" disappear.
- [ ] Lot 5.0 E1 can start without the leftover technical debt of
      lots 1 to 4.
