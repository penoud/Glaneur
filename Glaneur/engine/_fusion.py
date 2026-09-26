"""Merge UI marks (``supprime`` / ``restaure``) with the engine manifest."""

from __future__ import annotations


def _fusionner_marques_ui(memoire: dict, disque: dict) -> dict:
    """Merge UI marks (``supprime`` / ``restaure``) from disk into the engine manifest.

    Rule: for an identifier present in both versions, the engine's
    in-memory version wins — it has just been updated by the run — except
    for the ``supprime`` and ``restaure`` marks. If disk carries one of
    these marks and memory does not, it stems from a user action that
    happened after the engine loaded the manifest: it is re-injected into
    the result, and the opposite mark possibly present in memory is
    cleared (the two marks are mutually exclusive).

    Entries present only on disk (identifiers outside the current run's
    inventory, for example excluded by the date filter) survive
    unchanged. Entries present only in memory (new downloads) are
    written as-is.

    Args:
        memoire: Manifest as the engine holds it in memory.
        disque: Manifest as it stands on disk at merge time.

    Returns:
        The merged dictionary, ready to be written atomically.
    """
    fusionne = dict(memoire)
    for ident, etat_disque in disque.items():
        etat_mem = fusionne.get(ident)
        if etat_mem is None:
            # UI touched an ident that was not part of this run's inventory
            fusionne[ident] = etat_disque
            continue
        marque_disque = ("supprime" if "supprime" in etat_disque
                         else "restaure" if "restaure" in etat_disque
                         else None)
        marque_mem = ("supprime" if "supprime" in etat_mem
                      else "restaure" if "restaure" in etat_mem
                      else None)
        if marque_disque and marque_disque != marque_mem:
            # UI acted after the engine loaded this ident: disk mark wins,
            # opposite mark on the memory side is cleared
            resultat = {**etat_mem, marque_disque: etat_disque[marque_disque]}
            autre = "restaure" if marque_disque == "supprime" else "supprime"
            resultat.pop(autre, None)
            fusionne[ident] = resultat
    return fusionne
