"""Generic download engine.

This package knows nothing about the user interface: it communicates through
callbacks (``journal``, ``progression``) and interrupts cleanly via a
``threading.Event``. It can therefore drive the PySide6 UI as well as a
command-line script.

It also knows nothing about WordPress or Djangoplicity. It consumes
``Element`` values produced by an adapter from :mod:`Glaneur.sources`.

The only Qt dependency is ``QCoreApplication.translate`` used to localise
messages routed to the journal and to ``res.message`` — confined to
:mod:`Glaneur.engine.moteur`, with no widget and no thread introduced;
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

from ._constantes import SIZE_SUFFIX, UA
from .chemin_cache import chemin_cache
from .chemin_manifeste import chemin_manifeste
from .ecrire_cache import ecrire_cache
from .ecrire_manifeste import ecrire_manifeste
from .format_octets import format_octets
from .lire_cache import lire_cache
from .lire_manifeste import lire_manifeste
from .lister_supprimees import lister_supprimees
from .moteur import Moteur
from .nettoyer import nettoyer
from .options import Options
from .restaurer import restaurer
from .resultat import Resultat
from .supprimer_image import supprimer_image

__all__ = [
    "Interrompu",
    "Moteur",
    "Options",
    "Resultat",
    "SIZE_SUFFIX",
    "UA",
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
