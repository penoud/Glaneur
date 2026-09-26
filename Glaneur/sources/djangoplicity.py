"""Adaptateur Djangoplicity : flux `d2d/` (ESO, ESA/Hubble, ESA/Webb…).

Le flux paginé renvoie `{Count, Next, Previous, Collections: [...]}`. Chaque
entrée donne un `ID` (chaîne, parfois avec suffixe de langue), un
`PublicationDate`, un tableau `Assets[0].Resources[]` avec un `ResourceType`
(`Original`, `Large`, `Small`, `Thumbnail`, `Icon`), une `URL`, un `FileSize`
et des `Dimensions`.

Choix : `ident = "<ID>:<format>"` — changer de format téléchargera les nouvelles
versions sans effacer les anciennes, exactement comme changer de classement ne
déplace rien.
"""

from __future__ import annotations

import re
from typing import Iterator
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
    """Désencapsule un éventuel repr de bytes et renvoie une chaîne."""
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
    """Adaptateur pour un site Djangoplicity exposant ``/images/d2d/``.

    Fonctionne aussi bien avec ESO, ESA/Hubble ou ESA/Webb. Ne supporte
    pas le classement ``galerie`` (le CMS n'expose pas d'album cohérent
    en ligne — voir la note historique dans
    :file:`docs/design/evolution-multi-sources.md`).

    L'adaptateur propose un format d'image via ``reglages["format_image"]``
    (par défaut ``Large``) et retombe sur ``Small`` si le format demandé
    manque. ``Original`` n'est jamais choisi automatiquement pour éviter
    de rapatrier des TIFF de plusieurs centaines de Mo par surprise.
    """

    #: Key used in ``Glaneur.sources.SOURCES``.
    type = "djangoplicity"
    # No "galerie": Djangoplicity does not expose a coherent album online.
    # Sorting by `Subject.Category` (§9 Q5) is deliberately deferred.
    #: Set of supported sort modes (no ``galerie``).
    classements = frozenset({"date", "plat"})

    def __init__(self, base, transport, reglages, journal=None, progression=None):
        """Instancie l'adaptateur et calcule l'endpoint ``d2d``.

        Le point d'entrée est ``<base>/images/d2d/``. Sur ``eso.org`` la
        base inclut souvent déjà ``/public``, donc on ne rajoute que
        ``/images/d2d/``. Le format d'image effectif est lu dans
        ``reglages["format_image"]`` (défaut : ``Large``).

        Arguments identiques à :meth:`Glaneur.sources.base.Source.__init__`.
        """
        super().__init__(base, transport, reglages, journal, progression)
        # Feed entry point: `<base>/images/d2d/`. On eso.org the base
        # often already includes `/public`, so we only add `/images/d2d/`.
        self.endpoint = f"{self.base}/images/d2d/"
        self.format_image = reglages.get("format_image") or "Large"

    # -- utilities -------------------------------------------------------- #

    def convertir_depuis(self, iso: str | None) -> str | None:
        """Convertit ``AAAA-MM-JJThh:mm:ss`` en ``AAAAMMJJhhmmss``.

        Le champ ``after`` de Djangoplicity est **inclusif** (``>=``) :
        l'élément frontière reviendra donc à chaque passage. Le manifeste
        s'en charge, seuls les tests doivent en tenir compte.

        Args:
            iso: Date au format ISO 8601, éventuellement partielle.
                Tolère ``AAAA-MM-JJ`` seul.

        Returns:
            La date compactée sur 14 caractères, ou ``None`` si ``iso``
            est vide.
        """
        if not iso:
            return None
        # tolerant: accepts "YYYY-MM-DD" as well as "YYYY-MM-DDTHH:MM:SS"
        s = iso.replace("-", "").replace(":", "").replace("T", "").replace(" ", "")
        return s[:14].ljust(14, "0")

    def _choisir_ressource(self, ressources: list[dict]) -> tuple[dict | None, str]:
        """Renvoie (ressource, format_effectif). Repli sur Small si le format
        demandé n'est pas là ; (None, "") si aucun format n'est disponible."""
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
        """Parcourt le flux ``d2d`` en suivant les URL ``Next`` renvoyées.

        La pagination Djangoplicity donne son curseur dans le champ
        ``Next`` de la réponse : on l'utilise tel quel plutôt que de
        recalculer un numéro de page. La déduplication par ``ID`` protège
        contre d'éventuels doublons entre pages.

        Args:
            depuis: Date basse au format ``AAAAMMJJhhmmss`` (converti par
                :meth:`convertir_depuis`), inclusive.
            jusqua: Date haute au même format, exclusive.

        Yields:
            Les :class:`Glaneur.sources.base.Element` construits à partir
            des entrées ``Collections``.
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
