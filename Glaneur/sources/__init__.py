"""Adaptateurs de source pour le téléchargeur.

Le registre est un dictionnaire importé statiquement : PyInstaller voit les
modules à l'analyse et rien n'est chargé par découverte dynamique.
"""

from __future__ import annotations

from typing import Type

from .base import Element, Interrompu, Source, Transport
from .djangoplicity import Djangoplicity
from .wordpress import WordPress

SOURCES: dict[str, Type[Source]] = {
    WordPress.type: WordPress,
    Djangoplicity.type: Djangoplicity,
}


def classements_pour(type_source: str) -> frozenset[str]:
    """Ensemble de classements supportés par un type de source.

    Renvoyer un `frozenset` vide plutôt que lever pour un type inconnu :
    l'UI grise alors tout, sans planter.
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
