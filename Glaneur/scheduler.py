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

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .engine.result import RunResult

# Exponential backoff applied when the server did not provide a
# ``Retry-After``: level 0 -> 1 h, 1 -> 2 h, 2 -> 4 h. The level is
# incremented on each successive defer and capped at 2; it is reset to
# zero by :meth:`Scheduler.mark_run`.
BACKOFFS_S: tuple[int, ...] = (3600, 7200, 14400)


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
                ``Config.derniere_execution`` and
                ``Config.intervalle_heures`` are read, and on which
                ``Config.sauver`` is called by :meth:`mark_run`.
        """
        self.config = config

    # -- state --------------------------------------------------------------- #

    def last_run(self) -> datetime | None:
        """Timestamp of the last run, deserialised from the configuration.

        Returns:
            The datetime read from ``Config.derniere_execution``, or
            ``None`` if the field is empty or malformed.
        """
        try:
            return datetime.fromisoformat(self.config.derniere_execution)
        except (ValueError, TypeError):
            return None

    def _retry_after(self) -> datetime | None:
        """Resume date after a defer, or ``None`` when missing/malformed.

        Sole parsing point for ``config.retenter_apres`` — at the slightest
        doubt (empty string, broken format), the defer is ignored rather
        than raising.
        """
        brut = getattr(self.config, "retenter_apres", "") or ""
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
        if not self.config.intervalle_heures:
            return None
        derniere = self.last_run()
        if derniere is None:
            return datetime.now()       # never run: as soon as possible
        return derniere + timedelta(hours=self.config.intervalle_heures)

    def next_run(self) -> datetime | None:
        """Compute the date of the next automatic update.

        If no run has ever been recorded, the "next" is right now: the
        first launch fires immediately.

        An active defer (``config.retenter_apres`` in the future) pushes
        the nominal deadline out to that date.

        Returns:
            The scheduled date, or ``None`` in manual mode
            (``Config.intervalle_heures`` = 0).
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
        ``Config.derniere_execution`` in ISO 8601 with second precision.
        Also clears any ongoing defer (``retenter_apres`` and
        ``backoff_niveau``): a successful run closes a backoff.
        """
        self.config.derniere_execution = datetime.now().isoformat(timespec="seconds")
        self.config.retenter_apres = ""
        self.config.backoff_niveau = 0
        self.config.sauver()

    def defer(self, res: RunResult) -> None:
        """Defer the next run after a network circuit-breaker trips.

        Uses ``res.retry_after`` (aware UTC, produced by the engine via
        ``_trigger_defer``) when the server provided a
        ``Retry-After``. The server hint wins and the backoff level does
        not increase. Without a server hint, apply the local exponential
        backoff (``BACKOFFS_S`` — 1 h -> 2 h -> 4 h), then increment the
        level (capped at 2).

        ``config.retenter_apres`` is always written in naive local ISO
        8601 to remain comparable with ``Config.derniere_execution``.

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
            niveau = max(0, min(int(self.config.backoff_niveau), 2))
            cible = datetime.now() + timedelta(seconds=BACKOFFS_S[niveau])
            self.config.backoff_niveau = min(niveau + 1, 2)
        self.config.retenter_apres = cible.isoformat(timespec="seconds")
        self.config.sauver()
