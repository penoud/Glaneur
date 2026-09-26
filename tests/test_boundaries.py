"""Architecture boundaries from CLAUDE.md that review alone does not hold."""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "Glaneur"
QT_MODULES = ("PySide6", "shiboken6", "PyQt5", "PyQt6")
# Debt to shrink, never to extend. Strict xfail turns the fix into a failure
# until the entry is removed, so the list cannot silently go stale.
KNOWN_QT_IMPORTS = {"Glaneur/engine/moteur.py", "Glaneur/scheduler.py"}
NETWORK_CALLS = {"Session", "get", "post", "head", "put", "delete", "request"}


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _imports(path: Path) -> Iterator[str]:
    for node in ast.walk(_parse(path)):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.module


def _qt_cases() -> Iterator[object]:
    candidates = [PACKAGE / "scheduler.py", PACKAGE / "detect.py"]
    candidates += sorted((PACKAGE / "engine").glob("*.py"))
    candidates += sorted((PACKAGE / "sources").glob("*.py"))
    for path in (p for p in candidates if p.is_file()):
        rel = path.relative_to(ROOT).as_posix()
        marks = (
            [pytest.mark.xfail(strict=True, reason="known debt, see CLAUDE.md")]
            if rel in KNOWN_QT_IMPORTS else []
        )
        yield pytest.param(path, id=rel, marks=marks)


def _source_modules() -> list[object]:
    # base.py defines the Transport itself; every other source must go through it.
    return [
        pytest.param(p, id=p.name)
        for p in sorted((PACKAGE / "sources").glob("*.py"))
        if p.name not in ("__init__.py", "base.py")
    ]


@pytest.mark.parametrize("path", list(_qt_cases()))
def test_no_qt_outside_ui(path: Path) -> None:
    """Engine, sources, detection and scheduler run without Qt."""
    qt = sorted({m for m in _imports(path) if m.split(".")[0] in QT_MODULES})
    assert not qt, f"{path.name} imports {qt}"


@pytest.mark.parametrize("path", _source_modules())
def test_sources_use_the_engine_transport(path: Path) -> None:
    """A source never opens its own session nor calls requests directly."""
    offending = []
    for node in ast.walk(_parse(path)):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name) and node.func.value.id == "requests"
                and node.func.attr in NETWORK_CALLS):
            offending.append(node.lineno)
        elif isinstance(node, ast.ImportFrom) and node.module == "requests":
            offending += [node.lineno for a in node.names if a.name in NETWORK_CALLS]
    assert not offending, f"{path.name}: direct requests usage at lines {offending}"


def test_every_package_has_init() -> None:
    """A package without __init__.py imports as an empty namespace ('unknown location')."""
    dirs = [PACKAGE, *(d for d in PACKAGE.rglob("*") if d.is_dir())]
    missing = [
        d.relative_to(ROOT).as_posix() for d in dirs
        if "__pycache__" not in d.parts and any(d.glob("*.py"))
        and not (d / "__init__.py").is_file()
    ]
    assert not missing
