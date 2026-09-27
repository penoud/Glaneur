"""Tolerant read of the API cache of a run."""

from __future__ import annotations

import json
from pathlib import Path

from .cache_path import cache_path


def read_cache(dossier: Path) -> dict:
    """Load the JSON cache if present, an empty dict otherwise.

    Like :func:`Glaneur.engine.read_manifest`, tolerates a missing or
    corrupted cache.

    Args:
        dossier: Target directory of the run.

    Returns:
        The deserialised content, or ``{}`` if the file is missing or
        unreadable.
    """
    chemin = cache_path(dossier)
    if not chemin.exists():
        return {}
    try:
        with open(chemin, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}
