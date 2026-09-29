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

    def __init__(self, options, journal=None, progression=None, stop_event=None):
        self.options = options
        self.journal = journal
        self.progression = progression
        self.stop_event = _FauxArret()
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
    real_charger = cli.Config.load
    chemin = config_chemin or Path("/nonexistent-config-for-tests.json")

    def faux_charger(chemin_appelant=None):
        c = real_charger(chemin)
        for k, v in (config_kw or {}).items():
            setattr(c, k, v)
        return c

    monkeypatch.setattr(cli.Config, "load", staticmethod(faux_charger))

    _FauxEngine._resultat = resultat if resultat is not None else RunResult(message="OK")
    _FauxEngine._leve = leve
    _FauxEngine.dernier = None
    monkeypatch.setattr(cli, "Engine", _FauxEngine)

    return cli.main()


# --------------------------------------------------------------------------- #
# Argument parsing and forwarding to Options
# --------------------------------------------------------------------------- #


class TestArgumentsToOptions:
    def test_defaults_come_from_config(self, monkeypatch, tmp_path):
        rc = _run(
            monkeypatch,
            [],
            config_kw={
                "target_dir": str(tmp_path / "photos"),
                "site": "https://example.test",
                "source_type": "wordpress",
                "sort_mode": "date",
                "image_format": "Large",
                "min_width": 800,
                "request_delay": 1.5,
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
                "--folder", str(tmp_path / "cli-dest"),
                "--type", "djangoplicity",
                "--format", "Small",
                "--sort", "gallery",
                "--min-width", "1200",
                "--delay", "2.25",
                "--verify",
                "--force",
                "--no-cache",
                "--since", "2026-01-01",
                "--until", "2026-06-30",
            ],
        )
        assert rc == 0
        o = _FauxEngine.dernier.options
        assert o.target_dir == (tmp_path / "cli-dest").expanduser()
        assert o.source_type == "djangoplicity"
        assert o.image_format == "Small"
        assert o.sort_mode == "gallery"
        assert o.min_width == 1200
        assert o.delay == 2.25
        assert o.verify is True
        assert o.force is True
        assert o.use_cache is False   # --no-cache inverts the default
        assert o.since == "2026-01-01"
        assert o.until == "2026-06-30"

    def test_fr_aliases_still_work(self, monkeypatch, tmp_path):
        """Every FR flag from the pre-US-EN-06 CLI is preserved as a
        hidden alias sharing the EN dest, so existing scripts and
        scheduled tasks keep working."""
        rc = _run(
            monkeypatch,
            [
                "--dossier", str(tmp_path / "cli-dest"),
                "--classement", "gallery",
                "--largeur-min", "1200",
                "--delai", "2.25",
                "--verifier",
                "--pas-cache",
                "--depuis", "2026-01-01",
                "--jusqua", "2026-06-30",
            ],
        )
        assert rc == 0
        o = _FauxEngine.dernier.options
        assert o.target_dir == (tmp_path / "cli-dest").expanduser()
        assert o.sort_mode == "gallery"
        assert o.min_width == 1200
        assert o.delay == 2.25
        assert o.verify is True
        assert o.use_cache is False
        assert o.since == "2026-01-01"
        assert o.until == "2026-06-30"

    def test_help_hides_fr_aliases(self, monkeypatch, capsys):
        """`--help` lists the canonical EN flags but no FR alias."""
        with pytest.raises(SystemExit):
            _run(monkeypatch, ["--help"])
        out = capsys.readouterr().out
        for en in ("--folder", "--sort", "--min-width", "--delay",
                   "--verify", "--no-cache", "--since", "--until",
                   "--restore"):
            assert en in out, f"expected {en!r} in --help output"
        for fr in ("--dossier", "--classement", "--largeur-min", "--delai",
                   "--verifier", "--pas-cache", "--depuis", "--jusqua",
                   "--restaurer"):
            assert fr not in out, f"FR alias {fr!r} leaked into --help output"

    def test_invalid_source_type_choice(self, monkeypatch):
        with pytest.raises(SystemExit):
            _run(monkeypatch, ["--type", "flickr"])

    def test_invalid_format_choice(self, monkeypatch):
        with pytest.raises(SystemExit):
            _run(monkeypatch, ["--format", "Huge"])

    def test_invalid_sort_mode_choice(self, monkeypatch):
        with pytest.raises(SystemExit):
            _run(monkeypatch, ["--sort", "aleatoire"])

    def test_choices_track_config_registries(self, monkeypatch, tmp_path):
        """Lot 0.8 boundary: CLI --type/--format/--sort choices come from
        the SOURCE_TYPES / DJANGOPLICITY_FORMATS / SORT_MODES registries
        in Glaneur.config, not from a hard-coded copy. Adding a value to
        one of those registries must make the parser accept it, without
        touching cli.py.
        """
        from Glaneur.config import SOURCE_TYPES
        patched = dict(SOURCE_TYPES)
        patched["Test source"] = "test-source"
        monkeypatch.setattr(cli, "SOURCE_TYPES", patched)
        # Argparse now accepts the new key. The stub engine ignores the
        # value, so the run still returns 0.
        rc = _run(monkeypatch, ["--type", "test-source"])
        assert rc == 0
        assert _FauxEngine.dernier.options.source_type == "test-source"


# --------------------------------------------------------------------------- #
# Exit codes
# --------------------------------------------------------------------------- #


class TestReturnCodes:
    def test_success_returns_zero(self, monkeypatch):
        rc = _run(monkeypatch, [], resultat=RunResult(downloaded=3, message="OK"))
        assert rc == 0

    def test_zero_if_no_failure_even_without_download(self, monkeypatch):
        # Nothing new but nothing failed either: still success.
        rc = _run(monkeypatch, [], resultat=RunResult(already_present=10, message="OK"))
        assert rc == 0

    def test_one_if_everything_failed(self, monkeypatch):
        rc = _run(
            monkeypatch, [],
            resultat=RunResult(failures=5, downloaded=0, message="KO"),
        )
        assert rc == 1

    def test_zero_if_failures_but_at_least_one_download(self, monkeypatch):
        # Partial failure: not the "everything failed" branch.
        rc = _run(
            monkeypatch, [],
            resultat=RunResult(failures=3, downloaded=1, message="mixte"),
        )
        assert rc == 0

    def test_two_if_run_deferred(self, monkeypatch, tmp_path, capsys):
        # `Scheduler.defer` persists a defer via `Config.sauvegarder`,
        # so the config path has to be writable.
        rc = _run(
            monkeypatch, [],
            resultat=RunResult(deferred=True, message="reporté"),
            config_chemin=tmp_path / "cfg.json",
        )
        assert rc == 2
        err = capsys.readouterr().err
        # next_run_text goes to stderr as a next-run hint.
        assert err.strip() != ""

    def test_130_on_keyboard_interrupt(self, monkeypatch, capsys):
        rc = _run(monkeypatch, [], leve=KeyboardInterrupt())
        assert rc == 130
        # The stub engine's `stop_event` was signalled cooperatively.
        assert _FauxEngine.dernier.stop_event.set_called is True
        assert "Interrupted" in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# Output: summary lines
# --------------------------------------------------------------------------- #


class TestStdoutOutput:
    def test_summary_contains_the_counters(self, monkeypatch, capsys):
        _run(
            monkeypatch,
            [],
            resultat=RunResult(
                downloaded=4, resumed=1, already_present=10, unchanged=2,
                deleted=1, skipped=3, failures=0, bytes=2048,
                message="Done",
            ),
        )
        out = capsys.readouterr().out
        assert "Done" in out
        # All the labelled counters appear with their value.
        assert "downloaded    : 4" in out
        assert "resumed : 1" in out
        assert "up-to-date    : 10" in out
        assert "unchanged : 2" in out
        assert "deleted       : 1" in out
        assert "skipped : 3" in out
        assert "failures      : 0" in out
        # `format_bytes` turned 2048 into a human-readable string.
        assert "2" in out and "o" in out.lower()


# --------------------------------------------------------------------------- #
# --restaurer branch
# --------------------------------------------------------------------------- #


class TestRestore:
    def test_restore_with_explicit_ids(self, monkeypatch, tmp_path, capsys):
        appels = {}

        def faux_restaurer(dossier, ids):
            appels["target_dir"] = dossier
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
            ["--folder", str(tmp_path), "--restore", "12", "34", "56"],
        )
        assert rc == 0
        assert appels["target_dir"] == tmp_path.expanduser()
        assert appels["ids"] == ["12", "34", "56"]
        assert "3 image(s) re-queued" in capsys.readouterr().out

    def test_restore_without_ids_takes_all_deleted(
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

        rc = _run(monkeypatch, ["--folder", str(tmp_path), "--restore"])
        assert rc == 0
        assert appels["ids"] == ["a", "b"]
        assert "2 image(s) re-queued" in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# Progression callback
# --------------------------------------------------------------------------- #


class TestProgress:
    def test_writes_only_when_the_line_changes(self, monkeypatch, capsys):
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

    def test_truncates_the_label_to_60_characters(self, monkeypatch, capsys):
        _run(monkeypatch, [])
        prog = _FauxEngine.dernier.progression
        prog(1, 2, "x" * 200)
        out = capsys.readouterr().out
        # The 200 xs got clipped to 60.
        assert "x" * 60 in out
        assert "x" * 61 not in out
