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

import sys
from pathlib import Path

from PySide6.QtCore import QLocale, QTranslator

LANGUES_DISPONIBLES: dict[str, str] = {
    # code ISO -> libellé natif à afficher dans les préférences
    "fr": "Français",
    "en": "English",
}

_translator: QTranslator | None = None


def dossier_traductions() -> Path:
    """Cherche `translations/` en dev (racine du dépôt) et dans le bundle
    PyInstaller (`sys._MEIPASS`)."""
    candidats = [
        Path(__file__).resolve().parent.parent / "translations",
        Path(getattr(sys, "_MEIPASS", ".")) / "translations",
    ]
    for c in candidats:
        if c.is_dir():
            return c
    return candidats[0]


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
    if langue == "fr":
        return "fr"
    _translator = QTranslator()
    fichier = f"wpimagedownloader_{langue}"
    if _translator.load(fichier, str(dossier_traductions())):
        app.installTranslator(_translator)
        return langue
    _translator = None
    return "fr"
