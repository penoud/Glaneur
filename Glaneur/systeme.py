"""Petites intégrations système, isolées ici pour garder l'UI lisible.

Ce module rassemble les points de contact avec l'OS : détection de
l'exécutable PyInstaller, entrée de démarrage Windows, ouverture d'un
dossier dans l'explorateur, et pilotage du diaporama Windows via l'API
COM ``IDesktopWallpaper`` en ``ctypes`` brut (pour ne pas dépendre de
``pywin32`` ou ``comtypes``).

Hors Windows, les fonctions liées au diaporama et au démarrage
automatique renvoient un « rien à faire » silencieux plutôt que de
lever.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

CLE_RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"
NOM_ENTREE = "Glaneur"

# --- IDesktopWallpaper: identifiers and vtable indices ---------------------- #
# We access COM via raw ctypes rather than pulling in pywin32 or comtypes.
_CLSID_DESKTOP_WALLPAPER = "{C2CF3110-460E-4FC1-B9D0-8A1C0C9CC4BD}"
_IID_IDESKTOP_WALLPAPER = "{B92B56A9-8B55-4E14-9A89-0199BBB6F93B}"
_CLSCTX_ALL = 23
_COINIT_APARTMENTTHREADED = 0x2
_RPC_E_CHANGED_MODE = 0x80010106

# Indices in the IDesktopWallpaper vtable. IUnknown occupies 0-2 (QueryInterface,
# AddRef, Release), then the 16 interface methods: SetWallpaper=3,
# GetWallpaper=4, GetMonitorDevicePathAt=5, GetMonitorDevicePathCount=6,
# GetMonitorRECT=7, SetBackgroundColor=8, GetBackgroundColor=9, SetPosition=10,
# GetPosition=11, SetSlideshow=12, GetSlideshow=13, SetSlideshowOptions=14,
# GetSlideshowOptions=15, AdvanceSlideshow=16, GetStatus=17, Enable=18.
_VT_RELEASE = 2
_VT_GETWALLPAPER = 4
_VT_GETMONITORDEVICEPATHAT = 5
_VT_GETMONITORDEVICEPATHCOUNT = 6
_VT_SET_SLIDESHOW = 12
_VT_ADVANCESLIDESHOW = 16

_DSD_FORWARD = 0


def est_gele() -> bool:
    """Indique si l'application tourne depuis l'exécutable PyInstaller.

    Returns:
        ``True`` sous PyInstaller (attribut ``sys.frozen`` positionné),
        ``False`` en exécution Python directe.
    """
    return getattr(sys, "frozen", False)


def commande_lancement() -> str:
    """Commande à inscrire dans le registre pour relancer l'application.

    En build PyInstaller, la commande pointe directement sur l'exécutable ;
    en développement, elle enchaîne ``python`` et le script racine
    ``app.py``. L'option ``--reduit`` demande un démarrage minimisé
    dans la zone de notification.

    Returns:
        La ligne de commande, avec chemin d'exécutable entre guillemets.
    """
    if est_gele():
        return f'"{Path(sys.executable)}" --reduit'
    script = Path(__file__).resolve().parent.parent / "app.py"
    return f'"{Path(sys.executable)}" "{script}" --reduit'


def demarrage_automatique(actif: bool) -> bool:
    """Ajoute ou retire l'entrée de démarrage Windows.

    Args:
        actif: ``True`` pour ajouter, ``False`` pour retirer.

    Returns:
        L'état obtenu (``True`` si l'entrée est en place après appel,
        ``False`` sinon ou hors Windows).
    """
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
    """Indique si l'entrée de démarrage Windows est présente.

    Returns:
        ``True`` si l'entrée existe dans ``HKCU\\...\\Run``, ``False``
        sinon ou hors Windows.
    """
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
    """Ouvre le dossier dans l'explorateur de fichiers du système.

    Crée le dossier s'il n'existe pas encore (utile juste après un
    premier lancement où le dossier cible n'a rien reçu).

    Args:
        chemin: Dossier à ouvrir.
    """
    chemin.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        os.startfile(chemin)  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(chemin)])
    else:
        subprocess.Popen(["xdg-open", str(chemin)])


# --------------------------------------------------------------------------- #
# Windows wallpaper
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
        import ctypes  # local: not properly available off Windows

        class GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", ctypes.c_uint32),
                ("Data2", ctypes.c_uint16),
                ("Data3", ctypes.c_uint16),
                ("Data4", ctypes.c_ubyte * 8),
            ]

        ole32 = ctypes.windll.ole32
        hr_init = ole32.CoInitializeEx(None, _COINIT_APARTMENTTHREADED)
        uninit = hr_init in (0, 1)   # S_OK or S_FALSE: to be paired
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
    """Release une interface COM et éventuellement CoUninitialize."""
    import ctypes
    if isinstance(ptr, ctypes.c_void_p) and ptr.value:
        try:
            proto = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)
            _appel_com(ptr, _VT_RELEASE, proto)
        except (OSError, AttributeError, TypeError):
            pass
    if uninit:
        try:
            ctypes.windll.ole32.CoUninitialize()
        except OSError:
            pass


def _creer_tableau_images(chemin: Path):
    """Crée un IShellItemArray contenant les images du dossier Windows.

    Renvoie un `c_void_p` sur l'interface, ou `None` si rien n'a pu être créé
    (dossier vide, échec de SHParseDisplayName sur toutes les images, ou
    SHCreateShellItemArrayFromIDLists en erreur). Un unique type de retour,
    pour que l'appelant puisse tester `is None` sans piège.
    """
    import ctypes

    ole32 = ctypes.windll.ole32
    shell32 = ctypes.windll.shell32
    shell32.SHParseDisplayName.argtypes = [
        ctypes.c_wchar_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32),
    ]
    shell32.SHParseDisplayName.restype = ctypes.c_long

    pidls = []
    for fichier in sorted(chemin.rglob("*")):
        if not fichier.is_file() or fichier.suffix.lower() not in {
            ".bmp", ".gif", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp",
        }:
            continue
        pidl = ctypes.c_void_p()
        attributes = ctypes.c_uint32()
        hr = shell32.SHParseDisplayName(
            str(fichier), None, ctypes.byref(pidl), 0, ctypes.byref(attributes))
        if hr == 0 and pidl.value:
            pidls.append(pidl)

    if not pidls:
        return None

    tableau = ctypes.c_void_p()
    shell32.SHCreateShellItemArrayFromIDLists.argtypes = [
        ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    shell32.SHCreateShellItemArrayFromIDLists.restype = ctypes.c_long
    pidl_array = (ctypes.c_void_p * len(pidls))(*(pidl.value for pidl in pidls))
    hr = shell32.SHCreateShellItemArrayFromIDLists(
        len(pidls), pidl_array, ctypes.byref(tableau))
    for pidl in pidls:
        ole32.CoTaskMemFree(pidl)
    if hr != 0 or not tableau.value:
        return None
    return tableau


def definir_dossier_diaporama(chemin: Path) -> bool:
    """Configure le diaporama Windows pour utiliser ``chemin`` comme source.

    Fait un ``IDesktopWallpaper::SetSlideshow`` avec un
    ``IShellItemArray`` construit à partir des images du dossier.
    Aucune erreur COM ne fuite : elles sont converties en ``False``.

    Args:
        chemin: Dossier contenant les images (récursif). Extensions
            reconnues : ``.bmp``, ``.gif``, ``.jpeg``, ``.jpg``, ``.png``,
            ``.tif``, ``.tiff``, ``.webp``.

    Returns:
        ``True`` si le diaporama a été activé, ``False`` sinon (hors
        Windows, dossier vide, ou échec COM).
    """
    if sys.platform != "win32" or not chemin.is_dir():
        return False
    bureau, uninit = _instancier_bureau()
    if bureau is None:
        return False
    tableau = None
    try:
        tableau = _creer_tableau_images(chemin)
        if tableau is None:
            return False
        import ctypes
        proto = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p)
        return _appel_com(bureau, _VT_SET_SLIDESHOW, proto, tableau) == 0
    except (OSError, AttributeError, TypeError):
        return False
    finally:
        if tableau is not None:
            _liberer_bureau(tableau, False)
        _liberer_bureau(bureau, uninit)


def fond_ecran_actuel() -> Path | None:
    """Renvoie le chemin de l'image actuellement affichée en fond d'écran.

    Passe par ``IDesktopWallpaper::GetWallpaper``. Sous diaporama,
    ``SystemParametersInfo(SPI_GETDESKWALLPAPER)`` ne renverrait que le
    cache ``TranscodedWallpaper``, qui n'indique pas de quel original il
    provient — l'appel COM est donc nécessaire pour connaître le
    fichier réellement projeté.

    Returns:
        Le chemin de l'image, ou ``None`` hors Windows ou si l'appel
        COM échoue.
    """
    ptr, uninit = _instancier_bureau()
    if ptr is None:
        return None
    try:
        import ctypes
        proto = ctypes.WINFUNCTYPE(
            ctypes.c_long,
            ctypes.c_void_p,           # this
            ctypes.c_wchar_p,          # monitorID
            ctypes.POINTER(ctypes.c_void_p),  # out ppwszWallpaper
        )
        proto_count = ctypes.WINFUNCTYPE(
            ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint))
        count = ctypes.c_uint()
        hr = _appel_com(ptr, _VT_GETMONITORDEVICEPATHCOUNT,
                        proto_count, ctypes.byref(count))
        monitor_ids = [None]
        if hr == 0 and count.value:
            proto_monitor = ctypes.WINFUNCTYPE(
                ctypes.c_long, ctypes.c_void_p, ctypes.c_uint,
                ctypes.POINTER(ctypes.c_void_p))
            monitor_ids = []
            for index in range(count.value):
                monitor = ctypes.c_void_p()
                if _appel_com(ptr, _VT_GETMONITORDEVICEPATHAT,
                              proto_monitor, index, ctypes.byref(monitor)) == 0:
                    if monitor.value:
                        monitor_ids.append(ctypes.wstring_at(monitor.value))
                        ctypes.windll.ole32.CoTaskMemFree(monitor)

        for monitor_id in monitor_ids:
            out = ctypes.c_void_p()
            hr = _appel_com(ptr, _VT_GETWALLPAPER, proto, monitor_id,
                            ctypes.byref(out))
            if hr == 0 and out.value:
                chemin = ctypes.wstring_at(out.value)
                ctypes.windll.ole32.CoTaskMemFree(out)
                if chemin:
                    return Path(chemin)
        return None
    except (OSError, AttributeError):
        return None
    finally:
        _liberer_bureau(ptr, uninit)


def avancer_diaporama() -> None:
    """Passe à l'image suivante du diaporama Windows.

    Silencieux si le diaporama n'est pas configuré, si Windows refuse
    l'appel COM, ou hors Windows.
    """
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
