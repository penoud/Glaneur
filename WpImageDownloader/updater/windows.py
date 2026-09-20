"""Lancement de l'updater Windows sans installation Linux/macOS."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


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
    subprocess.Popen([
        str(updater), "--installer", str(installer), "--pid", str(pid),
        "--application", str(application),
    ], close_fds=True, creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))


def run_updater(arguments: list[str]) -> int:
    import argparse
    import time

    parser = argparse.ArgumentParser()
    parser.add_argument("--installer", required=True, type=Path)
    parser.add_argument("--pid", required=True, type=int)
    parser.add_argument("--application", required=True, type=Path)
    args = parser.parse_args(arguments)
    if sys.platform != "win32" or args.installer.suffix.lower() != ".exe":
        return 2
    if not args.installer.is_file() or not args.application.is_file() or args.pid <= 0:
        return 2
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            os.kill(args.pid, 0)
        except OSError:
            break
        time.sleep(0.25)
    else:
        return 3
    try:
        result = subprocess.run([str(args.installer), "/SILENT", "/CLOSEAPPLICATIONS"], check=False)
    except OSError:
        return 4
    if result.returncode != 0:
        return result.returncode
    try:
        subprocess.Popen([str(args.application), "--reduit"], close_fds=True)
    except OSError:
        return 5
    return 0
