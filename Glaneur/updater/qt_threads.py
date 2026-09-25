"""QThread PySide6 pour le check et le téléchargement de mise à jour.

Extraits d'app.py pour être testables sans démarrer l'UI complète.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QCoreApplication, QThread, Signal

from .. import __version__
from .downloader import download, temporary_directory, verify_sha256
from .github_release import GitHubReleaseProvider
from .version import Version

logger = logging.getLogger(__name__)


class VerificationMiseAJour(QThread):
    """Interroge GitHub à propos d'une release plus récente que la version en cours."""

    disponible = Signal(object)
    aucune_maj = Signal(object)
    erreur = Signal(str)

    def __init__(self, parent=None, provider: GitHubReleaseProvider | None = None) -> None:
        super().__init__(parent)
        self._provider = provider or GitHubReleaseProvider()

    def run(self) -> None:
        try:
            info = self._provider.check(Version.parse(__version__))
            if info.is_available:
                logger.info("Update available: %s", info.latest.version)
                self.disponible.emit(info)
            else:
                self.aucune_maj.emit(info)
        except Exception as error:   # noqa: BLE001 - remontée à l'UI via signal
            logger.exception("Update check failed")
            self.erreur.emit(QCoreApplication.translate(
                "Updater", "Vérification de mise à jour impossible : {erreur}").format(erreur=error))


class TelechargementMiseAJour(QThread):
    """Récupère l'installateur Windows et son SHA-256 pour la release ciblée."""

    termine = Signal(object, str)
    erreur = Signal(str)

    def __init__(self, release, parent=None) -> None:
        super().__init__(parent)
        self.release = release

    def run(self) -> None:
        try:
            installer = self.release.windows_installer()
            checksum = self.release.checksum_for(installer) if installer else None
            if installer is None or checksum is None:
                raise RuntimeError(QCoreApplication.translate(
                    "Updater", "Installateur Windows ou checksum absent de la release"))
            dossier = temporary_directory()
            fichier = download(installer, dossier)
            checksum_path = download(checksum, dossier)
            if not verify_sha256(fichier, checksum_path.read_text(encoding="utf-8")):
                fichier.unlink(missing_ok=True)
                raise RuntimeError(QCoreApplication.translate(
                    "Updater", "Vérification SHA-256 échouée"))
            self.termine.emit(fichier, str(dossier))
        except Exception as error:   # noqa: BLE001 - remontée à l'UI via signal
            logger.exception("Update download failed")
            self.erreur.emit(QCoreApplication.translate(
                "Updater", "Téléchargement de la mise à jour impossible : {erreur}").format(erreur=error))
