"""Engine-shared locks.

Serialize every read-modify-write on the manifest: UI-side delete_image /
restore must not race with the engine's periodic and final saves during a
run. UI and engine live in the same process, so a ``threading.Lock`` suffices.
"""

from __future__ import annotations

import threading

_MANIFEST_LOCK = threading.Lock()
