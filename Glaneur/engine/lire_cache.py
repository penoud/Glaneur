"""Tolerant read of the API cache of a run."""

from __future__ import annotations

import json
from pathlib import Path

from .chemin_cache import chemin_cache


def lire_cache(dossier: Path) -> dict:
    """Load the JSON cache if present, an empty dict otherwise.

    Like :func:`Glaneur.engine.lire_manifeste`, tolerates a missing or
    corrupted cache.

    Args:
        dossier: Target directory of the run.

    Returns:
        The deserialised content, or ``{}`` if the file is missing or
        unreadable.
    """
    chemin = chemin_cache(dossier)
    if not chemin.exists():
        return {}
    try:
        with open(chemin, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}
