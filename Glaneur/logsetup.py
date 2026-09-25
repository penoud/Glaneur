"""Configuration du logging applicatif.

Un handler fichier avec rotation dans le dossier de configuration, doublé
d'un handler console (stderr) pour le développement. Idempotent : plusieurs
appels ne dupliquent pas les handlers.
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
_TAG = "wpid.file"


def configure_logging(dossier: Path, debug: bool = False) -> Path:
    """Ajoute un handler fichier tournant dans ``dossier/logs/app.log``.

    Sûr à appeler plusieurs fois : le handler fichier est identifié par
    un tag interne et n'est jamais dupliqué.

    Args:
        dossier: Racine où créer le sous-dossier ``logs/`` et le fichier
            ``app.log``. Créé si nécessaire.
        debug: Force le niveau ``DEBUG``. Sans effet si la variable
            d'environnement ``WPID_DEBUG`` est déjà positionnée
            (même comportement).

    Returns:
        Le chemin absolu du fichier de log courant.
    """
    niveau = logging.DEBUG if (debug or os.environ.get("WPID_DEBUG")) else logging.INFO

    racine = logging.getLogger()
    racine.setLevel(niveau)

    log_dir = dossier / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    chemin = log_dir / "app.log"

    if not any(getattr(h, "_wpid_tag", None) == _TAG for h in racine.handlers):
        handler = RotatingFileHandler(
            chemin, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter(FORMAT))
        handler._wpid_tag = _TAG  # type: ignore[attr-defined]
        racine.addHandler(handler)

    return chemin
