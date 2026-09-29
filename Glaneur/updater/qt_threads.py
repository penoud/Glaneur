"""PySide6 ``QThread`` classes for the update check and download.

Extracted from ``app.py`` so they can be tested without starting the
full UI.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QCoreApplication, QThread, Signal

from .. import __version__
from .downloader import download, temporary_directory, verify_sha256
from .github_release import GitHubReleaseProvider
from .version import Version

logger = logging.getLogger(__name__)


class UpdateCheck(QThread):
    """Ask GitHub whether a release is newer than the running version.

    Signals:

    - ``available(UpdateInfo)``: an update was found.
    - ``up_to_date(UpdateInfo)``: the current version is already up to date.
    - ``error(str)``: localised message ready to display.
    """

    available = Signal(object)
    up_to_date = Signal(object)
    error = Signal(str)

    def __init__(self, parent=None, provider: GitHubReleaseProvider | None = None) -> None:
        """Build the thread with a provider (injectable for tests).

        Args:
            parent: Optional Qt parent.
            provider: :class:`GitHubReleaseProvider` to use. A default
                provider is created if ``None``.
        """
        super().__init__(parent)
        self._provider = provider or GitHubReleaseProvider()

    def run(self) -> None:
        """Run the check in the background and emit the matching signal."""
        try:
            info = self._provider.check(Version.parse(__version__))
            if info.is_available:
                logger.info("Update available: %s", info.latest.version)
                self.available.emit(info)
            else:
                self.up_to_date.emit(info)
        except Exception as error:
            logger.exception("Update check failed")
            self.error.emit(QCoreApplication.translate(
                "Updater", "Update check failed: {error}").format(error=error))


class UpdateDownload(QThread):
    """Fetch the Windows installer and its SHA-256 for the targeted release.

    Signals:

    - ``completed(Path, str)``: path of the verified file + temporary
      directory (the UI can clean it after installation). Named
      ``completed`` rather than ``finished`` to avoid overriding
      :attr:`QThread.finished` from the base class.
    - ``error(str)``: localised message ready to display.
    """

    completed = Signal(object, str)
    error = Signal(str)

    def __init__(self, release, parent=None) -> None:
        """Prepare the download for ``release``.

        Args:
            release: :class:`Glaneur.updater.models.Release` to download.
            parent: Optional Qt parent.
        """
        super().__init__(parent)
        self.release = release

    def run(self) -> None:
        """Download, verify SHA-256, emit ``completed`` or ``error``."""
        try:
            installer = self.release.windows_installer()
            checksum = self.release.checksum_for(installer) if installer else None
            if installer is None or checksum is None:
                raise RuntimeError(QCoreApplication.translate(
                    "Updater", "Windows installer or checksum missing from the release"))
            dossier = temporary_directory()
            fichier = download(installer, dossier)
            checksum_path = download(checksum, dossier)
            if not verify_sha256(fichier, checksum_path.read_text(encoding="utf-8")):
                fichier.unlink(missing_ok=True)
                raise RuntimeError(QCoreApplication.translate(
                    "Updater", "SHA-256 verification failed"))
            self.completed.emit(fichier, str(dossier))
        except Exception as error:
            logger.exception("Update download failed")
            self.error.emit(QCoreApplication.translate(
                "Updater", "Update download failed: {error}").format(error=error))
