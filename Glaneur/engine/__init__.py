"""Generic download engine.

This package knows nothing about the user interface: it communicates through
callbacks (``journal``, ``progression``) and interrupts cleanly via a
``threading.Event``. It can therefore drive the PySide6 UI as well as a
command-line script.

It also knows nothing about WordPress or Djangoplicity. It consumes
``Element`` values produced by an adapter from :mod:`Glaneur.sources`.

The only Qt dependency is ``QCoreApplication.translate`` used to localise
messages routed to the journal and to ``res.message`` — confined to
:mod:`Glaneur.engine.core`, with no widget and no thread introduced;
``.translate()`` falls back to the French source string when no
``QCoreApplication`` exists (the CLI and unit-test case).

This package is the direct successor of the former ``Glaneur/engine.py``
module: every public function and dataclass has been extracted into its
own file to simplify maintenance. The public surface is re-exported here:
anything that used to be importable via ``from Glaneur.engine import ...``
remains importable at the same path.
"""

from __future__ import annotations

from ..sources import Interrupted
from ._constants import SIZE_SUFFIX, UA
from .cache_path import cache_path
from .core import Engine
from .delete_image import delete_image
from .format_bytes import format_bytes
from .list_deleted import list_deleted
from .manifest_path import manifest_path
from .options import Options
from .read_cache import read_cache
from .read_manifest import read_manifest
from .restore import restore
from .result import RunResult
from .sanitize import clean
from .write_cache import write_cache
from .write_manifest import write_manifest

__all__ = [
    "SIZE_SUFFIX",
    "UA",
    "Engine",
    "Interrupted",
    "Options",
    "RunResult",
    "cache_path",
    "clean",
    "delete_image",
    "format_bytes",
    "list_deleted",
    "manifest_path",
    "read_cache",
    "read_manifest",
    "restore",
    "write_cache",
    "write_manifest",
]
