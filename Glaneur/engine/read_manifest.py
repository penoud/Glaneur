"""Tolerant read of the manifest of a run."""

from __future__ import annotations

import json
from pathlib import Path

from .manifest_path import chemin_manifeste


def lire_manifeste(dossier: Path) -> dict:
    """Load the JSON manifest if present, an empty dict otherwise.

    A corrupted or unreadable manifest is treated as missing: the next run
    starts from an empty state rather than crashing.

    Args:
        dossier: Target directory of the run.

    Returns:
        The deserialised content, or ``{}`` if the file is missing or
        unreadable.
    """
    chemin = chemin_manifeste(dossier)
    if not chemin.exists():
        return {}
    try:
        with open(chemin, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}
