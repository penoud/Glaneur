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
    """Calcule et affiche l'échéance des mises à jour automatiques.

    L'objet est passif : il ne démarre pas de timer, il répond à la
    question « est-ce l'heure ? ». C'est à l'UI de l'interroger
    périodiquement (typiquement via un ``QTimer``).
    """

    def __init__(self, config) -> None:
        """Attache le planificateur à un objet :class:`Glaneur.config.Config`.

        Args:
            config: Instance de configuration dont
                ``Config.derniere_execution`` et
                ``Config.intervalle_heures`` sont lus, et dont
                ``Config.sauver`` est appelé par :meth:`marquer_execution`.
        """
        self.config = config

    # -- état ---------------------------------------------------------------- #

    def derniere(self) -> datetime | None:
        """Date du dernier run, désérialisée depuis la configuration.

        Returns:
            La datetime lue dans ``Config.derniere_execution``, ou
            ``None`` si le champ est vide ou mal formé.
        """
        try:
            return datetime.fromisoformat(self.config.derniere_execution)
        except (ValueError, TypeError):
            return None

    def prochaine(self) -> datetime | None:
        """Calcule la date de la prochaine mise à jour automatique.

        Si aucun run n'a jamais été enregistré, la « prochaine » est
        l'instant présent : le premier lancement déclenche
        immédiatement.

        Returns:
            La date planifiée, ou ``None`` en mode manuel
            (``Config.intervalle_heures`` = 0).
        """
        if not self.config.intervalle_heures:
            return None
        derniere = self.derniere()
        if derniere is None:
            return datetime.now()      # jamais exécuté : dès que possible
        return derniere + timedelta(hours=self.config.intervalle_heures)

    def echeance_atteinte(self) -> bool:
        """Indique si un run automatique devrait démarrer maintenant.

        Returns:
            ``True`` si :meth:`prochaine` est passée, ``False`` sinon
            (mode manuel inclus).
        """
        prochaine = self.prochaine()
        return prochaine is not None and datetime.now() >= prochaine

    def marquer_execution(self) -> None:
        """Enregistre l'instant courant comme dernier run et persiste la config.

        Appelée par le moteur en fin de run réussi. Écrit dans
        ``Config.derniere_execution`` au format ISO 8601 seconde.
        """
        self.config.derniere_execution = datetime.now().isoformat(timespec="seconds")
        self.config.sauver()

    # -- affichage ----------------------------------------------------------- #

    def texte_prochaine(self) -> str:
        """Libellé localisé pour l'utilisateur : « Prochaine mise à jour dans… ».

        Format adapté au reste avant l'échéance : jours + heures au-delà
        de 24 h, heures + minutes au-delà d'une heure, minutes en
        dessous. Renvoie un message dédié en mode manuel ou quand
        l'échéance est déjà passée.

        Returns:
            Un texte prêt à afficher, traduit via
            ``QCoreApplication.translate`` (contexte
            ``"Planificateur"``).
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
        return QCoreApplication.translate(
            "Planificateur", "Prochaine mise à jour dans {delai} ({date})").format(
            delai=delai, date=f"{prochaine:%d/%m à %H:%M}")
