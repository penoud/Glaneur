"""Petites intégrations système, isolées ici pour garder l'UI lisible."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

CLE_RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"
NOM_ENTREE = "ServetteDownloader"

# --- IDesktopWallpaper : identifiants et indices de vtable ------------------ #
# On accède au COM en ctypes brut plutôt que de tirer pywin32 ou comtypes.
_CLSID_DESKTOP_WALLPAPER = "{C2CF3110-460E-4FC1-B9D0-8A1C0C9CC4BD}"
_IID_IDESKTOP_WALLPAPER = "{B92B56A9-8B55-4E14-9A89-0199BBB6F93B}"
_CLSCTX_ALL = 23
_COINIT_APARTMENTTHREADED = 0x2
_RPC_E_CHANGED_MODE = 0x80010106

# Indices dans la vtable : 0 = QueryInterface, 1 = AddRef, 2 = Release.
_VT_RELEASE = 2
_VT_GETWALLPAPER = 4
_VT_ADVANCESLIDESHOW = 16

_DSD_FORWARD = 0


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


# --------------------------------------------------------------------------- #
# Fond d'écran Windows
# --------------------------------------------------------------------------- #

def _instancier_bureau():
    """Instancie IDesktopWallpaper. Renvoie (ptr, uninit) ou (None, False).

    `uninit` indique si l'appelant doit rappeler CoUninitialize : c'est le cas
    quand notre CoInitializeEx a réellement fait l'initialisation (S_OK) ou
    a été apparié à une précédente sur le même mode (S_FALSE). Un
    RPC_E_CHANGED_MODE signifie que le thread est déjà en MTA et qu'on ne doit
    pas défaire ce que l'application a mis en place.
    """
    if sys.platform != "win32":
        return None, False
    try:
        import ctypes  # local : indisponible correctement hors Windows

        class GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", ctypes.c_uint32),
                ("Data2", ctypes.c_uint16),
                ("Data3", ctypes.c_uint16),
                ("Data4", ctypes.c_ubyte * 8),
            ]

        ole32 = ctypes.windll.ole32
        hr_init = ole32.CoInitializeEx(None, _COINIT_APARTMENTTHREADED)
        uninit = hr_init in (0, 1)   # S_OK ou S_FALSE : à apparier
        if hr_init not in (0, 1) and (hr_init & 0xFFFFFFFF) != _RPC_E_CHANGED_MODE:
            return None, False

        clsid = GUID()
        iid = GUID()
        if ole32.CLSIDFromString(_CLSID_DESKTOP_WALLPAPER, ctypes.byref(clsid)) != 0 \
                or ole32.IIDFromString(_IID_IDESKTOP_WALLPAPER, ctypes.byref(iid)) != 0:
            if uninit:
                ole32.CoUninitialize()
            return None, False

        ptr = ctypes.c_void_p()
        hr = ole32.CoCreateInstance(
            ctypes.byref(clsid), None, _CLSCTX_ALL,
            ctypes.byref(iid), ctypes.byref(ptr),
        )
        if hr != 0 or not ptr.value:
            if uninit:
                ole32.CoUninitialize()
            return None, False
        return ptr, uninit
    except (OSError, AttributeError, OverflowError):
        return None, False


def _appel_com(ptr, index: int, proto, *args):
    """Appelle la méthode d'indice `index` de la vtable pointée par `ptr`."""
    import ctypes
    vtable = ctypes.cast(
        ctypes.cast(ptr, ctypes.POINTER(ctypes.c_void_p))[0],
        ctypes.POINTER(ctypes.c_void_p),
    )
    fonction = proto(vtable[index])
    return fonction(ptr, *args)


def _liberer_bureau(ptr, uninit: bool) -> None:
    import ctypes
    try:
        proto = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)
        _appel_com(ptr, _VT_RELEASE, proto)
    except (OSError, AttributeError):
        pass
    if uninit:
        try:
            ctypes.windll.ole32.CoUninitialize()
        except OSError:
            pass


def fond_ecran_actuel() -> Path | None:
    """Chemin de l'image affichée par le diaporama de fond d'écran Windows.

    Passe par IDesktopWallpaper.GetWallpaper : sous diaporama,
    SystemParametersInfo(SPI_GETDESKWALLPAPER) renverrait le cache
    TranscodedWallpaper, qui n'indique pas de quel original il provient.
    Renvoie None hors Windows ou si l'appel COM échoue.
    """
    ptr, uninit = _instancier_bureau()
    if ptr is None:
        return None
    try:
        import ctypes
        proto = ctypes.WINFUNCTYPE(
            ctypes.c_long,
            ctypes.c_void_p,           # this
            ctypes.c_wchar_p,          # monitorID (None = tous les écrans)
            ctypes.POINTER(ctypes.c_void_p),  # out ppwszWallpaper
        )
        out = ctypes.c_void_p()
        hr = _appel_com(ptr, _VT_GETWALLPAPER, proto, None, ctypes.byref(out))
        if hr != 0 or not out.value:
            return None
        chemin = ctypes.wstring_at(out.value)
        ctypes.windll.ole32.CoTaskMemFree(out)
        return Path(chemin) if chemin else None
    except (OSError, AttributeError):
        return None
    finally:
        _liberer_bureau(ptr, uninit)


def avancer_diaporama() -> None:
    """Passe à l'image suivante du diaporama Windows. Silencieux si indisponible."""
    ptr, uninit = _instancier_bureau()
    if ptr is None:
        return
    try:
        import ctypes
        proto = ctypes.WINFUNCTYPE(
            ctypes.c_long,
            ctypes.c_void_p,       # this
            ctypes.c_wchar_p,      # monitorID
            ctypes.c_int,          # direction
        )
        _appel_com(ptr, _VT_ADVANCESLIDESHOW, proto, None, _DSD_FORWARD)
    except (OSError, AttributeError):
        pass
    finally:
        _liberer_bureau(ptr, uninit)
