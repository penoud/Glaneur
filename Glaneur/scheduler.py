"""Due-date logic for automatic updates.

Deliberately without a thread or a widget: the class only answers "is it
time?". The interface polls it periodically through a ``QTimer``. Fully
Qt-free — the localised label rendered from this state lives in
:mod:`Glaneur.scheduler_labels`, on the UI side of boundary 1.

The due date is computed from ``derniere_execution`` stored in the
configuration, so it survives an application shutdown: if the interval
has elapsed in the meantime, the update fires on the next launch.
"""

from __future__ import annotations

import math
from datetime import datetime, time, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .config import Profile
    from .engine.result import RunResult

# Exponential backoff applied when the server did not provide a
# ``Retry-After``: level 0 -> 1 h, 1 -> 2 h, 2 -> 4 h. The level is
# incremented on each successive defer and capped at 2; it is reset to
# zero by :meth:`Scheduler.mark_run`.
BACKOFFS_S: tuple[int, ...] = (3600, 7200, 14400)


def _parse_iso(brut: str | None) -> datetime | None:
    """Parse an ISO 8601 timestamp or return ``None`` on empty/broken input.

    Shared between the single-profile and per-profile paths — the
    latter has to swallow the same edge cases (empty string, malformed
    format, ``None`` field) without raising.
    """
    if not brut:
        return None
    try:
        return datetime.fromisoformat(brut)
    except (TypeError, ValueError):
        return None


class Scheduler:
    """Compute and display the next automatic-update deadline.

    The object is passive: it does not start a timer, it answers the
    question "is it time?". The UI polls it periodically (typically
    through a ``QTimer``).
    """

    def __init__(self, config) -> None:
        """Attach the scheduler to a :class:`Glaneur.config.Config` instance.

        Args:
            config: Configuration object from which
                ``Config.last_run`` and
                ``Config.interval_hours`` are read, and on which
                ``Config.save`` is called by :meth:`mark_run`.
        """
        self.config = config

    # -- state --------------------------------------------------------------- #

    def last_run(self) -> datetime | None:
        """Timestamp of the last run, deserialised from the configuration.

        Returns:
            The datetime read from ``Config.last_run``, or
            ``None`` if the field is empty or malformed.
        """
        try:
            return datetime.fromisoformat(self.config.last_run)
        except (ValueError, TypeError):
            return None

    def _retry_after(self) -> datetime | None:
        """Resume date after a defer, or ``None`` when missing/malformed.

        Sole parsing point for ``config.retry_after`` — at the slightest
        doubt (empty string, broken format), the defer is ignored rather
        than raising.
        """
        brut = getattr(self.config, "retry_after", "") or ""
        if not brut:
            return None
        try:
            return datetime.fromisoformat(brut)
        except (ValueError, TypeError):
            return None

    def _nominal(self) -> datetime | None:
        """Date of the next deadline without considering any defer.

        Returns:
            The raw date, or ``None`` in manual mode.
        """
        if not self.config.interval_hours:
            return None
        derniere = self.last_run()
        if derniere is None:
            return datetime.now()       # never run: as soon as possible
        return derniere + timedelta(hours=self.config.interval_hours)

    def next_run(self) -> datetime | None:
        """Compute the date of the next automatic update.

        If no run has ever been recorded, the "next" is right now: the
        first launch fires immediately.

        An active defer (``config.retry_after`` in the future) pushes
        the nominal deadline out to that date.

        Returns:
            The scheduled date, or ``None`` in manual mode
            (``Config.interval_hours`` = 0).
        """
        nominale = self._nominal()
        if nominale is None:
            return None
        report = self._retry_after()
        if report is not None and report > nominale:
            return report
        return nominale

    def is_due(self) -> bool:
        """Report whether an automatic run should start right now.

        Returns:
            ``True`` if :meth:`next_run` has passed, ``False`` otherwise
            (manual mode included).
        """
        prochaine = self.next_run()
        return prochaine is not None and datetime.now() >= prochaine

    def defer_active(self) -> bool:
        """True when a valid ``retenter_apres`` pushes the nominal deadline out.

        Exposed for the UI-side label helper so it can pick the "deferred"
        wording without touching private methods.
        """
        nominale = self._nominal()
        report = self._retry_after()
        return (report is not None
                and nominale is not None
                and report > nominale)

    def mark_run(self) -> None:
        """Record the current instant as the last run and persist the config.

        Called by the engine at the end of a successful run. Writes to
        ``Config.last_run`` in ISO 8601 with second precision.
        Also clears any ongoing defer (``retenter_apres`` and
        ``backoff_niveau``): a successful run closes a backoff.
        """
        self.config.last_run = datetime.now().isoformat(timespec="seconds")
        self.config.retry_after = ""
        self.config.backoff_level = 0
        self.config.save()

    # -- multi-profile grid (lot 5.2) --------------------------------------

    def _parse_anchor(self) -> time:
        """Parse ``config.schedule_anchor`` into a naive ``time`` value.

        The anchor is a ``HH:MM`` string set at v2 migration from the
        current ``last_run``'s time-of-day (see :meth:`Config.load` on
        :mod:`Glaneur.config`). Empty or malformed values fall back to
        midnight — a safe anchor for the periodic grid.
        """
        brut = getattr(self.config, "schedule_anchor", "") or ""
        try:
            return time.fromisoformat(brut)
        except (TypeError, ValueError):
            return time(0, 0)

    @staticmethod
    def _grid_slot(anchor_dt: datetime, k: int, n: int, interval_hours: int,
                   threshold: datetime) -> datetime:
        """Return the first grid slot for profile ``k`` at or after ``threshold``.

        The grid is ``anchor_dt + k x I/n + m x I`` for every integer
        ``m``. Given a threshold ``T``, the returned slot satisfies
        ``slot ≥ T`` and no earlier slot in the same profile's grid
        satisfies the same inequality — this is the smallest ``m`` such
        that ``base + m x I ≥ T`` (with ``base = anchor_dt + k x I/n``).

        Args:
            anchor_dt: A datetime whose time-of-day is
                ``config.schedule_anchor``. The date component is
                irrelevant — the grid is periodic with period ``I``.
            k: Profile rank in the list (0-based).
            n: Total number of profiles (at least 1).
            interval_hours: Shared ``config.interval_hours``.
            threshold: Earliest acceptable slot; usually
                ``last_run + I/2`` per the roadmap's
                I/2-no-double-run rule.
        """
        n = max(1, n)
        interval = timedelta(hours=interval_hours)
        offset = timedelta(hours=interval_hours * k / n)
        base = anchor_dt + offset
        delta = (threshold - base).total_seconds() / interval.total_seconds()
        m = math.ceil(delta)
        return base + m * interval

    def next_run_for(self, profile: Profile, k: int, n: int) -> datetime | None:
        """Return the next automatic-run date for ``profile``.

        Applies the roadmap §5.2 recipe:

        1. In manual mode (``interval_hours == 0``), no automatic run
           is scheduled; returns ``None``.
        2. ``threshold = last_run + I/2`` — or ``now`` when
           ``profile.last_run`` is empty (a fresh profile fires
           immediately).
        3. The slot is the first grid entry ≥ threshold.
        4. If ``profile.retry_after`` is later than the slot, the
           deferral pushes the run out to that date instead.

        The "now" clock is not read internally — it is derived from the
        threshold, so the method stays pure and testable.

        Args:
            profile: The :class:`Glaneur.config.Profile` whose next-run
                is being computed. Only its ``last_run`` and
                ``retry_after`` are consulted.
            k: Rank of ``profile`` in the profile list (0 for the
                default one).
            n: Total number of profiles.

        Returns:
            The naive local datetime of the next slot, or ``None`` in
            manual mode.
        """
        interval_hours = int(getattr(self.config, "interval_hours", 0) or 0)
        if not interval_hours:
            return None
        last = _parse_iso(profile.last_run)
        retry = _parse_iso(profile.retry_after)
        if last is None:
            # A profile that has never run fires immediately — matches
            # the existing single-profile ``Scheduler.next_run`` (which
            # returns ``datetime.now()`` on empty ``last_run``). A
            # deferral, if any, still pushes past the immediate slot.
            slot = datetime.now()  # noqa: DTZ005
        else:
            anchor = self._parse_anchor()
            anchor_dt = datetime.combine(
                datetime.now().date(), anchor)  # noqa: DTZ005
            threshold = last + timedelta(hours=interval_hours / 2)
            slot = self._grid_slot(anchor_dt, k, n, interval_hours, threshold)
        if retry is not None and retry > slot:
            return retry
        return slot

    def is_due_for(self, profile: Profile, k: int, n: int) -> bool:
        """Report whether ``profile`` should start now.

        Delegates to :meth:`next_run_for`; returns ``False`` in manual
        mode.
        """
        prochaine = self.next_run_for(profile, k, n)
        return prochaine is not None and datetime.now() >= prochaine  # noqa: DTZ005

    def next_due_index(self, profiles: Sequence[Profile]) -> int | None:
        """Return the index of the first profile that is due, or ``None``.

        Walks ``profiles`` in order and returns the first ``k`` for
        which :meth:`is_due_for` is true. This matches the roadmap's
        "one profile at a time, in queue order" rule (§5.2). Manual
        mode collapses the walk — no profile is ever due.
        """
        n = len(profiles)
        for k, prof in enumerate(profiles):
            if self.is_due_for(prof, k, n):
                return k
        return None

    def defer(self, res: RunResult) -> None:
        """Defer the next run after a network circuit-breaker trips.

        Uses ``res.retry_after`` (aware UTC, produced by the engine via
        ``_trigger_defer``) when the server provided a
        ``Retry-After``. The server hint wins and the backoff level does
        not increase. Without a server hint, apply the local exponential
        backoff (``BACKOFFS_S`` — 1 h -> 2 h -> 4 h), then increment the
        level (capped at 2).

        ``config.retry_after`` is always written in naive local ISO
        8601 to remain comparable with ``Config.last_run``.

        Args:
            res: :class:`Glaneur.engine.result.RunResult` from a run
                that finished with ``res.deferred = True``.
        """
        cible: datetime | None = None
        if res.retry_after:
            try:
                brut = datetime.fromisoformat(res.retry_after)
            except (ValueError, TypeError):
                brut = None
            if brut is not None:
                if brut.tzinfo is not None:
                    brut = brut.astimezone().replace(tzinfo=None)
                cible = brut
        if cible is None:
            niveau = max(0, min(int(self.config.backoff_level), 2))
            cible = datetime.now() + timedelta(seconds=BACKOFFS_S[niveau])
            self.config.backoff_level = min(niveau + 1, 2)
        self.config.retry_after = cible.isoformat(timespec="seconds")
        self.config.save()
