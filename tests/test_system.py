"""Tests for the system integrations.

The COM part (`IDesktopWallpaper`) can only be verified on Windows; here we
check at least that every function stays silent off Windows, without raising
an exception or requiring a Windows dependency.
"""

from __future__ import annotations

import sys

import pytest

from Glaneur import system
from Glaneur.system import (
    advance_slideshow,
    autostart,
    autostart_active,
    current_wallpaper,
    is_frozen,
    launch_command,
    set_slideshow_dir,
)

# --------------------------------------------------------------------------- #
# is_frozen / launch_command
# --------------------------------------------------------------------------- #

class TestEstGele:
    def test_defaut_faux(self, monkeypatch):
        monkeypatch.delattr(sys, "frozen", raising=False)
        assert is_frozen() is False

    def test_frozen(self, monkeypatch):
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        assert is_frozen() is True


class TestCommandeLancement:
    def test_dev_utilise_app_py(self, monkeypatch):
        monkeypatch.delattr(sys, "frozen", raising=False)
        cmd = launch_command()
        assert "app.py" in cmd
        assert "--reduit" in cmd

    def test_frozen_utilise_executable(self, monkeypatch):
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        cmd = launch_command()
        assert "app.py" not in cmd
        assert "--reduit" in cmd


# --------------------------------------------------------------------------- #
# Auto-start (Windows only, silent elsewhere)
# --------------------------------------------------------------------------- #

@pytest.mark.skipif(sys.platform == "win32",
                    reason="hors Windows uniquement")
class TestDemarrageHorsWindows:
    def test_activer_renvoie_false(self):
        assert autostart(True) is False

    def test_desactiver_renvoie_false(self):
        assert autostart(False) is False

    def test_actif_renvoie_false(self):
        assert autostart_active() is False


# --------------------------------------------------------------------------- #
# Wallpaper (Windows COM): silent off-platform
# --------------------------------------------------------------------------- #

@pytest.mark.skipif(sys.platform == "win32",
                    reason="hors Windows uniquement")
class TestFondEcranHorsWindows:
    def test_definir_dossier_diaporama_renvoie_false(self, tmp_path):
        assert set_slideshow_dir(tmp_path) is False

    def test_fond_ecran_actuel_renvoie_none(self):
        assert current_wallpaper() is None

    def test_avancer_diaporama_ne_leve_rien(self):
        # no return expected, silence is the success criterion
        advance_slideshow()

    def test_instancier_bureau_renvoie_none(self):
        ptr, uninit = system._instantiate_desktop()
        assert ptr is None
        assert uninit is False


# --------------------------------------------------------------------------- #
# On Windows we can at least verify no exception bubbles up
# --------------------------------------------------------------------------- #

@pytest.mark.skipif(sys.platform != "win32",
                    reason="Windows uniquement")
class TestFondEcranSousWindows:
    def test_fond_ecran_actuel_ne_leve_rien(self):
        # may return a path or None depending on the desktop state; no exception
        current_wallpaper()

    def test_avancer_diaporama_ne_leve_rien(self):
        advance_slideshow()


# --------------------------------------------------------------------------- #
# Internal contracts: vtable indices, return type of _build_images_array
# (bugs that caused the "slideshow" checkbox to crash).
# --------------------------------------------------------------------------- #

class TestContratsWallpaper:
    """These checks are platform-independent: they cover constants and
    invariants (`_release_desktop` must accept anything without raising)."""

    def test_indices_vtable_conformes_a_idesktopwallpaper(self):
        # Indices must match the Microsoft vtable: SetSlideshow=12,
        # AdvanceSlideshow=16. An off-by-one called GetPosition instead
        # and corrupted memory → crash.
        assert system._VT_RELEASE == 2
        assert system._VT_GETWALLPAPER == 4
        assert system._VT_GETMONITORDEVICEPATHAT == 5
        assert system._VT_GETMONITORDEVICEPATHCOUNT == 6
        assert system._VT_SET_SLIDESHOW == 12
        assert system._VT_ADVANCESLIDESHOW == 16

    def test_liberer_bureau_ignore_les_types_bizarres(self):
        # Robustness: calling _release_desktop with something other than a
        # c_void_p must never raise (set_slideshow_dir's finally relies on it).
        system._release_desktop(None, False)
        system._release_desktop((None, None), False)
        system._release_desktop("pas un pointeur", False)
        # no exception: success


# --------------------------------------------------------------------------- #
# Simulations: sys.platform = "win32" but COM/ctypes unavailable
# --------------------------------------------------------------------------- #

@pytest.mark.skipif(sys.platform == "win32",
                    reason="simulation only valid off Windows "
                           "(on Windows, ctypes.windll and COM are real)")
class TestSimulationsWin:
    """Checks that the Windows code degrades gracefully when COM/winreg
    are missing (which is the case when running the tests on Linux)."""

    def test_instancier_bureau_gerre_erreur_ctypes(self, monkeypatch):
        # on Linux, ctypes.windll does not exist: the AttributeError must
        # be caught and translated to (None, False)
        monkeypatch.setattr(sys, "platform", "win32")
        ptr, uninit = system._instantiate_desktop()
        assert ptr is None
        assert uninit is False

    def test_fond_ecran_actuel_retourne_none_si_com_ko(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        assert current_wallpaper() is None

    def test_avancer_diaporama_silencieux_si_com_ko(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        advance_slideshow()  # must not raise anything

    # `autostart` imports `winreg` unconditionally once we
    # are on Windows. Simulating that import's failure on Linux does not
    # match any real situation — Windows always has `winreg` — so no
    # dedicated test is added.


# --------------------------------------------------------------------------- #
# open_dir: non-blocking call (no subprocess is actually launched)
# --------------------------------------------------------------------------- #

class TestOuvrirDossier:
    def test_cree_dossier_manquant(self, tmp_path, monkeypatch):
        from unittest.mock import MagicMock
        cible = tmp_path / "pas-encore"
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setattr("Glaneur.system.subprocess.Popen",
                            MagicMock(return_value=None))
        system.open_dir(cible)
        assert cible.is_dir()

    def test_choisit_startfile_sous_windows(self, tmp_path, monkeypatch):
        from unittest.mock import MagicMock
        monkeypatch.setattr(sys, "platform", "win32")
        faux = MagicMock()
        # os.startfile does not exist on Linux: install it for the test
        import os
        monkeypatch.setattr(os, "startfile", faux, raising=False)
        system.open_dir(tmp_path)
        assert faux.called

    def test_choisit_open_sous_macos(self, tmp_path, monkeypatch):
        from unittest.mock import MagicMock
        monkeypatch.setattr(sys, "platform", "darwin")
        popen = MagicMock()
        monkeypatch.setattr("Glaneur.system.subprocess.Popen", popen)
        system.open_dir(tmp_path)
        args = popen.call_args.args[0]
        assert args[0] == "open"

    def test_choisit_xdg_open_ailleurs(self, tmp_path, monkeypatch):
        from unittest.mock import MagicMock
        monkeypatch.setattr(sys, "platform", "linux")
        popen = MagicMock()
        monkeypatch.setattr("Glaneur.system.subprocess.Popen", popen)
        system.open_dir(tmp_path)
        args = popen.call_args.args[0]
        assert args[0] == "xdg-open"
