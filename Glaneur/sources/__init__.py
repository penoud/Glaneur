"""Source adapters for the downloader.

The registry is a statically imported dictionary: PyInstaller sees every
module at analysis time and nothing is loaded through dynamic discovery.
"""

from __future__ import annotations

from typing import Type

from .base import Element, Interrompu, Source, Transport
from .djangoplicity import Djangoplicity
from .wordpress import WordPress

#: Registry of available source adapters. Key: the label carried by
#: the class (:attr:`Source.type`), value: the class itself.
SOURCES: dict[str, Type[Source]] = {
    WordPress.type: WordPress,
    Djangoplicity.type: Djangoplicity,
}


def classements_pour(type_source: str) -> frozenset[str]:
    """Return the set of sort modes supported by a source type.

    Return an empty ``frozenset`` rather than raising for an unknown
    type: the UI then greys everything out without crashing.

    Args:
        type_source: Key of ``Glaneur.sources.SOURCES``.

    Returns:
        The supported sort modes (for example
        ``frozenset({"galerie", "date", "plat"})``), or an empty frozenset
        if ``type_source`` is not registered.
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
