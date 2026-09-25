"""Installation du traducteur Qt au démarrage.

Politique : la langue source dans le code est le français. Les traductions
sont compilées depuis `translations/wpimagedownloader_<code>.ts` vers
`.qm` par `pyside6-lrelease`. Le choix se fait au lancement, avant la
construction de la fenêtre — pas de changement à chaud (voir la décision
d'i18n dans le README §4).

- Aucune langue configurée -> locale système (`en_US` -> `en`, etc.).
- Langue = "fr" ou traduction absente -> les chaînes affichent la source FR.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtCore import QLocale, QTranslator

LANGUES_DISPONIBLES: dict[str, str] = {
    # code ISO -> libellé natif à afficher dans les préférences
    "fr": "Français",
    "en": "English",
}

logger = logging.getLogger(__name__)

_translator: QTranslator | None = None


def dossier_traductions() -> Path:
    """Cherche `translations/` d'abord dans le bundle PyInstaller (`_MEIPASS`),
    puis en dev (racine du dépôt à côté du paquet).

    Ordre important : dans un bundle, `__file__` pointe dans le PYZ zip
    (`.parent.parent` ne mène nulle part d'utile), donc `_MEIPASS` doit
    passer en premier. En dev, `_MEIPASS` n'existe pas, on retombe sur
    la racine du dépôt."""
    candidats = [
        Path(getattr(sys, "_MEIPASS", "")) / "translations" if hasattr(sys, "_MEIPASS") else None,
        Path(__file__).resolve().parent.parent / "translations",
    ]
    for c in candidats:
        if c is not None and c.is_dir():
            return c
    return candidats[-1]


def resoudre_langue(langue_configuree: str) -> str:
    """Renvoie le code de langue effectif : la config si non vide, sinon
    la locale système (ex. `fr_CH` -> `fr`)."""
    if langue_configuree:
        return langue_configuree
    return QLocale.system().name().split("_")[0] or "fr"


def installer_traducteur(app, langue_configuree: str = "") -> str:
    """Charge le .qm correspondant et l'installe sur `app`. Renvoie le code
    de langue effectivement actif (peut différer si la traduction demandée
    n'existe pas — on tombe alors sur la source FR)."""
    global _translator
    langue = resoudre_langue(langue_configuree)
    dossier = dossier_traductions()
    logger.info("i18n : langue=%s dossier=%s existe=%s",
                langue, dossier, dossier.is_dir())
    if langue == "fr":
        return "fr"
    _translator = QTranslator()
    fichier = f"glaneur_{langue}"
    if _translator.load(fichier, str(dossier)):
        app.installTranslator(_translator)
        logger.info("i18n : traduction %s chargée depuis %s", fichier, dossier)
        return langue
    logger.warning("i18n : traduction %s introuvable dans %s — retombe sur FR",
                   fichier, dossier)
    _translator = None
    return "fr"
