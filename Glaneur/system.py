"""Small OS integrations, isolated here to keep the UI readable.

This module gathers the touch points with the OS: detection of a
PyInstaller executable, the Windows startup entry, opening a folder in
the explorer, and driving the Windows slideshow through the COM API
``IDesktopWallpaper`` in raw ``ctypes`` (so we don't depend on
``pywin32`` or ``comtypes``).

Off Windows, the slideshow-related and startup-related functions return
a silent "nothing to do" rather than raising.
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
    """Report whether the application runs from the PyInstaller executable.

    Returns:
        ``True`` under PyInstaller (``sys.frozen`` attribute set),
        ``False`` when running Python directly.
    """
    return getattr(sys, "frozen", False)


def commande_lancement() -> str:
    """Command to write in the registry to relaunch the application.

    In a PyInstaller build, the command points directly at the executable;
    in development, it chains ``python`` and the root script ``app.py``.
    The ``--reduit`` option requests a minimised start into the notification
    area.

    Returns:
        The command line, with the executable path quoted.
    """
    if est_gele():
        return f'"{Path(sys.executable)}" --reduit'
    script = Path(__file__).resolve().parent.parent / "app.py"
    return f'"{Path(sys.executable)}" "{script}" --reduit'


def demarrage_automatique(actif: bool) -> bool:
    """Add or remove the Windows startup entry.

    Args:
        actif: ``True`` to add, ``False`` to remove.

    Returns:
        The resulting state (``True`` if the entry is in place after the
        call, ``False`` otherwise or off Windows).
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
    """Report whether the Windows startup entry is present.

    Returns:
        ``True`` if the entry exists in ``HKCU\\...\\Run``, ``False``
        otherwise or off Windows.
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
    """Open the folder in the OS file explorer.

    Creates the folder if it does not exist yet (useful just after a
    first launch when the target folder has received nothing).

    Args:
        chemin: Folder to open.
    """
    chemin.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        os.startfile(chemin)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(chemin)])
    else:
        subprocess.Popen(["xdg-open", str(chemin)])


# --------------------------------------------------------------------------- #
# Windows wallpaper
# --------------------------------------------------------------------------- #

def _instancier_bureau():
    """Instantiate IDesktopWallpaper. Returns ``(ptr, uninit)`` or ``(None, False)``.

    ``uninit`` says whether the caller must call ``CoUninitialize``: that
    is the case when our ``CoInitializeEx`` actually performed the
    initialisation (S_OK) or was paired with an earlier one on the same
    mode (S_FALSE). ``RPC_E_CHANGED_MODE`` means the thread is already in
    MTA and we must not undo what the application set up.
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
    """Call the method at vtable ``index`` for the interface pointed by ``ptr``."""
    import ctypes
    vtable = ctypes.cast(
        ctypes.cast(ptr, ctypes.POINTER(ctypes.c_void_p))[0],
        ctypes.POINTER(ctypes.c_void_p),
    )
    fonction = proto(vtable[index])
    return fonction(ptr, *args)


def _liberer_bureau(ptr, uninit: bool) -> None:
    """``Release`` a COM interface and possibly call ``CoUninitialize``."""
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
    """Build an ``IShellItemArray`` containing the folder's images for Windows.

    Returns a ``c_void_p`` on the interface, or ``None`` if nothing could
    be created (empty folder, ``SHParseDisplayName`` failing on every
    image, or ``SHCreateShellItemArrayFromIDLists`` erroring). A single
    return type, so the caller can test ``is None`` without a pitfall.
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
    """Configure the Windows slideshow to use ``chemin`` as its source.

    Calls ``IDesktopWallpaper::SetSlideshow`` with an ``IShellItemArray``
    built from the folder's images. No COM error escapes: they are
    converted into ``False``.

    Args:
        chemin: Folder containing the images (recursive). Recognised
            extensions: ``.bmp``, ``.gif``, ``.jpeg``, ``.jpg``, ``.png``,
            ``.tif``, ``.tiff``, ``.webp``.

    Returns:
        ``True`` if the slideshow was enabled, ``False`` otherwise (off
        Windows, empty folder, or COM failure).
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
    """Return the path of the image currently displayed as wallpaper.

    Goes through ``IDesktopWallpaper::GetWallpaper``. Under a slideshow,
    ``SystemParametersInfo(SPI_GETDESKWALLPAPER)`` would only return the
    ``TranscodedWallpaper`` cache, which does not say which original it
    stems from — so the COM call is required to know the file actually
    being projected.

    Returns:
        The image path, or ``None`` off Windows or if the COM call fails.
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
    """Advance to the next image of the Windows slideshow.

    Silent when the slideshow is not configured, when Windows refuses the
    COM call, or off Windows.
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
