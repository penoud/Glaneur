"""Restauration d'entrées marquées ``supprime``."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from ._verrous import _MANIFESTE_LOCK
from .ecrire_manifeste import ecrire_manifeste
from .lire_manifeste import lire_manifeste


def restaurer(dossier: Path, ids: Iterable) -> int:
    """Lève la marque de suppression : ces images repasseront dans la file.

    La marque ``restaure`` reste posée jusqu'au prochain téléchargement
    réussi, pour qu'un échec réseau ne reclasse pas immédiatement l'image
    en « supprimée ».

    Args:
        dossier: Répertoire cible du run.
        ids: Identifiants (au sens de la source) à restaurer.

    Returns:
        Le nombre d'entrées effectivement rétablies.
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
