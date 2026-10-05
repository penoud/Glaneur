"""Enforce per-module branch coverage floors from the ``.coverage`` data file.

Run after ``pytest --cov``. Exits non-zero if any group falls below its floor.
"""

from __future__ import annotations

import io
import sys

import coverage
from coverage.exceptions import NoDataError

# Floors may only go up (see CONTRIBUTING / feuille de route). Values
# below are the branch-in baseline captured when the ratchet was first
# wired into CI (US-VERIF-01, 2026-09-28) — the aspirational 100/100/100
# numbers of the earlier design were never enforced. Each future sprint
# that closes a coverage gap raises the matching floor to the new
# measurement in the same PR.
FLOORS: dict[str, float] = {
    "Glaneur/sources/*": 98.0,
    "Glaneur/scheduler.py": 95.0,
    "Glaneur/config.py": 97.0,
    "Glaneur/engine/*": 98.5,
}


def main() -> int:
    """Check every coverage floor and report the failing groups.

    Returns:
        Process exit code: 0 if all floors are met, 1 otherwise.
    """
    cov = coverage.Coverage()
    cov.load()
    failures: list[str] = []
    for pattern, floor in FLOORS.items():
        out = io.StringIO()
        try:
            pct = cov.report(include=[pattern], file=out)
        except NoDataError:
            # A group with no measured file is a misconfiguration, not a pass.
            failures.append(f"{pattern}: no data")
            continue
        status = "ok" if pct >= floor else "FAIL"
        print(f"{status:4} {pattern:28} {pct:6.1f} % (floor {floor:.0f} %)")
        if pct < floor:
            failures.append(pattern)
            print(out.getvalue())
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
