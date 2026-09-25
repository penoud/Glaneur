"""Téléchargement et vérification d'artefacts de release."""

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
    """Levée quand le téléchargement d'un asset échoue ou renvoie un fichier vide."""


def download(asset: ReleaseAsset, directory: Path, session: requests.Session | None = None) -> Path:
    """Télécharge ``asset`` vers ``directory/asset.name`` en streaming.

    Le fichier partiellement téléchargé est supprimé en cas d'échec
    (réseau ou disque), pour ne jamais laisser un artefact tronqué qui
    serait ensuite pris pour un fichier valide.

    Args:
        asset: Asset à récupérer.
        directory: Répertoire de destination, créé si nécessaire.
        session: Session ``requests`` à réutiliser (une nouvelle est
            créée si ``None``).

    Returns:
        Le chemin du fichier téléchargé.

    Raises:
        DownloadError: En cas d'erreur réseau, d'erreur disque ou de
            réponse vide.
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
    """Vérifie que le SHA-256 de ``path`` correspond à ``checksum_text``.

    Un ``.sha256`` GitHub contient typiquement ``<hex>  <nom_de_fichier>``
    ; l'extraction regex accepte n'importe quel format tant qu'un digest
    hex de 64 caractères y figure.

    Args:
        path: Fichier à vérifier.
        checksum_text: Contenu du fichier ``.sha256`` (ou n'importe
            quel texte contenant le digest hex).

    Returns:
        ``True`` si le digest correspond, ``False`` sinon (fichier
        absent, digest introuvable, ou mismatch).
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
    """Crée un dossier temporaire dédié au téléchargement d'une mise à jour.

    Le préfixe ``Glaneur-update-`` facilite le nettoyage manuel a
    posteriori. Le dossier n'est pas supprimé automatiquement : l'UI
    le fait après l'installation.

    Returns:
        Le chemin absolu du dossier créé.
    """
    return Path(tempfile.mkdtemp(prefix="Glaneur-update-"))
