"""Restore entries marked ``supprime``."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from ._verrous import _MANIFESTE_LOCK
from .ecrire_manifeste import ecrire_manifeste
from .lire_manifeste import lire_manifeste


def restaurer(dossier: Path, ids: Iterable) -> int:
    """Clear the delete mark so these images re-enter the queue.

    The ``restaure`` mark stays in place until the next successful
    download, so that a network failure does not immediately reclassify
    the image as "deleted".

    Args:
        dossier: Target directory of the run.
        ids: Source-side identifiers to restore.

    Returns:
        The number of entries actually restored.
    """
    with _MANIFESTE_LOCK:
        manifeste = lire_manifeste(dossier)
        retablies = 0
        for ident in ids:
            etat = manifeste.get(str(ident))
            if etat and etat.pop("supprime", None):
                # the mark only clears on a successful download, which rewrites
                # the entry: a network failure will not reclassify the image as "deleted"
                etat["restaure"] = True
                retablies += 1
        if retablies:
            ecrire_manifeste(dossier, manifeste)
    return retablies
