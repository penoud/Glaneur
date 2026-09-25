"""Tests pytest-qt des QThread de vérification et téléchargement.

Requiert `pytest-qt` et un display Qt : sur CI headless, définir
`QT_QPA_PLATFORM=offscreen`.

Chaque test appelle `thread.wait()` après avoir reçu le signal attendu :
sans cela, le wrapper Python peut être garbage-collecté avant que Qt ait
fini de terminer le QThread C++, ce qui déclenche
« QThread: Destroyed while thread is still running » puis SIGABRT.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from Glaneur.updater.models import Release, ReleaseAsset, UpdateInfo
from Glaneur.updater.qt_threads import (
    TelechargementMiseAJour,
    VerificationMiseAJour,
)
from Glaneur.updater.version import Version


def _attendre_fin_propre(thread) -> None:
    """Attend que le QThread ait vraiment quitté run() avant le GC Python."""
    assert thread.wait(2000), "QThread ne s'est pas terminé dans le délai imparti"


# --------------------------------------------------------------------------- #
# VerificationMiseAJour
# --------------------------------------------------------------------------- #

class TestVerificationMiseAJour:
    def test_emet_disponible_si_release_plus_recente(self, qtbot):
        release = Release(Version.parse("v999.0.0"), "v999.0.0", assets=())
        provider = MagicMock()
        provider.check.return_value = UpdateInfo(Version.parse("1.0.0"), release)

        thread = VerificationMiseAJour(provider=provider)
        with qtbot.waitSignal(thread.disponible, timeout=3000) as blocker:
            thread.start()
        _attendre_fin_propre(thread)
        info = blocker.args[0]
        assert info.is_available
        assert info.latest.version == release.version

    def test_emet_aucune_maj_si_a_jour(self, qtbot):
        provider = MagicMock()
        provider.check.return_value = UpdateInfo(Version.parse("1.0.0"), None)

        thread = VerificationMiseAJour(provider=provider)
        with qtbot.waitSignal(thread.aucune_maj, timeout=3000) as blocker:
            thread.start()
        _attendre_fin_propre(thread)
        assert not blocker.args[0].is_available

    def test_emet_erreur_si_exception(self, qtbot):
        provider = MagicMock()
        provider.check.side_effect = RuntimeError("boom")

        thread = VerificationMiseAJour(provider=provider)
        with qtbot.waitSignal(thread.erreur, timeout=3000) as blocker:
            thread.start()
        _attendre_fin_propre(thread)
        assert "boom" in blocker.args[0]


# --------------------------------------------------------------------------- #
# TelechargementMiseAJour
# --------------------------------------------------------------------------- #

@pytest.fixture
def fausse_release():
    installer = ReleaseAsset("Glaneur-2.0.0-setup.exe", "https://x/i.exe", 42)
    checksum = ReleaseAsset("Glaneur-2.0.0-setup.exe.sha256", "https://x/i.sha256", 64)
    return Release(Version.parse("2.0.0"), "v2.0.0", assets=(installer, checksum))


class TestTelechargementMiseAJour:
    def test_emet_termine_apres_verification(self, qtbot, fausse_release, tmp_path, monkeypatch):
        installer_path = tmp_path / "installer.exe"
        installer_path.write_bytes(b"contenu")
        checksum_path = tmp_path / "installer.sha256"
        checksum_path.write_text("a" * 64)

        # download rend le fichier installateur puis le fichier checksum
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

        thread = TelechargementMiseAJour(fausse_release)
        with qtbot.waitSignal(thread.termine, timeout=3000) as blocker:
            thread.start()
        _attendre_fin_propre(thread)
        assert blocker.args[0] == installer_path
        assert installer_path.exists()  # non supprimé en cas de succès

    def test_supprime_fichier_si_sha256_incorrect(self, qtbot, fausse_release, tmp_path, monkeypatch):
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

        thread = TelechargementMiseAJour(fausse_release)
        with qtbot.waitSignal(thread.erreur, timeout=3000) as blocker:
            thread.start()
        _attendre_fin_propre(thread)
        assert "SHA-256" in blocker.args[0]
        assert not installer_path.exists()  # nettoyé après échec de vérification

    def test_emet_erreur_si_installateur_manquant(self, qtbot):
        # Release sans asset installer Windows attendu
        release_vide = Release(Version.parse("2.0.0"), "v2.0.0", assets=())
        thread = TelechargementMiseAJour(release_vide)
        with qtbot.waitSignal(thread.erreur, timeout=3000) as blocker:
            thread.start()
        _attendre_fin_propre(thread)
        assert "Installateur" in blocker.args[0] or "checksum" in blocker.args[0]
