#!/usr/bin/env python3
"""Génère et compile les traductions Qt.

Usage :
    python translations/build_translations.py update    # scanne le code -> .ts
    python translations/build_translations.py release   # .ts -> .qm

Après un `update`, ouvrir chaque `.ts` dans Qt Linguist
(`pyside6-linguist translations/wpimagedownloader_en.ts`) et remplir les
traductions, puis relancer `release` pour produire les `.qm` que l'appli
charge à l'exécution.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
DOSSIER_TS = RACINE / "translations"


def _outil(nom: str) -> str:
    """Trouve un exécutable PySide6 : d'abord dans le venv actif (Scripts/bin
    à côté du Python courant), sinon sur le PATH."""
    dossier_scripts = Path(sys.executable).parent
    for candidat in (dossier_scripts / nom, dossier_scripts / f"{nom}.exe"):
        if candidat.is_file():
            return str(candidat)
    trouve = shutil.which(nom)
    if trouve:
        return trouve
    raise RuntimeError(
        f"{nom} introuvable. Installe PySide6 dans le venv actif "
        f"(`pip install PySide6-Essentials`).")

# Langues cibles — FR est la langue source du code, on la garde en .ts pour
# uniformité mais le runtime n'a pas besoin de son .qm.
LANGUES = ["fr", "en"]

# Fichiers à scanner. On veut app.py et le paquet Python (bug_report.py, etc.),
# mais pas les tests ni le build.
SOURCES = [
    RACINE / "app.py",
    *(RACINE / "Glaneur").glob("*.py"),
    *(RACINE / "Glaneur" / "sources").glob("*.py"),
    *(RACINE / "Glaneur" / "updater").glob("*.py"),
]


def _run(cmd: list[str]) -> None:
    print(" ".join(cmd))
    subprocess.run(cmd, check=True)


def update() -> None:
    lupdate = _outil("pyside6-lupdate")
    for langue in LANGUES:
        cible = DOSSIER_TS / f"wpimagedownloader_{langue}.ts"
        _run([
            lupdate,
            *[str(s) for s in SOURCES if s.is_file()],
            "-source-language", "fr",
            "-target-language", langue,
            "-ts", str(cible),
        ])


def release() -> None:
    lrelease = _outil("pyside6-lrelease")
    for langue in LANGUES:
        source = DOSSIER_TS / f"wpimagedownloader_{langue}.ts"
        if not source.exists():
            print(f"[skip] {source} absent — lance d'abord `update`.")
            continue
        _run([lrelease, str(source)])


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "update"
    if action == "update":
        update()
    elif action == "release":
        release()
    else:
        print(f"Action inconnue : {action!r}. Utiliser 'update' ou 'release'.")
        sys.exit(1)
