"""pytest-qt tests for the update-check and download QThreads.

Requires `pytest-qt` and a Qt display: on headless CI, set
`QT_QPA_PLATFORM=offscreen`.

Every test calls `thread.wait()` after receiving the expected signal:
without it, the Python wrapper can be garbage-collected before Qt has
finished terminating the C++ QThread, which triggers
"QThread: Destroyed while thread is still running" followed by SIGABRT.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from Glaneur.updater.models import Release, ReleaseAsset, UpdateInfo
from Glaneur.updater.qt_threads import (
    UpdateCheck,
    UpdateDownload,
)
from Glaneur.updater.version import Version


def _attendre_fin_propre(thread) -> None:
    """Waits until the QThread has really exited run() before Python GC."""
    assert thread.wait(2000), "QThread ne s'est pas terminé dans le délai imparti"


# --------------------------------------------------------------------------- #
# UpdateCheck
# --------------------------------------------------------------------------- #

class TestUpdateCheck:
    def test_emits_available_when_release_is_newer(self, qtbot):
        release = Release(Version.parse("v999.0.0"), "v999.0.0", assets=())
        provider = MagicMock()
        provider.check.return_value = UpdateInfo(Version.parse("1.0.0"), release)

        thread = UpdateCheck(provider=provider)
        with qtbot.waitSignal(thread.available, timeout=3000) as blocker:
            thread.start()
        _attendre_fin_propre(thread)
        info = blocker.args[0]
        assert info.is_available
        assert info.latest.version == release.version

    def test_emits_no_update_when_up_to_date(self, qtbot):
        provider = MagicMock()
        provider.check.return_value = UpdateInfo(Version.parse("1.0.0"), None)

        thread = UpdateCheck(provider=provider)
        with qtbot.waitSignal(thread.up_to_date, timeout=3000) as blocker:
            thread.start()
        _attendre_fin_propre(thread)
        assert not blocker.args[0].is_available

    def test_emits_error_on_exception(self, qtbot):
        provider = MagicMock()
        provider.check.side_effect = RuntimeError("boom")

        thread = UpdateCheck(provider=provider)
        with qtbot.waitSignal(thread.error, timeout=3000) as blocker:
            thread.start()
        _attendre_fin_propre(thread)
        assert "boom" in blocker.args[0]


# --------------------------------------------------------------------------- #
# UpdateDownload
# --------------------------------------------------------------------------- #

@pytest.fixture
def fausse_release():
    installer = ReleaseAsset("Glaneur-2.0.0-setup.exe", "https://x/i.exe", 42)
    checksum = ReleaseAsset("Glaneur-2.0.0-setup.exe.sha256", "https://x/i.sha256", 64)
    return Release(Version.parse("2.0.0"), "v2.0.0", assets=(installer, checksum))


class TestUpdateDownload:
    def test_emits_finished_after_verification(self, qtbot, fausse_release, tmp_path, monkeypatch):
        installer_path = tmp_path / "installer.exe"
        installer_path.write_bytes(b"contenu")
        checksum_path = tmp_path / "installer.sha256"
        checksum_path.write_text("a" * 64)

        # download returns the installer file then the checksum file
        rendus = iter([installer_path, checksum_path])
        monkeypatch.setattr(
            "Glaneur.updater.qt_threads.download",
            lambda asset, dossier: next(rendus),
        )
        monkeypatch.setattr(
            "Glaneur.updater.qt_threads.temporary_directory",
            lambda: tmp_path,
        )
        monkeypatch.setattr(
            "Glaneur.updater.qt_threads.verify_sha256",
            lambda fichier, texte: True,
        )

        thread = UpdateDownload(fausse_release)
        with qtbot.waitSignal(thread.completed, timeout=3000) as blocker:
            thread.start()
        _attendre_fin_propre(thread)
        assert blocker.args[0] == installer_path
        assert installer_path.exists()  # not deleted on success

    def test_deletes_file_on_incorrect_sha256(self, qtbot, fausse_release, tmp_path, monkeypatch):
        installer_path = tmp_path / "installer.exe"
        installer_path.write_bytes(b"contenu")
        checksum_path = tmp_path / "installer.sha256"
        checksum_path.write_text("a" * 64)

        rendus = iter([installer_path, checksum_path])
        monkeypatch.setattr(
            "Glaneur.updater.qt_threads.download",
            lambda asset, dossier: next(rendus),
        )
        monkeypatch.setattr(
            "Glaneur.updater.qt_threads.temporary_directory",
            lambda: tmp_path,
        )
        monkeypatch.setattr(
            "Glaneur.updater.qt_threads.verify_sha256",
            lambda fichier, texte: False,
        )

        thread = UpdateDownload(fausse_release)
        with qtbot.waitSignal(thread.error, timeout=3000) as blocker:
            thread.start()
        _attendre_fin_propre(thread)
        assert "SHA-256" in blocker.args[0]
        assert not installer_path.exists()  # cleaned up after verification failure

    def test_emits_error_when_installer_missing(self, qtbot):
        # Release without the expected Windows installer asset
        release_vide = Release(Version.parse("2.0.0"), "v2.0.0", assets=())
        thread = UpdateDownload(release_vide)
        with qtbot.waitSignal(thread.error, timeout=3000) as blocker:
            thread.start()
        _attendre_fin_propre(thread)
        assert "Installateur" in blocker.args[0] or "checksum" in blocker.args[0]
