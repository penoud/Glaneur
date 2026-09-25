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

UA = "Mozilla/5.0 (compatible; WpImageDownloader/1.0)"


class Interrompu(Exception):
    """Levée quand l'utilisateur demande l'arrêt."""


@dataclass(frozen=True)
class Element:
    """Une image à synchroniser, telle que le moteur la comprend.

    - `ident` est unique au sein de la source et sert de clé au manifeste ;
      c'est une chaîne pour accepter aussi bien les entiers WordPress que
      les identifiants alphanumériques de Djangoplicity.
    - `url` peut être `None` si la source n'a pas trouvé de ressource pour
      le format demandé ; le moteur comptera alors l'élément en `ignoree`.
    """
    ident: str
    url: str | None
    nom_fichier: str
    date: str | None = None
    mois: str | None = None
    largeur: int | None = None
    taille: int | None = None
    groupe: str | None = None
    extra: dict = field(default_factory=dict)


class Transport:
    """Plomberie HTTP partagée : une session, un délai, un arrêt.

    Une source ne crée jamais sa propre session : elle reçoit ce transport
    du moteur, ce qui garantit qu'un plancher de délai et l'arrêt coopératif
    s'appliquent à toutes les sources sans qu'un adaptateur puisse l'oublier.
    """

    def __init__(self, delai: float, arret: threading.Event | None = None) -> None:
        self.delai = delai
        self.arret = arret or threading.Event()
        self.session = requests.Session()
        self.session.headers["User-Agent"] = UA

    def verifier_arret(self) -> None:
        if self.arret.is_set():
            raise Interrompu()

    def pause(self, secondes: float | None = None) -> None:
        """Attente fractionnée, pour réagir vite à une demande d'arrêt."""
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
        """GET JSON avec rejeux ; renvoie (données, en-têtes).

        Un code de `fin_si` est traité comme une fin normale : le résultat
        est `(None, en-têtes)` sans lever d'exception. WordPress passe
        `fin_si={400}` pour dire « page au-delà de la dernière ».
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
        self.base = base.rstrip("/")
        self.transport = transport
        self.reglages = reglages or {}
        self._journal = journal or (lambda msg: None)
        self._progression = progression or (lambda fait, total, etiquette: None)

    @abstractmethod
    def inventaire(
        self, depuis: str | None, jusqua: str | None,
    ) -> Iterator[Element]:
        """Parcourt le catalogue dans l'ordre chronologique si possible."""

    def resoudre_groupes(
        self, cles: set[str], connus: dict[str, str] | None = None,
    ) -> dict[str, str]:
        """Clé de groupe → nom de dossier. Par défaut : aucun regroupement."""
        return dict(connus or {})

    def convertir_depuis(self, iso: str | None) -> str | None:
        """Traduit une date ISO du cache vers le format attendu par la source.

        Par défaut, on laisse tel quel : les sources qui, comme
        Djangoplicity, veulent `AAAAMMJJhhmmss` la surchargent.
        """
        return iso
