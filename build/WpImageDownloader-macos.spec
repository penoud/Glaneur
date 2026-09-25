# -*- mode: python ; coding: utf-8 -*-
"""Recette PyInstaller pour l'application macOS."""

from pathlib import Path
import sys

RACINE = Path(SPECPATH).parent
sys.path.insert(0, str(RACINE))
from WpImageDownloader import __version__  # noqa: E402

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
    datas=[],
    hiddenimports=["WpImageDownloader.config", "WpImageDownloader.engine",
                   "WpImageDownloader.scheduler", "WpImageDownloader.systeme",
                   "WpImageDownloader.sources",
                   "WpImageDownloader.sources.base",
                   "WpImageDownloader.sources.wordpress",
                   "WpImageDownloader.sources.djangoplicity"],
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
    name="WpImageDownloader",
    debug=False,
    strip=False,
    upx=False,
    console=False,
)

app = BUNDLE(
    exe,
    a.binaries,
    a.datas,
    name="WpImageDownloader.app",
    icon=None,
    bundle_identifier="org.wpimagedownloader.WpImageDownloader",
    info_plist={
        "CFBundleDisplayName": "WP Image Downloader",
        "CFBundleName": "WpImageDownloader",
        "CFBundleShortVersionString": __version__,
        "CFBundleVersion": __version__,
        "LSMinimumSystemVersion": "11.0",
    },
)