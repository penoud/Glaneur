"""Chemin du cache API d'un run.

API cache: max date of media seen, titles of resolved galleries.
Speeds up subsequent runs — the manifest says what has been downloaded,
the cache says what has been asked of the API to avoid asking again.
"""

from __future__ import annotations

from pathlib import Path


def chemin_cache(dossier: Path) -> Path:
    """Chemin du fichier cache (``.cache.json``) à l'intérieur de ``dossier``.

    Args:
        dossier: Répertoire cible du run.

    Returns:
        Le chemin absolu du cache. Le fichier peut ne pas exister.
    """
    return dossier / ".cache.json"
