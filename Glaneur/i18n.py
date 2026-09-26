"""Install the Qt translator at startup.

Policy: the source language in the code is French. Translations are
compiled from ``translations/glaneur_<code>.ts`` to ``.qm`` by
``pyside6-lrelease``. The choice is made at launch, before the window is
built — no hot swap (see the i18n decision in the README §4).

- No configured language -> system locale (``en_US`` -> ``en``, etc.).
- Language = "fr" or translation missing -> UI shows the French source.
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
    """Locate the ``translations/`` folder depending on the run mode.

    Order matters: inside a PyInstaller bundle ``__file__`` points into
    the PYZ zip (``.parent.parent`` leads nowhere useful), so
    ``sys._MEIPASS`` must be tried first. In dev, ``_MEIPASS`` does not
    exist and we fall back to the repository root next to the package.

    Returns:
        The first existing path, or the default path (repository root)
        if no candidate exists.
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
    """Return the effective language code to apply.

    Args:
        langue_configuree: Code stored in the configuration (``fr``,
            ``en``, ``""``, ...).

    Returns:
        The configured code if not empty, otherwise the short code of
        the system locale (for example ``fr_CH`` -> ``fr``), with
        ``fr`` as a last resort.
    """
    if langue_configuree:
        return langue_configuree
    return QLocale.system().name().split("_")[0] or "fr"


def installer_traducteur(app, langue_configuree: str = "") -> str:
    """Load the matching ``.qm`` and install it on ``app``.

    Installation happens before the main window is built: there is no
    hot language change (deliberate constraint, see the i18n decision
    in the README §4).

    Args:
        app: ``QCoreApplication`` (typically a ``QApplication``) to
            equip with a translator.
        langue_configuree: Desired code, ``""`` to let
            :func:`resoudre_langue` decide.

    Returns:
        The language code actually active after the call. May differ
        from the request when the translation is missing: we fall back
        on the French source in that case.
    """
    global _translator
    langue = resoudre_langue(langue_configuree)
    dossier = dossier_traductions()
    logger.info("i18n: language=%s folder=%s exists=%s",
                langue, dossier, dossier.is_dir())
    if langue == "fr":
        return "fr"
    _translator = QTranslator()
    fichier = f"glaneur_{langue}"
    if _translator.load(fichier, str(dossier)):
        app.installTranslator(_translator)
        logger.info("i18n: translation %s loaded from %s", fichier, dossier)
        return langue
    logger.warning("i18n: translation %s not found in %s — falling back to FR",
                   fichier, dossier)
    _translator = None
    return "fr"
