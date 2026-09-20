"""Rend le paquet `WpImageDownloader` importable pendant les tests."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
