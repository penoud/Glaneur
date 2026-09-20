"""Point d'entree minimal de l'updater Windows."""

from __future__ import annotations

import sys

from .updater.windows import run_updater


if __name__ == "__main__":
    raise SystemExit(run_updater(sys.argv[1:]))
