"""PostToolUse hook: report fatal Python errors right after an edit.

Only syntax errors and undefined names: the full ruff configuration still
fails on files that carry known debt, and unused-import checks would fire
between adding an import and using it. The test-runner agent runs full ruff.
"""

from __future__ import annotations

import json
import subprocess
import sys

_FATAL_RULES = "E9,F63,F7,F82"


def main() -> int:
    """Lint the edited file and feed fatal errors back to Claude.

    Returns:
        2 when ruff reports fatal errors, 0 otherwise.
    """
    payload = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    path = (payload.get("tool_input") or {}).get("file_path") or ""
    if not path.endswith(".py"):
        return 0
    proc = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--quiet", "--select", _FATAL_RULES, path],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
    )
    if proc.returncode == 0 or "No module named ruff" in proc.stderr:
        # Missing dev dependencies are the test-runner's to report, not a reason to block edits.
        return 0
    sys.stderr.write(proc.stdout + proc.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
