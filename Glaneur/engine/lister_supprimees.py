"""Liste des images marquées ``supprime`` dans le manifeste."""

from __future__ import annotations

from pathlib import Path

from .lire_manifeste import lire_manifeste


def lister_supprimees(dossier: Path) -> list[dict]:
    """Images téléchargées puis effacées du disque par l'utilisateur.

    Args:
        dossier: Répertoire cible du run.

    Returns:
        Les entrées du manifeste portant la marque ``supprime``, triées
        par date de suppression puis par nom de fichier.
    """
    manifeste = lire_manifeste(dossier)
    entrees = [{"id": ident, **etat} for ident, etat in manifeste.items()
               if etat.get("supprime")]
    entrees.sort(key=lambda e: (e.get("supprime", ""), e.get("fichier", "")))
    return entrees
