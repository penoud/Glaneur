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
from typing import TYPE_CHECKING

from PySide6.QtCore import QCoreApplication

if TYPE_CHECKING:
    from .engine.resultat import Resultat

# lupdate only extracts QCoreApplication.translate("Ctx", "src") calls
# with literals: we inline rather than aliasing (see bug_report.py).

# Backoff exponentiel appliqué quand le serveur n'a pas fourni de
# `Retry-After` : niveau 0 → 1 h, 1 → 2 h, 2 → 4 h. Le niveau est
# incrémenté à chaque report successif et cappé à 2 ; il est remis
# à zéro par :meth:`Planificateur.marquer_execution`.
BACKOFFS_S: tuple[int, ...] = (3600, 7200, 14400)


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

    # -- state --------------------------------------------------------------- #

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

    def _retenter_apres(self) -> datetime | None:
        """Date de reprise après report, ou ``None`` si aucun/mal formé.

        Sert d'unique point de parsing de ``config.retenter_apres`` — au
        moindre doute (chaîne vide, format cassé), on ignore le report
        plutôt que de lever.
        """
        brut = getattr(self.config, "retenter_apres", "") or ""
        if not brut:
            return None
        try:
            return datetime.fromisoformat(brut)
        except (ValueError, TypeError):
            return None

    def _nominale(self) -> datetime | None:
        """Date de la prochaine échéance sans tenir compte d'un report.

        Returns:
            La date brute, ou ``None`` en mode manuel.
        """
        if not self.config.intervalle_heures:
            return None
        derniere = self.derniere()
        if derniere is None:
            return datetime.now()       # never run: as soon as possible
        return derniere + timedelta(hours=self.config.intervalle_heures)

    def prochaine(self) -> datetime | None:
        """Calcule la date de la prochaine mise à jour automatique.

        Si aucun run n'a jamais été enregistré, la « prochaine » est
        l'instant présent : le premier lancement déclenche
        immédiatement.

        Un report actif (``config.retenter_apres`` dans le futur)
        repousse l'échéance nominale jusqu'à cette date.

        Returns:
            La date planifiée, ou ``None`` en mode manuel
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
        ``Config.derniere_execution`` au format ISO 8601 seconde. Remet
        aussi à zéro l'éventuel report en cours (``retenter_apres`` et
        ``backoff_niveau``) : un run qui aboutit clôt un backoff.
        """
        self.config.derniere_execution = datetime.now().isoformat(timespec="seconds")
        self.config.retenter_apres = ""
        self.config.backoff_niveau = 0
        self.config.sauver()

    def differer(self, res: Resultat) -> None:
        """Reporte le prochain run après un coupe-circuit réseau.

        Utilise ``res.retenter_apres`` (aware UTC produit par
        :meth:`Glaneur.engine.moteur.Moteur._declencher_report`) quand
        le serveur a fourni un ``Retry-After`` : la consigne serveur
        prime, et on ne fait pas monter le niveau de backoff. Sans
        consigne serveur, on applique le backoff exponentiel local
        (``BACKOFFS_S`` : 1 h → 2 h → 4 h), puis on incrémente le
        niveau (cappé à 2).

        ``config.retenter_apres`` est toujours écrit en ISO 8601 naïf
        local pour rester comparable à ``Config.derniere_execution``.

        Args:
            res: :class:`Glaneur.engine.resultat.Resultat` d'un run
                terminé avec ``res.reporte = True``.
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
