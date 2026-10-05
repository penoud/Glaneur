# Impact Map

<!--
Temporary scratchpad, one story at a time. Reset to this empty state
between two stories. Do not store copies of files, logs, bulky test
output, or information that already lives in CLAUDE.md. See CLAUDE.md
sections "Impact Map" and "Minimal context policy".
-->

## Task

**Lot 5.2 — Per-profile scheduler grid (pure computation).**

Adds the multi-profile scheduling algorithm from
`docs/design/evolution-multi-sources.md` §3.1 and roadmap §5.2 as
pure methods on :class:`Glaneur.scheduler.Scheduler`. No wiring into
:class:`app.Fenetre` or :class:`Glaneur.config.Config`'s state
yet — that follows in a next commit once the core computation has
its own tests and reviewer sign-off.

### Grid formula

For ``n`` scheduled profiles, ``k`` = profile rank (0 to n-1),
``I`` = ``interval_hours``, the grid of slots for profile ``k`` is:

    anchor + k × I/n + m × I,  m ∈ ℤ

The **anchor** is a time-of-day (``HH:MM``) stored on
:attr:`Config.schedule_anchor` (already added in E3 part A). Empty
anchor falls back to midnight.

Due-time for a profile:

- ``threshold = last_run + I/2`` (or ``now`` when ``last_run`` is
  empty — a fresh profile fires immediately);
- slot = first grid slot ≥ threshold;
- if a ``retry_after`` is set and it is later than the slot,
  ``retry_after`` wins (the deferral pushes the run out further).

The **I/2 rule** is what makes the computation robust — a run made
on time lands on the next slot exactly ``+I`` later, a late catch-up
realigns within 0.5–1.5 intervals without a double run, and adding
or reordering profiles never restarts a profile less than ``I/2``
after its last run. That last invariant is already documented in
CLAUDE.md's multi-source section.

### API added

- `Scheduler._parse_anchor()` — parses
  ``config.schedule_anchor`` into a naive ``time`` object,
  fallback ``00:00`` on empty/malformed.
- `Scheduler._grid_slot(anchor_dt, k, n, threshold)` — pure
  computation returning the first slot ≥ threshold.
- `Scheduler.next_run_for(profile, k, n)` — the runtime entry
  point. Reads scheduler state (``last_run`` /
  ``retry_after``) from the passed :class:`Glaneur.config.Profile`;
  ``k`` / ``n`` come from the caller iterating
  :meth:`Glaneur.config.Config.profiles`.
- `Scheduler.is_due_for(profile, k, n)` — boolean wrapper.
- `Scheduler.next_due_index(profiles)` — walks a list of profiles
  and returns the index of the first one that is due, or ``None``.

## Directly modified

- `Glaneur/scheduler.py` — five new methods (four private + one
  public helper). Existing single-profile API
  (`next_run`, `is_due`, `mark_run`, `defer`) unchanged; still
  drives the default-profile auto-run cadence.
- `tests/test_scheduler.py` — new `TestGridSlot` and
  `TestNextRunFor` classes locking the math.

## Direct dependencies

- Uses :attr:`Config.schedule_anchor`, :attr:`Config.interval_hours`,
  and reads `profile.last_run` / `profile.retry_after` — all already
  in place.

## Explicitly out of scope

- Wiring `Fenetre._verifier_echeance` to iterate profiles — next
  commit.
- Per-profile `mark_run` / `defer` mutators on Scheduler — next
  commit (they touch how per-profile state gets persisted, since
  the default profile's state is flat on Config while extras'
  state is on the Profile object in `_extra_profiles`).
- Multi-profile queueing / one-profile-at-a-time worker — E3 part
  B step 11 (queue) and lot 5.3.
- `__version__` — unchanged.

## Tests

- `TestGridSlot`:
  - single-profile grid == single-slot walk;
  - two-profile grid staggered by I/2;
  - three-profile grid staggered by I/3;
  - threshold before base returns base (m=0);
  - threshold exactly at base returns base;
  - threshold exactly at a future slot returns that slot;
  - anchor midnight vs. non-midnight give parallel grids.
- `TestNextRunFor`:
  - empty last_run + fresh profile → due immediately;
  - manual mode (interval 0) returns None;
  - deferral pushes past the nominal slot;
  - I/2 rule: last_run == just now, next slot is exactly +I later;
  - N=1 case matches today's single-profile Scheduler.next_run().

Verification:

- `pytest -q` → 634 + new tests.
- `python tools/check_coverage.py` → floors held.
- `ruff check` clean on touched files.

## Invariants

- `__version__` unchanged.
- Existing Scheduler behaviour unchanged.
- I/2-no-double-run invariant enforced (already documented in
  CLAUDE.md).
- All new methods pure (no side-effects, no persistence, no
  clock — every "now" value is a parameter, matching the existing
  scheduler pattern for testability).

## Validation

Level `subsystem` per lot 5.2's engine-scheduler footprint. No
persisted-format touched, no boundary crossed.

- `pytest -q --cov=Glaneur --cov-branch` green.
- `python tools/check_coverage.py` green.
- `ruff check` clean on touched files.
