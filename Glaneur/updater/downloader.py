"""Telechargement et verification d'artefacts de release."""

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
    pass


def download(asset: ReleaseAsset, directory: Path, session: requests.Session | None = None) -> Path:
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
    return Path(tempfile.mkdtemp(prefix="Glaneur-update-"))
