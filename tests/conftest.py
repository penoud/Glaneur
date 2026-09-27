# tests/conftest.py — at the very top, before any PySide6 import
from __future__ import annotations

import os

# Tests must never need a display: without this, Qt tries the xcb plugin and
# aborts the whole process (SIGABRT) on headless machines instead of failing.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
