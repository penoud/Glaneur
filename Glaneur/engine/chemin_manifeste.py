"""Chemin du fichier manifeste d'un run."""

from __future__ import annotations

from pathlib import Path


def chemin_manifeste(dossier: Path) -> Path:
    """Chemin du fichier manifeste (``.etat.json``) à l'intérieur de ``dossier``.

    Args:
        dossier: Répertoire cible du run.

    Returns:
        Le chemin absolu du manifeste. Le fichier peut ne pas exister.
    """
    return dossier / ".etat.json"
