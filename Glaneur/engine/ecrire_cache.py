"""Écriture atomique du cache API d'un run."""

from __future__ import annotations

import json
from pathlib import Path

from .chemin_cache import chemin_cache


def ecrire_cache(dossier: Path, cache: dict) -> None:
    """Écrit le cache de façon atomique (fichier temporaire + rename).

    Args:
        dossier: Répertoire cible du run. Créé s'il n'existe pas.
        cache: Dictionnaire sérialisable en JSON à persister.
    """
    chemin = chemin_cache(dossier)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    tmp = chemin.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=1)
    tmp.replace(chemin)
