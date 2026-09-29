"""Persistent application configuration.

The file lives in ``%APPDATA%\\Glaneur\\config.json`` on Windows and in
``~/.config/glaneur/`` elsewhere. It is written atomically so that it
never gets truncated if the application is killed.

Schema versioning
-----------------

`Glaneur.config` writes JSON in the **v2 schema** described in
``docs/design/evolution-multi-sources.md`` §3.1: a top-level
application block, a ``defaults`` block, and a ``profiles`` list
containing one entry today. Older files (no ``schema_version`` key,
or ``schema_version < 2``) are read as v1 and, on the next call to
:meth:`Config.save`, migrated in place — the pre-migration bytes are
copied to ``config.v1.json`` for rollback.

At runtime :class:`Config` stays flat: every attribute callers rely on
(``cfg.site``, ``cfg.min_width``, ``cfg.last_run``, ...) is preserved.
The v2 shape only affects the load/save I/O boundary.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

APP_NAME = "Glaneur"
GITHUB_OWNER = "penoud"
GITHUB_REPOSITORY = "Glaneur"

#: Version of the on-disk configuration schema. Incremented on
#: incompatible format changes; on load, an older or missing value
#: triggers a one-way migration.
SCHEMA_VERSION = 2

#: Config fields that live under the ``defaults`` block in v2 and can
#: be overridden per-profile with ``None`` meaning "inherit".
_DEFAULT_FIELDS: tuple[str, ...] = (
    "min_width",
    "verify_integrity",
)

#: Config fields that live inside a profile in v2 as its run state
#: (per-profile scheduler bookkeeping). Not overridable by defaults.
_PROFILE_STATE_FIELDS: tuple[str, ...] = (
    "last_run",
    "retry_after",
    "backoff_level",
)


def _current_schema_version(chemin: Path) -> int | None:
    """Return the schema version currently on disk at ``chemin``.

    Reads the file, extracts its ``schema_version`` field, and returns
    the integer value. A file without that field is treated as v1. The
    return value is ``None`` when the file is missing, unreadable, or
    holds JSON whose top level is not a mapping — the caller then
    treats it as "no on-disk state to consider".
    """
    if not chemin.exists():
        return None
    try:
        with open(chemin, encoding="utf-8") as f:
            brut = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(brut, dict):
        return None
    version = brut.get("schema_version")
    if isinstance(version, int):
        return version
    return 1   # v1 shape: no schema_version key

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

#: `Config` fields that belong to a sync **profile** rather than to the
#: application. Drives the "Site" tab of :class:`DialoguePreferences`
#: today, and the v1 → v2 migration described in
#: ``docs/design/evolution-multi-sources.md`` §3.1: on migration, these
#: fields move from the top-level `Config` into a `Profile` entry, while
#: every other field stays at the application level.
#:
#: Order matters — the migration writes profile keys in this order, and
#: the "Site" tab lays them out top-to-bottom.
PROFILE_FIELDS: tuple[str, ...] = (
    "source_type",
    "site",
    "image_format",
    "target_dir",
    "sort_mode",
    "min_width",
    "verify_integrity",
)


@dataclass
class Profile:
    """One sync job: a site, a source type, a target directory.

    Represents a single entry of the v2 ``profiles`` list. Today
    :class:`Config` still holds a single implicit profile flat on
    itself and this class is not instantiated at runtime; it will be
    used when E3 part B promotes each profile field into a real
    per-profile object.

    Fields documented inline with ``#:`` to avoid the Sphinx
    autodoc/Napoleon duplication (same pattern as :class:`Config`).
    """

    #: Stable ``uuid4().hex`` — the scheduler state and the log key
    #: point here, never at the display name.
    id: str = ""
    #: Human-readable display name shown in the profile table.
    name: str = ""
    source_type: str = "wordpress"
    site: str = ""
    target_dir: str = ""
    image_format: str = "Large"
    sort_mode: str = "gallery"
    #: Overrides — ``None`` means "inherit from ``Config.defaults``".
    min_width: int | None = None
    verify_integrity: bool | None = None
    #: Scheduler state, per profile (roadmap §5.1).
    last_run: str = ""
    retry_after: str = ""
    backoff_level: int = 0


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
    #: Anchor of the scheduler grid, ``HH:MM`` (local naive time).
    #: Introduced with v2 (roadmap §5.1). Seeded from ``last_run`` on
    #: migration to keep today's rhythm; empty means "start at
    #: midnight".
    schedule_anchor: str = ""

    _path: Path | None = field(default=None, repr=False, compare=False)
    #: Stable ``uuid4().hex`` of the single implicit profile. Seeded
    #: on v1 → v2 migration or on the first save without a prior load;
    #: never serialised at the top level (it appears as
    #: ``profiles[0].id`` in v2).
    _profile_id: str = field(default="", repr=False, compare=False)

    # -- load / save ------------------------------------------------------- #

    @classmethod
    def load(cls, chemin: Path | None = None) -> Config:
        """Load the config from ``chemin`` or fall back to default values.

        Accepts both the v1 flat layout and the v2 layered layout
        (``schema_version`` + ``defaults`` + ``profiles``). A v1 file
        is read into the flat :class:`Config` as before; the on-disk
        migration to v2 happens on the next call to :meth:`save`,
        where the pre-migration bytes are copied to
        ``config.v1.json`` for rollback.

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
                if isinstance(brut, dict):
                    version = brut.get("schema_version")
                    if version == SCHEMA_VERSION:
                        cfg._load_v2(brut)
                    elif not isinstance(version, int) or version < SCHEMA_VERSION:
                        # No `schema_version` field, or a version we
                        # know about — read as v1.
                        cfg._load_v1(brut)
                    # else: version > SCHEMA_VERSION (a file from a
                    # future Glaneur). Do not misread it as v1 — that
                    # would silently drop every future-only field. Fall
                    # back to defaults; ``save()`` refuses to overwrite
                    # the file so the future version is preserved.
            except (AttributeError, json.JSONDecodeError, OSError,
                    TypeError, ValueError):
                pass  # unreadable config: fall back to default values
        if not cfg.target_dir:
            cfg.target_dir = str(default_images_dir())
        cfg.validate()
        # Every Config that reaches the runtime has a stable profile id;
        # first-time save carries it into ``profiles[0].id`` on disk.
        if not cfg._profile_id:
            cfg._profile_id = uuid.uuid4().hex
        return cfg

    def _load_v1(self, brut: dict) -> None:
        """Populate this instance from a v1 flat dict.

        Applies :data:`_LEGACY_FIELD_ALIASES` on keys and
        :data:`_LEGACY_SORT_MODE_ALIASES` on the sort_mode value so
        pre-US-EN-04/US-EN-05 files still load without loss.

        Seeds ``schedule_anchor`` from the current ``last_run``'s
        time-of-day so the scheduler grid (roadmap §5.1) keeps today's
        rhythm: the first slot after migration lands at the same hour
        of the day as the user has been used to. When ``last_run`` is
        empty, the anchor stays empty (the caller then treats it as
        midnight).
        """
        connus = {f.name for f in fields(type(self)) if not f.name.startswith("_")}
        for cle, valeur in brut.items():
            cle = _LEGACY_FIELD_ALIASES.get(cle, cle)
            if cle in connus:
                setattr(self, cle, valeur)
        if self.sort_mode in _LEGACY_SORT_MODE_ALIASES:
            self.sort_mode = _LEGACY_SORT_MODE_ALIASES[self.sort_mode]
        if not self.schedule_anchor and self.last_run:
            # last_run is an ISO 8601 timestamp — extract HH:MM.
            candidate = self.last_run[:16].split("T")[-1]
            if len(candidate) == 5 and candidate[2] == ":":
                self.schedule_anchor = candidate

    def _load_v2(self, brut: dict) -> None:
        """Populate this instance from a v2 layered dict.

        Layout: application keys at the top level, inheritable settings
        under ``defaults``, per-profile state under ``profiles[0]``.
        A profile-level override of ``None`` inherits from ``defaults``.
        Only the first profile is read today; multi-profile support
        arrives with E3 part B.

        Tolerant to malformed nesting: a ``defaults`` value that is not
        a dict, or a ``profiles[0]`` entry that is not a dict, is
        skipped rather than crashing the load — the outer
        :meth:`load` treats a corrupt config as absent and falls back
        to default values.
        """
        connus = {f.name for f in fields(type(self)) if not f.name.startswith("_")}
        # -- Top-level (application) keys ---------------------------------
        for cle in ("language", "interval_hours", "schedule_anchor",
                    "request_delay", "run_at_startup", "close_to_tray",
                    "notifications", "check_updates_on_start",
                    "slideshow_dir"):
            if cle in brut and cle in connus:
                setattr(self, cle, brut[cle])
        # -- Defaults block (inheritable settings) ------------------------
        defaults = brut.get("defaults")
        if isinstance(defaults, dict):
            for cle in _DEFAULT_FIELDS:
                if cle in defaults and cle in connus:
                    setattr(self, cle, defaults[cle])
        # -- profiles[0] --------------------------------------------------
        profiles = brut.get("profiles")
        if isinstance(profiles, list) and profiles:
            first = profiles[0]
            if not isinstance(first, dict):
                return
            self._profile_id = str(first.get("id") or "")
            for cle in ("source_type", "site", "target_dir", "image_format",
                        "sort_mode", *_PROFILE_STATE_FIELDS):
                if cle in first and cle in connus:
                    setattr(self, cle, first[cle])
            # Overrides: profile-level `null` means "inherit"; a real
            # value wins over the defaults value.
            for cle in _DEFAULT_FIELDS:
                valeur = first.get(cle)
                if valeur is not None and cle in connus:
                    setattr(self, cle, valeur)
            if self.sort_mode in _LEGACY_SORT_MODE_ALIASES:
                self.sort_mode = _LEGACY_SORT_MODE_ALIASES[self.sort_mode]

    def save(self) -> None:
        """Write the config to disk atomically, in the v2 shape.

        Uses the path stored by :meth:`load` if any, otherwise
        ``<config_dir()>/config.json``. If the current on-disk file is
        in an older shape (v1, or a future schema we know about), its
        bytes are copied to ``config.v<n>.json`` (n = the current
        file's version, ``1`` if none) before the v2 file replaces it.
        The backup is never overwritten if it already exists.

        Refuses to touch a file whose ``schema_version`` is greater
        than :data:`SCHEMA_VERSION` — that would silently drop every
        field the future version added. A downgrade run must delete
        the file by hand before the older Glaneur can rewrite it.

        Private fields (prefixed with ``_``) are not serialised at the
        top level; ``_profile_id`` appears inside ``profiles[0]`` as
        its ``id`` field.
        """
        chemin = self._path or (config_dir() / "config.json")
        chemin.parent.mkdir(parents=True, exist_ok=True)
        current_version = _current_schema_version(chemin)
        if current_version is not None and current_version > SCHEMA_VERSION:
            # Future format on disk — do not overwrite.
            self._path = chemin
            return
        self._snapshot_older(chemin, current_version)
        if not self._profile_id:
            self._profile_id = uuid.uuid4().hex
        donnees = self._to_v2_dict()
        tmp = chemin.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(donnees, f, ensure_ascii=False, indent=2)
        tmp.replace(chemin)
        self._path = chemin

    def _to_v2_dict(self) -> dict:
        """Serialise the current state as the v2 on-disk layout.

        Since :class:`Config` still stores a single implicit profile
        flat on itself, the inheritable values live in ``defaults`` and
        the per-profile overrides are set to ``None`` — the effective
        value on the next load is unchanged.
        """
        flat = {k: v for k, v in asdict(self).items() if not k.startswith("_")}
        # Split into three buckets: profile, defaults, top-level.
        defaults = {cle: flat.pop(cle) for cle in _DEFAULT_FIELDS}
        profile: dict = {"id": self._profile_id, "name": "default"}
        for cle in ("source_type", "site", "image_format", "target_dir",
                    "sort_mode", *_PROFILE_STATE_FIELDS):
            profile[cle] = flat.pop(cle)
        # Overrides null: the effective value lives in `defaults`.
        for cle in _DEFAULT_FIELDS:
            profile[cle] = None
        return {
            "schema_version": SCHEMA_VERSION,
            **flat,
            "defaults": defaults,
            "profiles": [profile],
        }

    def _snapshot_older(self, chemin: Path, current_version: int | None) -> None:
        """Copy an older on-disk config to ``config.v<n>.json`` before overwriting.

        Called only when the current file exists and its schema version
        is strictly older than :data:`SCHEMA_VERSION`. The snapshot goes
        through a ``.tmp`` sidecar and an atomic rename so a crash mid-
        backup cannot leave a truncated snapshot in place. Idempotent:
        if the target snapshot already exists, no snapshot is written —
        the older backup is the source of truth.

        Args:
            chemin: Path of the live config file.
            current_version: The schema version currently on disk, as
                returned by :func:`_current_schema_version`. ``None``
                means the file is missing or unreadable (nothing to
                snapshot).
        """
        if current_version is None or current_version >= SCHEMA_VERSION:
            return
        backup = chemin.with_name(f"{chemin.stem}.v{current_version}.json")
        if backup.exists():
            return
        # Atomic backup: bytes → tmp → rename. A partial write cannot
        # leave a truncated backup because the rename is atomic and the
        # tmp file is removed on failure.
        tmp = backup.with_suffix(".json.tmp")
        try:
            tmp.write_bytes(chemin.read_bytes())
            tmp.replace(backup)
        except OSError:
            try:
                tmp.unlink()
            except OSError:
                pass
            # Snapshot failed — best-effort; the migration continues.

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
