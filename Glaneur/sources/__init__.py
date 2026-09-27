"""Source adapters for the downloader.

The registry is a statically imported dictionary: PyInstaller sees every
module at analysis time and nothing is loaded through dynamic discovery.
"""

from __future__ import annotations

from typing import Type

from .base import Element, Interrupted, Source, Transport
from .djangoplicity import Djangoplicity
from .wordpress import WordPress

#: Registry of available source adapters. Key: the label carried by
#: the class (:attr:`Source.type`), value: the class itself.
SOURCES: dict[str, type[Source]] = {
    WordPress.type: WordPress,
    Djangoplicity.type: Djangoplicity,
}


def sort_modes_for(source_type: str) -> frozenset[str]:
    """Return the set of sort modes supported by a source type.

    Return an empty ``frozenset`` rather than raising for an unknown
    type: the UI then greys everything out without crashing.

    Args:
        source_type: Key of ``Glaneur.sources.SOURCES``.

    Returns:
        The supported sort modes (for example
        ``frozenset({"galerie", "date", "plat"})``), or an empty frozenset
        if ``source_type`` is not registered.
    """
    classe = SOURCES.get(source_type)
    return classe.sort_modes if classe else frozenset()


__all__ = [
    "SOURCES",
    "Element",
    "Interrupted",
    "Source",
    "Transport",
    "sort_modes_for",
]
