"""PreToolUse guard: agents never change ``__version__``.

A push on ``main`` publishes whatever ``__version__`` says, so only the
maintainer may change it.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_VERSION = re.compile(r"""__version__\s*=\s*["']([^"']+)["']""")


def _is_version_file(path: Path) -> bool:
    return path.name == "__init__.py" and path.parent.name.lower() == "glaneur"


def main() -> int:
    """Read the hook payload from stdin and block version changes.

    Returns:
        2 to block the tool call, 0 to let it run.
    """
    # Windows stdin defaults to the ANSI code page; payloads carry French text.
    payload = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    tool_input = payload.get("tool_input") or {}
    path = Path(tool_input.get("file_path") or "")
    if not _is_version_file(path):
        return 0

    if payload.get("tool_name") == "Write":
        new = _VERSION.search(tool_input.get("content") or "")
        old = _VERSION.search(path.read_text(encoding="utf-8")) if path.is_file() else None
        changed = old is not None and (new is None or new.group(1) != old.group(1))
    else:
        edits = tool_input.get("edits") or [tool_input]
        changed = any(
            "__version__" in (e.get("old_string") or "") + (e.get("new_string") or "")
            for e in edits
        )

    if changed:
        print(
            "Blocked: __version__ is changed only by the maintainer "
            "(a push on main publishes a release).",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
