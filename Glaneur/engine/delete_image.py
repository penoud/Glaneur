"""Disk delete + manifest mark of a downloaded image."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from ._locks import _MANIFESTE_LOCK
from .read_manifest import lire_manifeste
from .write_manifest import ecrire_manifeste


def supprimer_image(dossier: Path, fichier: Path) -> bool:
    """Delete ``fichier`` from disk and set the ``supprime`` mark in the manifest.

    Without this mark, the next update would see the image missing and
    re-download it: deleting on disk alone is not enough.

    Refuses if ``fichier`` is not inside ``dossier`` — a function that
    deletes must not trust its caller. The comparison goes through
    ``realpath`` + ``normcase`` and then ``commonpath``, never through
    ``startswith`` which would match a sibling folder with an identical
    prefix.

    Args:
        dossier: Target directory of the run (run root).
        fichier: Absolute path of the file to delete.

    Returns:
        ``True`` if the file was deleted (or already missing) and the
        manifest possibly marked, ``False`` if the file is outside
        ``dossier`` or if the unlink failed.
    """
    try:
        base = os.path.normcase(os.path.realpath(str(dossier)))
        cible = os.path.normcase(os.path.realpath(str(fichier)))
    except OSError:
        return False
    try:
        commun = os.path.commonpath([base, cible])
    except ValueError:
        return False   # different drives on Windows
    if commun != base or cible == base:
        return False

    # Relative path to compare against manifest entries. A manifest written
    # on Windows contains backslashes; we normalize both forms to a common
    # separator before `normcase`.
    try:
        relatif = os.path.relpath(cible, base)
    except ValueError:
        return False
    aiguille = os.path.normcase(relatif.replace("\\", "/"))

    with _MANIFESTE_LOCK:
        manifeste = lire_manifeste(dossier)
        ident_trouve: str | None = None
        for ident, etat in manifeste.items():
            stocke = etat.get("fichier")
            if not stocke:
                continue
            if os.path.normcase(str(stocke).replace("\\", "/")) == aiguille:
                ident_trouve = ident
                break

        try:
            Path(fichier).unlink()
        except FileNotFoundError:
            pass   # already gone: the mark is set anyway
        except OSError:
            return False

        if ident_trouve is not None:
            entree = manifeste[ident_trouve]
            entree["supprime"] = datetime.now().isoformat(timespec="seconds")
            entree.pop("restaure", None)
            ecrire_manifeste(dossier, manifeste)
    return True
