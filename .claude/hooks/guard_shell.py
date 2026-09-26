"""PreToolUse guard: block operations that must never run without maintainer approval.

``git push`` and ``git tag`` go through the ``permissions.ask`` mechanism in
``.claude/settings.json`` — the user confirms each call — so this hook only
blocks what has no confirmation path: GitHub release creation, PR merge, and
unrequested dependency installs. Windows has no Claude Code sandbox, so the
hook applies equally to Bash and PowerShell.
"""

from __future__ import annotations

import json
import re
import shlex
import sys
from pathlib import PurePath

_SEPARATORS = re.compile(r"&&|\|\||[;|&\n]")
_GIT_OPTIONS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree"}
_REQUIREMENT_FLAGS = ("-r", "--requirement")


def _tokens(segment: str) -> list[str]:
    try:
        return shlex.split(segment)
    except ValueError:
        return segment.split()


def _program(token: str) -> str:
    return PurePath(token.replace("\\", "/")).name.lower().removesuffix(".exe")


def _skip_options(args: list[str], with_value: set[str]) -> list[str]:
    i = 0
    while i < len(args) and args[i].startswith("-"):
        i += 2 if args[i] in with_value else 1
    return args[i:]


def _only_requirements(args: list[str]) -> bool:
    files = [args[i + 1] for i, a in enumerate(args[:-1]) if a in _REQUIREMENT_FLAGS]
    others = [
        a for i, a in enumerate(args)
        if not a.startswith("-") and (i == 0 or args[i - 1] not in _REQUIREMENT_FLAGS)
    ]
    return bool(files) and not others and all(
        PurePath(f).name.startswith("requirements") for f in files
    )


def reason(command: str) -> str | None:
    """Explain why a shell command must be blocked.

    Args:
        command: Command line as sent by the Bash or PowerShell tool.

    Returns:
        A message for Claude, or ``None`` if the command may run.
    """
    for segment in _SEPARATORS.split(command):
        tokens = _tokens(segment)
        if not tokens:
            continue
        prog, args = _program(tokens[0]), tokens[1:]
        if prog in ("python", "python3", "py") and args[:2] == ["-m", "pip"]:
            prog, args = "pip", args[2:]

        if prog == "gh" and args[:1] == ["release"] and args[1:2] not in (["list"], ["view"]):
            return "GitHub releases are created by the release workflow."
        elif prog == "gh" and args[:2] == ["pr", "merge"]:
            return "merging into main publishes; the maintainer merges."
        elif prog in ("pip", "pip3") and args[:1] == ["install"] and not _only_requirements(args[1:]):
            return "installing a new dependency needs the maintainer's approval."
    return None


def main() -> int:
    """Read the hook payload from stdin and block forbidden commands.

    Returns:
        2 to block the tool call, 0 to let it run.
    """
    payload = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    why = reason((payload.get("tool_input") or {}).get("command") or "")
    if why is None:
        return 0
    print(f"Blocked: {why} Report it instead of working around this guard.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
