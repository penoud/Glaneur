"""Petites intégrations système, isolées ici pour garder l'UI lisible."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

CLE_RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"
NOM_ENTREE = "ServetteDownloader"


def est_gele() -> bool:
    """Vrai si on tourne depuis l'exécutable PyInstaller."""
    return getattr(sys, "frozen", False)


def commande_lancement() -> str:
    """Commande à inscrire dans le registre pour relancer l'application."""
    if est_gele():
        return f'"{Path(sys.executable)}" --reduit'
    script = Path(__file__).resolve().parent.parent / "app.py"
    return f'"{Path(sys.executable)}" "{script}" --reduit'


def demarrage_automatique(actif: bool) -> bool:
    """Ajoute ou retire l'entrée de démarrage Windows. Renvoie l'état obtenu."""
    if sys.platform != "win32":
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CLE_RUN, 0,
                            winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE) as cle:
            if actif:
                winreg.SetValueEx(cle, NOM_ENTREE, 0, winreg.REG_SZ, commande_lancement())
            else:
                try:
                    winreg.DeleteValue(cle, NOM_ENTREE)
                except FileNotFoundError:
                    pass
        return actif
    except OSError:
        return False


def demarrage_automatique_actif() -> bool:
    if sys.platform != "win32":
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CLE_RUN) as cle:
            winreg.QueryValueEx(cle, NOM_ENTREE)
            return True
    except OSError:
        return False


def ouvrir_dossier(chemin: Path) -> None:
    """Ouvre le dossier dans l'explorateur de fichiers du système."""
    chemin.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        os.startfile(chemin)  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(chemin)])
    else:
        subprocess.Popen(["xdg-open", str(chemin)])
