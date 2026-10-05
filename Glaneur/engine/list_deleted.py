"""List of images marked ``deleted`` in the manifest."""

from __future__ import annotations

from pathlib import Path

from .read_manifest import read_manifest


def list_deleted(dossier: Path) -> list[dict]:
    """Images downloaded then deleted from disk by the user.

    Args:
        dossier: Target directory of the run.

    Returns:
        The manifest entries carrying the ``deleted`` mark, sorted by
        deletion timestamp then by file name.
    """
    manifeste = read_manifest(dossier)
    entrees = [{"id": ident, **etat} for ident, etat in manifeste.items()
               if etat.get("deleted")]
    entrees.sort(key=lambda e: (e.get("deleted", ""), e.get("filename", "")))
    return entrees
