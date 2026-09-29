"""Tests for the per-folder OS lock (US-VERIF-03).

Covers three layers of the same invariant — a target directory must be
held by at most one Glaneur process at a time:

- the :func:`Glaneur.engine._folder_lock.folder_lock` context manager
  itself (intra-process double acquisition, sequential re-acquisition,
  manual removal of the lock file, cross-process contention);
- the :meth:`Glaneur.engine.core.Engine.run` wrapper (a busy folder
  returns ``RunResult(busy=True)`` without touching the manifest, the
  cache, or the source);
- the :func:`cli.main` translation of ``res.busy`` into exit code 3.

No network. No real ``time.sleep`` waits: the multiprocessing test
synchronises through a handshake queue with a timeout.
"""

from __future__ import annotations

import multiprocessing
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import cli
from Glaneur.engine import Engine, Options
from Glaneur.engine._folder_lock import LOCK_NAME, FolderBusy, folder_lock
from Glaneur.engine.cache_path import cache_path
from Glaneur.engine.manifest_path import manifest_path
from Glaneur.engine.result import RunResult

# --------------------------------------------------------------------------- #
# Top-level worker for the multiprocessing test.
#
# `multiprocessing.get_context("spawn")` re-imports this module in the child
# process, so its target function must be picklable and defined at module
# level. A nested `def` or lambda would fail on Windows.
# --------------------------------------------------------------------------- #


def _child_try_lock(target_dir_str: str, go_queue, result_queue) -> None:
    """Wait for the parent's go signal then try to acquire the folder lock.

    Pushes ``"FolderBusy"`` when the parent still holds the lock,
    ``"acquired"`` when the acquisition unexpectedly succeeds, or an
    error tag on any other failure. Never raises to the caller — the
    parent only reads the queue.
    """
    try:
        go_queue.get(timeout=10)
        try:
            with folder_lock(Path(target_dir_str)):
                result_queue.put("acquired")
        except FolderBusy:
            result_queue.put("FolderBusy")
        except BaseException as exc:  # noqa: BLE001 - defensive report to parent
            result_queue.put(f"error:{exc!r}")  # pragma: no cover
    except BaseException as exc:  # noqa: BLE001 - defensive report to parent
        result_queue.put(f"handshake-error:{exc!r}")  # pragma: no cover


# --------------------------------------------------------------------------- #
# folder_lock context manager
# --------------------------------------------------------------------------- #


class TestFolderLock:
    """Direct tests of the ``folder_lock`` context manager contract."""

    def test_double_acquisition_intraprocess_raises_folder_busy(self, tmp_path):
        """A second acquisition on the same folder raises FolderBusy."""
        with folder_lock(tmp_path), pytest.raises(FolderBusy), folder_lock(
            tmp_path,
        ):
            pass  # pragma: no cover - the inner enter must raise

    def test_sequential_acquisition_succeeds(self, tmp_path):
        """Releasing then re-acquiring the same folder is allowed."""
        with folder_lock(tmp_path):
            pass
        # The lock file itself persists after release: only the OS-level
        # lock is dropped, not the sentinel file.
        assert (tmp_path / LOCK_NAME).exists()
        # A second acquisition must succeed cleanly.
        with folder_lock(tmp_path):
            pass

    def test_manual_deletion_of_file_does_not_break_next_acquisition(
        self, tmp_path,
    ):
        """Deleting the lock sentinel between two runs stays safe."""
        with folder_lock(tmp_path):
            pass
        (tmp_path / LOCK_NAME).unlink()
        # The context manager must recreate the file and take the lock.
        with folder_lock(tmp_path):
            assert (tmp_path / LOCK_NAME).exists()

    def test_two_processes_second_raises_folder_busy(self, tmp_path):
        """A second process trying to enter a locked folder gets FolderBusy."""
        ctx = multiprocessing.get_context("spawn")
        go_queue = ctx.Queue()
        result_queue = ctx.Queue()
        process = ctx.Process(
            target=_child_try_lock,
            args=(str(tmp_path), go_queue, result_queue),
        )
        process.start()
        try:
            with folder_lock(tmp_path):
                # Signal the child to attempt its acquisition while the
                # parent still holds the OS-level lock.
                go_queue.put("go")
                result = result_queue.get(timeout=10)
            process.join(timeout=10)
        finally:
            if process.is_alive():  # pragma: no cover - safety net
                process.terminate()
                process.join(timeout=5)
        assert result == "FolderBusy"


# --------------------------------------------------------------------------- #
# Engine.run integration
# --------------------------------------------------------------------------- #


class TestEngineRunBusy:
    """Integration: Engine.run under a held folder lock returns busy."""

    def test_engine_run_returns_busy_true_when_folder_locked(self, tmp_path):
        """Engine.run bails out with RunResult(busy=True) on a locked folder."""
        options = Options(
            target_dir=tmp_path,
            site="https://x.example",
            delay=0,
            source_type="wordpress",
        )
        moteur = Engine(options)
        # A busy folder must never touch the source: swap it for a mock
        # so any attempted call would show up.
        moteur.source = MagicMock()

        with folder_lock(tmp_path):
            res = moteur.run()

        assert res.busy is True
        assert res.downloaded == 0
        assert res.resumed == 0
        assert res.failures == 0
        assert res.message == ""
        assert res.interrupted is False
        assert res.deferred is False
        # No manifest, no cache: the busy branch writes nothing.
        assert not manifest_path(tmp_path).exists()
        assert not cache_path(tmp_path).exists()
        # And absolutely no source traffic.
        moteur.source.inventory.assert_not_called()
        moteur.source.resolve_groups.assert_not_called()


# --------------------------------------------------------------------------- #
# CLI translation of the busy flag
# --------------------------------------------------------------------------- #


class _FauxBusyEngine:
    """Stub `Engine` returning a busy `RunResult` unconditionally.

    Mirrors the stub pattern used in ``tests/test_cli.py`` but scoped to
    the busy branch: no configurable resultat, no captured options.
    """

    def __init__(self, options, journal=None, progression=None, stop_event=None):
        self.options = options
        self.stop_event = MagicMock()

    def run(self) -> RunResult:
        return RunResult(busy=True)


class TestCliBusyExitCode:
    """cli.main translates RunResult(busy=True) into exit code 3."""

    def test_cli_exits_code_3_when_engine_returns_busy(
        self, monkeypatch, tmp_path, capsys,
    ):
        """A busy engine result yields exit code 3 and a stderr hint."""
        # Insulate Config from the user's real settings file.
        real_charger = cli.Config.load

        def faux_charger(_chemin=None):
            return real_charger(Path("/nonexistent-config-for-tests.json"))

        monkeypatch.setattr(cli.Config, "load", staticmethod(faux_charger))
        monkeypatch.setattr(cli, "Engine", _FauxBusyEngine)
        monkeypatch.setattr(
            sys, "argv", ["cli.py", "--dossier", str(tmp_path)],
        )

        rc = cli.main()

        assert rc == 3
        err = capsys.readouterr().err
        assert str(tmp_path) in err


