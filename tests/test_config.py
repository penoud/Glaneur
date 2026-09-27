"""Tests for the persisted configuration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from Glaneur.config import (
    DJANGOPLICITY_FORMATS,
    INTERVALS,
    SORT_MODES,
    SOURCE_TYPES,
    Config,
    config_dir,
    default_images_dir,
    migrate_from_legacy_name,
)

# --------------------------------------------------------------------------- #
# Default location of the configuration file
# --------------------------------------------------------------------------- #

class TestEmplacements:
    def test_dossier_config_renvoie_chemin(self):
        d = config_dir()
        assert isinstance(d, Path)
        assert d.name  # non-empty

    def test_dossier_images_defaut_pointe_vers_home(self):
        d = default_images_dir()
        # must contain the application name somewhere in the path
        assert "Glaneur" in str(d)

    def test_dossier_config_windows(self, monkeypatch, tmp_path):
        monkeypatch.setattr("sys.platform", "win32")
        monkeypatch.setenv("APPDATA", str(tmp_path))
        d = config_dir()
        assert d == tmp_path / "Glaneur"

    def test_dossier_config_windows_sans_appdata(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "win32")
        monkeypatch.delenv("APPDATA", raising=False)
        d = config_dir()
        assert d.name == "Glaneur"
        assert "AppData" in str(d) or "Roaming" in str(d)

    def test_dossier_config_macos(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "darwin")
        d = config_dir()
        assert "Library" in str(d)
        assert d.name == "Glaneur"

    def test_dossier_config_linux_xdg(self, monkeypatch, tmp_path):
        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        d = config_dir()
        assert d == tmp_path / "glaneur"

    def test_dossier_config_linux_sans_xdg(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        d = config_dir()
        assert d.name == "glaneur"

    def test_dossier_images_defaut_repli_sur_home(self, monkeypatch, tmp_path):
        # no "Pictures"/"Images" directory present -> fall back to ~/Glaneur
        vide = tmp_path / "vide-home"
        vide.mkdir()
        monkeypatch.setattr(Path, "home", classmethod(lambda _cls: vide))
        d = default_images_dir()
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

        source = migrate_from_legacy_name()

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

        source = migrate_from_legacy_name()

        assert source is None
        assert (cible / "config.json").read_text() == "actuel"

    def test_no_op_si_pas_d_ancien(self, monkeypatch, tmp_path):
        monkeypatch.setenv("APPDATA", str(tmp_path))
        monkeypatch.setattr("sys.platform", "win32")
        assert migrate_from_legacy_name() is None

    def test_xdg_linux(self, monkeypatch, tmp_path):
        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        ancien = tmp_path / "wp-image-downloader"
        ancien.mkdir()
        (ancien / "config.json").write_text("x")

        source = migrate_from_legacy_name()

        assert source == ancien
        assert (tmp_path / "glaneur" / "config.json").read_text() == "x"


# --------------------------------------------------------------------------- #
# Load / save
# --------------------------------------------------------------------------- #

class TestChargement:
    def test_fichier_absent_valeurs_par_defaut(self, tmp_path):
        cfg = Config.load(tmp_path / "absent.json")
        assert cfg.interval_hours == 24
        assert cfg.sort_mode == "galerie"
        assert cfg.min_width == 800
        assert cfg.verify_integrity is False
        assert cfg.slideshow_dir is False
        assert cfg.check_updates_on_start is True
        # dossier populated even without a file
        assert cfg.target_dir

    def test_relecture(self, tmp_path):
        chemin = tmp_path / "c.json"
        c = Config.load(chemin)
        c.interval_hours = 12
        c.min_width = 1200
        c.sort_mode = "date"
        c.slideshow_dir = True
        c.check_updates_on_start = False
        c.save()

        c2 = Config.load(chemin)
        assert c2.interval_hours == 12
        assert c2.min_width == 1200
        assert c2.sort_mode == "date"
        assert c2.slideshow_dir is True
        assert c2.check_updates_on_start is False

    def test_verifier_maj_demarrage_absent_du_json_reprend_defaut(self, tmp_path):
        # config pre-dating the field addition: must re-read without error
        # and fall back to the default value True.
        chemin = tmp_path / "c.json"
        chemin.write_text(json.dumps({"interval_hours": 12}))
        c = Config.load(chemin)
        assert c.check_updates_on_start is True

    def test_json_invalide_recharge_par_defaut(self, tmp_path):
        chemin = tmp_path / "c.json"
        chemin.write_text("{pas du json")
        c = Config.load(chemin)
        assert c.interval_hours == 24   # default recovered

    def test_cles_inconnues_ignorees(self, tmp_path):
        chemin = tmp_path / "c.json"
        chemin.write_text(json.dumps({
            "interval_hours": 6,
            "cle_inconnue": "poubelle",
            "_path": "/attaque/tentative",   # private attribute, ignored
        }))
        c = Config.load(chemin)
        assert c.interval_hours == 6
        assert not hasattr(c, "cle_inconnue")
        # _path is our internal attribute, not the one from JSON
        assert c._path == chemin

    def test_sauver_atomique_pas_de_tmp(self, tmp_path):
        c = Config.load(tmp_path / "c.json")
        c.save()
        assert not (tmp_path / "c.json.tmp").exists()
        assert (tmp_path / "c.json").exists()

    def test_sauver_omet_chemin_prive(self, tmp_path):
        chemin = tmp_path / "c.json"
        c = Config.load(chemin)
        c.save()
        donnees = json.loads(chemin.read_text())
        # `_path` must not leak into the JSON
        assert "_path" not in donnees

    def test_dossier_par_defaut_conserve_apres_sauvegarde(self, tmp_path):
        chemin = tmp_path / "c.json"
        c = Config.load(chemin)
        d0 = c.target_dir
        c.save()
        c2 = Config.load(chemin)
        assert c2.target_dir == d0


# --------------------------------------------------------------------------- #
# Validation (clamping aberrant values)
# --------------------------------------------------------------------------- #

class TestValider:
    def _neuve(self, tmp_path):
        return Config.load(tmp_path / "c.json")

    def test_intervalle_inconnu_ramene_a_24(self, tmp_path):
        c = self._neuve(tmp_path)
        c.interval_hours = 999
        c.validate()
        assert c.interval_hours == 24

    def test_intervalle_manuel_admis(self, tmp_path):
        c = self._neuve(tmp_path)
        c.interval_hours = 0   # "Manual only"
        c.validate()
        assert c.interval_hours == 0

    def test_largeur_negative(self, tmp_path):
        c = self._neuve(tmp_path)
        c.min_width = -5
        c.validate()
        assert c.min_width == 0

    def test_largeur_trop_grande(self, tmp_path):
        c = self._neuve(tmp_path)
        c.min_width = 999_999
        c.validate()
        assert c.min_width == 10_000

    def test_largeur_flottant_accepte(self, tmp_path):
        c = self._neuve(tmp_path)
        c.min_width = 1234.7   # int cast
        c.validate()
        assert c.min_width == 1234

    def test_classement_inconnu_repart_galerie(self, tmp_path):
        c = self._neuve(tmp_path)
        c.sort_mode = "pouet"
        c.validate()
        assert c.sort_mode == "galerie"

    def test_delai_plancher(self, tmp_path):
        c = self._neuve(tmp_path)
        c.request_delay = 0.01
        c.validate()
        # floor at 0.2 to avoid hammering the server
        assert c.request_delay == pytest.approx(0.2)

    def test_delai_plafond(self, tmp_path):
        c = self._neuve(tmp_path)
        c.request_delay = 999
        c.validate()
        assert c.request_delay == 10.0

    def test_type_source_par_defaut_wordpress(self, tmp_path):
        # fresh config: type_source default = "wordpress", zero migration
        c = self._neuve(tmp_path)
        assert c.source_type == "wordpress"
        assert c.image_format == "Large"

    def test_type_source_inconnu_snap_wordpress(self, tmp_path):
        c = self._neuve(tmp_path)
        c.source_type = "n-importe-quoi"
        c.validate()
        assert c.source_type == "wordpress"

    def test_format_image_inconnu_snap_large(self, tmp_path):
        c = self._neuve(tmp_path)
        c.image_format = "Ultra"
        c.validate()
        assert c.image_format == "Large"

    def test_classement_snap_si_source_ne_le_supporte_pas(self, tmp_path):
        # Djangoplicity does not support "galerie": `valider` falls back to "date"
        c = self._neuve(tmp_path)
        c.source_type = "djangoplicity"
        c.sort_mode = "galerie"
        c.validate()
        assert c.sort_mode == "date"

    def test_classement_conserve_si_supporte(self, tmp_path):
        # WordPress supports "galerie": nothing to change
        c = self._neuve(tmp_path)
        c.source_type = "wordpress"
        c.sort_mode = "galerie"
        c.validate()
        assert c.sort_mode == "galerie"

    def test_v1038_config_charge_sans_champs_nouveaux(self, tmp_path):
        # config written by 1.0.38 (without type_source or format_image):
        # must re-read without error, with default values, and the
        # WordPress behavior is preserved.
        chemin = tmp_path / "c.json"
        chemin.write_text(json.dumps({
            "site": "https://old.example",
            "interval_hours": 6,
            "sort_mode": "galerie",
        }))
        c = Config.load(chemin)
        assert c.source_type == "wordpress"
        assert c.image_format == "Large"
        assert c.sort_mode == "galerie"   # not snapped because WP supports it


class TestConstantesSource:
    def test_types_source_contient_wordpress_et_djangoplicity(self):
        # sanity check: both keys expected by the engine are present.
        valeurs = set(SOURCE_TYPES.values())
        assert "wordpress" in valeurs
        assert "djangoplicity" in valeurs

    def test_formats_djangoplicity_contient_large(self):
        assert "Large" in DJANGOPLICITY_FORMATS.values()


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
        assert c.retry_after == ""
        assert c.backoff_level == 0

    def test_round_trip_retenter_apres_et_backoff(self, tmp_path):
        """Saving then reloading preserves both deferral fields."""
        chemin = tmp_path / "c.json"
        c = Config.load(chemin)
        c.retry_after = "2026-09-27T10:00:00"
        c.backoff_level = 2
        c.save()

        c2 = Config.load(chemin)
        assert c2.retry_after == "2026-09-27T10:00:00"
        assert c2.backoff_level == 2

    def test_config_sans_champs_defer_charge_avec_defauts(self, tmp_path):
        """An older config.json without the deferral fields loads with defaults."""
        chemin = tmp_path / "c.json"
        chemin.write_text(json.dumps({"interval_hours": 6}))
        c = Config.load(chemin)
        assert c.retry_after == ""
        assert c.backoff_level == 0

    def test_valider_borne_backoff_niveau_negatif(self, tmp_path):
        """Valider clamps a negative backoff level to zero."""
        c = Config.load(tmp_path / "c.json")
        c.backoff_level = -3
        c.validate()
        assert c.backoff_level == 0

    def test_valider_borne_backoff_niveau_trop_haut(self, tmp_path):
        """Valider clamps a backoff level above the ceiling down to 2."""
        c = Config.load(tmp_path / "c.json")
        c.backoff_level = 5
        c.validate()
        assert c.backoff_level == 2


class TestLibelles:
    def test_libelle_intervalle_connu(self, tmp_path):
        c = Config.load(tmp_path / "c.json")
        for libelle, heures in INTERVALS.items():
            c.interval_hours = heures
            assert c.interval_label == libelle

    def test_libelle_intervalle_repli(self, tmp_path):
        c = Config.load(tmp_path / "c.json")
        c.interval_hours = -1   # not listed
        assert c.interval_label == "Une fois par jour"

    def test_libelle_classement_connu(self, tmp_path):
        c = Config.load(tmp_path / "c.json")
        for libelle, valeur in SORT_MODES.items():
            c.sort_mode = valeur
            assert c.sort_mode_label == libelle

    def test_libelle_classement_repli(self, tmp_path):
        c = Config.load(tmp_path / "c.json")
        c.sort_mode = "inconnu"
        assert c.sort_mode_label == "Par galerie"


# --------------------------------------------------------------------------- #
# Batch 4b: legacy FR key compat shim
# --------------------------------------------------------------------------- #

class TestLegacyFieldAliases:
    """A ``config.json`` written before batch 4b uses FR keys. It must load
    without loss and get rewritten with EN keys on the next save.
    """

    _LEGACY_JSON: dict = {  # noqa: RUF012 — read-only test fixture
        "site": "https://example.com",
        "dossier": "/tmp/glaneur-old",
        "intervalle_heures": 12,
        "largeur_min": 1200,
        "classement": "date",
        "type_source": "djangoplicity",
        "format_image": "Small",
        "verifier_integrite": True,
        "diaporama_dossier": True,
        "delai_requetes": 1.5,
        "derniere_execution": "2026-09-01T12:00:00",
        "retenter_apres": "2026-09-01T13:00:00",
        "backoff_niveau": 1,
        "lancer_au_demarrage": True,
        "fermer_dans_barre": False,
        "notifications": False,
        "verifier_maj_demarrage": False,
        "langue": "en",
    }

    def test_charge_les_cles_fr(self, tmp_path):
        """Every legacy FR key is read into its EN field."""
        chemin = tmp_path / "config.json"
        chemin.write_text(json.dumps(self._LEGACY_JSON), encoding="utf-8")
        c = Config.load(chemin)
        assert c.target_dir == "/tmp/glaneur-old"
        assert c.interval_hours == 12
        assert c.min_width == 1200
        assert c.sort_mode == "date"
        assert c.source_type == "djangoplicity"
        assert c.image_format == "Small"
        assert c.verify_integrity is True
        assert c.slideshow_dir is True
        assert c.request_delay == 1.5
        assert c.last_run == "2026-09-01T12:00:00"
        assert c.retry_after == "2026-09-01T13:00:00"
        assert c.backoff_level == 1
        assert c.run_at_startup is True
        assert c.close_to_tray is False
        assert c.check_updates_on_start is False
        assert c.language == "en"

    def test_save_apres_load_reecrit_en_cles_en(self, tmp_path):
        """A load → save cycle migrates a legacy file to EN keys silently."""
        chemin = tmp_path / "config.json"
        chemin.write_text(json.dumps(self._LEGACY_JSON), encoding="utf-8")
        Config.load(chemin).save()
        reecrit = json.loads(chemin.read_text(encoding="utf-8"))
        for cle in self._LEGACY_JSON:
            if cle in ("site", "notifications"):
                continue   # always EN
            assert cle not in reecrit, f"legacy key {cle!r} still on disk"
        for cle in ("target_dir", "interval_hours", "sort_mode", "source_type"):
            assert cle in reecrit

    def test_json_hybride_prefere_en_puis_fr(self, tmp_path):
        """When both an EN and FR key are present, the EN wins.

        The load loop iterates over ``brut.items()``: whichever key comes
        last in the dict wins. Since Python 3.7 dicts preserve insertion
        order, we craft the file to put EN after FR — the EN wins.
        """
        chemin = tmp_path / "config.json"
        chemin.write_text(json.dumps({
            "dossier": "/tmp/via-fr",
            "target_dir": "/tmp/via-en",
        }), encoding="utf-8")
        c = Config.load(chemin)
        assert c.target_dir == "/tmp/via-en"
