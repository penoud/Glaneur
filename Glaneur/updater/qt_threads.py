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
    """Interroge GitHub à propos d'une release plus récente que la version en cours.

    Signals :

    - ``disponible(UpdateInfo)`` : mise à jour trouvée.
    - ``aucune_maj(UpdateInfo)`` : version courante déjà à jour.
    - ``erreur(str)`` : message localisé prêt à afficher.
    """

    disponible = Signal(object)
    aucune_maj = Signal(object)
    erreur = Signal(str)

    def __init__(self, parent=None, provider: GitHubReleaseProvider | None = None) -> None:
        """Construit le thread avec un fournisseur (injectable pour les tests).

        Args:
            parent: Parent Qt éventuel.
            provider: :class:`GitHubReleaseProvider` à utiliser. Un
                fournisseur par défaut est créé si ``None``.
        """
        super().__init__(parent)
        self._provider = provider or GitHubReleaseProvider()

    def run(self) -> None:
        """Lance le check en arrière-plan et émet le signal correspondant."""
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
    """Récupère l'installateur Windows et son SHA-256 pour la release ciblée.

    Signals :

    - ``termine(Path, str)`` : chemin du fichier vérifié + dossier
      temporaire (que l'UI pourra nettoyer après installation).
    - ``erreur(str)`` : message localisé prêt à afficher.
    """

    termine = Signal(object, str)
    erreur = Signal(str)

    def __init__(self, release, parent=None) -> None:
        """Prépare le téléchargement pour ``release``.

        Args:
            release: :class:`Glaneur.updater.models.Release` à
                télécharger.
            parent: Parent Qt éventuel.
        """
        super().__init__(parent)
        self.release = release

    def run(self) -> None:
        """Télécharge, vérifie SHA-256, émet ``termine`` ou ``erreur``."""
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
