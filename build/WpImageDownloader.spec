# -*- mode: python ; coding: utf-8 -*-
"""Recette PyInstaller pour l'application PySide6.

    pyinstaller build/WpImageDownloader.spec --noconfirm --clean

Produit dist/ServetteDownloader/ServetteDownloader.exe (mode dossier).
Le mode dossier est préféré au --onefile : démarrage plus rapide, et pas
d'extraction dans %TEMP% à chaque lancement — ce qui compte d'autant plus
avec Qt, dont le paquet est volumineux.
"""

from pathlib import Path

RACINE = Path(SPECPATH).parent
ICONE = RACINE / "build" / "WpImageDownloader.ico"

# Qt embarque beaucoup de modules dont une application comme celle-ci n'a que
# faire. Les écarter fait passer la distribution d'environ 180 Mo à 60 Mo.
QT_INUTILES = [
    "PySide6.Qt3DAnimation", "PySide6.Qt3DCore", "PySide6.Qt3DExtras",
    "PySide6.Qt3DInput", "PySide6.Qt3DLogic", "PySide6.Qt3DRender",
    "PySide6.QtBluetooth", "PySide6.QtCharts", "PySide6.QtDataVisualization",
    "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets", "PySide6.QtNfc", "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets", "PySide6.QtPdf", "PySide6.QtPdfWidgets",
    "PySide6.QtPositioning", "PySide6.QtQml", "PySide6.QtQuick",
    "PySide6.QtQuick3D", "PySide6.QtQuickControls2", "PySide6.QtQuickWidgets",
    "PySide6.QtRemoteObjects", "PySide6.QtScxml", "PySide6.QtSensors",
    "PySide6.QtSerialPort", "PySide6.QtSpatialAudio", "PySide6.QtSql",
    "PySide6.QtStateMachine", "PySide6.QtSvg", "PySide6.QtSvgWidgets",
    "PySide6.QtTest", "PySide6.QtTextToSpeech", "PySide6.QtUiTools",
    "PySide6.QtWebChannel", "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets", "PySide6.QtWebSockets",
]

a = Analysis(
    [str(RACINE / "app.py")],
    pathex=[str(RACINE)],
    binaries=[],
    datas=[(str(ICONE), "build")] if ICONE.exists() else [],
    hiddenimports=["WpImageDownloader.config", "WpImageDownloader.engine",
                   "WpImageDownloader.scheduler", "WpImageDownloader.systeme"],
    hookspath=[],
    runtime_hooks=[],
    excludes=QT_INUTILES + [
        "tkinter", "numpy", "pandas", "matplotlib", "scipy", "PIL",
        "PyQt5", "PyQt6", "test", "unittest", "pydoc", "setuptools",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ServetteDownloader",
    debug=False,
    strip=False,
    upx=False,                 # UPX déclenche des faux positifs antivirus
    console=False,             # application fenêtrée, pas de console noire
    icon=str(ICONE) if ICONE.exists() else None,
    version=str(RACINE / "build" / "version_info.txt")
    if (RACINE / "build" / "version_info.txt").exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="ServetteDownloader",
)
