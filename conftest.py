"""Rend le paquet `Glaneur` importable pendant les tests."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
