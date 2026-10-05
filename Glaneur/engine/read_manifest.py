"""Tolerant read of the manifest of a run."""

from __future__ import annotations

import json
from pathlib import Path

from .manifest_path import manifest_path

# Legacy manifest key aliases: entries written before US-EN-05 stored
# French keys. On read, translate them so the rest of the engine sees
# the English names. Writes always emit the new keys, so the next
# ``write_manifest`` migrates the file in place.
_MANIFEST_KEY_ALIASES: dict[str, str] = {
    "taille": "size",
    "fichier": "filename",
    "modifie": "modified",
    "supprime": "deleted",
    "restaure": "restored",
}


def _translate_entry(etat: dict) -> dict:
    """Return ``etat`` with every legacy FR key renamed to its EN name.

    Values are copied as-is; only keys are translated. If both the FR
    and EN variant coexist in the same entry (a hybrid file from a
    partial hand-edit or a partial rewrite by a mixed-version Glaneur),
    the EN one wins regardless of insertion order: it is copied first
    unconditionally, and the FR variant is only injected if the EN
    slot is still empty.
    """
    if not isinstance(etat, dict):
        return etat
    traduit: dict = {}
    # Pass 1: copy every EN key as-is (both native EN and non-aliased
    # keys like `etag`, `url`, `extra`).
    for cle, valeur in etat.items():
        if cle not in _MANIFEST_KEY_ALIASES:
            traduit[cle] = valeur
    # Pass 2: translate FR keys, but never overwrite an EN one already
    # written above — the EN one is always the more recent write.
    for cle, valeur in etat.items():
        if cle in _MANIFEST_KEY_ALIASES:
            traduit.setdefault(_MANIFEST_KEY_ALIASES[cle], valeur)
    return traduit


def read_manifest(dossier: Path) -> dict:
    """Load the JSON manifest if present, an empty dict otherwise.

    A corrupted or unreadable manifest is treated as missing: the next run
    starts from an empty state rather than crashing. Every per-entry FR
    key is translated via :data:`_MANIFEST_KEY_ALIASES` so callers only
    ever see the English names.

    Args:
        dossier: Target directory of the run.

    Returns:
        The deserialised content, or ``{}`` if the file is missing or
        unreadable.
    """
    chemin = manifest_path(dossier)
    if not chemin.exists():
        return {}
    try:
        with open(chemin, encoding="utf-8") as f:
            brut = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(brut, dict):
        return {}
    return {ident: _translate_entry(etat) for ident, etat in brut.items()}
