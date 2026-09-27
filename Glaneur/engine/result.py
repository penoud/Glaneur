"""Dataclass :class:`RunResult` — counters and message of a run."""

from __future__ import annotations

from dataclasses import dataclass, field


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
    #: Summary ready to display to the user (localized).
    message: str = ""
    #: Free-form bag for extra information.
    details: dict = field(default_factory=dict)
