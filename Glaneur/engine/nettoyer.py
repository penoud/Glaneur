"""Nettoyage d'un titre HTML en nom de dossier sûr."""

from __future__ import annotations

import html
import re
import unicodedata


def nettoyer(titre: str, defaut: str = "divers") -> str:
    """Transforme un titre HTML en nom de dossier sûr sur tous les systèmes.

    Décode les entités HTML, translittère en ASCII, remplace les espaces
    par des tirets, borne à 80 caractères et retire les caractères refusés
    par Windows.

    Args:
        titre: Titre source, éventuellement avec entités HTML ou accents.
        defaut: Valeur renvoyée si le titre nettoyé est vide.

    Returns:
        Une chaîne utilisable comme nom de dossier sur Windows, macOS et
        Linux.
    """
    texte = html.unescape(titre or "").strip()
    texte = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode("ascii")
    texte = re.sub(r"[^\w\s-]", "", texte).strip()
    texte = re.sub(r"[\s_]+", "-", texte).lower()
    texte = texte.strip(".-")            # Windows rejects names ending with a dot
    return texte[:80] or defaut
