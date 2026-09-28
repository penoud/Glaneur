"""Cross-platform per-folder OS lock.

Guards a target directory against concurrent Glaneur runs — application
UI plus scheduled task, or a legacy install still running alongside the
new one. The lock is an OS-level advisory lock: `fcntl.flock` on POSIX,
`msvcrt.locking` on Windows. The OS releases it automatically when the
holding process dies, so there is no stale-lock file to detect and no
PID heuristic to trust.

The lock file (``.glaneur.lock`` in the target directory) also carries a
small JSON diagnostic (PID, host, UTC time). That content is data, never
consulted for the lock decision — deleting the file by hand between two
runs does not break the next acquisition, it just recreates it.

Not tested on SMB shares: the roadmap does not require that case.
"""

from __future__ import annotations

import json
import os
import socket
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import IO

#: Name of the lock file placed in the target directory. Underscore-free
#: on purpose: hidden by dot prefix, easy to grep for support.
LOCK_NAME: str = ".glaneur.lock"


class FolderBusy(Exception):
    """Raised when another process already holds the folder lock.

    The engine converts this into ``RunResult(busy=True)`` in
    :meth:`Glaneur.engine.core.Engine.run`; the CLI translates it into
    exit code 3 (see :func:`cli.main`).
    """


def _diagnostic_payload() -> bytes:
    """Return a small JSON blob describing the current holder."""
    payload = {
        "pid": os.getpid(),
        "host": socket.gethostname(),
        "utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    return json.dumps(payload, ensure_ascii=False).encode("utf-8") + b"\n"


if sys.platform == "win32":  # pragma: no cover - platform-specific
    import msvcrt

    def _acquire(fh: IO[bytes]) -> None:
        """Take an exclusive, non-blocking lock on byte 0 of ``fh``."""
        try:
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)  # type: ignore[attr-defined]
        except OSError as exc:
            raise FolderBusy(str(exc)) from exc

    def _release(fh: IO[bytes]) -> None:
        """Release the byte-0 lock; ignore errors on best-effort cleanup."""
        try:
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)  # type: ignore[attr-defined]
        except OSError:
            pass

else:
    import fcntl

    def _acquire(fh: IO[bytes]) -> None:
        """Take an exclusive, non-blocking flock on ``fh``."""
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, OSError) as exc:
            raise FolderBusy(str(exc)) from exc

    def _release(fh: IO[bytes]) -> None:
        """Release the flock; ignore errors on best-effort cleanup."""
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        except OSError:  # pragma: no cover - defensive cleanup
            pass


@contextmanager
def folder_lock(target_dir: Path) -> Iterator[None]:
    """Hold an exclusive OS lock on ``target_dir / .glaneur.lock``.

    The context manager acquires on entry and releases on exit, even if
    the guarded block raises. The lock file is created if missing and
    then rewritten with the current diagnostic payload. The payload is
    informational only — deleting the file by hand between runs is safe.

    Args:
        target_dir: Directory to protect. Created by the engine before
            this call, so it must exist.

    Yields:
        Control to the guarded block. The lock is held for the whole
        block and released on exit.

    Raises:
        FolderBusy: If another process already holds the lock.
    """
    lock_path = target_dir / LOCK_NAME
    # ``a+b`` creates on demand without truncating; we then re-position
    # to 0 so the Windows byte-range lock consistently targets byte 0.
    with open(lock_path, "a+b") as fh:
        _acquire(fh)
        try:
            fh.seek(0)
            fh.truncate()
            fh.write(_diagnostic_payload())
            fh.flush()
            yield
        finally:
            _release(fh)
