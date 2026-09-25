"""Logique d'échéance des mises à jour automatiques.

Volontairement sans thread ni widget : la classe ne fait que répondre à
« est-ce l'heure ? ». C'est l'interface qui l'interroge périodiquement via
un QTimer. Seule dépendance Qt : `QCoreApplication.translate` pour les
libellés visibles renvoyés par `texte_prochaine()` (aucun widget, aucun
thread introduit).

L'échéance est calculée à partir de `derniere_execution` stocké dans la
configuration, donc elle survit à une fermeture de l'application : si
l'intervalle s'est écoulé pendant ce temps, la mise à jour part au lancement
suivant.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from PySide6.QtCore import QCoreApplication

# lupdate n'extrait que les appels QCoreApplication.translate("Ctx", "src")
# avec des littéraux : on inline plutôt que d'aliaser (voir bug_report.py).


class Planificateur:
    def __init__(self, config) -> None:
        self.config = config

    # -- état ---------------------------------------------------------------- #

    def derniere(self) -> datetime | None:
        try:
            return datetime.fromisoformat(self.config.derniere_execution)
        except (ValueError, TypeError):
            return None

    def prochaine(self) -> datetime | None:
        """Date de la prochaine mise à jour, ou None en mode manuel."""
        if not self.config.intervalle_heures:
            return None
        derniere = self.derniere()
        if derniere is None:
            return datetime.now()      # jamais exécuté : dès que possible
        return derniere + timedelta(hours=self.config.intervalle_heures)

    def echeance_atteinte(self) -> bool:
        prochaine = self.prochaine()
        return prochaine is not None and datetime.now() >= prochaine

    def marquer_execution(self) -> None:
        self.config.derniere_execution = datetime.now().isoformat(timespec="seconds")
        self.config.sauver()

    # -- affichage ----------------------------------------------------------- #

    def texte_prochaine(self) -> str:
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
        return QCoreApplication.translate(
            "Planificateur", "Prochaine mise à jour dans {delai} ({date})").format(
            delai=delai, date=f"{prochaine:%d/%m à %H:%M}")
