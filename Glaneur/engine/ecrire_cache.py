"""Atomic write of the API cache of a run."""

from __future__ import annotations

import json
from pathlib import Path

from .chemin_cache import chemin_cache


def ecrire_cache(dossier: Path, cache: dict) -> None:
    """Write the cache atomically (temp file + rename).

    Args:
        dossier: Target directory of the run. Created if it does not exist.
        cache: JSON-serialisable dictionary to persist.
    """
    chemin = chemin_cache(dossier)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    tmp = chemin.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=1)
    tmp.replace(chemin)
