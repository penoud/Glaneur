"""Atomic write of the manifest of a run."""

from __future__ import annotations

import json
from pathlib import Path

from .manifest_path import chemin_manifeste


def ecrire_manifeste(dossier: Path, manifeste: dict) -> None:
    """Write the manifest atomically (temp file + rename).

    The manifest is saved every 25 images during a run: the atomic write
    prevents an interruption from leaving a truncated file in place.

    Args:
        dossier: Target directory of the run. Created if it does not exist.
        manifeste: JSON-serialisable dictionary to persist.
    """
    chemin = chemin_manifeste(dossier)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    tmp = chemin.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(manifeste, f, ensure_ascii=False, indent=1)
    tmp.replace(chemin)
