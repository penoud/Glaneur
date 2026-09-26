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

from ..sources import Interrompu
from ._constants import SIZE_SUFFIX, UA
from .cache_path import chemin_cache
from .core import Moteur
from .delete_image import supprimer_image
from .format_bytes import format_octets
from .list_deleted import lister_supprimees
from .manifest_path import chemin_manifeste
from .options import Options
from .read_cache import lire_cache
from .read_manifest import lire_manifeste
from .restore import restaurer
from .result import Resultat
from .sanitize import nettoyer
from .write_cache import ecrire_cache
from .write_manifest import ecrire_manifeste

__all__ = [
    "SIZE_SUFFIX",
    "UA",
    "Interrompu",
    "Moteur",
    "Options",
    "Resultat",
    "chemin_cache",
    "chemin_manifeste",
    "ecrire_cache",
    "ecrire_manifeste",
    "format_octets",
    "lire_cache",
    "lire_manifeste",
    "lister_supprimees",
    "nettoyer",
    "restaurer",
    "supprimer_image",
]
