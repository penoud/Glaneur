"""The Claude Code guard hooks block what they must, and only that."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / ".claude" / "hooks"
INIT = ROOT / "Glaneur" / "__init__.py"


def _run(script: str, payload: dict, *args: str) -> int:
    proc = subprocess.run(
        [sys.executable, str(HOOKS / script), *args],
        input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        capture_output=True, check=False,
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(ROOT)},
    )
    return proc.returncode


@pytest.mark.parametrize(("command", "code"), [
    ("gh release create v9.9.9", 2),
    ("gh pr merge 12", 2),
    ("pip install httpx", 2),
    ("python -m pip install httpx", 2),
    ("git status", 0),
    ("git tag --list", 0),
    # `git push` and `git tag` are no longer hard-blocked by the hook —
    # they go through the `ask` permission in .claude/settings.json instead,
    # so the user confirms each call.
    ("git push origin main", 0),
    ("git -C . push", 0),
    ("cd sub && git push", 0),
    ("git tag v9.9.9", 0),
    ('git commit -m "réglage : do not push yet"', 0),
    ("python -m pip install -r requirements-dev.txt", 0),
])
def test_guard_shell(command: str, code: int) -> None:
    """GitHub releases and new dependencies are blocked; everyday git is not."""
    payload = {"tool_name": "Bash", "tool_input": {"command": command}}
    assert _run("guard_shell.py", payload) == code


def test_guard_version_blocks_edit() -> None:
    """An edit touching __version__ is blocked."""
    payload = {"tool_name": "Edit", "tool_input": {
        "file_path": str(INIT), "old_string": "__version__", "new_string": "__version__"}}
    assert _run("guard_version.py", payload) == 2


def test_guard_version_write_same_version_passes() -> None:
    """Rewriting the file with the same version is allowed; changing it is not."""
    text = INIT.read_text(encoding="utf-8")
    same = {"tool_name": "Write", "tool_input": {"file_path": str(INIT), "content": text}}
    bumped_text = re.sub(r"""(__version__\s*=\s*["'])[^"']+""", r"\g<1>99.0.0", text)
    bumped = {"tool_name": "Write", "tool_input": {"file_path": str(INIT), "content": bumped_text}}
    assert _run("guard_version.py", same) == 0
    assert _run("guard_version.py", bumped) == 2


def test_guard_version_ignores_other_files() -> None:
    """Other files are not concerned by the version guard."""
    payload = {"tool_name": "Edit", "tool_input": {
        "file_path": str(ROOT / "Glaneur" / "engine.py"),
        "old_string": "__version__", "new_string": "x"}}
    assert _run("guard_version.py", payload) == 0


@pytest.mark.parametrize(("target", "code"), [
    (ROOT / "tests" / "test_new.py", 0),
    (ROOT / "Glaneur" / "engine.py", 2),
    (ROOT.parent / "elsewhere.py", 2),
])
def test_guard_paths(target: Path, code: int) -> None:
    """Test-only agents cannot write production code or outside the repository."""
    payload = {"tool_name": "Write", "tool_input": {"file_path": str(target), "content": ""}}
    assert _run("guard_paths.py", payload, "tests") == code
