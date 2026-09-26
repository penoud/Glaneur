"""Engine-shared locks.

Serialize every read-modify-write on the manifest: UI-side supprimer_image /
restaurer must not race with the engine's periodic and final saves during a
run. UI and engine live in the same process, so a ``threading.Lock`` suffices.
"""

from __future__ import annotations

import threading

_MANIFESTE_LOCK = threading.Lock()
