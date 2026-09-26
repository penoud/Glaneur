"""Djangoplicity adapter: ``d2d/`` feed (ESO, ESA/Hubble, ESA/Webb, ...).

The paginated feed returns ``{Count, Next, Previous, Collections: [...]}``.
Each entry provides an ``ID`` (string, sometimes with a language suffix),
a ``PublicationDate``, an ``Assets[0].Resources[]`` array with a
``ResourceType`` (``Original``, ``Large``, ``Small``, ``Thumbnail``,
``Icon``), a ``URL``, a ``FileSize`` and ``Dimensions``.

Choice: ``ident = "<ID>:<format>"`` — switching format downloads the new
versions without deleting the old ones, exactly like switching sort mode
moves nothing.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from urllib.parse import urlparse

from .base import Element, Source

PER_PAGE = 100

# Fallback order when the requested format is missing: from closest to "Large"
# down to the lightest. `Original` is not in the automatic fallback list:
# accidentally pulling down a one-GB TIFF is not a pleasant surprise.
REPLIS = ("Large", "Small")

# Some Djangoplicity installations return texts in the form
# `"b'…'"` (Python bytes repr). We unwrap them before turning them into
# a directory name or storing them in the manifest.
_BYTES_REPR = re.compile(r"^b'(.*)'$|^b\"(.*)\"$")


def _sain(texte) -> str:
    """Unwrap a possible bytes-repr and return a string."""
    if texte is None:
        return ""
    if isinstance(texte, bytes):
        try:
            return texte.decode("utf-8", "replace")
        except Exception:
            return ""
    s = str(texte)
    m = _BYTES_REPR.match(s)
    if m:
        s = m.group(1) or m.group(2) or ""
    return s


class Djangoplicity(Source):
    """Adapter for a Djangoplicity site exposing ``/images/d2d/``.

    Works with ESO, ESA/Hubble or ESA/Webb. Does not support the
    ``galerie`` sort mode (the CMS does not expose a coherent album
    online — see the historical note in
    :file:`docs/design/evolution-multi-sources.md`).

    The adapter offers an image format via ``reglages["format_image"]``
    (default ``Large``) and falls back to ``Small`` if the requested
    format is missing. ``Original`` is never picked automatically to
    avoid pulling down surprise TIFFs of several hundred MB.
    """

    #: Key used in ``Glaneur.sources.SOURCES``.
    type = "djangoplicity"
    # No "galerie": Djangoplicity does not expose a coherent album online.
    # Sorting by `Subject.Category` (§9 Q5) is deliberately deferred.
    #: Set of supported sort modes (no ``galerie``).
    classements = frozenset({"date", "plat"})

    def __init__(self, base, transport, reglages, journal=None, progression=None):
        """Instantiate the adapter and compute the ``d2d`` endpoint.

        The entry point is ``<base>/images/d2d/``. On ``eso.org`` the base
        often already includes ``/public``, so we only append
        ``/images/d2d/``. The effective image format is read from
        ``reglages["format_image"]`` (default: ``Large``).

        Arguments identical to :meth:`Glaneur.sources.base.Source.__init__`.
        """
        super().__init__(base, transport, reglages, journal, progression)
        # Feed entry point: `<base>/images/d2d/`. On eso.org the base
        # often already includes `/public`, so we only add `/images/d2d/`.
        self.endpoint = f"{self.base}/images/d2d/"
        self.format_image = reglages.get("format_image") or "Large"

    # -- utilities -------------------------------------------------------- #

    def convertir_depuis(self, iso: str | None) -> str | None:
        """Convert ``YYYY-MM-DDThh:mm:ss`` into ``YYYYMMDDhhmmss``.

        Djangoplicity's ``after`` field is **inclusive** (``>=``): the
        boundary element therefore comes back on every pass. The manifest
        handles that; only the tests must account for it.

        Args:
            iso: Date in ISO 8601 format, possibly partial. Tolerates
                ``YYYY-MM-DD`` alone.

        Returns:
            The date compacted to 14 characters, or ``None`` if ``iso``
            is empty.
        """
        if not iso:
            return None
        # tolerant: accepts "YYYY-MM-DD" as well as "YYYY-MM-DDTHH:MM:SS"
        s = iso.replace("-", "").replace(":", "").replace("T", "").replace(" ", "")
        return s[:14].ljust(14, "0")

    def _choisir_ressource(self, ressources: list[dict]) -> tuple[dict | None, str]:
        """Return ``(resource, effective_format)``. Fall back to Small if the
        requested format is missing; ``(None, "")`` if no format is available."""
        par_type = {r.get("ResourceType"): r for r in ressources or []}
        for fmt in (self.format_image, *REPLIS):
            if fmt in par_type:
                return par_type[fmt], fmt
        return None, ""

    def _to_element(self, entree: dict) -> Element:
        ident_brut = _sain(entree.get("ID") or "")
        assets = entree.get("Assets") or []
        premier = (assets[0] if assets else {}) or {}
        ressources = premier.get("Resources") or []
        ressource, format_effectif = self._choisir_ressource(ressources)

        publication = _sain(entree.get("PublicationDate") or "")
        # Typical `PublicationDate`: "2026-09-21T13:00:00"; we extract
        # "YYYY-MM" from it for the by-date sort.
        mois = publication[:7] if len(publication) >= 7 else None

        extra: dict = {}
        if entree.get("Credit"):
            extra["credit"] = _sain(entree.get("Credit"))
        if entree.get("Rights"):
            extra["rights"] = _sain(entree.get("Rights"))

        if ressource is None:
            # No usable resource: return an Element without URL,
            # which the engine will count as `ignoree`.
            return Element(
                ident=f"{ident_brut}:{self.format_image}",
                url=None,
                nom_fichier="",
                date=publication or None,
                mois=mois,
                largeur=None,
                taille=None,
                groupe=None,
                extra=extra,
            )

        url = _sain(ressource.get("URL") or "")
        nom_fichier = urlparse(url).path.rsplit("/", 1)[-1] if url else ""

        dims = ressource.get("Dimensions") or []
        largeur: int | None = None
        if dims:
            try:
                largeur = int(dims[0])
            except (TypeError, ValueError):
                largeur = None

        try:
            taille = int(ressource.get("FileSize")) if ressource.get("FileSize") is not None else None
        except (TypeError, ValueError):
            taille = None

        if ressource.get("Checksum"):
            extra["checksum"] = _sain(ressource.get("Checksum"))

        return Element(
            ident=f"{ident_brut}:{format_effectif}",
            url=url,
            nom_fichier=nom_fichier,
            date=publication or None,
            mois=mois,
            largeur=largeur,
            taille=taille,
            groupe=None,
            extra=extra,
        )

    # -- Inventory -------------------------------------------------------- #

    def inventaire(
        self, depuis: str | None, jusqua: str | None,
    ) -> Iterator[Element]:
        """Walk the ``d2d`` feed by following the ``Next`` URLs returned.

        Djangoplicity's pagination provides its cursor in the response's
        ``Next`` field: we use it as-is rather than recomputing a page
        number. Deduplication by ``ID`` guards against possible cross-page
        duplicates.

        Args:
            depuis: Lower-bound date in ``YYYYMMDDhhmmss`` format
                (converted by :meth:`convertir_depuis`), inclusive.
            jusqua: Upper-bound date in the same format, exclusive.

        Yields:
            The :class:`Glaneur.sources.base.Element` values built from
            the ``Collections`` entries.
        """
        params: dict = {"count": PER_PAGE}
        if depuis:
            params["after"] = depuis
        if jusqua:
            params["before"] = jusqua

        rendus: list[Element] = []
        vus: set[str] = set()
        url: str | None = self.endpoint
        page = 0
        while url:
            page += 1
            data, _ = self.transport.get_json(url, params=params if page == 1 else None)
            data = data or {}
            if page == 1:
                compte = data.get("Count")
                if compte is not None:
                    self._journal(f"Catalogue : {compte} image(s)")

            entrees = data.get("Collections") or []
            for entree in entrees:
                ident = _sain(entree.get("ID") or "")
                if not ident or ident in vus:
                    continue
                vus.add(ident)
                rendus.append(self._to_element(entree))
            self._progression(page, page, f"Inventaire… {len(rendus)} image(s)")

            suivante = data.get("Next")
            if not suivante:
                break
            url = suivante
            self.transport.pause()

        return iter(rendus)
