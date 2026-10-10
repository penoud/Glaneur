# tests/conftest.py — at the very top, before any PySide6 import
from __future__ import annotations

import os

# Tests must never need a display: without this, Qt tries the xcb plugin and
# aborts the whole process (SIGABRT) on headless machines instead of failing.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def pytest_configure(config):
    """Ensure QApplication exists before any test module imports app.

    ``test_app_preferences.py`` and ``test_app_profile_table.py`` import
    ``app`` at module level.  Without this hook pytest-qt hasn't yet
    created ``qapp`` at that point, so ``import app`` triggers the
    dreaded *Application shutdowned while processing pending Qt events*
    error.

    Creating it here (during pytest's configuration phase) guarantees
    ``QApplication.instance()`` is available when the test modules are
    imported, before any test method runs.
    """
    from PySide6.QtWidgets import QApplication

    if QApplication.instance() is None:
        QApplication([])
