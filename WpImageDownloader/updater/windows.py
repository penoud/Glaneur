"""Lancement de l'updater Windows sans installation Linux/macOS."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

logger = logging.getLogger(__name__)


def updater_executable() -> Path:
    base = Path(sys.executable).resolve().parent
    return base / "WpImageDownloaderUpdater.exe"


def start(installer: Path, application: Path, pid: int) -> None:
    if sys.platform != "win32":
        raise RuntimeError("L'installation automatique est disponible uniquement sous Windows")
    if installer.suffix.lower() != ".exe" or not installer.is_file():
        raise ValueError("Installateur Windows invalide")
    if not application.is_file() or pid <= 0:
        raise ValueError("Application ou PID invalide")
    updater = updater_executable()
    if not updater.is_file():
        raise FileNotFoundError(updater)
    logger.info("Starting updater for pid=%d installer=%s", pid, installer.name)
    subprocess.Popen([
        str(updater), "--installer", str(installer), "--pid", str(pid),
        "--application", str(application),
    ], close_fds=True, creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))


# --------------------------------------------------------------------------- #
# run_updater : exécuté dans WpImageDownloaderUpdater.exe (process séparé)
# --------------------------------------------------------------------------- #

def _configurer_log_updater() -> Path | None:
    """Ajoute un RotatingFileHandler dans <config>/logs/updater.log.

    L'updater est un binaire séparé, détaché de l'app principale (pas de
    console, pas de stdout visible) : sans ce log, un échec de wait/install
    disparaît silencieusement. Renvoie le chemin du log ou None si le
    dossier config n'a pas pu être créé.
    """
    try:
        from ..config import dossier_config
        dossier = dossier_config() / "logs"
        dossier.mkdir(parents=True, exist_ok=True)
        chemin = dossier / "updater.log"
        handler = RotatingFileHandler(
            chemin, maxBytes=500_000, backupCount=2, encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s: %(message)s"))
        racine = logging.getLogger()
        racine.setLevel(logging.DEBUG)
        racine.addHandler(handler)
        return chemin
    except Exception:   # noqa: BLE001 - on ne veut jamais planter l'updater à cause du log
        return None


def _process_vivant(pid: int) -> bool:
    """True si le PID est encore vivant, False si mort.

    PermissionError = process existe mais accès refusé → considéré vivant
    pour ne pas lancer l'installateur trop tôt.

    Sous Windows, os.kill(pid, 0) peut lever OSError avec WinError 6
    (« Descripteur non valide ») quand le process meurt entre l'OpenProcess
    interne et le check — Python ne le remappe pas en ProcessLookupError.
    On considère ce cas comme « mort », sinon l'updater tourne en boucle
    jusqu'au timeout de 30 s.
    """
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError as error:
        # Codes Windows synonymes de « process disparu » :
        #   6   = ERROR_INVALID_HANDLE
        #   87  = ERROR_INVALID_PARAMETER (déjà remappé en ProcessLookupError
        #         par Python, mais on ceinture-et-bretelles)
        if getattr(error, "winerror", None) in (6, 87):
            return False
        logger.warning("os.kill(%d, 0) inattendu : %s", pid, error)
        return True


def run_updater(arguments: list[str]) -> int:
    import argparse
    import time

    log_path = _configurer_log_updater()
    logger.info("=" * 60)
    logger.info("Updater démarré, argv=%r", arguments)
    logger.info("Python=%s, executable=%s", sys.version.split()[0], sys.executable)
    if log_path:
        logger.info("Log fichier : %s", log_path)

    parser = argparse.ArgumentParser()
    parser.add_argument("--installer", required=True, type=Path)
    parser.add_argument("--pid", required=True, type=int)
    parser.add_argument("--application", required=True, type=Path)
    try:
        args = parser.parse_args(arguments)
    except SystemExit as error:
        logger.error("Arguments invalides : %s", error)
        return 2

    logger.info("Installer=%s (existe=%s)", args.installer, args.installer.is_file())
    logger.info("Application=%s (existe=%s)", args.application, args.application.is_file())
    logger.info("PID à attendre=%d", args.pid)

    if sys.platform != "win32":
        logger.error("Refus : plateforme %s (Windows requis)", sys.platform)
        return 2
    if args.installer.suffix.lower() != ".exe":
        logger.error("Refus : extension installer invalide (%s)", args.installer.suffix)
        return 2
    if not args.installer.is_file() or not args.application.is_file() or args.pid <= 0:
        logger.error("Refus : validation des chemins/PID échouée")
        return 2

    deadline = time.monotonic() + 30
    logger.info("Attente de la fermeture du PID %d (timeout 30 s)…", args.pid)
    ticks = 0
    while time.monotonic() < deadline:
        if not _process_vivant(args.pid):
            logger.info("PID %d disparu après %d ticks (%.1fs)",
                        args.pid, ticks, ticks * 0.25)
            break
        ticks += 1
        time.sleep(0.25)
    else:
        logger.error("Timeout : le PID %d est toujours vivant après 30 s — abandon", args.pid)
        return 3

    # /VERYSILENT : aucune UI Inno visible (même pas la barre de progression) —
    #   toute fenêtre qui apparaîtrait quand même vient d'ailleurs (UAC,
    #   SmartScreen, Defender), ce qui aide à localiser un blocage.
    # /SUPPRESSMSGBOXES : supprime les msgboxes Inno résiduels.
    # /CLOSEAPPLICATIONSFILTER limite `/CLOSEAPPLICATIONS` à l'exe principal :
    #   sans filtre, Inno tente aussi de fermer WpImageDownloaderUpdater.exe
    #   (ce process, qui tourne dans le dossier d'install) et sort code 5.
    cmd = [
        str(args.installer),
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/CLOSEAPPLICATIONS",
        "/CLOSEAPPLICATIONSFILTER=WpImagerDownloader.exe",
    ]
    logger.info("Lancement de l'installateur : %r", cmd)
    # L'updater tourne en DETACHED_PROCESS sans stdio valides : on redirige
    # explicitement vers DEVNULL pour éviter tout blocage I/O du process
    # enfant. Timeout large pour ne pas rester coincé éternellement si
    # l'installateur attend une interaction invisible.
    try:
        result = subprocess.run(
            cmd, check=False, timeout=300,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        logger.error("Installateur bloqué plus de 300 s — abandon")
        return 4
    except OSError:
        logger.exception("Échec de lancement de l'installateur")
        return 4
    logger.info("Installateur terminé avec code=%d", result.returncode)
    if result.returncode != 0:
        logger.error("Installateur en erreur (code %d) — pas de redémarrage", result.returncode)
        return result.returncode

    logger.info("Redémarrage de l'application : %s --reduit", args.application)
    try:
        subprocess.Popen([str(args.application), "--reduit"], close_fds=True)
    except OSError as error:
        logger.exception("Échec du redémarrage")
        return 5
    logger.info("Updater terminé avec succès")
    return 0
