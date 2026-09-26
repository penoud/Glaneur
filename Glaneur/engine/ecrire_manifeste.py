"""Écriture atomique du manifeste d'un run."""

from __future__ import annotations

import json
from pathlib import Path

from .chemin_manifeste import chemin_manifeste


def ecrire_manifeste(dossier: Path, manifeste: dict) -> None:
    """Écrit le manifeste de façon atomique (fichier temporaire + rename).

    Le manifeste est sauvegardé toutes les 25 images pendant un run :
    l'écriture atomique évite qu'une interruption ne laisse un fichier
    tronqué en place.

    Args:
        dossier: Répertoire cible du run. Créé s'il n'existe pas.
        manifeste: Dictionnaire sérialisable en JSON à persister.
    """
    chemin = chemin_manifeste(dossier)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    tmp = chemin.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(manifeste, f, ensure_ascii=False, indent=1)
    tmp.replace(chemin)
