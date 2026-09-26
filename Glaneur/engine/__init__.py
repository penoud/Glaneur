"""Moteur de téléchargement générique.

Ce paquet ne connaît rien de l'interface : il communique par callbacks
(`journal`, `progression`) et s'interrompt proprement via un threading.Event.
Il peut donc servir aussi bien à l'UI PySide6 qu'à un script en ligne de commande.

Il ne connaît pas non plus WordPress ni Djangoplicity. Il consomme des
`Element` produits par un adaptateur de `Glaneur.sources`.

Seule dépendance Qt : `QCoreApplication.translate` pour localiser les
messages remontés au journal et à `res.message` — cantonnée à
:mod:`Glaneur.engine.moteur`, pas de widget, pas de thread introduit,
et `.translate()` retombe sur la source FR quand aucune QCoreApplication
n'existe (cas de la CLI et des tests unitaires).

Le paquet est le successeur direct du module ``Glaneur/engine.py`` : chaque
fonction et dataclass publique a été extraite dans son propre fichier pour
simplifier la maintenance. La surface publique est ré-exportée ici : tout
ce que l'ancien module rendait accessible via ``from Glaneur.engine import
…`` reste importable au même chemin.
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
