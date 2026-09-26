"""Due-date logic for automatic updates.

Deliberately without a thread or a widget: the class only answers "is it
time?". The interface polls it periodically through a ``QTimer``. The
only Qt dependency is ``QCoreApplication.translate`` for the visible
labels returned by :meth:`Planificateur.texte_prochaine` (no widget, no
thread introduced).

The due date is computed from ``derniere_execution`` stored in the
configuration, so it survives an application shutdown: if the interval
has elapsed in the meantime, the update fires on the next launch.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from PySide6.QtCore import QCoreApplication

if TYPE_CHECKING:
    from .engine.resultat import Resultat

# lupdate only extracts QCoreApplication.translate("Ctx", "src") calls
# with literals: we inline rather than aliasing (see bug_report.py).

# Exponential backoff applied when the server did not provide a
# ``Retry-After``: level 0 -> 1 h, 1 -> 2 h, 2 -> 4 h. The level is
# incremented on each successive defer and capped at 2; it is reset to
# zero by :meth:`Planificateur.marquer_execution`.
BACKOFFS_S: tuple[int, ...] = (3600, 7200, 14400)


class Planificateur:
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
                ``Config.sauver`` is called by :meth:`marquer_execution`.
        """
        self.config = config

    # -- state --------------------------------------------------------------- #

    def derniere(self) -> datetime | None:
        """Timestamp of the last run, deserialised from the configuration.

        Returns:
            The datetime read from ``Config.derniere_execution``, or
            ``None`` if the field is empty or malformed.
        """
        try:
            return datetime.fromisoformat(self.config.derniere_execution)
        except (ValueError, TypeError):
            return None

    def _retenter_apres(self) -> datetime | None:
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

    def _nominale(self) -> datetime | None:
        """Date of the next deadline without considering any defer.

        Returns:
            The raw date, or ``None`` in manual mode.
        """
        if not self.config.intervalle_heures:
            return None
        derniere = self.derniere()
        if derniere is None:
            return datetime.now()       # never run: as soon as possible
        return derniere + timedelta(hours=self.config.intervalle_heures)

    def prochaine(self) -> datetime | None:
        """Compute the date of the next automatic update.

        If no run has ever been recorded, the "next" is right now: the
        first launch fires immediately.

        An active defer (``config.retenter_apres`` in the future) pushes
        the nominal deadline out to that date.

        Returns:
            The scheduled date, or ``None`` in manual mode
            (``Config.intervalle_heures`` = 0).
        """
        nominale = self._nominale()
        if nominale is None:
            return None
        report = self._retenter_apres()
        if report is not None and report > nominale:
            return report
        return nominale

    def echeance_atteinte(self) -> bool:
        """Report whether an automatic run should start right now.

        Returns:
            ``True`` if :meth:`prochaine` has passed, ``False`` otherwise
            (manual mode included).
        """
        prochaine = self.prochaine()
        return prochaine is not None and datetime.now() >= prochaine

    def marquer_execution(self) -> None:
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

    def differer(self, res: Resultat) -> None:
        """Defer the next run after a network circuit-breaker trips.

        Uses ``res.retenter_apres`` (aware UTC, produced by the engine via
        ``_declencher_report``) when the server provided a
        ``Retry-After``. The server hint wins and the backoff level does
        not increase. Without a server hint, apply the local exponential
        backoff (``BACKOFFS_S`` — 1 h -> 2 h -> 4 h), then increment the
        level (capped at 2).

        ``config.retenter_apres`` is always written in naive local ISO
        8601 to remain comparable with ``Config.derniere_execution``.

        Args:
            res: :class:`Glaneur.engine.result.Resultat` from a run
                that finished with ``res.reporte = True``.
        """
        cible: datetime | None = None
        if res.retenter_apres:
            try:
                brut = datetime.fromisoformat(res.retenter_apres)
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

    # -- display ------------------------------------------------------------- #

    def texte_prochaine(self) -> str:
        """Localised label for the user: "Next update in ...".

        Format adapted to the remaining time before the deadline: days +
        hours above 24 h, hours + minutes above one hour, minutes below.
        Returns a dedicated message in manual mode or when the deadline
        is already past.

        Returns:
            A ready-to-display text, translated through
            ``QCoreApplication.translate`` (context ``"Planificateur"``).
        """
        if not self.config.intervalle_heures:
            return QCoreApplication.translate("Planificateur", "Mise à jour automatique désactivée")
        prochaine = self.prochaine()
        if prochaine is None:
            return QCoreApplication.translate("Planificateur", "Mise à jour automatique désactivée")
        reste = prochaine - datetime.now()
        if reste.total_seconds() <= 0:
            return QCoreApplication.translate("Planificateur", "Prochaine mise à jour : imminente")
        heures, secondes = divmod(int(reste.total_seconds()), 3600)
        minutes = secondes // 60
        if heures >= 24:
            jours, heures = divmod(heures, 24)
            delai = QCoreApplication.translate(
                "Planificateur", "{jours} j {heures} h").format(jours=jours, heures=heures)
        elif heures:
            delai = QCoreApplication.translate(
                "Planificateur", "{heures} h {minutes:02d} min").format(heures=heures, minutes=minutes)
        else:
            delai = QCoreApplication.translate(
                "Planificateur", "{minutes} min").format(minutes=minutes)
        nominale = self._nominale()
        report = self._retenter_apres()
        report_actif = (report is not None
                        and nominale is not None
                        and report > nominale)
        if report_actif:
            return QCoreApplication.translate(
                "Planificateur", "Reprise reportée dans {delai} ({date})").format(
                delai=delai, date=f"{prochaine:%d/%m à %H:%M}")
        return QCoreApplication.translate(
            "Planificateur", "Prochaine mise à jour dans {delai} ({date})").format(
            delai=delai, date=f"{prochaine:%d/%m à %H:%M}")
