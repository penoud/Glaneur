"""Logique d'échéance des mises à jour automatiques.

Volontairement sans thread ni dépendance à Qt : la classe ne fait que répondre
à « est-ce l'heure ? ». C'est l'interface qui l'interroge périodiquement via un
QTimer, ce qui évite un thread de plus et garde tout le déclenchement sur le
thread principal.

L'échéance est calculée à partir de `derniere_execution` stocké dans la
configuration, donc elle survit à une fermeture de l'application : si
l'intervalle s'est écoulé pendant ce temps, la mise à jour part au lancement
suivant.
"""

from __future__ import annotations

from datetime import datetime, timedelta


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
            return "Mise à jour automatique désactivée"
        prochaine = self.prochaine()
        if prochaine is None:
            return "Mise à jour automatique désactivée"
        reste = prochaine - datetime.now()
        if reste.total_seconds() <= 0:
            return "Prochaine mise à jour : imminente"
        heures, secondes = divmod(int(reste.total_seconds()), 3600)
        minutes = secondes // 60
        if heures >= 24:
            jours, heures = divmod(heures, 24)
            delai = f"{jours} j {heures} h"
        elif heures:
            delai = f"{heures} h {minutes:02d} min"
        else:
            delai = f"{minutes} min"
        return f"Prochaine mise à jour dans {delai} ({prochaine:%d/%m à %H:%M})"
