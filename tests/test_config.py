"""Tests de la configuration persistée."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from WpImageDownloader.config import (
    CLASSEMENTS,
    INTERVALLES,
    Config,
    dossier_config,
    dossier_images_defaut,
)


# --------------------------------------------------------------------------- #
# Emplacement par défaut du fichier de configuration
# --------------------------------------------------------------------------- #

class TestEmplacements:
    def test_dossier_config_renvoie_chemin(self):
        d = dossier_config()
        assert isinstance(d, Path)
        assert d.name  # non vide

    def test_dossier_images_defaut_pointe_vers_home(self):
        d = dossier_images_defaut()
        # doit contenir le nom d'application quelque part dans le chemin
        assert "Servette FC" in str(d)

    def test_dossier_config_windows(self, monkeypatch, tmp_path):
        monkeypatch.setattr("sys.platform", "win32")
        monkeypatch.setenv("APPDATA", str(tmp_path))
        d = dossier_config()
        assert d == tmp_path / "ServetteDownloader"

    def test_dossier_config_windows_sans_appdata(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "win32")
        monkeypatch.delenv("APPDATA", raising=False)
        d = dossier_config()
        assert d.name == "ServetteDownloader"
        assert "AppData" in str(d) or "Roaming" in str(d)

    def test_dossier_config_macos(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "darwin")
        d = dossier_config()
        assert "Library" in str(d)
        assert d.name == "ServetteDownloader"

    def test_dossier_config_linux_xdg(self, monkeypatch, tmp_path):
        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        d = dossier_config()
        assert d == tmp_path / "servette-downloader"

    def test_dossier_config_linux_sans_xdg(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        d = dossier_config()
        assert d.name == "servette-downloader"

    def test_dossier_images_defaut_repli_sur_home(self, monkeypatch, tmp_path):
        # aucun dossier "Pictures"/"Images" présent → repli sur ~/Servette FC
        vide = tmp_path / "vide-home"
        vide.mkdir()
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: vide))
        d = dossier_images_defaut()
        assert d == vide / "Servette FC"


# --------------------------------------------------------------------------- #
# Chargement / sauvegarde
# --------------------------------------------------------------------------- #

class TestChargement:
    def test_fichier_absent_valeurs_par_defaut(self, tmp_path):
        cfg = Config.charger(tmp_path / "absent.json")
        assert cfg.intervalle_heures == 24
        assert cfg.classement == "galerie"
        assert cfg.largeur_min == 800
        assert cfg.verifier_integrite is False
        assert cfg.diaporama_dossier is False
        # dossier renseigné même sans fichier
        assert cfg.dossier

    def test_relecture(self, tmp_path):
        chemin = tmp_path / "c.json"
        c = Config.charger(chemin)
        c.intervalle_heures = 12
        c.largeur_min = 1200
        c.classement = "date"
        c.diaporama_dossier = True
        c.sauver()

        c2 = Config.charger(chemin)
        assert c2.intervalle_heures == 12
        assert c2.largeur_min == 1200
        assert c2.classement == "date"
        assert c2.diaporama_dossier is True

    def test_json_invalide_recharge_par_defaut(self, tmp_path):
        chemin = tmp_path / "c.json"
        chemin.write_text("{pas du json")
        c = Config.charger(chemin)
        assert c.intervalle_heures == 24   # défaut recouvré

    def test_cles_inconnues_ignorees(self, tmp_path):
        chemin = tmp_path / "c.json"
        chemin.write_text(json.dumps({
            "intervalle_heures": 6,
            "cle_inconnue": "poubelle",
            "_chemin": "/attaque/tentative",   # attribut privé, ignoré
        }))
        c = Config.charger(chemin)
        assert c.intervalle_heures == 6
        assert not hasattr(c, "cle_inconnue")
        # _chemin est notre attribut interne, pas celui du JSON
        assert c._chemin == chemin

    def test_sauver_atomique_pas_de_tmp(self, tmp_path):
        c = Config.charger(tmp_path / "c.json")
        c.sauver()
        assert not (tmp_path / "c.json.tmp").exists()
        assert (tmp_path / "c.json").exists()

    def test_sauver_omet_chemin_prive(self, tmp_path):
        chemin = tmp_path / "c.json"
        c = Config.charger(chemin)
        c.sauver()
        donnees = json.loads(chemin.read_text())
        # `_chemin` ne doit pas fuiter dans le JSON
        assert "_chemin" not in donnees

    def test_dossier_par_defaut_conserve_apres_sauvegarde(self, tmp_path):
        chemin = tmp_path / "c.json"
        c = Config.charger(chemin)
        d0 = c.dossier
        c.sauver()
        c2 = Config.charger(chemin)
        assert c2.dossier == d0


# --------------------------------------------------------------------------- #
# Validation (clamp des valeurs aberrantes)
# --------------------------------------------------------------------------- #

class TestValider:
    def _neuve(self, tmp_path):
        return Config.charger(tmp_path / "c.json")

    def test_intervalle_inconnu_ramene_a_24(self, tmp_path):
        c = self._neuve(tmp_path)
        c.intervalle_heures = 999
        c.valider()
        assert c.intervalle_heures == 24

    def test_intervalle_manuel_admis(self, tmp_path):
        c = self._neuve(tmp_path)
        c.intervalle_heures = 0   # « Manuel uniquement »
        c.valider()
        assert c.intervalle_heures == 0

    def test_largeur_negative(self, tmp_path):
        c = self._neuve(tmp_path)
        c.largeur_min = -5
        c.valider()
        assert c.largeur_min == 0

    def test_largeur_trop_grande(self, tmp_path):
        c = self._neuve(tmp_path)
        c.largeur_min = 999_999
        c.valider()
        assert c.largeur_min == 10_000

    def test_largeur_flottant_accepte(self, tmp_path):
        c = self._neuve(tmp_path)
        c.largeur_min = 1234.7   # cast int
        c.valider()
        assert c.largeur_min == 1234

    def test_classement_inconnu_repart_galerie(self, tmp_path):
        c = self._neuve(tmp_path)
        c.classement = "pouet"
        c.valider()
        assert c.classement == "galerie"

    def test_delai_plancher(self, tmp_path):
        c = self._neuve(tmp_path)
        c.delai_requetes = 0.01
        c.valider()
        # plancher à 0.2 pour ne pas marteler le serveur
        assert c.delai_requetes == pytest.approx(0.2)

    def test_delai_plafond(self, tmp_path):
        c = self._neuve(tmp_path)
        c.delai_requetes = 999
        c.valider()
        assert c.delai_requetes == 10.0


# --------------------------------------------------------------------------- #
# Libellés d'affichage (traduction interne ↔ interface)
# --------------------------------------------------------------------------- #

class TestLibelles:
    def test_libelle_intervalle_connu(self, tmp_path):
        c = Config.charger(tmp_path / "c.json")
        for libelle, heures in INTERVALLES.items():
            c.intervalle_heures = heures
            assert c.libelle_intervalle == libelle

    def test_libelle_intervalle_repli(self, tmp_path):
        c = Config.charger(tmp_path / "c.json")
        c.intervalle_heures = -1   # non listé
        assert c.libelle_intervalle == "Une fois par jour"

    def test_libelle_classement_connu(self, tmp_path):
        c = Config.charger(tmp_path / "c.json")
        for libelle, valeur in CLASSEMENTS.items():
            c.classement = valeur
            assert c.libelle_classement == libelle

    def test_libelle_classement_repli(self, tmp_path):
        c = Config.charger(tmp_path / "c.json")
        c.classement = "inconnu"
        assert c.libelle_classement == "Par galerie"
