"""Lecture tolérante du cache API d'un run."""

from __future__ import annotations

import json
from pathlib import Path

from .chemin_cache import chemin_cache


def lire_cache(dossier: Path) -> dict:
    """Charge le cache JSON s'il existe, dictionnaire vide sinon.

    Comme :func:`Glaneur.engine.lire_manifeste`, tolère un cache absent
    ou corrompu.

    Args:
        dossier: Répertoire cible du run.

    Returns:
        Le contenu désérialisé, ou ``{}`` si le fichier est absent ou
        illisible.
    """
    chemin = chemin_cache(dossier)
    if not chemin.exists():
        return {}
    try:
        with open(chemin, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}
