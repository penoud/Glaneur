"""Application logging configuration.

A rotating file handler inside the configuration folder, plus a console
(stderr) handler for development. Idempotent: several calls do not
duplicate handlers.
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
_TAG = "wpid.file"


def configure_logging(dossier: Path, debug: bool = False) -> Path:
    """Attach a rotating file handler in ``dossier/logs/app.log``.

    Safe to call multiple times: the file handler is identified by an
    internal tag and is never duplicated.

    Args:
        dossier: Root under which the ``logs/`` sub-folder and the
            ``app.log`` file are created. Created as needed.
        debug: Forces the ``DEBUG`` level. No effect if the environment
            variable ``WPID_DEBUG`` is already set (same behaviour).

    Returns:
        The absolute path of the current log file.
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
