"""Adaptateurs de source pour le téléchargeur.

Le registre est un dictionnaire importé statiquement : PyInstaller voit les
modules à l'analyse et rien n'est chargé par découverte dynamique.
"""

from __future__ import annotations

from typing import Type

from .base import Element, Interrompu, Source, Transport
from .djangoplicity import Djangoplicity
from .wordpress import WordPress

#: Registre des adaptateurs de source disponibles. Clé : le libellé porté
#: par la classe (:attr:`Source.type`), valeur : la classe elle-même.
SOURCES: dict[str, Type[Source]] = {
    WordPress.type: WordPress,
    Djangoplicity.type: Djangoplicity,
}


def classements_pour(type_source: str) -> frozenset[str]:
    """Renvoie l'ensemble des classements supportés par un type de source.

    Renvoyer un ``frozenset`` vide plutôt que lever pour un type inconnu :
    l'UI grise alors tout, sans planter.

    Args:
        type_source: Clé de ``Glaneur.sources.SOURCES``.

    Returns:
        Les classements supportés (par exemple
        ``frozenset({"galerie", "date", "plat"})``), ou un frozenset vide
        si ``type_source`` n'est pas enregistré.
    """
    classe = SOURCES.get(type_source)
    return classe.classements if classe else frozenset()


__all__ = [
    "Element",
    "Interrompu",
    "Source",
    "Transport",
    "SOURCES",
    "classements_pour",
]
