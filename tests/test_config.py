"""Tests de la configuration persistée."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from Glaneur.config import (
    CLASSEMENTS,
    FORMATS_DJANGOPLICITY,
    INTERVALLES,
    TYPES_SOURCE,
    Config,
    dossier_config,
    dossier_images_defaut,
    migrer_depuis_ancien_nom,
)

# --------------------------------------------------------------------------- #
# Default location of the configuration file
# --------------------------------------------------------------------------- #

class TestEmplacements:
    def test_dossier_config_renvoie_chemin(self):
        d = dossier_config()
        assert isinstance(d, Path)
        assert d.name  # non-empty

    def test_dossier_images_defaut_pointe_vers_home(self):
        d = dossier_images_defaut()
        # must contain the application name somewhere in the path
        assert "Glaneur" in str(d)

    def test_dossier_config_windows(self, monkeypatch, tmp_path):
        monkeypatch.setattr("sys.platform", "win32")
        monkeypatch.setenv("APPDATA", str(tmp_path))
        d = dossier_config()
        assert d == tmp_path / "Glaneur"

    def test_dossier_config_windows_sans_appdata(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "win32")
        monkeypatch.delenv("APPDATA", raising=False)
        d = dossier_config()
        assert d.name == "Glaneur"
        assert "AppData" in str(d) or "Roaming" in str(d)

    def test_dossier_config_macos(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "darwin")
        d = dossier_config()
        assert "Library" in str(d)
        assert d.name == "Glaneur"

    def test_dossier_config_linux_xdg(self, monkeypatch, tmp_path):
        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        d = dossier_config()
        assert d == tmp_path / "glaneur"

    def test_dossier_config_linux_sans_xdg(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        d = dossier_config()
        assert d.name == "glaneur"

    def test_dossier_images_defaut_repli_sur_home(self, monkeypatch, tmp_path):
        # no "Pictures"/"Images" directory present -> fall back to ~/Glaneur
        vide = tmp_path / "vide-home"
        vide.mkdir()
        monkeypatch.setattr(Path, "home", classmethod(lambda _cls: vide))
        d = dossier_images_defaut()
        assert d == vide / "Glaneur"


# --------------------------------------------------------------------------- #
# Migration from the legacy WpImageDownloader name
# --------------------------------------------------------------------------- #

class TestMigrationAncienNom:
    def test_copie_ancienne_config_si_cible_absente(self, monkeypatch, tmp_path):
        # Simulate a populated legacy `%APPDATA%\WpImageDownloader\`
        # directory and a non-existent new target `%APPDATA%\Glaneur\`.
        monkeypatch.setenv("APPDATA", str(tmp_path))
        monkeypatch.setattr("sys.platform", "win32")
        ancien = tmp_path / "WpImageDownloader"
        ancien.mkdir()
        (ancien / "config.json").write_text('{"site": "https://ex.com"}')
        (ancien / "logs").mkdir()
        (ancien / "logs" / "app.log").write_text("historique\n")

        source = migrer_depuis_ancien_nom()

        assert source == ancien
        cible = tmp_path / "Glaneur"
        assert (cible / "config.json").read_text() == '{"site": "https://ex.com"}'
        assert (cible / "logs" / "app.log").read_text() == "historique\n"
        # The legacy directory remains intact (copy, not move)
        assert (ancien / "config.json").exists()

    def test_ne_ecrase_pas_config_glaneur_existante(self, monkeypatch, tmp_path):
        monkeypatch.setenv("APPDATA", str(tmp_path))
        monkeypatch.setattr("sys.platform", "win32")
        ancien = tmp_path / "WpImageDownloader"
        ancien.mkdir()
        (ancien / "config.json").write_text("ancien")
        cible = tmp_path / "Glaneur"
        cible.mkdir()
        (cible / "config.json").write_text("actuel")

        source = migrer_depuis_ancien_nom()

        assert source is None
        assert (cible / "config.json").read_text() == "actuel"

    def test_no_op_si_pas_d_ancien(self, monkeypatch, tmp_path):
        monkeypatch.setenv("APPDATA", str(tmp_path))
        monkeypatch.setattr("sys.platform", "win32")
        assert migrer_depuis_ancien_nom() is None

    def test_xdg_linux(self, monkeypatch, tmp_path):
        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        ancien = tmp_path / "wp-image-downloader"
        ancien.mkdir()
        (ancien / "config.json").write_text("x")

        source = migrer_depuis_ancien_nom()

        assert source == ancien
        assert (tmp_path / "glaneur" / "config.json").read_text() == "x"


# --------------------------------------------------------------------------- #
# Load / save
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
        # dossier populated even without a file
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
        # config pre-dating the field addition: must re-read without error
        # and fall back to the default value True.
        chemin = tmp_path / "c.json"
        chemin.write_text(json.dumps({"intervalle_heures": 12}))
        c = Config.charger(chemin)
        assert c.verifier_maj_demarrage is True

    def test_json_invalide_recharge_par_defaut(self, tmp_path):
        chemin = tmp_path / "c.json"
        chemin.write_text("{pas du json")
        c = Config.charger(chemin)
        assert c.intervalle_heures == 24   # default recovered

    def test_cles_inconnues_ignorees(self, tmp_path):
        chemin = tmp_path / "c.json"
        chemin.write_text(json.dumps({
            "intervalle_heures": 6,
            "cle_inconnue": "poubelle",
            "_chemin": "/attaque/tentative",   # private attribute, ignored
        }))
        c = Config.charger(chemin)
        assert c.intervalle_heures == 6
        assert not hasattr(c, "cle_inconnue")
        # _chemin is our internal attribute, not the one from JSON
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
        # `_chemin` must not leak into the JSON
        assert "_chemin" not in donnees

    def test_dossier_par_defaut_conserve_apres_sauvegarde(self, tmp_path):
        chemin = tmp_path / "c.json"
        c = Config.charger(chemin)
        d0 = c.dossier
        c.sauver()
        c2 = Config.charger(chemin)
        assert c2.dossier == d0


# --------------------------------------------------------------------------- #
# Validation (clamping aberrant values)
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
        c.intervalle_heures = 0   # "Manual only"
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
        c.largeur_min = 1234.7   # int cast
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
        # floor at 0.2 to avoid hammering the server
        assert c.delai_requetes == pytest.approx(0.2)

    def test_delai_plafond(self, tmp_path):
        c = self._neuve(tmp_path)
        c.delai_requetes = 999
        c.valider()
        assert c.delai_requetes == 10.0

    def test_type_source_par_defaut_wordpress(self, tmp_path):
        # fresh config: type_source default = "wordpress", zero migration
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
        # Djangoplicity does not support "galerie": `valider` falls back to "date"
        c = self._neuve(tmp_path)
        c.type_source = "djangoplicity"
        c.classement = "galerie"
        c.valider()
        assert c.classement == "date"

    def test_classement_conserve_si_supporte(self, tmp_path):
        # WordPress supports "galerie": nothing to change
        c = self._neuve(tmp_path)
        c.type_source = "wordpress"
        c.classement = "galerie"
        c.valider()
        assert c.classement == "galerie"

    def test_v1038_config_charge_sans_champs_nouveaux(self, tmp_path):
        # config written by 1.0.38 (without type_source or format_image):
        # must re-read without error, with default values, and the
        # WordPress behavior is preserved.
        chemin = tmp_path / "c.json"
        chemin.write_text(json.dumps({
            "site": "https://old.example",
            "intervalle_heures": 6,
            "classement": "galerie",
        }))
        c = Config.charger(chemin)
        assert c.type_source == "wordpress"
        assert c.format_image == "Large"
        assert c.classement == "galerie"   # not snapped because WP supports it


class TestConstantesSource:
    def test_types_source_contient_wordpress_et_djangoplicity(self):
        # sanity check: both keys expected by the engine are present.
        valeurs = set(TYPES_SOURCE.values())
        assert "wordpress" in valeurs
        assert "djangoplicity" in valeurs

    def test_formats_djangoplicity_contient_large(self):
        assert "Large" in FORMATS_DJANGOPLICITY.values()


# --------------------------------------------------------------------------- #
# Display labels (internal value ↔ UI label)
# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
# Deferral fields (lot 3: circuit-breaker / backoff persistence)
# --------------------------------------------------------------------------- #

class TestReportDiff:
    def test_defauts_retenter_apres_et_backoff(self):
        """Fresh Config exposes an empty retenter_apres and a zero backoff level."""
        c = Config()
        assert c.retenter_apres == ""
        assert c.backoff_niveau == 0

    def test_round_trip_retenter_apres_et_backoff(self, tmp_path):
        """Saving then reloading preserves both deferral fields."""
        chemin = tmp_path / "c.json"
        c = Config.charger(chemin)
        c.retenter_apres = "2026-09-27T10:00:00"
        c.backoff_niveau = 2
        c.sauver()

        c2 = Config.charger(chemin)
        assert c2.retenter_apres == "2026-09-27T10:00:00"
        assert c2.backoff_niveau == 2

    def test_config_sans_champs_defer_charge_avec_defauts(self, tmp_path):
        """An older config.json without the deferral fields loads with defaults."""
        chemin = tmp_path / "c.json"
        chemin.write_text(json.dumps({"intervalle_heures": 6}))
        c = Config.charger(chemin)
        assert c.retenter_apres == ""
        assert c.backoff_niveau == 0

    def test_valider_borne_backoff_niveau_negatif(self, tmp_path):
        """Valider clamps a negative backoff level to zero."""
        c = Config.charger(tmp_path / "c.json")
        c.backoff_niveau = -3
        c.valider()
        assert c.backoff_niveau == 0

    def test_valider_borne_backoff_niveau_trop_haut(self, tmp_path):
        """Valider clamps a backoff level above the ceiling down to 2."""
        c = Config.charger(tmp_path / "c.json")
        c.backoff_niveau = 5
        c.valider()
        assert c.backoff_niveau == 2


class TestLibelles:
    def test_libelle_intervalle_connu(self, tmp_path):
        c = Config.charger(tmp_path / "c.json")
        for libelle, heures in INTERVALLES.items():
            c.intervalle_heures = heures
            assert c.libelle_intervalle == libelle

    def test_libelle_intervalle_repli(self, tmp_path):
        c = Config.charger(tmp_path / "c.json")
        c.intervalle_heures = -1   # not listed
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
