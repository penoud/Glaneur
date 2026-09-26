"""Dataclass :class:`Options` — parameters of an engine run."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class Options:
    """Parameters of an engine run.

    Each field is documented by an inline ``#:`` comment to avoid the
    index duplication between autodoc and Napoleon.
    """

    #: Target directory where manifest, cache and files land.
    dossier: Path
    #: Source site origin (for example ``https://example.com``).
    site: str = "https://example.com"
    #: ``galerie`` (by parent title), ``date`` (by month) or ``plat``
    #: (everything at the same level).
    classement: str = "galerie"
    #: Skips resources narrower than this, in pixels.
    largeur_min: int = 800
    #: Floor of the pause between two network requests, in seconds.
    delai: float = 0.5
    #: Revalidates files already present via ``If-None-Match`` and
    #: ``If-Modified-Since``.
    verifier: bool = False
    #: Fully ignores the existing manifest.
    force: bool = False
    #: Lower bound in ``YYYY-MM-DD`` format.
    depuis: str | None = None
    #: Upper bound in ``YYYY-MM-DD`` format.
    jusqua: str | None = None
    #: Enables the disk cache (max date seen, gallery titles).
    utiliser_cache: bool = True
    #: Key of ``Glaneur.sources.SOURCES`` (for example ``wordpress`` or
    #: ``djangoplicity``).
    type_source: str = "wordpress"
    #: Image variant requested from sources that expose several
    #: formats (used by Djangoplicity).
    format_image: str = "Large"
