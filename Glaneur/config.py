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

APP_NAME = "Glaneur"
GITHUB_OWNER = "penoud"
GITHUB_REPOSITORY = "Glaneur"

# intervals offered in the UI: label -> hours (0 = manual)
INTERVALS: dict[str, int] = {
    "Manuel uniquement": 0,
    "Toutes les 6 heures": 6,
    "Toutes les 12 heures": 12,
    "Une fois par jour": 24,
    "Une fois par semaine": 168,
}

# sort modes offered in the UI: label -> stored value
SORT_MODES: dict[str, str] = {
    "Par galerie": "gallery",
    "Par date": "date",
    "Tout dans un dossier": "flat",
}

# supported site types: label -> key of the `sources.SOURCES` registry
SOURCE_TYPES: dict[str, str] = {
    "WordPress (API REST)": "wordpress",
    "Djangoplicity (ESO, ESA/Hubble…)": "djangoplicity",
}

# Djangoplicity image formats: label -> `ResourceType` from the d2d feed
DJANGOPLICITY_FORMATS: dict[str, str] = {
    "Grand JPEG": "Large",
    "Original (TIFF, très lourd)": "Original",
    "Écran (1280 px)": "Small",
}


def config_dir() -> Path:
    """Return the folder where the config lives, per platform.

    - Windows: ``%APPDATA%\\Glaneur``.
    - macOS: ``~/Library/Application Support/Glaneur``.
    - Elsewhere: ``$XDG_CONFIG_HOME/glaneur`` (default: ``~/.config/glaneur``).

    Returns:
        The absolute folder path. The folder is not created.
    """
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return base / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "glaneur"


# Legacy names used before the WpImageDownloader → Glaneur rename.
# `migrate_from_legacy_name()` copies the contents of the first of these
# directories that still exists to `config_dir()` on first launch of Glaneur.
_LEGACY_APP_NAMES: tuple[str, ...] = ("WpImageDownloader",)
_LEGACY_XDG_NAMES: tuple[str, ...] = ("wp-image-downloader",)


def _legacy_config_dirs() -> list[Path]:
    """Possible locations of the legacy-named config, most preferred first."""
    dossiers: list[Path] = []
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        dossiers += [base / nom for nom in _LEGACY_APP_NAMES]
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
        dossiers += [base / nom for nom in _LEGACY_APP_NAMES]
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        dossiers += [base / nom for nom in _LEGACY_XDG_NAMES]
    return dossiers


def migrate_from_legacy_name(cible: Path | None = None) -> Path | None:
    """Copy the config from a legacy name (``WpImageDownloader``) to Glaneur.

    Does nothing if a non-empty Glaneur folder already exists.
    Deliberately copied rather than moved: the old install may still be
    running in parallel during the transition, and we do not want to
    break its config.

    Args:
        cible: Destination folder. Uses :func:`config_dir` when
            ``None``.

    Returns:
        The source path actually used, or ``None`` if there is nothing to
        migrate (target non-empty or no legacy folder found).
    """
    import logging
    import shutil
    cible = cible or config_dir()
    if cible.exists() and any(cible.iterdir()):
        return None
    for source in _legacy_config_dirs():
        if source.is_dir() and any(source.iterdir()):
            logger = logging.getLogger(__name__)
            logger.info("Config migration: %s -> %s", source, cible)
            cible.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, cible, dirs_exist_ok=True)
            return source
    return None


def default_images_dir() -> Path:
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


# Legacy JSON keys → new EN field names. A ``config.json`` written by
# a pre-4b version is loaded through this table so no user loses their
# settings; the next ``Config.save`` rewrites the file with EN keys.
_LEGACY_FIELD_ALIASES: dict[str, str] = {
    "dossier": "target_dir",
    "intervalle_heures": "interval_hours",
    "largeur_min": "min_width",
    "classement": "sort_mode",
    "type_source": "source_type",
    "format_image": "image_format",
    "verifier_integrite": "verify_integrity",
    "diaporama_dossier": "slideshow_dir",
    "delai_requetes": "request_delay",
    "derniere_execution": "last_run",
    "retenter_apres": "retry_after",
    "backoff_niveau": "backoff_level",
    "lancer_au_demarrage": "run_at_startup",
    "fermer_dans_barre": "close_to_tray",
    "verifier_maj_demarrage": "check_updates_on_start",
    "langue": "language",
}

# Legacy sort_mode value aliases: a config.json written before US-EN-04
# stored "galerie"/"plat" as the sort_mode value. Translate on load so
# users do not lose their chosen sort mode; the next Config.save
# rewrites the file with the English value.
_LEGACY_SORT_MODE_ALIASES: dict[str, str] = {
    "galerie": "gallery",
    "plat": "flat",
}


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
    #: :func:`default_images_dir`.
    target_dir: str = ""
    #: Interval between two automatic runs, in hours. Must belong to
    #: the values of ``INTERVALS`` (``0`` = manual only).
    interval_hours: int = 24
    #: Skips images narrower than this (in pixels).
    min_width: int = 800
    #: ``gallery``, ``date`` or ``flat``.
    sort_mode: str = "gallery"
    #: Key of the ``Glaneur.sources.SOURCES`` registry.
    source_type: str = "wordpress"
    #: Used by Djangoplicity; values in ``DJANGOPLICITY_FORMATS``.
    image_format: str = "Large"
    #: ETag/Last-Modified revalidation of files already present.
    verify_integrity: bool = False
    #: Sets the directory as the Windows desktop wallpaper slideshow.
    slideshow_dir: bool = False
    #: Floor of the pause between two requests, in seconds.
    request_delay: float = 0.5
    #: ISO 8601 date of the last run, fed by the scheduler.
    last_run: str = ""
    #: ISO 8601 date (naive local) of the next run deferred by a network
    #: circuit-breaker — see
    #: :meth:`Glaneur.scheduler.Scheduler.defer`.
    #: Empty = no defer in progress.
    retry_after: str = ""
    #: Exponential-backoff level — 0 -> 1 h, 1 -> 2 h, 2 -> 4 h.
    #: Reset to 0 by
    #: :meth:`Glaneur.scheduler.Scheduler.mark_run`.
    backoff_level: int = 0
    #: Adds the application to the user session's startup items.
    run_at_startup: bool = False
    #: The close button minimizes to the notification area instead of exiting.
    close_to_tray: bool = True
    #: System notification bubble after an automatic update.
    notifications: bool = True
    #: Queries GitHub Releases at launch to offer an update.
    check_updates_on_start: bool = True
    #: Language code (``fr``, ``en``, ...). Empty = system locale.
    language: str = ""

    _path: Path | None = field(default=None, repr=False, compare=False)

    # -- load / save ------------------------------------------------------- #

    @classmethod
    def load(cls, chemin: Path | None = None) -> Config:
        """Load the config from ``chemin`` or fall back to default values.

        Missing or unknown keys are ignored, and an unreadable file
        (invalid JSON, OS error) is treated as an absent config: we
        start over from default values rather than crashing.
        :meth:`validate` is always called before returning the object.

        Args:
            chemin: Path of the ``config.json`` file. Uses
                :func:`config_dir` when ``None``.

        Returns:
            A :class:`Config` ready to use, with its path stored for
            :meth:`save`.
        """
        chemin = chemin or (config_dir() / "config.json")
        cfg = cls()
        cfg._path = chemin
        if chemin.exists():
            try:
                with open(chemin, encoding="utf-8") as f:
                    brut = json.load(f)
                connus = {f.name for f in fields(cls) if not f.name.startswith("_")}
                for cle, valeur in brut.items():
                    # Translate legacy FR keys to their EN name so a
                    # config.json written before batch 4b keeps loading.
                    cle = _LEGACY_FIELD_ALIASES.get(cle, cle)
                    if cle in connus:
                        setattr(cfg, cle, valeur)
                # Translate legacy sort_mode values ("galerie"/"plat")
                # so US-EN-04 does not silently reset the user's choice.
                if cfg.sort_mode in _LEGACY_SORT_MODE_ALIASES:
                    cfg.sort_mode = _LEGACY_SORT_MODE_ALIASES[cfg.sort_mode]
            except (json.JSONDecodeError, OSError, TypeError):
                pass  # unreadable config: fall back to default values
        if not cfg.target_dir:
            cfg.target_dir = str(default_images_dir())
        cfg.validate()
        return cfg

    def save(self) -> None:
        """Write the config to disk atomically.

        Uses the path stored by :meth:`load` if any, otherwise
        ``<config_dir()>/config.json``. Private fields (prefixed
        with ``_``) are not serialised.
        """
        chemin = self._path or (config_dir() / "config.json")
        chemin.parent.mkdir(parents=True, exist_ok=True)
        donnees = {k: v for k, v in asdict(self).items() if not k.startswith("_")}
        tmp = chemin.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(donnees, f, ensure_ascii=False, indent=2)
        tmp.replace(chemin)
        self._path = chemin

    # -- guardrails --------------------------------------------------------- #

    def validate(self) -> None:
        """Coerce out-of-range values back into reasonable bounds.

        Forces a known interval, clamps the minimum width between 0 and
        10 000 px, falls back to the default values when the sort mode,
        the source type or the image format is unknown, and makes sure
        the sort mode is supported by the source type (deferred import
        to avoid the ``config → sources → engine → config`` cycle). The
        request delay is clamped between 0.2 and 10 seconds.
        """
        if self.interval_hours not in INTERVALS.values():
            self.interval_hours = 24
        self.min_width = max(0, min(int(self.min_width), 10000))
        if self.sort_mode not in SORT_MODES.values():
            self.sort_mode = "gallery"
        if self.source_type not in SOURCE_TYPES.values():
            self.source_type = "wordpress"
        if self.image_format not in DJANGOPLICITY_FORMATS.values():
            self.image_format = "Large"
        # The sort mode must be supported by the source. Deferred import to
        # avoid the `config → sources → engine → config` cycle.
        from .sources import sort_modes_for
        classements_ok = sort_modes_for(self.source_type)
        if classements_ok and self.sort_mode not in classements_ok:
            self.sort_mode = "date"
        # too short a delay would hammer the club's server
        self.request_delay = max(0.2, min(float(self.request_delay), 10.0))
        # The exponential defer backoff only knows three tiers.
        try:
            niveau = int(self.backoff_level)
        except (TypeError, ValueError):
            niveau = 0
        self.backoff_level = max(0, min(niveau, 2))

    @property
    def interval_label(self) -> str:
        """UI label of :attr:`interval_hours` (key of ``INTERVALS``).

        Returns:
            The label associated with the numeric value, or the default
            label ``"Une fois par jour"`` when the value is not listed.
        """
        for libelle, heures in INTERVALS.items():
            if heures == self.interval_hours:
                return libelle
        return "Une fois par jour"

    @property
    def sort_mode_label(self) -> str:
        """UI label of :attr:`sort_mode` (key of ``SORT_MODES``).

        Returns:
            The label associated with the stored value, or
            ``"Par galerie"`` by default.
        """
        for libelle, valeur in SORT_MODES.items():
            if valeur == self.sort_mode:
                return libelle
        return "Par galerie"
