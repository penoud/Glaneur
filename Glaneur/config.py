"""Configuration persistante de l'application.

Le fichier vit dans %APPDATA%\\Glaneur\\config.json sous Windows,
dans ~/.config/glaneur/ ailleurs. Il est écrit de façon atomique
pour ne jamais se retrouver tronqué si l'application est tuée.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

NOM_APP = "Glaneur"
GITHUB_OWNER = "penoud"
GITHUB_REPOSITORY = "Glaneur"

# intervalles proposés dans l'interface : libellé -> heures (0 = manuel)
INTERVALLES: dict[str, int] = {
    "Manuel uniquement": 0,
    "Toutes les 6 heures": 6,
    "Toutes les 12 heures": 12,
    "Une fois par jour": 24,
    "Une fois par semaine": 168,
}

# classements proposés dans l'interface : libellé -> valeur stockée
CLASSEMENTS: dict[str, str] = {
    "Par galerie": "galerie",
    "Par date": "date",
    "Tout dans un dossier": "plat",
}

# types de sites supportés : libellé -> clé du registre `sources.SOURCES`
TYPES_SOURCE: dict[str, str] = {
    "WordPress (API REST)": "wordpress",
    "Djangoplicity (ESO, ESA/Hubble…)": "djangoplicity",
}

# formats d'image Djangoplicity : libellé -> `ResourceType` du flux d2d
FORMATS_DJANGOPLICITY: dict[str, str] = {
    "Grand JPEG": "Large",
    "Original (TIFF, très lourd)": "Original",
    "Écran (1280 px)": "Small",
}


def dossier_config() -> Path:
    """Renvoie le dossier où vit la config, selon la plateforme.

    - Windows : ``%APPDATA%\\Glaneur``.
    - macOS : ``~/Library/Application Support/Glaneur``.
    - Ailleurs : ``$XDG_CONFIG_HOME/glaneur`` (défaut : ``~/.config/glaneur``).

    Returns:
        Le chemin absolu du dossier. Le dossier n'est pas créé.
    """
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return base / NOM_APP
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / NOM_APP
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "glaneur"


# Anciens noms utilisés avant le rename WpImageDownloader → Glaneur.
# `migrer_depuis_ancien_nom()` copie le contenu du premier de ces dossiers
# qui existe encore vers `dossier_config()` au premier lancement de Glaneur.
_ANCIENS_NOMS_APP: tuple[str, ...] = ("WpImageDownloader",)
_ANCIENS_NOMS_XDG: tuple[str, ...] = ("wp-image-downloader",)


def _anciens_dossiers_config() -> list[Path]:
    """Emplacements possibles de la config héritée de l'ancien nom, dans
    l'ordre de préférence (le plus récent d'abord)."""
    dossiers: list[Path] = []
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        dossiers += [base / nom for nom in _ANCIENS_NOMS_APP]
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
        dossiers += [base / nom for nom in _ANCIENS_NOMS_APP]
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        dossiers += [base / nom for nom in _ANCIENS_NOMS_XDG]
    return dossiers


def migrer_depuis_ancien_nom(cible: Path | None = None) -> Path | None:
    """Copie la config d'un ancien nom (``WpImageDownloader``) vers Glaneur.

    Ne fait rien si un dossier Glaneur non vide existe déjà. Volontairement
    copié plutôt que déplacé : l'ancien install peut encore tourner en
    parallèle pendant la transition, on ne casse pas sa config.

    Args:
        cible: Dossier de destination. Utilise :func:`dossier_config` si
            ``None``.

    Returns:
        Le chemin source effectivement utilisé, ou ``None`` si rien à
        migrer (cible non vide ou aucun dossier legacy trouvé).
    """
    import logging
    import shutil
    cible = cible or dossier_config()
    if cible.exists() and any(cible.iterdir()):
        return None
    for source in _anciens_dossiers_config():
        if source.is_dir() and any(source.iterdir()):
            logger = logging.getLogger(__name__)
            logger.info("Migration config : %s -> %s", source, cible)
            cible.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, cible, dirs_exist_ok=True)
            return source
    return None


def dossier_images_defaut() -> Path:
    """Sous-dossier ``Glaneur`` d'un répertoire d'images de l'utilisateur.

    Tente ``~/Pictures/Glaneur`` puis ``~/Images/Glaneur`` (nom localisé
    Windows/GNOME), sinon ``~/Glaneur``.

    Returns:
        Le chemin proposé par défaut à l'utilisateur au premier lancement.
        Le dossier n'est pas créé.
    """
    for nom in ("Pictures", "Images"):
        candidat = Path.home() / nom
        if candidat.is_dir():
            return candidat / "Glaneur"
    return Path.home() / "Glaneur"


@dataclass
class Config:
    """Configuration persistante sérialisée en JSON.

    Champs documentés inline par ``#:`` pour éviter le doublon d'index
    entre autodoc et Napoleon (même motif que
    :class:`Glaneur.engine.Options`).
    """

    #: Origine du site source, propagée à :attr:`Glaneur.engine.Options.site`.
    site: str = "https://example.com"
    #: Dossier cible de synchronisation ; vide = valeur de
    #: :func:`dossier_images_defaut`.
    dossier: str = ""
    #: Intervalle entre deux runs automatiques, en heures. Doit appartenir
    #: aux valeurs de ``INTERVALLES`` (``0`` = manuel uniquement).
    intervalle_heures: int = 24
    #: Écarte les images plus étroites (en pixels).
    largeur_min: int = 800
    #: ``galerie``, ``date`` ou ``plat``.
    classement: str = "galerie"
    #: Clé du registre ``Glaneur.sources.SOURCES``.
    type_source: str = "wordpress"
    #: Utilisé par Djangoplicity ; valeurs dans ``FORMATS_DJANGOPLICITY``.
    format_image: str = "Large"
    #: Revalidation ETag/Last-Modified des fichiers déjà présents.
    verifier_integrite: bool = False
    #: Configure le dossier comme diaporama de fond d'écran Windows.
    diaporama_dossier: bool = False
    #: Plancher de pause entre deux requêtes, en secondes.
    delai_requetes: float = 0.5
    #: Date ISO 8601 du dernier run, alimentée par le planificateur.
    derniere_execution: str = ""
    #: Ajoute l'application au démarrage de la session utilisateur.
    lancer_au_demarrage: bool = False
    #: La croix réduit dans la zone de notification au lieu de fermer.
    fermer_dans_barre: bool = True
    #: Bulle système après une mise à jour automatique.
    notifications: bool = True
    #: Interroge GitHub Releases au lancement pour proposer une mise à jour.
    verifier_maj_demarrage: bool = True
    #: Code de langue (``fr``, ``en``…). Vide = locale système.
    langue: str = ""

    _chemin: Path | None = field(default=None, repr=False, compare=False)

    # -- chargement / sauvegarde ------------------------------------------- #

    @classmethod
    def charger(cls, chemin: Path | None = None) -> "Config":
        """Charge la config depuis ``chemin`` ou la retombe sur les valeurs par défaut.

        Les clés absentes ou inconnues sont ignorées, et un fichier illisible
        (JSON invalide, erreur OS) est traité comme une config absente : on
        repart des valeurs par défaut plutôt que de planter.
        :meth:`valider` est toujours appelée avant de rendre l'objet.

        Args:
            chemin: Chemin du fichier ``config.json``. Utilise
                :func:`dossier_config` si ``None``.

        Returns:
            Une :class:`Config` prête à l'emploi, avec son chemin
            mémorisé pour :meth:`sauver`.
        """
        chemin = chemin or (dossier_config() / "config.json")
        cfg = cls()
        cfg._chemin = chemin
        if chemin.exists():
            try:
                with open(chemin, encoding="utf-8") as f:
                    brut = json.load(f)
                connus = {f.name for f in fields(cls) if not f.name.startswith("_")}
                for cle, valeur in brut.items():
                    if cle in connus:
                        setattr(cfg, cle, valeur)
            except (json.JSONDecodeError, OSError, TypeError):
                pass  # config illisible : on repart sur les valeurs par défaut
        if not cfg.dossier:
            cfg.dossier = str(dossier_images_defaut())
        cfg.valider()
        return cfg

    def sauver(self) -> None:
        """Écrit la config sur disque de façon atomique.

        Utilise le chemin mémorisé par :meth:`charger` s'il existe,
        sinon ``<dossier_config()>/config.json``. Les champs privés
        (préfixés ``_``) ne sont pas sérialisés.
        """
        chemin = self._chemin or (dossier_config() / "config.json")
        chemin.parent.mkdir(parents=True, exist_ok=True)
        donnees = {k: v for k, v in asdict(self).items() if not k.startswith("_")}
        tmp = chemin.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(donnees, f, ensure_ascii=False, indent=2)
        tmp.replace(chemin)
        self._chemin = chemin

    # -- garde-fous --------------------------------------------------------- #

    def valider(self) -> None:
        """Ramène les valeurs aberrantes dans des bornes raisonnables.

        Force un intervalle connu, borne la largeur minimale entre 0 et
        10 000 px, retombe sur les valeurs par défaut si le classement,
        le type de source ou le format d'image sont inconnus, et
        s'assure que le classement est supporté par le type de source
        (import différé pour éviter le cycle
        ``config → sources → engine → config``). Le délai est borné
        entre 0.2 et 10 secondes.
        """
        if self.intervalle_heures not in INTERVALLES.values():
            self.intervalle_heures = 24
        self.largeur_min = max(0, min(int(self.largeur_min), 10000))
        if self.classement not in CLASSEMENTS.values():
            self.classement = "galerie"
        if self.type_source not in TYPES_SOURCE.values():
            self.type_source = "wordpress"
        if self.format_image not in FORMATS_DJANGOPLICITY.values():
            self.format_image = "Large"
        # Le classement doit être supporté par la source. Import différé pour
        # éviter le cycle `config → sources → engine → config`.
        from .sources import classements_pour
        classements_ok = classements_pour(self.type_source)
        if classements_ok and self.classement not in classements_ok:
            self.classement = "date"
        # un délai trop court martèlerait le serveur du club
        self.delai_requetes = max(0.2, min(float(self.delai_requetes), 10.0))

    @property
    def libelle_intervalle(self) -> str:
        """Libellé UI de :attr:`intervalle_heures` (clé de ``INTERVALLES``).

        Returns:
            Le libellé associé à la valeur numérique, ou le libellé par
            défaut ``"Une fois par jour"`` si la valeur n'est pas listée.
        """
        for libelle, heures in INTERVALLES.items():
            if heures == self.intervalle_heures:
                return libelle
        return "Une fois par jour"

    @property
    def libelle_classement(self) -> str:
        """Libellé UI de :attr:`classement` (clé de ``CLASSEMENTS``).

        Returns:
            Le libellé associé à la valeur stockée, ou ``"Par galerie"``
            par défaut.
        """
        for libelle, valeur in CLASSEMENTS.items():
            if valeur == self.classement:
                return libelle
        return "Par galerie"
