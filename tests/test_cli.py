"""Tests for the command-line interface (`cli.py`).

The engine and the config layer have their own tests: here we only
check that `cli.main`

- parses the command line correctly and defers to `Config` for the
  defaults,
- passes the arguments to `Options` without losing anything,
- prints a readable summary,
- returns the documented exit codes (0 success, 1 all failed,
  2 deferred, 130 keyboard interrupt).
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

import cli
from Glaneur.engine.result import RunResult


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


class _FauxEngine:
    """Stub `Engine` that captures its `Options` and returns a canned
    `RunResult`. `run` can also raise, to test the KeyboardInterrupt
    branch.
    """

    dernier: "_FauxEngine | None" = None

    def __init__(self, options, journal=None, progression=None, arret=None):
        self.options = options
        self.journal = journal
        self.progression = progression
        self.arret = _FauxArret()
        _FauxEngine.dernier = self

    # Filled by the test before `main()` is called.
    _resultat: RunResult = RunResult(message="OK")
    _leve: BaseException | None = None

    def run(self) -> RunResult:
        if self._leve is not None:
            raise self._leve
        return self._resultat


class _FauxArret:
    def __init__(self) -> None:
        self.set_called = False

    def set(self) -> None:
        self.set_called = True


def _run(monkeypatch, argv, *, resultat=None, leve=None, config_kw=None,
         config_chemin=None):
    """Invoke `cli.main` with a stubbed engine and forged argv.

    Args:
        monkeypatch: pytest fixture.
        argv: extra arguments after `cli.py`.
        resultat: `RunResult` the stub engine should return.
        leve: exception the stub engine should raise instead of running.
        config_kw: overrides applied on the loaded `Config` object.
        config_chemin: path used to load and persist the `Config`; must
            be writable when the tested branch calls `sauvegarder`.

    Returns:
        The int exit code from `cli.main`.
    """
    monkeypatch.setattr(sys, "argv", ["cli.py", *argv])

    # Insulate Config from the user's real settings file.
    real_charger = cli.Config.charger
    chemin = config_chemin or Path("/nonexistent-config-for-tests.json")

    def faux_charger(chemin_appelant=None):
        c = real_charger(chemin)
        for k, v in (config_kw or {}).items():
            setattr(c, k, v)
        return c

    monkeypatch.setattr(cli.Config, "charger", staticmethod(faux_charger))

    _FauxEngine._resultat = resultat if resultat is not None else RunResult(message="OK")
    _FauxEngine._leve = leve
    _FauxEngine.dernier = None
    monkeypatch.setattr(cli, "Engine", _FauxEngine)

    return cli.main()


# --------------------------------------------------------------------------- #
# Argument parsing and forwarding to Options
# --------------------------------------------------------------------------- #


class TestArgumentsVersOptions:
    def test_defaults_viennent_de_config(self, monkeypatch, tmp_path):
        rc = _run(
            monkeypatch,
            [],
            config_kw={
                "dossier": str(tmp_path / "photos"),
                "site": "https://example.test",
                "type_source": "wordpress",
                "classement": "date",
                "format_image": "Large",
                "largeur_min": 800,
                "delai_requetes": 1.5,
            },
        )
        assert rc == 0
        o = _FauxEngine.dernier.options
        assert o.target_dir == (tmp_path / "photos").expanduser()
        assert o.site == "https://example.test"
        assert o.source_type == "wordpress"
        assert o.sort_mode == "date"
        assert o.image_format == "Large"
        assert o.min_width == 800
        assert o.delay == 1.5
        assert o.verify is False
        assert o.force is False
        assert o.use_cache is True
        assert o.since is None
        assert o.until is None

    def test_overrides_via_flags(self, monkeypatch, tmp_path):
        rc = _run(
            monkeypatch,
            [
                "--dossier", str(tmp_path / "cli-dest"),
                "--type", "djangoplicity",
                "--format", "Small",
                "--classement", "galerie",
                "--largeur-min", "1200",
                "--delai", "2.25",
                "--verifier",
                "--force",
                "--pas-cache",
                "--depuis", "2026-01-01",
                "--jusqua", "2026-06-30",
            ],
        )
        assert rc == 0
        o = _FauxEngine.dernier.options
        assert o.target_dir == (tmp_path / "cli-dest").expanduser()
        assert o.source_type == "djangoplicity"
        assert o.image_format == "Small"
        assert o.sort_mode == "galerie"
        assert o.min_width == 1200
        assert o.delay == 2.25
        assert o.verify is True
        assert o.force is True
        assert o.use_cache is False   # --pas-cache inverts the default
        assert o.since == "2026-01-01"
        assert o.until == "2026-06-30"

    def test_choix_type_source_invalide(self, monkeypatch):
        with pytest.raises(SystemExit):
            _run(monkeypatch, ["--type", "flickr"])

    def test_choix_format_invalide(self, monkeypatch):
        with pytest.raises(SystemExit):
            _run(monkeypatch, ["--format", "Huge"])

    def test_choix_classement_invalide(self, monkeypatch):
        with pytest.raises(SystemExit):
            _run(monkeypatch, ["--classement", "aleatoire"])


# --------------------------------------------------------------------------- #
# Exit codes
# --------------------------------------------------------------------------- #


class TestCodesRetour:
    def test_succes_renvoie_zero(self, monkeypatch):
        rc = _run(monkeypatch, [], resultat=RunResult(downloaded=3, message="OK"))
        assert rc == 0

    def test_zero_si_aucun_echec_meme_sans_telechargement(self, monkeypatch):
        # Nothing new but nothing failed either: still success.
        rc = _run(monkeypatch, [], resultat=RunResult(already_present=10, message="OK"))
        assert rc == 0

    def test_un_si_tout_a_echoue(self, monkeypatch):
        rc = _run(
            monkeypatch, [],
            resultat=RunResult(failures=5, downloaded=0, message="KO"),
        )
        assert rc == 1

    def test_zero_si_echecs_mais_au_moins_un_telechargement(self, monkeypatch):
        # Partial failure: not the "everything failed" branch.
        rc = _run(
            monkeypatch, [],
            resultat=RunResult(failures=3, downloaded=1, message="mixte"),
        )
        assert rc == 0

    def test_deux_si_run_reporte(self, monkeypatch, tmp_path, capsys):
        # `Planificateur.differer` persists a defer via `Config.sauvegarder`,
        # so the config path has to be writable.
        rc = _run(
            monkeypatch, [],
            resultat=RunResult(deferred=True, message="reporté"),
            config_chemin=tmp_path / "cfg.json",
        )
        assert rc == 2
        err = capsys.readouterr().err
        # texte_prochaine goes to stderr as a next-run hint.
        assert err.strip() != ""

    def test_130_sur_keyboard_interrupt(self, monkeypatch, capsys):
        rc = _run(monkeypatch, [], leve=KeyboardInterrupt())
        assert rc == 130
        # The stub engine's `arret` event was signalled cooperatively.
        assert _FauxEngine.dernier.arret.set_called is True
        assert "Interrompu" in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# Output: summary lines
# --------------------------------------------------------------------------- #


class TestSortieStdout:
    def test_resume_contient_les_compteurs(self, monkeypatch, capsys):
        _run(
            monkeypatch,
            [],
            resultat=RunResult(
                downloaded=4, resumed=1, already_present=10, unchanged=2,
                deleted=1, skipped=3, failures=0, bytes=2048,
                message="Terminé",
            ),
        )
        out = capsys.readouterr().out
        assert "Terminé" in out
        # All the labelled counters appear with their value.
        assert "téléchargées : 4" in out
        assert "reprises : 1" in out
        assert "déjà à jour  : 10" in out
        assert "inchangées : 2" in out
        assert "supprimées   : 1" in out
        assert "ignorées : 3" in out
        assert "échecs       : 0" in out
        # `format_bytes` turned 2048 into a human-readable string.
        assert "2" in out and "o" in out.lower()


# --------------------------------------------------------------------------- #
# --restaurer branch
# --------------------------------------------------------------------------- #


class TestRestaurer:
    def test_restaurer_avec_ids_explicites(self, monkeypatch, tmp_path, capsys):
        appels = {}

        def faux_restaurer(dossier, ids):
            appels["dossier"] = dossier
            appels["ids"] = list(ids)
            return len(appels["ids"])

        monkeypatch.setattr(cli, "restore", faux_restaurer)
        # Not expected to be called when explicit IDs are given.
        monkeypatch.setattr(
            cli, "list_deleted",
            lambda _d: (_ for _ in ()).throw(AssertionError("must not be called")),
        )

        rc = _run(
            monkeypatch,
            ["--dossier", str(tmp_path), "--restaurer", "12", "34", "56"],
        )
        assert rc == 0
        assert appels["dossier"] == tmp_path.expanduser()
        assert appels["ids"] == ["12", "34", "56"]
        assert "3 image(s) remise(s)" in capsys.readouterr().out

    def test_restaurer_sans_ids_prend_toutes_les_supprimees(
        self, monkeypatch, tmp_path, capsys,
    ):
        def faux_lister(dossier):
            assert dossier == tmp_path.expanduser()
            return [{"id": "a"}, {"id": "b"}]

        appels = {}

        def faux_restaurer(dossier, ids):
            appels["ids"] = list(ids)
            return len(appels["ids"])

        monkeypatch.setattr(cli, "list_deleted", faux_lister)
        monkeypatch.setattr(cli, "restore", faux_restaurer)

        rc = _run(monkeypatch, ["--dossier", str(tmp_path), "--restaurer"])
        assert rc == 0
        assert appels["ids"] == ["a", "b"]
        assert "2 image(s) remise(s)" in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# Progression callback
# --------------------------------------------------------------------------- #


class TestProgression:
    def test_ecrit_seulement_quand_la_ligne_change(self, monkeypatch, capsys):
        """The progression callback rewrites a single line on stdout and
        skips writes when the formatted output would be identical.
        """
        _run(monkeypatch, [])
        prog = _FauxEngine.dernier.progression
        prog(1, 10, "photo-1")
        prog(1, 10, "photo-1")   # identical: must not write again
        prog(2, 10, "photo-2")
        out = capsys.readouterr().out
        # Two carriage-returned progress lines, not three — the duplicate
        # `photo-1` call is skipped because the formatted line is identical.
        assert out.count("\r") == 2
        assert out.count("photo-1") == 1
        assert "photo-2" in out

    def test_tronque_l_etiquette_a_60_caracteres(self, monkeypatch, capsys):
        _run(monkeypatch, [])
        prog = _FauxEngine.dernier.progression
        prog(1, 2, "x" * 200)
        out = capsys.readouterr().out
        # The 200 xs got clipped to 60.
        assert "x" * 60 in out
        assert "x" * 61 not in out
