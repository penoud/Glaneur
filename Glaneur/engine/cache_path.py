"""Path to the API cache file of a run.

API cache: max date of media seen, titles of resolved galleries. Speeds up
subsequent runs — the manifest says what has been downloaded, the cache
says what has been asked of the API to avoid asking again.
"""

from __future__ import annotations

from pathlib import Path


def chemin_cache(dossier: Path) -> Path:
    """Path to the cache file (``.cache.json``) inside ``dossier``.

    Args:
        dossier: Target directory of the run.

    Returns:
        The absolute cache path. The file may not exist yet.
    """
    return dossier / ".cache.json"
