"""Persistent application configuration.

The file lives in ``%APPDATA%\\Glaneur\\config.json`` on Windows and in
``~/.config/glaneur/`` elsewhere. It is written atomically so that it
never gets truncated if the application is killed.
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

# intervals offered in the UI: label -> hours (0 = manual)
INTERVALLES: dict[str, int] = {
    "Manuel uniquement": 0,
    "Toutes les 6 heures": 6,
    "Toutes les 12 heures": 12,
    "Une fois par jour": 24,
    "Une fois par semaine": 168,
}

# sort modes offered in the UI: label -> stored value
CLASSEMENTS: dict[str, str] = {
    "Par galerie": "galerie",
    "Par date": "date",
    "Tout dans un dossier": "plat",
}

# supported site types: label -> key of the `sources.SOURCES` registry
TYPES_SOURCE: dict[str, str] = {
    "WordPress (API REST)": "wordpress",
    "Djangoplicity (ESO, ESA/Hubble…)": "djangoplicity",
}

# Djangoplicity image formats: label -> `ResourceType` from the d2d feed
FORMATS_DJANGOPLICITY: dict[str, str] = {
    "Grand JPEG": "Large",
    "Original (TIFF, très lourd)": "Original",
    "Écran (1280 px)": "Small",
}


def dossier_config() -> Path:
    """Return the folder where the config lives, per platform.

    - Windows: ``%APPDATA%\\Glaneur``.
    - macOS: ``~/Library/Application Support/Glaneur``.
    - Elsewhere: ``$XDG_CONFIG_HOME/glaneur`` (default: ``~/.config/glaneur``).

    Returns:
        The absolute folder path. The folder is not created.
    """
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return base / NOM_APP
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / NOM_APP
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "glaneur"


# Legacy names used before the WpImageDownloader → Glaneur rename.
# `migrer_depuis_ancien_nom()` copies the contents of the first of these
# directories that still exists to `dossier_config()` on first launch of Glaneur.
_ANCIENS_NOMS_APP: tuple[str, ...] = ("WpImageDownloader",)
_ANCIENS_NOMS_XDG: tuple[str, ...] = ("wp-image-downloader",)


def _anciens_dossiers_config() -> list[Path]:
    """Possible locations of the legacy-named config, most preferred first."""
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
    """Copy the config from a legacy name (``WpImageDownloader``) to Glaneur.

    Does nothing if a non-empty Glaneur folder already exists.
    Deliberately copied rather than moved: the old install may still be
    running in parallel during the transition, and we do not want to
    break its config.

    Args:
        cible: Destination folder. Uses :func:`dossier_config` when
            ``None``.

    Returns:
        The source path actually used, or ``None`` if there is nothing to
        migrate (target non-empty or no legacy folder found).
    """
    import logging
    import shutil
    cible = cible or dossier_config()
    if cible.exists() and any(cible.iterdir()):
        return None
    for source in _anciens_dossiers_config():
        if source.is_dir() and any(source.iterdir()):
            logger = logging.getLogger(__name__)
            logger.info("Config migration: %s -> %s", source, cible)
            cible.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, cible, dirs_exist_ok=True)
            return source
    return None


def dossier_images_defaut() -> Path:
    """Return the ``Glaneur`` sub-folder of one of the user's picture folders.

    Tries ``~/Pictures/Glaneur`` then ``~/Images/Glaneur`` (localised
    Windows/GNOME name), falling back to ``~/Glaneur``.

    Returns:
        The default path proposed to the user on first launch. The
        folder is not created.
    """
    for nom in ("Pictures", "Images"):
        candidat = Path.home() / nom
        if candidat.is_dir():
            return candidat / "Glaneur"
    return Path.home() / "Glaneur"


@dataclass
class Config:
    """Persistent configuration serialised as JSON.

    Fields documented inline with ``#:`` to avoid the index duplication
    between autodoc and Napoleon (same pattern as
    :class:`Glaneur.engine.options.Options`).
    """

    #: Source site origin, propagated to :attr:`Glaneur.engine.options.Options.site`.
    site: str = "https://example.com"
    #: Target sync directory; empty = value returned by
    #: :func:`dossier_images_defaut`.
    dossier: str = ""
    #: Interval between two automatic runs, in hours. Must belong to
    #: the values of ``INTERVALLES`` (``0`` = manual only).
    intervalle_heures: int = 24
    #: Skips images narrower than this (in pixels).
    largeur_min: int = 800
    #: ``galerie``, ``date`` or ``plat``.
    classement: str = "galerie"
    #: Key of the ``Glaneur.sources.SOURCES`` registry.
    type_source: str = "wordpress"
    #: Used by Djangoplicity; values in ``FORMATS_DJANGOPLICITY``.
    format_image: str = "Large"
    #: ETag/Last-Modified revalidation of files already present.
    verifier_integrite: bool = False
    #: Sets the directory as the Windows desktop wallpaper slideshow.
    diaporama_dossier: bool = False
    #: Floor of the pause between two requests, in seconds.
    delai_requetes: float = 0.5
    #: ISO 8601 date of the last run, fed by the scheduler.
    derniere_execution: str = ""
    #: ISO 8601 date (naive local) of the next run deferred by a network
    #: circuit-breaker — see
    #: :meth:`Glaneur.scheduler.Planificateur.differer`.
    #: Empty = no defer in progress.
    retenter_apres: str = ""
    #: Exponential-backoff level — 0 -> 1 h, 1 -> 2 h, 2 -> 4 h.
    #: Reset to 0 by
    #: :meth:`Glaneur.scheduler.Planificateur.marquer_execution`.
    backoff_niveau: int = 0
    #: Adds the application to the user session's startup items.
    lancer_au_demarrage: bool = False
    #: The close button minimizes to the notification area instead of exiting.
    fermer_dans_barre: bool = True
    #: System notification bubble after an automatic update.
    notifications: bool = True
    #: Queries GitHub Releases at launch to offer an update.
    verifier_maj_demarrage: bool = True
    #: Language code (``fr``, ``en``, ...). Empty = system locale.
    langue: str = ""

    _chemin: Path | None = field(default=None, repr=False, compare=False)

    # -- load / save ------------------------------------------------------- #

    @classmethod
    def charger(cls, chemin: Path | None = None) -> "Config":
        """Load the config from ``chemin`` or fall back to default values.

        Missing or unknown keys are ignored, and an unreadable file
        (invalid JSON, OS error) is treated as an absent config: we
        start over from default values rather than crashing.
        :meth:`valider` is always called before returning the object.

        Args:
            chemin: Path of the ``config.json`` file. Uses
                :func:`dossier_config` when ``None``.

        Returns:
            A :class:`Config` ready to use, with its path stored for
            :meth:`sauver`.
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
                pass  # unreadable config: fall back to default values
        if not cfg.dossier:
            cfg.dossier = str(dossier_images_defaut())
        cfg.valider()
        return cfg

    def sauver(self) -> None:
        """Write the config to disk atomically.

        Uses the path stored by :meth:`charger` if any, otherwise
        ``<dossier_config()>/config.json``. Private fields (prefixed
        with ``_``) are not serialised.
        """
        chemin = self._chemin or (dossier_config() / "config.json")
        chemin.parent.mkdir(parents=True, exist_ok=True)
        donnees = {k: v for k, v in asdict(self).items() if not k.startswith("_")}
        tmp = chemin.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(donnees, f, ensure_ascii=False, indent=2)
        tmp.replace(chemin)
        self._chemin = chemin

    # -- guardrails --------------------------------------------------------- #

    def valider(self) -> None:
        """Coerce out-of-range values back into reasonable bounds.

        Forces a known interval, clamps the minimum width between 0 and
        10 000 px, falls back to the default values when the sort mode,
        the source type or the image format is unknown, and makes sure
        the sort mode is supported by the source type (deferred import
        to avoid the ``config → sources → engine → config`` cycle). The
        request delay is clamped between 0.2 and 10 seconds.
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
        # The sort mode must be supported by the source. Deferred import to
        # avoid the `config → sources → engine → config` cycle.
        from .sources import classements_pour
        classements_ok = classements_pour(self.type_source)
        if classements_ok and self.classement not in classements_ok:
            self.classement = "date"
        # too short a delay would hammer the club's server
        self.delai_requetes = max(0.2, min(float(self.delai_requetes), 10.0))
        # The exponential defer backoff only knows three tiers.
        try:
            niveau = int(self.backoff_niveau)
        except (TypeError, ValueError):
            niveau = 0
        self.backoff_niveau = max(0, min(niveau, 2))

    @property
    def libelle_intervalle(self) -> str:
        """UI label of :attr:`intervalle_heures` (key of ``INTERVALLES``).

        Returns:
            The label associated with the numeric value, or the default
            label ``"Une fois par jour"`` when the value is not listed.
        """
        for libelle, heures in INTERVALLES.items():
            if heures == self.intervalle_heures:
                return libelle
        return "Une fois par jour"

    @property
    def libelle_classement(self) -> str:
        """UI label of :attr:`classement` (key of ``CLASSEMENTS``).

        Returns:
            The label associated with the stored value, or
            ``"Par galerie"`` by default.
        """
        for libelle, valeur in CLASSEMENTS.items():
            if valeur == self.classement:
                return libelle
        return "Par galerie"
