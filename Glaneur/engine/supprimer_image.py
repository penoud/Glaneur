"""Suppression disque + marque manifeste d'une image téléchargée."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from ._verrous import _MANIFESTE_LOCK
from .ecrire_manifeste import ecrire_manifeste
from .lire_manifeste import lire_manifeste


def supprimer_image(dossier: Path, fichier: Path) -> bool:
    """Efface ``fichier`` du disque et pose la marque ``supprime`` dans le manifeste.

    Sans cette marque, la mise à jour suivante verrait l'image manquante
    et la retéléchargerait : la suppression disque seule ne suffit pas.

    Refuse si ``fichier`` n'est pas à l'intérieur de ``dossier`` — une
    fonction qui efface ne fait pas confiance à son appelant. La
    comparaison passe par ``realpath`` + ``normcase`` puis ``commonpath``,
    jamais par ``startswith`` qui matcherait un dossier voisin de préfixe
    identique.

    Args:
        dossier: Répertoire cible du run (racine du run).
        fichier: Chemin absolu du fichier à effacer.

    Returns:
        ``True`` si le fichier a été effacé (ou déjà absent) et le
        manifeste éventuellement marqué, ``False`` si le fichier est hors
        de ``dossier`` ou si l'unlink a échoué.
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
