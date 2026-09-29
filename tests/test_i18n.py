"""Tests for `Glaneur.i18n`."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from Glaneur import i18n


@pytest.fixture(autouse=True)
def _reset_translator():
    """Ensure the module-level translator does not leak between tests."""
    i18n._translator = None
    yield
    i18n._translator = None


@pytest.fixture
def qapp():
    """Provide a `QApplication` — required by `installTranslator` and
    aligned with pytest-qt's expectations."""
    return QApplication.instance() or QApplication([])


# --------------------------------------------------------------------------- #
# translations_dir
# --------------------------------------------------------------------------- #


class TestTranslationsDir:
    def test_dev_returns_folder_beside_package(self):
        # No `_MEIPASS`: fall back to `<repo>/translations`.
        # It exists in the repo, so the function returns that path.
        d = i18n.translations_dir()
        assert d.is_dir()
        assert d.name == "translations"

    def test_meipass_wins_when_folder_exists(
        self, tmp_path, monkeypatch,
    ):
        # Simulate a PyInstaller bundle by setting `sys._MEIPASS` to a
        # temporary directory that contains a `translations/` folder.
        bundle = tmp_path / "bundle"
        (bundle / "translations").mkdir(parents=True)
        monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)
        assert i18n.translations_dir() == bundle / "translations"

    def test_meipass_absent_falls_back_to_package(self, monkeypatch):
        # If `_MEIPASS` exists but points nowhere, the second candidate
        # (repo root) still wins.
        monkeypatch.setattr(
            sys, "_MEIPASS", "/nonexistent-meipass-xxx", raising=False,
        )
        d = i18n.translations_dir()
        assert d.is_dir()
        assert d.name == "translations"

    def test_last_resort_returns_theoretical_path(self, monkeypatch):
        # Neither candidate exists on disk: the function still returns
        # the theoretical package-adjacent path so the caller sees a
        # coherent (if empty) directory.
        monkeypatch.delattr(sys, "_MEIPASS", raising=False)
        with patch.object(Path, "is_dir", return_value=False):
            d = i18n.translations_dir()
        assert d.name == "translations"


# --------------------------------------------------------------------------- #
# resolve_language
# --------------------------------------------------------------------------- #


class TestResolveLanguage:
    def test_configured_language_wins(self):
        assert i18n.resolve_language("en") == "en"
        assert i18n.resolve_language("fr") == "fr"
        # Any non-empty configured value is returned as-is; validation
        # happens later in `install_translator`.
        assert i18n.resolve_language("zz") == "zz"

    def test_empty_uses_system_locale(self, monkeypatch):
        faux_locale = MagicMock()
        faux_locale.name.return_value = "fr_CH"
        monkeypatch.setattr(
            "Glaneur.i18n.QLocale.system", staticmethod(lambda: faux_locale),
        )
        assert i18n.resolve_language("") == "fr"

    def test_system_locale_without_underscore(self, monkeypatch):
        faux_locale = MagicMock()
        faux_locale.name.return_value = "en"
        monkeypatch.setattr(
            "Glaneur.i18n.QLocale.system", staticmethod(lambda: faux_locale),
        )
        assert i18n.resolve_language("") == "en"

    def test_last_resort_is_fr(self, monkeypatch):
        # `QLocale.system().name()` returning an empty string leads to
        # the `or "fr"` fallback.
        faux_locale = MagicMock()
        faux_locale.name.return_value = ""
        monkeypatch.setattr(
            "Glaneur.i18n.QLocale.system", staticmethod(lambda: faux_locale),
        )
        assert i18n.resolve_language("") == "fr"


# --------------------------------------------------------------------------- #
# install_translator
# --------------------------------------------------------------------------- #


class TestInstallTranslator:
    def test_fr_loads_nothing(self, qapp):
        app = MagicMock(spec=QCoreApplication)
        assert i18n.install_translator(app, "fr") == "fr"
        app.installTranslator.assert_not_called()
        assert i18n._translator is None

    def test_en_loads_the_real_qm(self, qapp):
        # `translations/glaneur_en.qm` ships in the repo — load it end
        # to end, then confirm the translator was installed.
        app = MagicMock(spec=QCoreApplication)
        assert i18n.install_translator(app, "en") == "en"
        app.installTranslator.assert_called_once()
        assert i18n._translator is not None

    def test_unknown_language_falls_back_to_fr(self, qapp):
        app = MagicMock(spec=QCoreApplication)
        # `zz` has no `.qm`: fall back to French and clear the
        # module-level translator.
        assert i18n.install_translator(app, "zz") == "fr"
        app.installTranslator.assert_not_called()
        assert i18n._translator is None

    def test_empty_language_delegated_to_resolve(self, qapp, monkeypatch):
        # An empty configured language reads the system locale.
        faux_locale = MagicMock()
        faux_locale.name.return_value = "fr_FR"
        monkeypatch.setattr(
            "Glaneur.i18n.QLocale.system", staticmethod(lambda: faux_locale),
        )
        app = MagicMock(spec=QCoreApplication)
        assert i18n.install_translator(app) == "fr"
        app.installTranslator.assert_not_called()
