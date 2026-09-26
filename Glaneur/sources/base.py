"""Contrat des adaptateurs de source : Element, Source, Transport.

Le moteur ne connaît que ces trois classes. Une source (WordPress,
Djangoplicity…) traduit un site en `Element` normalisés que le moteur
sait consommer sans savoir d'où ils viennent.
"""

from __future__ import annotations

import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, ClassVar, Iterator, Mapping

import requests

UA = "Mozilla/5.0 (compatible; Glaneur/1.0)"


class Interrompu(Exception):
    """Levée quand l'utilisateur demande l'arrêt coopératif.

    Portée par le transport et propagée jusqu'au moteur, qui la traite
    comme une fin normale (voir :attr:`Glaneur.engine.resultat.Resultat.interrompu`).
    """


@dataclass(frozen=True)
class Element:
    """Une image à synchroniser, telle que le moteur la comprend.

    Champs documentés inline par commentaires ``#:`` — voir
    :class:`Glaneur.engine.options.Options` pour la raison (éviter le doublon
    d'index entre autodoc et Napoleon).
    """

    #: Unique identifier within the source, key of the manifest. String,
    #: to accept both WordPress integers and the alphanumeric identifiers
    #: from Djangoplicity.
    ident: str
    #: URL of the resource to download. ``None`` if the source did not
    #: find a resource for the requested format: the engine will count
    #: the element in :attr:`Glaneur.engine.resultat.Resultat.ignorees`.
    url: str | None
    #: File name to give the resource on disk, without directory.
    nom_fichier: str
    #: Publication date in ISO format, if known.
    date: str | None = None
    #: ``YYYY-MM`` month extracted from the date, used for the
    #: by-date sort.
    mois: str | None = None
    #: Width in pixels, when the source provides it — used by the
    #: :attr:`Glaneur.engine.options.Options.largeur_min` filter.
    largeur: int | None = None
    #: File size in bytes, if announced by the source (allows
    #: :meth:`Glaneur.engine.moteur.Moteur.fichier_complet` to validate).
    taille: int | None = None
    #: Parent identifier (WordPress gallery, Djangoplicity collection)
    #: for the ``galerie`` sort mode.
    groupe: str | None = None
    #: Free-form metadata passed through to the manifest (credit,
    #: checksum…). The engine does not interpret them.
    extra: dict = field(default_factory=dict)


class Transport:
    """Plomberie HTTP partagée : une session, un délai, un arrêt.

    Une source ne crée jamais sa propre session : elle reçoit ce transport
    du moteur, ce qui garantit qu'un plancher de délai et l'arrêt coopératif
    s'appliquent à toutes les sources sans qu'un adaptateur puisse l'oublier.
    """

    def __init__(self, delai: float, arret: threading.Event | None = None) -> None:
        """Construit le transport avec sa session et son plancher de délai.

        Args:
            delai: Plancher de pause entre deux requêtes, en secondes.
            arret: Event partagé qui coupe les requêtes en cours. Créé à
                la demande si non fourni.
        """
        self.delai = delai
        self.arret = arret or threading.Event()
        self.session = requests.Session()
        self.session.headers["User-Agent"] = UA

    def verifier_arret(self) -> None:
        """Lève :class:`Interrompu` si ``self.arret`` a été positionné.

        Raises:
            Interrompu: Si l'arrêt coopératif est demandé.
        """
        if self.arret.is_set():
            raise Interrompu()

    def pause(self, secondes: float | None = None) -> None:
        """Attente fractionnée réagissant vite à une demande d'arrêt.

        Args:
            secondes: Durée à attendre. Utilise ``self.delai`` si ``None``.

        Raises:
            Interrompu: Si l'arrêt coopératif est demandé pendant
                l'attente.
        """
        fin = time.monotonic() + (self.delai if secondes is None else secondes)
        while time.monotonic() < fin:
            self.verifier_arret()
            time.sleep(min(0.1, max(0.0, fin - time.monotonic())))

    def get_json(
        self,
        url: str,
        params: dict | None = None,
        essais: int = 3,
        fin_si: frozenset[int] = frozenset(),
    ) -> tuple[object | None, Mapping]:
        """GET JSON avec rejeux.

        Un code de ``fin_si`` est traité comme une fin normale : le
        résultat est ``(None, en-têtes)`` sans lever d'exception.
        WordPress passe ``fin_si={400}`` pour dire « page au-delà de la
        dernière ».

        Args:
            url: URL absolue à requêter.
            params: Paramètres de la requête, passés à ``requests``.
            essais: Nombre maximum de tentatives (backoff linéaire :
                2s, 4s, 6s…).
            fin_si: Codes HTTP à interpréter comme fin normale.

        Returns:
            Tuple ``(données, en-têtes)``. ``données`` vaut ``None``
            quand le code de réponse est dans ``fin_si``.

        Raises:
            RuntimeError: Après épuisement des ``essais`` sans succès.
            Interrompu: Si l'arrêt coopératif est demandé.
        """
        derniere: Exception | None = None
        for tentative in range(essais):
            self.verifier_arret()
            try:
                r = self.session.get(url, params=params, timeout=30)
                if r.status_code in fin_si:
                    return None, r.headers
                r.raise_for_status()
                return r.json(), r.headers
            except requests.RequestException as e:
                derniere = e
                self.pause(2 * (tentative + 1))
        raise RuntimeError(f"L'API ne répond pas ({derniere})")


class Source(ABC):
    """Adaptateur d'un type de site vers des `Element`.

    Un adaptateur reçoit sa base (URL du site), le transport partagé, ses
    réglages (dictionnaire libre — l'adaptateur y trouve par exemple le
    format d'image choisi) et un callback de progression pour ses phases
    d'inventaire longues.
    """

    type: ClassVar[str]
    classements: ClassVar[frozenset[str]]

    def __init__(
        self,
        base: str,
        transport: Transport,
        reglages: dict,
        journal: Callable[[str], None] | None = None,
        progression: Callable[[int, int, str], None] | None = None,
    ) -> None:
        """Instancie l'adaptateur avec son transport partagé.

        Args:
            base: URL du site source, sans slash final.
            transport: :class:`Transport` fourni par le moteur.
            reglages: Dictionnaire libre (par exemple
                ``{"format_image": "Large"}`` pour Djangoplicity).
            journal: Callback texte pour messages destinés à
                l'utilisateur. ``None`` = muet.
            progression: Callback ``(fait, total, etiquette)`` pour les
                phases longues d'inventaire. ``None`` = muet.
        """
        self.base = base.rstrip("/")
        self.transport = transport
        self.reglages = reglages or {}
        self._journal = journal or (lambda msg: None)
        self._progression = progression or (lambda fait, total, etiquette: None)

    @abstractmethod
    def inventaire(
        self, depuis: str | None, jusqua: str | None,
    ) -> Iterator[Element]:
        """Parcourt le catalogue dans l'ordre chronologique si possible.

        Args:
            depuis: Borne basse au format propre à la source
                (voir :meth:`convertir_depuis`). ``None`` = pas de borne.
            jusqua: Borne haute. ``None`` = pas de borne.

        Yields:
            Les :class:`Element` inventoriés, dans l'ordre chronologique
            quand la source le permet.
        """

    def resoudre_groupes(
        self, cles: set[str], connus: dict[str, str] | None = None,
    ) -> dict[str, str]:
        """Résout les identifiants de groupe en noms de dossier.

        Implémentation par défaut : renvoie ``connus`` tel quel — aucun
        regroupement supplémentaire. Les sources qui exposent un
        classement ``galerie`` (voir :attr:`classements`) surchargent
        pour requêter les titres manquants.

        Args:
            cles: Identifiants de groupe à résoudre.
            connus: Table déjà résolue (par exemple par le cache).

        Returns:
            Table ``{clé -> titre nettoyé}``, prête à être passée à
            :meth:`Glaneur.engine.moteur.Moteur.dossier_pour`.
        """
        return dict(connus or {})

    def convertir_depuis(self, iso: str | None) -> str | None:
        """Traduit une date ISO du cache vers le format attendu par la source.

        Par défaut, on laisse tel quel : les sources qui, comme
        Djangoplicity, veulent ``AAAAMMJJhhmmss`` la surchargent.

        Args:
            iso: Date au format ISO 8601, ou ``None``.

        Returns:
            La date convertie ou ``None``.
        """
        return iso
