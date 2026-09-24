"""Tests de la configuration persistée."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from WpImageDownloader.config import (
    CLASSEMENTS,
    FORMATS_DJANGOPLICITY,
    INTERVALLES,
    TYPES_SOURCE,
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
        assert "WpImageDownloader" in str(d)

    def test_dossier_config_windows(self, monkeypatch, tmp_path):
        monkeypatch.setattr("sys.platform", "win32")
        monkeypatch.setenv("APPDATA", str(tmp_path))
        d = dossier_config()
        assert d == tmp_path / "WpImageDownloader"

    def test_dossier_config_windows_sans_appdata(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "win32")
        monkeypatch.delenv("APPDATA", raising=False)
        d = dossier_config()
        assert d.name == "WpImageDownloader"
        assert "AppData" in str(d) or "Roaming" in str(d)

    def test_dossier_config_macos(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "darwin")
        d = dossier_config()
        assert "Library" in str(d)
        assert d.name == "WpImageDownloader"

    def test_dossier_config_linux_xdg(self, monkeypatch, tmp_path):
        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        d = dossier_config()
        assert d == tmp_path / "wp-image-downloader"

    def test_dossier_config_linux_sans_xdg(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        d = dossier_config()
        assert d.name == "wp-image-downloader"

    def test_dossier_images_defaut_repli_sur_home(self, monkeypatch, tmp_path):
        # aucun dossier "Pictures"/"Images" présent -> repli sur ~/WpImageDownloader
        vide = tmp_path / "vide-home"
        vide.mkdir()
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: vide))
        d = dossier_images_defaut()
        assert d == vide / "WpImageDownloader"


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
        assert cfg.verifier_maj_demarrage is True
        # dossier renseigné même sans fichier
        assert cfg.dossier

    def test_relecture(self, tmp_path):
        chemin = tmp_path / "c.json"
        c = Config.charger(chemin)
        c.intervalle_heures = 12
        c.largeur_min = 1200
        c.classement = "date"
        c.diaporama_dossier = True
        c.verifier_maj_demarrage = False
        c.sauver()

        c2 = Config.charger(chemin)
        assert c2.intervalle_heures == 12
        assert c2.largeur_min == 1200
        assert c2.classement == "date"
        assert c2.diaporama_dossier is True
        assert c2.verifier_maj_demarrage is False

    def test_verifier_maj_demarrage_absent_du_json_reprend_defaut(self, tmp_path):
        # config antérieure à l'ajout du champ : doit se relire sans erreur
        # et retomber sur la valeur par défaut True.
        chemin = tmp_path / "c.json"
        chemin.write_text(json.dumps({"intervalle_heures": 12}))
        c = Config.charger(chemin)
        assert c.verifier_maj_demarrage is True

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

    def test_type_source_par_defaut_wordpress(self, tmp_path):
        # config vierge : type_source défaut = "wordpress", zéro migration
        c = self._neuve(tmp_path)
        assert c.type_source == "wordpress"
        assert c.format_image == "Large"

    def test_type_source_inconnu_snap_wordpress(self, tmp_path):
        c = self._neuve(tmp_path)
        c.type_source = "n-importe-quoi"
        c.valider()
        assert c.type_source == "wordpress"

    def test_format_image_inconnu_snap_large(self, tmp_path):
        c = self._neuve(tmp_path)
        c.format_image = "Ultra"
        c.valider()
        assert c.format_image == "Large"

    def test_classement_snap_si_source_ne_le_supporte_pas(self, tmp_path):
        # Djangoplicity ne fait pas "galerie" : `valider` rabat sur "date"
        c = self._neuve(tmp_path)
        c.type_source = "djangoplicity"
        c.classement = "galerie"
        c.valider()
        assert c.classement == "date"

    def test_classement_conserve_si_supporte(self, tmp_path):
        # WordPress supporte "galerie" : rien à changer
        c = self._neuve(tmp_path)
        c.type_source = "wordpress"
        c.classement = "galerie"
        c.valider()
        assert c.classement == "galerie"

    def test_v1038_config_charge_sans_champs_nouveaux(self, tmp_path):
        # config écrite par 1.0.38 (sans type_source ni format_image) :
        # elle doit se relire sans erreur, avec les valeurs par défaut,
        # et le comportement WordPress est préservé.
        chemin = tmp_path / "c.json"
        chemin.write_text(json.dumps({
            "site": "https://old.example",
            "intervalle_heures": 6,
            "classement": "galerie",
        }))
        c = Config.charger(chemin)
        assert c.type_source == "wordpress"
        assert c.format_image == "Large"
        assert c.classement == "galerie"   # non snapée car WP la supporte


class TestConstantesSource:
    def test_types_source_contient_wordpress_et_djangoplicity(self):
        # sanity check : les deux clés attendues par l'engine sont là.
        valeurs = set(TYPES_SOURCE.values())
        assert "wordpress" in valeurs
        assert "djangoplicity" in valeurs

    def test_formats_djangoplicity_contient_large(self):
        assert "Large" in FORMATS_DJANGOPLICITY.values()


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
