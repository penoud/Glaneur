"""Path to the manifest file of a run."""

from __future__ import annotations

from pathlib import Path


def chemin_manifeste(dossier: Path) -> Path:
    """Path to the manifest file (``.etat.json``) inside ``dossier``.

    Args:
        dossier: Target directory of the run.

    Returns:
        The absolute manifest path. The file may not exist yet.
    """
    return dossier / ".etat.json"
