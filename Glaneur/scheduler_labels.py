"""Localised labels for :class:`Glaneur.scheduler.Scheduler`.

Sits on the UI side of boundary 1 so the scheduler itself stays Qt-free.
lupdate only extracts ``QCoreApplication.translate("Ctx", "src")`` calls
with literals: we inline rather than aliasing (see ``bug_report.py``).
Context is ``"Scheduler"`` — the previous FR name ``"Planificateur"``
was renamed by US-EN-07 in lockstep with the sourcelanguage flip.
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
        A translated text (context ``"Scheduler"``).
    """
    config = scheduler.config
    if not config.interval_hours:
        return QCoreApplication.translate("Scheduler", "Automatic update disabled")
    prochaine = scheduler.next_run()
    if prochaine is None:
        return QCoreApplication.translate("Scheduler", "Automatic update disabled")
    reste = prochaine - datetime.now()
    if reste.total_seconds() <= 0:
        return QCoreApplication.translate("Scheduler", "Next update: imminent")
    heures, secondes = divmod(int(reste.total_seconds()), 3600)
    minutes = secondes // 60
    if heures >= 24:
        jours, heures = divmod(heures, 24)
        delai = QCoreApplication.translate(
            "Scheduler", "{days} d {hours} h").format(days=jours, hours=heures)
    elif heures:
        delai = QCoreApplication.translate(
            "Scheduler", "{hours} h {minutes:02d} min").format(hours=heures, minutes=minutes)
    else:
        delai = QCoreApplication.translate(
            "Scheduler", "{minutes} min").format(minutes=minutes)
    if scheduler.defer_active():
        return QCoreApplication.translate(
            "Scheduler", "Resume deferred, in {delay} ({date})").format(
            delay=delai, date=f"{prochaine:%d/%m at %H:%M}")
    return QCoreApplication.translate(
        "Scheduler", "Next update in {delay} ({date})").format(
        delay=delai, date=f"{prochaine:%d/%m at %H:%M}")
