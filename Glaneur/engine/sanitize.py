"""Turn an HTML title into a safe folder name."""

from __future__ import annotations

import html
import re
import unicodedata


def nettoyer(titre: str, defaut: str = "divers") -> str:
    """Turn an HTML title into a folder name safe on every OS.

    Decodes HTML entities, transliterates to ASCII, replaces spaces with
    dashes, caps at 80 characters and strips characters rejected by
    Windows.

    Args:
        titre: Source title, possibly with HTML entities or accents.
        defaut: Value returned when the cleaned title is empty.

    Returns:
        A string usable as a folder name on Windows, macOS and Linux.
    """
    texte = html.unescape(titre or "").strip()
    texte = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode("ascii")
    texte = re.sub(r"[^\w\s-]", "", texte).strip()
    texte = re.sub(r"[\s_]+", "-", texte).lower()
    texte = texte.strip(".-")            # Windows rejects names ending with a dot
    return texte[:80] or defaut
