"""Lecture tolérante du manifeste d'un run."""

from __future__ import annotations

import json
from pathlib import Path

from .chemin_manifeste import chemin_manifeste


def lire_manifeste(dossier: Path) -> dict:
    """Charge le manifeste JSON s'il existe, dictionnaire vide sinon.

    Un manifeste corrompu ou illisible est traité comme absent : le
    prochain run repartira d'un état vide plutôt que de planter.

    Args:
        dossier: Répertoire cible du run.

    Returns:
        Le contenu désérialisé, ou ``{}`` si le fichier est absent ou
        illisible.
    """
    chemin = chemin_manifeste(dossier)
    if not chemin.exists():
        return {}
    try:
        with open(chemin, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}
