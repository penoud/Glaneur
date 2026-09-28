"""Structured user-facing events emitted by the engine.

The engine's ``journal`` callback receives :class:`EngineEvent` values
rather than pre-translated strings. Each event is a stable ``code`` plus
a dictionary of ``params`` needed to render it. This decouples the
engine from Qt (no more ``QCoreApplication.translate`` on the engine
side, see boundary 1 in ``CLAUDE.md``) and gives the UI's profile
status column of lot 5.0 E2 something to build state from.

Rendering rules:

- the UI (``app.py``) is the only place that renders events in French,
  through ``QCoreApplication.translate("UiJournal", …)``;
- the CLI and the file log render events in English via
  :func:`render_en`, defined below;
- unknown codes fall back to ``"<code> <params>"`` so a missing
  template never silently swallows information.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True)
class EngineEvent:
    """Structured user-facing message from the engine.

    Fields documented inline with ``#:`` to keep autodoc/Napoleon from
    duplicating them (same pattern as :class:`Glaneur.engine.options.Options`).
    """

    #: Stable kebab-case identifier of the event. Callers (UI mapper,
    #: file log, CLI, test assertions) key off this value; the engine
    #: never assembles a user-facing string.
    code: str
    #: Named values needed to render the event. Kept a ``Mapping`` so
    #: any read-only mapping is accepted; the frozen dataclass guarantees
    #: the reference itself is immutable.
    params: Mapping[str, object] = field(default_factory=dict)


#: English templates for every event the engine emits. Values use
#: ``str.format`` with named fields matching ``EngineEvent.params``.
#: Adding a code without an entry here is caught at runtime by the
#: fallback in :func:`render_en`.
_EN_TEMPLATES: dict[str, str] = {
    #: Free-form message forwarded from a source adapter (still French
    #: today). Rendered as-is so information is never lost, at the cost
    #: of not being English yet — migrating source strings is a future
    #: US, not this one.
    "source-message": "{text}",
    "manifest-unreadable": "Manifest unreadable, full rebuild.",
    "already-known": "{count} image(s) already known.",
    "cache-since-date": (
        "Cache: only asking the API for media newer than {date}."
    ),
    "discarded-below-min-width": (
        "{count} thumbnail(s)/logo(s) discarded (below {min_width} px)."
    ),
    "nothing-matches": "No image matches the criteria.",
    "known-and-todo": "{known} already up-to-date, {todo} to process.",
    "n-files-erased-locally": (
        "{count} image(s) erased from disk, will not be re-downloaded."
    ),
    "all-up-to-date": "Everything is already up to date.",
    "identifying-galleries": "Identifying galleries…",
    "file-not-found": "{filename}: not found",
    "file-failed": "{filename}: {error}",
    "n-new-images": "{count} new image(s), {size} downloaded.",
    "interrupted": "Interrupted — the resume will start here.",
    "runtime-error": "Error: {error}",
    "write-problem": "Write problem: {error}",
    "defer-with-time": (
        "Server unavailable or quota reached — resume after {until}."
    ),
    "defer-no-time": (
        "Server unavailable or quota reached — resume deferred."
    ),
}


def render_en(event: EngineEvent) -> str:
    """Return a stable English rendering of ``event``.

    Used by the CLI (``print``) and, eventually, by the file log. Not
    used by the Qt UI: the UI has its own French mapper under context
    ``UiJournal``.

    Args:
        event: The event to render.

    Returns:
        A single-line, non-empty English string. On an unknown code or a
        missing template placeholder, the fallback ``"<code> <params>"``
        is returned rather than raising, so the caller always has
        something to show.
    """
    template = _EN_TEMPLATES.get(event.code)
    if template is None:
        return f"{event.code} {dict(event.params)}"
    try:
        return template.format(**event.params)
    except KeyError:
        return f"{event.code} {dict(event.params)}"
