"""Tests des intégrations système.

La partie COM (`IDesktopWallpaper`) n'est vérifiable que sous Windows ; ici on
teste au minimum que toutes les fonctions ont un comportement silencieux hors
Windows, sans lever d'exception ni exiger de dépendance Windows.
"""

from __future__ import annotations

import sys

import pytest

from WpImageDownloader import systeme
from WpImageDownloader.systeme import (
    avancer_diaporama,
    commande_lancement,
    demarrage_automatique,
    demarrage_automatique_actif,
    definir_dossier_diaporama,
    est_gele,
    fond_ecran_actuel,
)


# --------------------------------------------------------------------------- #
# est_gele / commande_lancement
# --------------------------------------------------------------------------- #

class TestEstGele:
    def test_defaut_faux(self, monkeypatch):
        monkeypatch.delattr(sys, "frozen", raising=False)
        assert est_gele() is False

    def test_frozen(self, monkeypatch):
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        assert est_gele() is True


class TestCommandeLancement:
    def test_dev_utilise_app_py(self, monkeypatch):
        monkeypatch.delattr(sys, "frozen", raising=False)
        cmd = commande_lancement()
        assert "app.py" in cmd
        assert "--reduit" in cmd

    def test_frozen_utilise_executable(self, monkeypatch):
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        cmd = commande_lancement()
        assert "app.py" not in cmd
        assert "--reduit" in cmd


# --------------------------------------------------------------------------- #
# Démarrage automatique (Windows uniquement, silencieux ailleurs)
# --------------------------------------------------------------------------- #

@pytest.mark.skipif(sys.platform == "win32",
                    reason="hors Windows uniquement")
class TestDemarrageHorsWindows:
    def test_activer_renvoie_false(self):
        assert demarrage_automatique(True) is False

    def test_desactiver_renvoie_false(self):
        assert demarrage_automatique(False) is False

    def test_actif_renvoie_false(self):
        assert demarrage_automatique_actif() is False


# --------------------------------------------------------------------------- #
# Fond d'écran (COM Windows) : silencieux hors plateforme
# --------------------------------------------------------------------------- #

@pytest.mark.skipif(sys.platform == "win32",
                    reason="hors Windows uniquement")
class TestFondEcranHorsWindows:
    def test_definir_dossier_diaporama_renvoie_false(self, tmp_path):
        assert definir_dossier_diaporama(tmp_path) is False

    def test_fond_ecran_actuel_renvoie_none(self):
        assert fond_ecran_actuel() is None

    def test_avancer_diaporama_ne_leve_rien(self):
        # aucun retour attendu, seul le silence est un succès
        avancer_diaporama()

    def test_instancier_bureau_renvoie_none(self):
        ptr, uninit = systeme._instancier_bureau()
        assert ptr is None
        assert uninit is False


# --------------------------------------------------------------------------- #
# Sous Windows on peut au moins vérifier qu'aucune exception ne remonte
# --------------------------------------------------------------------------- #

@pytest.mark.skipif(sys.platform != "win32",
                    reason="Windows uniquement")
class TestFondEcranSousWindows:
    def test_fond_ecran_actuel_ne_leve_rien(self):
        # peut renvoyer un chemin ou None selon l'état du bureau ; pas d'exception
        fond_ecran_actuel()

    def test_avancer_diaporama_ne_leve_rien(self):
        avancer_diaporama()


# --------------------------------------------------------------------------- #
# Contrats internes : indices vtable, type de retour de _creer_tableau_images
# (bugs qui ont provoqué le crash de la case « diaporama »).
# --------------------------------------------------------------------------- #

class TestContratsWallpaper:
    """Ces vérifications sont indépendantes de la plateforme : elles portent
    sur des constantes et sur des invariants (`_liberer_bureau` doit accepter
    n'importe quoi sans lever)."""

    def test_indices_vtable_conformes_a_idesktopwallpaper(self):
        # Les indices doivent correspondre à la vtable Microsoft : SetSlideshow=12,
        # AdvanceSlideshow=16. Une valeur off-by-one appelait GetPosition à la
        # place et corrompait la mémoire → crash.
        assert systeme._VT_RELEASE == 2
        assert systeme._VT_GETWALLPAPER == 4
        assert systeme._VT_GETMONITORDEVICEPATHAT == 5
        assert systeme._VT_GETMONITORDEVICEPATHCOUNT == 6
        assert systeme._VT_SET_SLIDESHOW == 12
        assert systeme._VT_ADVANCESLIDESHOW == 16

    def test_liberer_bureau_ignore_les_types_bizarres(self):
        # Robustesse : appeler _liberer_bureau avec autre chose qu'un c_void_p
        # ne doit jamais lever (le finally de definir_dossier_diaporama en dépend).
        systeme._liberer_bureau(None, False)
        systeme._liberer_bureau((None, None), False)
        systeme._liberer_bureau("pas un pointeur", False)
        # aucune exception : succès


# --------------------------------------------------------------------------- #
# Simulations : sys.platform = "win32" mais COM/ctypes non disponibles
# --------------------------------------------------------------------------- #

@pytest.mark.skipif(
    sys.platform == "win32",
    reason="Ces tests simulent l'absence de COM/ctypes.windll ; sur un vrai "
    "Windows, ces dépendances sont présentes et le chemin dégradé n'est "
    "pas atteignable.",
)
class TestSimulationsWin:
    """Vérifie que le code Windows dégénère proprement quand COM/winreg
    ne sont pas là (ce qui est le cas quand on tourne les tests sur Linux)."""

    def test_instancier_bureau_gerre_erreur_ctypes(self, monkeypatch):
        # sur Linux, ctypes.windll n'existe pas : l'AttributeError doit être
        # attrapée et se traduire par (None, False)
        monkeypatch.setattr(sys, "platform", "win32")
        ptr, uninit = systeme._instancier_bureau()
        assert ptr is None
        assert uninit is False

    def test_fond_ecran_actuel_retourne_none_si_com_ko(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        assert fond_ecran_actuel() is None

    def test_avancer_diaporama_silencieux_si_com_ko(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        avancer_diaporama()  # ne doit rien lever

    # `demarrage_automatique` importe `winreg` de manière inconditionnelle
    # une fois qu'on est sous Windows. Simuler l'échec de cet import sur
    # Linux ne correspond à aucune situation réelle — Windows a toujours
    # `winreg` — donc on n'ajoute pas de test dédié.


# --------------------------------------------------------------------------- #
# ouvrir_dossier : appel non-bloquant (aucun subprocess réellement lancé)
# --------------------------------------------------------------------------- #

class TestOuvrirDossier:
    def test_cree_dossier_manquant(self, tmp_path, monkeypatch):
        from unittest.mock import MagicMock
        cible = tmp_path / "pas-encore"
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setattr("WpImageDownloader.systeme.subprocess.Popen",
                            MagicMock(return_value=None))
        systeme.ouvrir_dossier(cible)
        assert cible.is_dir()

    def test_choisit_startfile_sous_windows(self, tmp_path, monkeypatch):
        from unittest.mock import MagicMock
        monkeypatch.setattr(sys, "platform", "win32")
        faux = MagicMock()
        # os.startfile n'existe pas sous Linux : on l'installe pour le test
        import os
        monkeypatch.setattr(os, "startfile", faux, raising=False)
        systeme.ouvrir_dossier(tmp_path)
        assert faux.called

    def test_choisit_open_sous_macos(self, tmp_path, monkeypatch):
        from unittest.mock import MagicMock
        monkeypatch.setattr(sys, "platform", "darwin")
        popen = MagicMock()
        monkeypatch.setattr("WpImageDownloader.systeme.subprocess.Popen", popen)
        systeme.ouvrir_dossier(tmp_path)
        args = popen.call_args.args[0]
        assert args[0] == "open"

    def test_choisit_xdg_open_ailleurs(self, tmp_path, monkeypatch):
        from unittest.mock import MagicMock
        monkeypatch.setattr(sys, "platform", "linux")
        popen = MagicMock()
        monkeypatch.setattr("WpImageDownloader.systeme.subprocess.Popen", popen)
        systeme.ouvrir_dossier(tmp_path)
        args = popen.call_args.args[0]
        assert args[0] == "xdg-open"
