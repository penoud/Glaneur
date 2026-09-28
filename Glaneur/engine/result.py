"""Dataclass :class:`RunResult` — counters and message of a run."""

from __future__ import annotations

from dataclasses import dataclass, field

from .events import EngineEvent


@dataclass
class RunResult:
    """Counters and message returned by an engine run."""

    #: New files actually downloaded.
    downloaded: int = 0
    #: Files resumed from a partial ``.part``.
    resumed: int = 0
    #: 304 responses (ETag/Last-Modified unchanged).
    unchanged: int = 0
    #: Files already up to date in the manifest and on disk.
    already_present: int = 0
    #: Files missing from disk on this pass — marked as
    #: deleted in the manifest.
    deleted: int = 0
    #: Files known as deleted or without a usable URL, not
    #: re-downloaded.
    skipped: int = 0
    #: Files whose download failed.
    failures: int = 0
    #: Total volume downloaded, in bytes.
    bytes: int = 0
    #: True if the user requested a stop mid-run.
    interrupted: bool = False
    #: True if the run bailed out because the server cut us off
    #: (rate limit, DNS blackhole, 429/503...). The scheduler uses this
    #: to defer the next automatic run — see ``Glaneur.scheduler`` at
    #: lot 3.
    deferred: bool = False
    #: ISO 8601 hint of the earliest resume time, populated from a
    #: ``Retry-After`` header when the server provides one. Empty
    #: means "no hint": the scheduler falls back on its own backoff.
    retry_after: str = ""
    #: True when the run bailed out because another process already
    #: holds the per-folder OS lock — see
    #: :func:`Glaneur.engine._folder_lock.folder_lock`. The engine
    #: writes nothing to disk in that case; the CLI translates it into
    #: exit code 3.
    busy: bool = False
    #: Summary ready to display to the user, rendered in English by the
    #: engine. Kept for the CLI and for tests that predate structured
    #: events; the UI uses :attr:`message_event` and translates it.
    message: str = ""
    #: Structured version of :attr:`message`, populated at every place
    #: where the engine used to build a translated summary. ``None`` on
    #: run paths that do not produce a summary (``busy`` short-circuit).
    message_event: EngineEvent | None = None
    #: Free-form bag for extra information.
    details: dict = field(default_factory=dict)
