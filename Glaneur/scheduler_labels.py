"""Localised labels for :class:`Glaneur.scheduler.Scheduler`.

Sits on the UI side of boundary 1 so the scheduler itself stays Qt-free.
lupdate only extracts ``QCoreApplication.translate("Ctx", "src")`` calls
with literals: we inline rather than aliasing (see ``bug_report.py``).
The ``"Planificateur"`` context is kept so the existing ``.ts`` entries
remain matched.
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QCoreApplication

from .scheduler import Scheduler


def next_run_text(scheduler: Scheduler) -> str:
    """Ready-to-display label for the next automatic update.

    Format adapted to the remaining time before the deadline: days +
    hours above 24 h, hours + minutes above one hour, minutes below.
    Returns a dedicated message in manual mode or when the deadline is
    already past.

    Args:
        scheduler: The scheduler whose state is rendered.

    Returns:
        A translated text (context ``"Planificateur"``).
    """
    config = scheduler.config
    if not config.intervalle_heures:
        return QCoreApplication.translate("Planificateur", "Mise à jour automatique désactivée")
    prochaine = scheduler.next_run()
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
    if scheduler.defer_active():
        return QCoreApplication.translate(
            "Planificateur", "Reprise reportée dans {delai} ({date})").format(
            delai=delai, date=f"{prochaine:%d/%m à %H:%M}")
    return QCoreApplication.translate(
        "Planificateur", "Prochaine mise à jour dans {delai} ({date})").format(
        delai=delai, date=f"{prochaine:%d/%m à %H:%M}")
