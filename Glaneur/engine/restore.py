"""Restore entries marked ``supprime``."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from ._locks import _MANIFEST_LOCK
from .read_manifest import read_manifest
from .write_manifest import write_manifest


def restore(dossier: Path, ids: Iterable) -> int:
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
    with _MANIFEST_LOCK:
        manifeste = read_manifest(dossier)
        retablies = 0
        for ident in ids:
            etat = manifeste.get(str(ident))
            if etat and etat.pop("supprime", None):
                # the mark only clears on a successful download, which rewrites
                # the entry: a network failure will not reclassify the image as "deleted"
                etat["restaure"] = True
                retablies += 1
        if retablies:
            write_manifest(dossier, manifeste)
    return retablies
