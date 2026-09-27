"""Direct-call tests of `UpdateCheck.run` and
`UpdateDownload.run`.

The pytest-qt tests in `test_updater_threads.py` drive the threads via
`thread.start()` — code executed inside the worker thread is not seen
by `coverage.py` (which tracks the main thread only). These tests
invoke `run()` synchronously in the main thread so coverage picks it
up. Signals are captured via a plain slot connected in the same
thread, so no event loop is needed.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from Glaneur.updater.models import Release, ReleaseAsset, UpdateInfo
from Glaneur.updater.qt_threads import (
    UpdateDownload,
    UpdateCheck,
)
from Glaneur.updater.version import Version


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


class _Recepteur:
    """Buffer that a Qt Signal can connect to; stores each emission."""

    def __init__(self) -> None:
        self.args: list[tuple] = []

    def __call__(self, *args) -> None:
        self.args.append(args)


@pytest.fixture
def qapp():
    """Ensure a `QCoreApplication` exists — `QThread` and `Signal` need
    one, even when we do not spin its event loop.
    """
    from PySide6.QtCore import QCoreApplication
    app = QCoreApplication.instance() or QCoreApplication([])
    return app


# --------------------------------------------------------------------------- #
# UpdateCheck.run
# --------------------------------------------------------------------------- #


class TestVerificationRun:
    def test_disponible_emis_si_release_plus_recente(self, qapp):
        release = Release(Version.parse("v999.0.0"), "v999.0.0", assets=())
        provider = MagicMock()
        provider.check.return_value = UpdateInfo(Version.parse("1.0.0"), release)

        thread = UpdateCheck(provider=provider)
        recu_dispo, recu_aucune, recu_err = _Recepteur(), _Recepteur(), _Recepteur()
        thread.available.connect(recu_dispo)
        thread.up_to_date.connect(recu_aucune)
        thread.error.connect(recu_err)

        thread.run()

        assert len(recu_dispo.args) == 1
        assert recu_dispo.args[0][0].latest.version == release.version
        assert recu_aucune.args == []
        assert recu_err.args == []

    def test_aucune_maj_emis_si_deja_a_jour(self, qapp):
        provider = MagicMock()
        provider.check.return_value = UpdateInfo(Version.parse("1.0.0"), None)

        thread = UpdateCheck(provider=provider)
        recu_aucune, recu_dispo = _Recepteur(), _Recepteur()
        thread.up_to_date.connect(recu_aucune)
        thread.available.connect(recu_dispo)

        thread.run()

        assert len(recu_aucune.args) == 1
        assert recu_aucune.args[0][0].is_available is False
        assert recu_dispo.args == []

    def test_erreur_emise_si_exception(self, qapp):
        provider = MagicMock()
        provider.check.side_effect = RuntimeError("boom")

        thread = UpdateCheck(provider=provider)
        recu = _Recepteur()
        thread.error.connect(recu)

        thread.run()

        assert len(recu.args) == 1
        assert "boom" in recu.args[0][0]

    def test_provider_par_defaut_utilise_github(self, qapp):
        # Not exercising a network call: only verifying that omitting
        # `provider` picks the `GitHubReleaseProvider` default.
        thread = UpdateCheck()
        assert thread._provider.__class__.__name__ == "GitHubReleaseProvider"


# --------------------------------------------------------------------------- #
# UpdateDownload.run
# --------------------------------------------------------------------------- #


@pytest.fixture
def fausse_release():
    installer = ReleaseAsset("Glaneur-2.0.0-setup.exe", "https://x/i.exe", 42)
    checksum = ReleaseAsset(
        "Glaneur-2.0.0-setup.exe.sha256", "https://x/i.sha256", 64,
    )
    return Release(Version.parse("2.0.0"), "v2.0.0", assets=(installer, checksum))


def _mock_download_pair(monkeypatch, installer_path: Path, checksum_path: Path,
                       tmp_path: Path, *, verify: bool = True):
    """Patch qt_threads' download/temporary_directory/verify_sha256 for
    a two-step download (installer then checksum).
    """
    rendus = iter([installer_path, checksum_path])
    monkeypatch.setattr(
        "Glaneur.updater.qt_threads.download",
        lambda _asset, _dossier: next(rendus),
    )
    monkeypatch.setattr(
        "Glaneur.updater.qt_threads.temporary_directory",
        lambda: tmp_path,
    )
    monkeypatch.setattr(
        "Glaneur.updater.qt_threads.verify_sha256",
        lambda _fichier, _texte: verify,
    )


class TestTelechargementRun:
    def test_termine_emis_apres_verification_ok(
        self, qapp, fausse_release, tmp_path, monkeypatch,
    ):
        installer_path = tmp_path / "installer.exe"
        installer_path.write_bytes(b"contenu")
        checksum_path = tmp_path / "installer.sha256"
        checksum_path.write_text("a" * 64)
        _mock_download_pair(monkeypatch, installer_path, checksum_path, tmp_path)

        thread = UpdateDownload(fausse_release)
        recu_termine, recu_err = _Recepteur(), _Recepteur()
        thread.completed.connect(recu_termine)
        thread.error.connect(recu_err)

        thread.run()

        assert len(recu_termine.args) == 1
        fichier, dossier = recu_termine.args[0]
        assert fichier == installer_path
        assert dossier == str(tmp_path)
        assert installer_path.exists()
        assert recu_err.args == []

    def test_supprime_fichier_si_sha256_faux(
        self, qapp, fausse_release, tmp_path, monkeypatch,
    ):
        installer_path = tmp_path / "installer.exe"
        installer_path.write_bytes(b"contenu")
        checksum_path = tmp_path / "installer.sha256"
        checksum_path.write_text("a" * 64)
        _mock_download_pair(
            monkeypatch, installer_path, checksum_path, tmp_path, verify=False,
        )

        thread = UpdateDownload(fausse_release)
        recu_err, recu_termine = _Recepteur(), _Recepteur()
        thread.error.connect(recu_err)
        thread.completed.connect(recu_termine)

        thread.run()

        assert len(recu_err.args) == 1
        assert "SHA-256" in recu_err.args[0][0]
        assert not installer_path.exists()
        assert recu_termine.args == []

    def test_erreur_si_installateur_manquant(self, qapp):
        release_vide = Release(Version.parse("2.0.0"), "v2.0.0", assets=())
        thread = UpdateDownload(release_vide)
        recu = _Recepteur()
        thread.error.connect(recu)

        thread.run()

        assert len(recu.args) == 1
        message = recu.args[0][0]
        assert "Installateur" in message or "checksum" in message

    def test_erreur_si_checksum_manquant(self, qapp):
        # Installer is present, but its `.sha256` sibling is not.
        installer = ReleaseAsset(
            "Glaneur-2.0.0-setup.exe", "https://x/i.exe", 42,
        )
        release = Release(Version.parse("2.0.0"), "v2.0.0", assets=(installer,))
        thread = UpdateDownload(release)
        recu = _Recepteur()
        thread.error.connect(recu)

        thread.run()

        assert len(recu.args) == 1
        assert "checksum" in recu.args[0][0].lower() or "Installateur" in recu.args[0][0]

    def test_erreur_si_download_echoue(
        self, qapp, fausse_release, tmp_path, monkeypatch,
    ):
        # `download` raises: the thread must translate it into an
        # `erreur` signal, not let the exception propagate.
        from Glaneur.updater.downloader import DownloadError

        monkeypatch.setattr(
            "Glaneur.updater.qt_threads.temporary_directory",
            lambda: tmp_path,
        )

        def download_qui_leve(*_args, **_kw):
            raise DownloadError("réseau HS")

        monkeypatch.setattr(
            "Glaneur.updater.qt_threads.download", download_qui_leve,
        )

        thread = UpdateDownload(fausse_release)
        recu = _Recepteur()
        thread.error.connect(recu)

        thread.run()

        assert len(recu.args) == 1
        assert "réseau HS" in recu.args[0][0]
