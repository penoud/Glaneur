"""Installation du traducteur Qt au démarrage.

Politique : la langue source dans le code est le français. Les traductions
sont compilées depuis `translations/glaneur_<code>.ts` vers
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
    # ISO code -> native label displayed in the preferences
    "fr": "Français",
    "en": "English",
}

logger = logging.getLogger(__name__)

_translator: QTranslator | None = None


def dossier_traductions() -> Path:
    """Localise le dossier ``translations/`` selon le mode d'exécution.

    Ordre important : dans un bundle PyInstaller, ``__file__`` pointe
    dans le PYZ zip (``.parent.parent`` ne mène nulle part d'utile),
    donc ``sys._MEIPASS`` doit passer en premier. En dev, ``_MEIPASS``
    n'existe pas, on retombe sur la racine du dépôt à côté du paquet.

    Returns:
        Le premier chemin existant, ou le chemin par défaut (racine du
        dépôt) si aucun candidat n'existe.
    """
    candidats = [
        Path(getattr(sys, "_MEIPASS", "")) / "translations" if hasattr(sys, "_MEIPASS") else None,
        Path(__file__).resolve().parent.parent / "translations",
    ]
    for c in candidats:
        if c is not None and c.is_dir():
            return c
    return candidats[-1]


def resoudre_langue(langue_configuree: str) -> str:
    """Renvoie le code de langue effectif à appliquer.

    Args:
        langue_configuree: Code stocké dans la configuration (``fr``,
            ``en``, ``""``…).

    Returns:
        Le code configuré s'il n'est pas vide, sinon le code court de
        la locale système (par exemple ``fr_CH`` → ``fr``), avec ``fr``
        comme dernier repli.
    """
    if langue_configuree:
        return langue_configuree
    return QLocale.system().name().split("_")[0] or "fr"


def installer_traducteur(app, langue_configuree: str = "") -> str:
    """Charge le ``.qm`` correspondant et l'installe sur ``app``.

    L'installation est faite avant la construction de la fenêtre
    principale : il n'y a pas de changement de langue à chaud
    (contrainte volontaire, voir la décision d'i18n dans le README §4).

    Args:
        app: ``QCoreApplication`` (typiquement une ``QApplication``) à
            équiper d'un traducteur.
        langue_configuree: Code désiré, ``""`` pour laisser
            :func:`resoudre_langue` décider.

    Returns:
        Le code de langue effectivement actif après appel. Peut
        différer de la demande si la traduction est absente : on
        retombe alors sur la source française.
    """
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
