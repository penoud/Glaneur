"""Release-artifact download and verification."""

from __future__ import annotations

import hashlib
import logging
import re
import tempfile
from pathlib import Path

import requests
from PySide6.QtCore import QCoreApplication

from .models import ReleaseAsset

logger = logging.getLogger(__name__)


class DownloadError(RuntimeError):
    """Raised when an asset download fails or returns an empty file."""


def download(asset: ReleaseAsset, directory: Path, session: requests.Session | None = None) -> Path:
    """Stream ``asset`` to ``directory/asset.name``.

    The partially-downloaded file is deleted on failure (network or
    disk), so we never leave a truncated artifact that would later be
    mistaken for a valid file.

    Args:
        asset: Asset to fetch.
        directory: Destination directory, created if needed.
        session: ``requests`` session to reuse (a new one is created
            if ``None``).

    Returns:
        The path of the downloaded file.

    Raises:
        DownloadError: On network error, disk error, or empty response.
    """
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / asset.name
    client = session or requests.Session()
    logger.info("Downloading %s", asset.name)
    try:
        with client.get(asset.download_url, stream=True, timeout=60) as response:
            response.raise_for_status()
            with destination.open("wb") as output:
                for chunk in response.iter_content(1024 * 1024):
                    if chunk:
                        output.write(chunk)
    except (OSError, requests.RequestException) as error:
        destination.unlink(missing_ok=True)
        logger.exception("Download failed: %s", asset.name)
        raise DownloadError(QCoreApplication.translate(
            "Updater", "Téléchargement impossible : {erreur}").format(erreur=error)) from error
    if not destination.exists() or destination.stat().st_size == 0:
        destination.unlink(missing_ok=True)
        logger.error("Empty download: %s", asset.name)
        raise DownloadError(QCoreApplication.translate("Updater", "Téléchargement vide"))
    logger.info("Download completed: %s (%d bytes)", asset.name, destination.stat().st_size)
    return destination


def verify_sha256(path: Path, checksum_text: str) -> bool:
    """Verify that the SHA-256 of ``path`` matches ``checksum_text``.

    A GitHub ``.sha256`` typically contains ``<hex>  <filename>``; the
    regex extraction accepts any format as long as a 64-character hex
    digest is present.

    Args:
        path: File to verify.
        checksum_text: Content of the ``.sha256`` file (or any text
            containing the hex digest).

    Returns:
        ``True`` if the digest matches, ``False`` otherwise (missing
        file, digest not found, or mismatch).
    """
    match = re.search(r"\b([0-9a-fA-F]{64})\b", checksum_text)
    if not match or not path.is_file():
        logger.error("Checksum verification failed: no digest or missing file (%s)", path.name)
        return False
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    ok = digest.hexdigest().lower() == match.group(1).lower()
    if ok:
        logger.info("SHA-256 verification successful: %s", path.name)
    else:
        logger.error("SHA-256 mismatch: %s", path.name)
    return ok


def temporary_directory() -> Path:
    """Create a temporary directory dedicated to an update download.

    The ``Glaneur-update-`` prefix makes manual after-the-fact cleanup
    easier. The directory is not deleted automatically: the UI removes
    it after installation.

    Returns:
        The absolute path of the created directory.
    """
    return Path(tempfile.mkdtemp(prefix="Glaneur-update-"))
