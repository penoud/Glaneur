"""PreToolUse guard for subagents allowed to write only under given directories."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    """Block writes outside the directories given on the command line.

    Args:
        argv: Script name followed by allowed directories, relative to the repository root.

    Returns:
        2 to block the tool call, 0 to let it run.
    """
    allowed = [a.strip("/\\").replace("\\", "/") for a in argv[1:]]
    payload = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    raw = (payload.get("tool_input") or {}).get("file_path")
    if not raw:
        return 0
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or ".").resolve()
    try:
        rel = Path(raw).resolve().relative_to(root).as_posix()
    except ValueError:
        rel = None
    if rel and any(rel == a or rel.startswith(a + "/") for a in allowed):
        return 0
    print(
        f"Blocked: this agent may only write under {', '.join(allowed)}. "
        "Describe the production change in your report instead.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
