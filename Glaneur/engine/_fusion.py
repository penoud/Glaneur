"""Fusion des marques UI (``supprime``/``restaure``) avec le manifeste moteur."""

from __future__ import annotations


def _fusionner_marques_ui(memoire: dict, disque: dict) -> dict:
    """Fusionne les marques UI (``supprime``/``restaure``) du disque avec le manifeste du moteur.

    Règle : pour un identifiant présent dans les deux versions, la
    version mémoire du moteur l'emporte — c'est elle qui vient d'être
    mise à jour par le run — sauf pour les marques ``supprime`` et
    ``restaure``. Si le disque porte une de ces marques que la mémoire
    n'a pas, elle provient d'un geste utilisateur postérieur au
    chargement du manifeste par le moteur : elle est réinjectée dans le
    résultat, et la marque opposée éventuellement présente en mémoire
    est écartée (les deux marques sont mutuellement exclusives).

    Les entrées présentes uniquement sur disque (identifiants hors
    inventaire du run courant, par exemple hors filtre de date)
    survivent inchangées. Les entrées présentes uniquement en mémoire
    (nouveaux téléchargements) sont écrites telles quelles.

    Args:
        memoire: Manifeste tel que le moteur l'a en mémoire.
        disque: Manifeste tel qu'il se trouve sur disque au moment
            de la fusion.

    Returns:
        Dictionnaire fusionné, prêt à être écrit atomiquement.
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
