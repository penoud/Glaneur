"""Tests for the persisted configuration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from Glaneur.config import (
    DJANGOPLICITY_FORMATS,
    INTERVALS,
    PROFILE_FIELDS,
    SCHEMA_VERSION,
    SORT_MODES,
    SOURCE_TYPES,
    Config,
    Profile,
    config_dir,
    default_images_dir,
    migrate_from_legacy_name,
)

# --------------------------------------------------------------------------- #
# Default location of the configuration file
# --------------------------------------------------------------------------- #

class TestLocations:
    def test_config_dir_returns_a_path(self):
        d = config_dir()
        assert isinstance(d, Path)
        assert d.name  # non-empty

    def test_default_images_dir_points_to_home(self):
        d = default_images_dir()
        # must contain the application name somewhere in the path
        assert "Glaneur" in str(d)

    def test_config_dir_windows(self, monkeypatch, tmp_path):
        monkeypatch.setattr("sys.platform", "win32")
        monkeypatch.setenv("APPDATA", str(tmp_path))
        d = config_dir()
        assert d == tmp_path / "Glaneur"

    def test_config_dir_windows_without_appdata(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "win32")
        monkeypatch.delenv("APPDATA", raising=False)
        d = config_dir()
        assert d.name == "Glaneur"
        assert "AppData" in str(d) or "Roaming" in str(d)

    def test_config_dir_macos(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "darwin")
        d = config_dir()
        assert "Library" in str(d)
        assert d.name == "Glaneur"

    def test_config_dir_linux_xdg(self, monkeypatch, tmp_path):
        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        d = config_dir()
        assert d == tmp_path / "glaneur"

    def test_config_dir_linux_without_xdg(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        d = config_dir()
        assert d.name == "glaneur"

    def test_default_images_dir_falls_back_to_home(self, monkeypatch, tmp_path):
        # no "Pictures"/"Images" directory present -> fall back to ~/Glaneur
        vide = tmp_path / "vide-home"
        vide.mkdir()
        monkeypatch.setattr(Path, "home", classmethod(lambda _cls: vide))
        d = default_images_dir()
        assert d == vide / "Glaneur"


# --------------------------------------------------------------------------- #
# Migration from the legacy WpImageDownloader name
# --------------------------------------------------------------------------- #

class TestLegacyNameMigration:
    def test_copies_legacy_config_when_target_missing(self, monkeypatch, tmp_path):
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

    def test_does_not_overwrite_existing_glaneur_config(self, monkeypatch, tmp_path):
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

    def test_noop_when_no_legacy(self, monkeypatch, tmp_path):
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

class TestLoad:
    def test_missing_file_uses_default_values(self, tmp_path):
        cfg = Config.load(tmp_path / "absent.json")
        assert cfg.interval_hours == 24
        assert cfg.sort_mode == "gallery"
        assert cfg.min_width == 800
        assert cfg.verify_integrity is False
        assert cfg.slideshow_dir is False
        assert cfg.check_updates_on_start is True
        # dossier populated even without a file
        assert cfg.target_dir

    def test_round_trip(self, tmp_path):
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

    def test_check_updates_on_start_missing_from_json_uses_default(self, tmp_path):
        # config pre-dating the field addition: must re-read without error
        # and fall back to the default value True.
        chemin = tmp_path / "c.json"
        chemin.write_text(json.dumps({"interval_hours": 12}))
        c = Config.load(chemin)
        assert c.check_updates_on_start is True

    def test_invalid_json_falls_back_to_defaults(self, tmp_path):
        chemin = tmp_path / "c.json"
        chemin.write_text("{pas du json")
        c = Config.load(chemin)
        assert c.interval_hours == 24   # default recovered

    def test_unknown_keys_are_ignored(self, tmp_path):
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

    def test_save_is_atomic_no_tmp_left(self, tmp_path):
        c = Config.load(tmp_path / "c.json")
        c.save()
        assert not (tmp_path / "c.json.tmp").exists()
        assert (tmp_path / "c.json").exists()

    def test_save_omits_private_path(self, tmp_path):
        chemin = tmp_path / "c.json"
        c = Config.load(chemin)
        c.save()
        donnees = json.loads(chemin.read_text())
        # `_path` must not leak into the JSON
        assert "_path" not in donnees

    def test_default_folder_kept_after_save(self, tmp_path):
        chemin = tmp_path / "c.json"
        c = Config.load(chemin)
        d0 = c.target_dir
        c.save()
        c2 = Config.load(chemin)
        assert c2.target_dir == d0


# --------------------------------------------------------------------------- #
# Validation (clamping aberrant values)
# --------------------------------------------------------------------------- #

class TestValidate:
    def _neuve(self, tmp_path):
        return Config.load(tmp_path / "c.json")

    def test_unknown_interval_snaps_to_24(self, tmp_path):
        c = self._neuve(tmp_path)
        c.interval_hours = 999
        c.validate()
        assert c.interval_hours == 24

    def test_manual_interval_is_accepted(self, tmp_path):
        c = self._neuve(tmp_path)
        c.interval_hours = 0   # "Manual only"
        c.validate()
        assert c.interval_hours == 0

    def test_negative_width(self, tmp_path):
        c = self._neuve(tmp_path)
        c.min_width = -5
        c.validate()
        assert c.min_width == 0

    def test_width_too_large(self, tmp_path):
        c = self._neuve(tmp_path)
        c.min_width = 999_999
        c.validate()
        assert c.min_width == 10_000

    def test_float_width_accepted(self, tmp_path):
        c = self._neuve(tmp_path)
        c.min_width = 1234.7   # int cast
        c.validate()
        assert c.min_width == 1234

    def test_unknown_sort_mode_falls_back_to_gallery(self, tmp_path):
        c = self._neuve(tmp_path)
        c.sort_mode = "pouet"
        c.validate()
        assert c.sort_mode == "gallery"

    def test_delay_floor(self, tmp_path):
        c = self._neuve(tmp_path)
        c.request_delay = 0.01
        c.validate()
        # floor at 0.2 to avoid hammering the server
        assert c.request_delay == pytest.approx(0.2)

    def test_delay_ceiling(self, tmp_path):
        c = self._neuve(tmp_path)
        c.request_delay = 999
        c.validate()
        assert c.request_delay == 10.0

    def test_default_source_type_is_wordpress(self, tmp_path):
        # fresh config: type_source default = "wordpress", zero migration
        c = self._neuve(tmp_path)
        assert c.source_type == "wordpress"
        assert c.image_format == "Large"

    def test_unknown_source_type_snaps_to_wordpress(self, tmp_path):
        c = self._neuve(tmp_path)
        c.source_type = "n-importe-quoi"
        c.validate()
        assert c.source_type == "wordpress"

    def test_unknown_image_format_snaps_to_large(self, tmp_path):
        c = self._neuve(tmp_path)
        c.image_format = "Ultra"
        c.validate()
        assert c.image_format == "Large"

    def test_sort_mode_snaps_when_source_does_not_support_it(self, tmp_path):
        # Djangoplicity does not support "gallery": `valider` falls back to "date"
        c = self._neuve(tmp_path)
        c.source_type = "djangoplicity"
        c.sort_mode = "gallery"
        c.validate()
        assert c.sort_mode == "date"

    def test_sort_mode_kept_when_supported(self, tmp_path):
        # WordPress supports "gallery": nothing to change
        c = self._neuve(tmp_path)
        c.source_type = "wordpress"
        c.sort_mode = "gallery"
        c.validate()
        assert c.sort_mode == "gallery"

    def test_v1038_config_loads_without_new_fields(self, tmp_path):
        # config written by 1.0.38 (without type_source or format_image):
        # must re-read without error, with default values, and the
        # WordPress behavior is preserved.
        chemin = tmp_path / "c.json"
        chemin.write_text(json.dumps({
            "site": "https://old.example",
            "interval_hours": 6,
            "sort_mode": "gallery",
        }))
        c = Config.load(chemin)
        assert c.source_type == "wordpress"
        assert c.image_format == "Large"
        assert c.sort_mode == "gallery"   # not snapped because WP supports it


class TestSourceConstants:
    def test_source_types_contains_wordpress_and_djangoplicity(self):
        # sanity check: both keys expected by the engine are present.
        valeurs = set(SOURCE_TYPES.values())
        assert "wordpress" in valeurs
        assert "djangoplicity" in valeurs

    def test_djangoplicity_formats_contain_large(self):
        assert "Large" in DJANGOPLICITY_FORMATS.values()


# --------------------------------------------------------------------------- #
# Display labels (internal value ↔ UI label)
# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
# Deferral fields (lot 3: circuit-breaker / backoff persistence)
# --------------------------------------------------------------------------- #

class TestDeferState:
    def test_defaults_for_retry_after_and_backoff(self):
        """Fresh Config exposes an empty retenter_apres and a zero backoff level."""
        c = Config()
        assert c.retry_after == ""
        assert c.backoff_level == 0

    def test_round_trip_retry_after_and_backoff(self, tmp_path):
        """Saving then reloading preserves both deferral fields."""
        chemin = tmp_path / "c.json"
        c = Config.load(chemin)
        c.retry_after = "2026-09-27T10:00:00"
        c.backoff_level = 2
        c.save()

        c2 = Config.load(chemin)
        assert c2.retry_after == "2026-09-27T10:00:00"
        assert c2.backoff_level == 2

    def test_config_without_defer_fields_loads_with_defaults(self, tmp_path):
        """An older config.json without the deferral fields loads with defaults."""
        chemin = tmp_path / "c.json"
        chemin.write_text(json.dumps({"interval_hours": 6}))
        c = Config.load(chemin)
        assert c.retry_after == ""
        assert c.backoff_level == 0

    def test_validate_clamps_negative_backoff_level(self, tmp_path):
        """Valider clamps a negative backoff level to zero."""
        c = Config.load(tmp_path / "c.json")
        c.backoff_level = -3
        c.validate()
        assert c.backoff_level == 0

    def test_validate_clamps_too_high_backoff_level(self, tmp_path):
        """Valider clamps a backoff level above the ceiling down to 2."""
        c = Config.load(tmp_path / "c.json")
        c.backoff_level = 5
        c.validate()
        assert c.backoff_level == 2


class TestLabels:
    def test_known_interval_label(self, tmp_path):
        c = Config.load(tmp_path / "c.json")
        for libelle, heures in INTERVALS.items():
            c.interval_hours = heures
            assert c.interval_label == libelle

    def test_interval_label_fallback(self, tmp_path):
        c = Config.load(tmp_path / "c.json")
        c.interval_hours = -1   # not listed
        assert c.interval_label == "Une fois par jour"

    def test_known_sort_mode_label(self, tmp_path):
        c = Config.load(tmp_path / "c.json")
        for libelle, valeur in SORT_MODES.items():
            c.sort_mode = valeur
            assert c.sort_mode_label == libelle

    def test_sort_mode_label_fallback(self, tmp_path):
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

    def test_loads_french_keys(self, tmp_path):
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

    def test_save_after_load_rewrites_with_english_keys(self, tmp_path):
        """A load → save cycle migrates a legacy file to EN keys and to
        the v2 layered shape (schema_version + profiles + defaults)."""
        chemin = tmp_path / "config.json"
        chemin.write_text(json.dumps(self._LEGACY_JSON), encoding="utf-8")
        Config.load(chemin).save()
        reecrit = json.loads(chemin.read_text(encoding="utf-8"))
        # Legacy FR keys never survive the migration at any level.
        flat_reecrit = {**reecrit, **(reecrit.get("defaults") or {}),
                        **(reecrit.get("profiles") or [{}])[0]}
        for cle in self._LEGACY_JSON:
            if cle in ("site", "notifications"):
                continue   # always EN
            assert cle not in flat_reecrit, (
                f"legacy key {cle!r} still on disk")
        # Application keys land at the top level.
        assert reecrit["schema_version"] == 2
        assert reecrit["interval_hours"] == 12
        # Per-profile keys land in profiles[0].
        profile = reecrit["profiles"][0]
        assert profile["source_type"] == "djangoplicity"
        assert profile["sort_mode"] == "date"
        assert profile["target_dir"] == "/tmp/glaneur-old"

    def test_hybrid_json_prefers_english_over_french(self, tmp_path):
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


class TestLegacySortModeAliases:
    """A ``config.json`` written before US-EN-04 used ``"galerie"`` /
    ``"plat"`` as the ``sort_mode`` value. The load path translates
    them, so the user does not silently lose their choice.
    """

    def test_galerie_becomes_gallery(self, tmp_path):
        chemin = tmp_path / "c.json"
        chemin.write_text(json.dumps({"sort_mode": "galerie"}),
                          encoding="utf-8")
        assert Config.load(chemin).sort_mode == "gallery"

    def test_plat_becomes_flat(self, tmp_path):
        chemin = tmp_path / "c.json"
        chemin.write_text(json.dumps({"sort_mode": "plat"}),
                          encoding="utf-8")
        assert Config.load(chemin).sort_mode == "flat"

    def test_date_is_kept_as_is(self, tmp_path):
        chemin = tmp_path / "c.json"
        chemin.write_text(json.dumps({"sort_mode": "date"}),
                          encoding="utf-8")
        assert Config.load(chemin).sort_mode == "date"

    def test_save_rewrites_with_english_value(self, tmp_path):
        chemin = tmp_path / "c.json"
        chemin.write_text(json.dumps({"sort_mode": "galerie"}),
                          encoding="utf-8")
        Config.load(chemin).save()
        # v2 layout: sort_mode is a per-profile key.
        reecrit = json.loads(chemin.read_text())
        assert reecrit["profiles"][0]["sort_mode"] == "gallery"


# --------------------------------------------------------------------------- #
# Lot 5.0 E1 preparation: `PROFILE_FIELDS`
# --------------------------------------------------------------------------- #

class TestProfileFields:
    """`PROFILE_FIELDS` is the single source of truth for the split
    between application preferences and per-profile preferences. It
    will drive the tabbed Preferences dialog (E1) and the v1 → v2
    migration (E3, roadmap §5.1) that promotes each profile field into
    a `Profile` entry.
    """

    def test_matches_design_document(self):
        """The tuple's exact contents and order come from
        docs/design/evolution-multi-sources.md §3.1 and
        docs/design/roadmap.md §5.0. Adding or reordering is a
        deliberate design change."""
        assert PROFILE_FIELDS == (
            "source_type",
            "site",
            "image_format",
            "target_dir",
            "sort_mode",
            "min_width",
            "verify_integrity",
        )

    def test_every_entry_is_a_real_config_field(self):
        """Guard against a typo splitting the two levels: every name in
        PROFILE_FIELDS must be an existing dataclass field of Config."""
        from dataclasses import fields
        config_field_names = {f.name for f in fields(Config)}
        for name in PROFILE_FIELDS:
            assert name in config_field_names, (
                f"{name!r} in PROFILE_FIELDS is not a Config dataclass field")

    def test_no_private_field_leaks_in(self):
        """A field starting with `_` is an internal attribute (path
        stash, etc.) and must never appear in PROFILE_FIELDS."""
        for name in PROFILE_FIELDS:
            assert not name.startswith("_"), (
                f"{name!r} is private and cannot be a profile field")


# --------------------------------------------------------------------------- #
# Lot 5.1 E3 part A: v2 schema on disk
# --------------------------------------------------------------------------- #

class TestSchemaVersion:
    """v2 layout: schema_version at the top, application keys at the
    top, `defaults` block for inheritable settings, `profiles` list with
    one entry today. Runtime API of Config unchanged.
    """

    def _minimal_v1(self, tmp_path):
        chemin = tmp_path / "c.json"
        chemin.write_text(json.dumps({
            "site": "https://example.test",
            "target_dir": str(tmp_path / "photos"),
            "interval_hours": 12,
            "min_width": 1200,
            "sort_mode": "date",
            "source_type": "djangoplicity",
            "image_format": "Small",
            "verify_integrity": True,
            "last_run": "2026-09-29T15:00:00",
        }), encoding="utf-8")
        return chemin

    # -- save shape ---------------------------------------------------------

    def test_fresh_save_writes_v2_layout(self, tmp_path):
        cfg = Config.load(tmp_path / "c.json")
        cfg.site = "https://example.test"
        cfg.save()
        data = json.loads((tmp_path / "c.json").read_text(encoding="utf-8"))
        assert data["schema_version"] == SCHEMA_VERSION
        # Application keys land at the top level.
        for cle in ("language", "interval_hours", "schedule_anchor",
                    "request_delay", "run_at_startup", "close_to_tray",
                    "notifications", "check_updates_on_start",
                    "slideshow_dir"):
            assert cle in data, f"top-level key {cle!r} missing"
        assert "defaults" in data and "profiles" in data
        assert isinstance(data["profiles"], list) and len(data["profiles"]) == 1

    def test_defaults_holds_inheritable_settings(self, tmp_path):
        cfg = Config.load(tmp_path / "c.json")
        cfg.min_width = 1500
        cfg.verify_integrity = True
        cfg.save()
        data = json.loads((tmp_path / "c.json").read_text(encoding="utf-8"))
        assert data["defaults"] == {"min_width": 1500, "verify_integrity": True}

    def test_profile_overrides_null_by_default(self, tmp_path):
        cfg = Config.load(tmp_path / "c.json")
        cfg.save()
        data = json.loads((tmp_path / "c.json").read_text(encoding="utf-8"))
        profile = data["profiles"][0]
        # The single implicit profile inherits every default via null
        # overrides; the effective value lives in `defaults`.
        assert profile["min_width"] is None
        assert profile["verify_integrity"] is None

    def test_profile_carries_id_name_and_per_profile_keys(self, tmp_path):
        cfg = Config.load(tmp_path / "c.json")
        cfg.site = "https://x.example"
        cfg.target_dir = "/tmp/x"
        cfg.save()
        profile = json.loads((tmp_path / "c.json").read_text(
            encoding="utf-8"))["profiles"][0]
        assert profile["id"] == cfg._profile_id
        assert len(profile["id"]) == 32   # uuid4().hex
        assert profile["name"] == "default"
        assert profile["site"] == "https://x.example"
        assert profile["target_dir"] == "/tmp/x"
        # Run state travels with the profile.
        assert profile["last_run"] == ""
        assert profile["retry_after"] == ""
        assert profile["backoff_level"] == 0

    # -- v2 read ------------------------------------------------------------

    def test_load_v2_populates_flat_config(self, tmp_path):
        chemin = tmp_path / "c.json"
        cfg = Config.load(chemin)
        cfg.site = "https://y.example"
        cfg.target_dir = "/tmp/y"
        cfg.min_width = 999
        cfg.save()
        # Read back through Config.load — flat access still works.
        loaded = Config.load(chemin)
        assert loaded.site == "https://y.example"
        assert loaded.target_dir == "/tmp/y"
        assert loaded.min_width == 999

    def test_profile_override_wins_over_defaults(self, tmp_path):
        """A non-null override at the profile level replaces the
        `defaults` value for that field."""
        chemin = tmp_path / "c.json"
        chemin.write_text(json.dumps({
            "schema_version": 2,
            "defaults": {"min_width": 500, "verify_integrity": False},
            "profiles": [{
                "id": "abc",
                "name": "default",
                "source_type": "wordpress",
                "site": "https://x",
                "target_dir": "/tmp",
                "image_format": "Large",
                "sort_mode": "gallery",
                "min_width": 1500,          # override
                "verify_integrity": True,   # override
                "last_run": "",
                "retry_after": "",
                "backoff_level": 0,
            }],
        }), encoding="utf-8")
        cfg = Config.load(chemin)
        assert cfg.min_width == 1500        # override, not defaults' 500
        assert cfg.verify_integrity is True
        assert cfg._profile_id == "abc"

    def test_unknown_v2_keys_are_ignored(self, tmp_path):
        chemin = tmp_path / "c.json"
        chemin.write_text(json.dumps({
            "schema_version": 2,
            "surprise": "future feature",
            "defaults": {"unexpected": 1},
            "profiles": [{"id": "z", "name": "d",
                           "source_type": "wordpress", "site": "https://x",
                           "target_dir": "/tmp", "image_format": "Large",
                           "sort_mode": "gallery"}],
        }), encoding="utf-8")
        cfg = Config.load(chemin)
        assert cfg.site == "https://x"

    def test_profile_id_stable_across_round_trip(self, tmp_path):
        chemin = tmp_path / "c.json"
        cfg = Config.load(chemin)
        first_id = cfg._profile_id
        assert first_id and len(first_id) == 32
        cfg.save()
        cfg2 = Config.load(chemin)
        assert cfg2._profile_id == first_id

    def test_v2_round_trip_is_byte_stable(self, tmp_path):
        chemin = tmp_path / "c.json"
        Config.load(chemin).save()   # canonicalise to v2 bytes
        before = chemin.read_bytes()
        Config.load(chemin).save()   # v2 → v2, no change
        assert chemin.read_bytes() == before

    # -- v1 → v2 migration --------------------------------------------------

    def test_v1_save_creates_v1_backup(self, tmp_path):
        chemin = self._minimal_v1(tmp_path)
        Config.load(chemin).save()
        backup = chemin.with_name(f"{chemin.stem}.v1.json")
        assert backup.exists()
        # Backup keeps the pre-migration bytes verbatim.
        assert "schema_version" not in json.loads(backup.read_text(
            encoding="utf-8"))

    def test_v1_backup_not_overwritten_on_second_save(self, tmp_path):
        chemin = self._minimal_v1(tmp_path)
        cfg = Config.load(chemin)
        cfg.save()
        backup = chemin.with_name(f"{chemin.stem}.v1.json")
        original = backup.read_bytes()
        # Second save: file is now v2 on disk, no backup step; the
        # original v1 snapshot survives.
        cfg.site = "https://mutated.example"
        cfg.save()
        assert backup.read_bytes() == original

    def test_v1_content_preserved_after_migration(self, tmp_path):
        chemin = self._minimal_v1(tmp_path)
        cfg = Config.load(chemin)
        cfg.save()
        loaded = Config.load(chemin)
        assert loaded.site == "https://example.test"
        assert loaded.min_width == 1200
        assert loaded.sort_mode == "date"
        assert loaded.source_type == "djangoplicity"
        assert loaded.image_format == "Small"
        assert loaded.verify_integrity is True
        assert loaded.last_run == "2026-09-29T15:00:00"


    def test_v2_sort_mode_legacy_value_is_migrated(self, tmp_path):
        """A v2 file with a legacy FR sort_mode value inside profiles[0]
        still upgrades on load — same one-way alias as US-EN-04."""
        chemin = tmp_path / "c.json"
        chemin.write_text(json.dumps({
            "schema_version": 2,
            "defaults": {"min_width": 800, "verify_integrity": False},
            "profiles": [{
                "id": "a", "name": "d",
                "source_type": "wordpress", "site": "https://x",
                "target_dir": "/tmp", "image_format": "Large",
                "sort_mode": "galerie",   # legacy FR value
                "min_width": None, "verify_integrity": None,
                "last_run": "", "retry_after": "", "backoff_level": 0,
            }],
        }), encoding="utf-8")
        cfg = Config.load(chemin)
        assert cfg.sort_mode == "gallery"

    def test_backup_left_alone_when_backup_already_exists(self, tmp_path):
        """Re-running the migration on a corrupted or reverted v1 file
        must not overwrite an existing config.v1.json snapshot."""
        chemin = tmp_path / "c.json"
        backup = chemin.with_name(f"{chemin.stem}.v1.json")
        # Pre-existing backup that must survive.
        backup.write_text("{}", encoding="utf-8")
        chemin.write_text('{"site": "https://x"}', encoding="utf-8")
        Config.load(chemin).save()
        # The snapshot stays untouched even though the file was v1.
        assert backup.read_text(encoding="utf-8") == "{}"

    def test_backup_skipped_for_non_dict_toplevel(self, tmp_path):
        """A stray list at the top level is treated as absent; the
        backup step does not fire."""
        chemin = tmp_path / "c.json"
        chemin.write_text("[]", encoding="utf-8")
        Config.load(chemin).save()
        backup = chemin.with_name(f"{chemin.stem}.v1.json")
        assert not backup.exists()

    def test_save_without_prior_load_gets_a_profile_id(self, tmp_path):
        """A Config instantiated directly (no load()) still gains a
        stable profile id on first save — the id is written into
        profiles[0].id."""
        cfg = Config()
        cfg._path = tmp_path / "c.json"
        cfg.save()
        data = json.loads((tmp_path / "c.json").read_text(encoding="utf-8"))
        assert len(data["profiles"][0]["id"]) == 32
        assert cfg._profile_id == data["profiles"][0]["id"]

    def test_v2_with_empty_profiles_list_falls_back_to_defaults(self, tmp_path):
        """A v2 file with `profiles: []` (edge case, e.g. user manually
        cleared the list) yields a Config on default values — load must
        not crash."""
        chemin = tmp_path / "c.json"
        chemin.write_text(json.dumps({
            "schema_version": 2,
            "defaults": {"min_width": 800, "verify_integrity": False},
            "profiles": [],
        }), encoding="utf-8")
        cfg = Config.load(chemin)
        assert cfg.site == "https://example.com"   # default
        assert cfg._profile_id != ""               # seeded by load()

    def test_v2_profile_omitting_optional_keys_uses_defaults(self, tmp_path):
        """A v2 profile that omits per-profile state fields
        (last_run, retry_after, backoff_level) keeps the Config
        defaults for them."""
        chemin = tmp_path / "c.json"
        chemin.write_text(json.dumps({
            "schema_version": 2,
            "defaults": {"min_width": 800, "verify_integrity": False},
            "profiles": [{
                "id": "a", "name": "d",
                "source_type": "wordpress", "site": "https://x",
                "target_dir": "/tmp", "image_format": "Large",
                "sort_mode": "gallery",
                "min_width": None, "verify_integrity": None,
                # last_run / retry_after / backoff_level intentionally absent
            }],
        }), encoding="utf-8")
        cfg = Config.load(chemin)
        assert cfg.last_run == ""
        assert cfg.retry_after == ""
        assert cfg.backoff_level == 0

    def test_backup_skipped_when_toplevel_json_is_corrupt(self, tmp_path):
        """A corrupt config.json is treated as absent for backup
        purposes — the migration itself carries on with defaults."""
        chemin = tmp_path / "c.json"
        chemin.write_text("{not valid json", encoding="utf-8")
        Config.load(chemin).save()
        backup = chemin.with_name(f"{chemin.stem}.v1.json")
        assert not backup.exists()


    # -- Downgrade + malformed safety (post invariant-reviewer) ------------

    def test_future_schema_is_not_read_as_v1(self, tmp_path):
        """A file with ``schema_version`` higher than SCHEMA_VERSION must
        not be misread as a v1 flat dict — that would silently drop
        every future-only field. Load falls back to defaults instead."""
        chemin = tmp_path / "c.json"
        chemin.write_text(json.dumps({
            "schema_version": SCHEMA_VERSION + 1,
            "site": "https://future.example",
            "future_only_field": "x",
        }), encoding="utf-8")
        cfg = Config.load(chemin)
        # Site defaults (not read from the future file).
        assert cfg.site == "https://example.com"

    def test_save_refuses_to_overwrite_future_schema(self, tmp_path):
        """A downgrade run must not clobber a future-format config —
        the future version needs to be preserved for a re-upgrade."""
        chemin = tmp_path / "c.json"
        chemin.write_text(json.dumps({
            "schema_version": SCHEMA_VERSION + 1,
            "keep_me": "please",
        }), encoding="utf-8")
        before = chemin.read_bytes()
        cfg = Config.load(chemin)
        cfg.site = "https://mutated.example"
        cfg.save()
        # File on disk untouched.
        assert chemin.read_bytes() == before
        # No spurious backup either.
        assert not chemin.with_name(f"{chemin.stem}.v{SCHEMA_VERSION + 1}.json").exists()

    def test_snapshot_is_atomic_via_tmp(self, tmp_path):
        """A crash mid-backup would leave a truncated snapshot if the
        write went directly to the target path. The snapshot must go
        through a ``.tmp`` sidecar renamed atomically. Verify by
        monkey-patching ``Path.replace`` on the snapshot side to fail
        and checking the target file never exists."""
        chemin = self._minimal_v1(tmp_path)
        backup = chemin.with_name(f"{chemin.stem}.v1.json")
        cfg = Config.load(chemin)
        # Fail the backup rename; the live config write must still
        # succeed and no half-written backup must survive.
        original_replace = Path.replace
        target_backup_tmp = backup.with_suffix(".json.tmp")

        def faux_replace(self, dest):
            if Path(self) == target_backup_tmp:
                raise OSError("simulated crash")
            return original_replace(self, dest)

        from unittest import mock
        with mock.patch.object(Path, "replace", faux_replace):
            cfg.save()
        # Backup absent (rename failed) but no truncated file left behind.
        assert not backup.exists()
        assert not target_backup_tmp.exists()
        # The live migration itself completed.
        assert Config.load(chemin).site == "https://example.test"

    def test_load_survives_defaults_being_a_list(self, tmp_path):
        """A malformed ``defaults`` (list instead of dict) is skipped
        rather than crashing the load."""
        chemin = tmp_path / "c.json"
        chemin.write_text(json.dumps({
            "schema_version": 2,
            "defaults": ["nope"],
            "profiles": [{"id": "a", "name": "d",
                           "source_type": "wordpress", "site": "https://x",
                           "target_dir": "/tmp", "image_format": "Large",
                           "sort_mode": "gallery"}],
        }), encoding="utf-8")
        cfg = Config.load(chemin)
        assert cfg.site == "https://x"

    def test_load_survives_profiles_zero_being_a_string(self, tmp_path):
        """A malformed ``profiles[0]`` (string instead of dict) is
        skipped rather than crashing the load."""
        chemin = tmp_path / "c.json"
        chemin.write_text(json.dumps({
            "schema_version": 2,
            "defaults": {"min_width": 800, "verify_integrity": False},
            "profiles": ["not a dict"],
        }), encoding="utf-8")
        cfg = Config.load(chemin)
        # Defaults applied, profile ignored.
        assert cfg.min_width == 800
        assert cfg.site == "https://example.com"   # untouched default

    # -- schedule_anchor seeding on v1 → v2 migration ---------------------

    def test_schedule_anchor_seeded_from_last_run_on_migration(self, tmp_path):
        chemin = tmp_path / "c.json"
        chemin.write_text(json.dumps({
            "site": "https://x", "last_run": "2026-09-29T15:30:00",
        }), encoding="utf-8")
        cfg = Config.load(chemin)
        assert cfg.schedule_anchor == "15:30"

    def test_schedule_anchor_empty_when_last_run_empty(self, tmp_path):
        chemin = tmp_path / "c.json"
        chemin.write_text(json.dumps({
            "site": "https://x", "last_run": "",
        }), encoding="utf-8")
        cfg = Config.load(chemin)
        assert cfg.schedule_anchor == ""

    def test_schedule_anchor_kept_when_already_set(self, tmp_path):
        """A v2 file whose top-level schedule_anchor is set is not
        overwritten by v1 seeding — v1 seeding only fires in _load_v1."""
        chemin = tmp_path / "c.json"
        chemin.write_text(json.dumps({
            "schema_version": 2,
            "schedule_anchor": "09:00",
            "defaults": {"min_width": 800, "verify_integrity": False},
            "profiles": [{"id": "a", "name": "d",
                           "source_type": "wordpress", "site": "https://x",
                           "target_dir": "/tmp", "image_format": "Large",
                           "sort_mode": "gallery", "last_run": "2026-01-01T18:45:00"}],
        }), encoding="utf-8")
        cfg = Config.load(chemin)
        assert cfg.schedule_anchor == "09:00"


class TestProfileDataclass:
    """The Profile dataclass is defined now; runtime use lands in
    E3 part B. This test locks the field list against the design
    document so a rename or reorder is deliberate.
    """

    def test_field_list(self):
        from dataclasses import fields
        names = tuple(f.name for f in fields(Profile))
        assert names == (
            "id", "name", "source_type", "site", "target_dir",
            "image_format", "sort_mode",
            "min_width", "verify_integrity",
            "last_run", "retry_after", "backoff_level",
        )

    def test_override_fields_default_to_none(self):
        p = Profile()
        assert p.min_width is None
        assert p.verify_integrity is None


class TestProfileInheritance:
    """None-inheritance rule (evolution-multi-sources.md §3.2,
    roadmap §5.1): a profile field set to ``None`` inherits the
    default; a default is never copied into a profile. Formalised on
    Profile as ``effective_min_width`` and
    ``effective_verify_integrity``, both used once E3 part B moves
    per-profile state off Config.
    """

    _DEFAULTS: dict = {"min_width": 800, "verify_integrity": False}  # noqa: RUF012 — read-only test fixture

    def test_override_wins_over_defaults(self):
        p = Profile(min_width=1500, verify_integrity=True)
        assert p.effective_min_width(self._DEFAULTS) == 1500
        assert p.effective_verify_integrity(self._DEFAULTS) is True

    def test_defaults_used_when_override_is_none(self):
        p = Profile(min_width=None, verify_integrity=None)
        assert p.effective_min_width(self._DEFAULTS) == 800
        assert p.effective_verify_integrity(self._DEFAULTS) is False

    def test_fallback_used_when_both_missing(self):
        """Empty defaults block (config file omitted it, or the key
        isn't there yet): the resolver falls back to Config's
        class-level defaults."""
        p = Profile(min_width=None, verify_integrity=None)
        assert p.effective_min_width({}) == 800
        assert p.effective_verify_integrity({}) is False

    def test_verify_integrity_semantics_mirror_min_width(self):
        """The rule is uniform — the two methods do not diverge."""
        p_override_false = Profile(verify_integrity=False)
        # False is a valid explicit override, NOT missing — must win over
        # a True default, otherwise "turning off integrity check for this
        # profile" is unrepresentable.
        assert p_override_false.effective_verify_integrity(
            {"verify_integrity": True}) is False
        # Same edge for min_width: 0 is a legal explicit override.
        p_zero = Profile(min_width=0)
        assert p_zero.effective_min_width({"min_width": 800}) == 0
