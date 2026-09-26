"""Source adapter contract: ``Element``, ``Source``, ``Transport``.

The engine only knows these three classes. A source (WordPress,
Djangoplicity, ...) translates a site into normalised ``Element``
values the engine can consume without knowing where they came from.
"""

from __future__ import annotations

import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import ClassVar, Literal

import requests

UA = "Mozilla/5.0 (compatible; Glaneur/1.0)"

# Message fragments that, in a `ConnectionError`, mean a server-side cut
# (DNS blackhole, exhausted pool). The real ESO case from the "network
# circuit-breaker" sprint reports a `NameResolutionError` under this
# exception type.
_MOTS_COUPURE = (
    "NameResolutionError",
    "Failed to resolve",
    "getaddrinfo failed",
    "Max retries exceeded",
)

#: Upstream HTTP codes meaning a cut: the server explicitly says it
#: cannot/will not respond (429) or an intermediary is down (502/503/504).
_STATUTS_COUPURE = frozenset({429, 502, 503, 504})

#: Definitive client HTTP codes: nothing to retry without intervention.
_STATUTS_DEFINITIFS = frozenset({400, 401, 403, 404, 405, 410})


@dataclass(frozen=True)
class Classification:
    """Result of :func:`classer_erreur` — pure value, no I/O.

    Fields documented inline with ``#:`` comments (same reason as
    :class:`Element`: avoid Sphinx index duplication between autodoc
    and Napoleon).
    """

    #: Error category. ``"transitoire"`` = retry immediately,
    #: ``"coupure"`` = the server cut us off (the engine must defer the
    #: run), ``"definitif"`` = nothing to retry.
    categorie: Literal["transitoire", "coupure", "definitif"]
    #: Number of seconds to wait before retrying, extracted from a
    #: ``Retry-After`` header (integer or HTTP-date). ``None`` if the
    #: information is missing — the engine falls back on its own backoff.
    retry_after: float | None = None


def _retry_after(reponse: requests.Response | None) -> float | None:
    """Extract ``Retry-After`` from a response, in seconds.

    Accepts both forms allowed by RFC 7231: integer number of seconds,
    or HTTP-date. Returns ``None`` if the header is missing, empty or
    unparsable.
    """
    if reponse is None:
        return None
    brut = reponse.headers.get("Retry-After") if reponse.headers else None
    if not brut:
        return None
    brut = brut.strip()
    try:
        return float(int(brut))
    except ValueError:
        pass
    try:
        cible = parsedate_to_datetime(brut)
    except (TypeError, ValueError):
        return None
    if cible is None:
        return None
    if cible.tzinfo is None:
        cible = cible.replace(tzinfo=timezone.utc)
    delta = (cible - datetime.now(timezone.utc)).total_seconds()
    return max(0.0, delta)


def classer_erreur(
    exc: BaseException | None,
    reponse: requests.Response | None = None,
) -> Classification:
    """Classify a network exception and/or an HTTP response.

    The caller passes what it has: an exception alone (no response
    because the connection never landed), a response alone (HTTP status
    to interpret), or both.

    Args:
        exc: Exception raised by ``requests``. ``None`` is allowed when
            only a response needs classifying.
        reponse: HTTP response from which ``status_code`` and
            ``headers['Retry-After']`` are read. ``None`` is allowed.

    Returns:
        An immutable :class:`Classification`. The function performs no
        I/O — it is testable without a network.
    """
    retry_after = _retry_after(reponse)

    if reponse is not None:
        code = reponse.status_code
        if code in _STATUTS_COUPURE:
            return Classification("coupure", retry_after)
        if code in _STATUTS_DEFINITIFS:
            return Classification("definitif", retry_after)
        if 500 <= code < 600:
            # 5xx not listed above: treated as transient
            # (an isolated 500 is not a cut).
            return Classification("transitoire", retry_after)

    if exc is not None:
        if isinstance(exc, requests.exceptions.Timeout):
            return Classification("transitoire", retry_after)
        if isinstance(exc, requests.exceptions.ConnectionError):
            message = str(exc)
            if any(mot in message for mot in _MOTS_COUPURE):
                return Classification("coupure", retry_after)
            return Classification("transitoire", retry_after)
        if isinstance(exc, (
            requests.exceptions.MissingSchema,
            requests.exceptions.InvalidSchema,
            requests.exceptions.InvalidURL,
            requests.exceptions.URLRequired,
        )):
            return Classification("definitif", retry_after)

    return Classification("transitoire", retry_after)


class Interrompu(Exception):
    """Raised when the user requests a cooperative stop.

    Carried by the transport and propagated up to the engine, which
    treats it as a normal end (see
    :attr:`Glaneur.engine.result.Resultat.interrompu`).
    """


@dataclass(frozen=True)
class Element:
    """An image to synchronise, as the engine understands it.

    Fields documented inline with ``#:`` comments — see
    :class:`Glaneur.engine.options.Options` for the reason (avoid the
    index duplication between autodoc and Napoleon).
    """

    #: Unique identifier within the source, key of the manifest. String,
    #: to accept both WordPress integers and the alphanumeric identifiers
    #: from Djangoplicity.
    ident: str
    #: URL of the resource to download. ``None`` if the source did not
    #: find a resource for the requested format: the engine will count
    #: the element in :attr:`Glaneur.engine.result.Resultat.ignorees`.
    url: str | None
    #: File name to give the resource on disk, without directory.
    nom_fichier: str
    #: Publication date in ISO format, if known.
    date: str | None = None
    #: ``YYYY-MM`` month extracted from the date, used for the
    #: by-date sort.
    mois: str | None = None
    #: Width in pixels, when the source provides it — used by the
    #: :attr:`Glaneur.engine.options.Options.largeur_min` filter.
    largeur: int | None = None
    #: File size in bytes, if announced by the source (allows
    #: :meth:`Glaneur.engine.core.Moteur.fichier_complet` to validate).
    taille: int | None = None
    #: Parent identifier (WordPress gallery, Djangoplicity collection)
    #: for the ``galerie`` sort mode.
    groupe: str | None = None
    #: Free-form metadata passed through to the manifest (credit,
    #: checksum, ...). The engine does not interpret them.
    extra: dict = field(default_factory=dict)


class Transport:
    """Shared HTTP plumbing: one session, one delay, one stop.

    A source never creates its own session: it receives this transport
    from the engine, which guarantees that a delay floor and cooperative
    stop apply to every source without an adapter being able to forget.
    """

    def __init__(self, delai: float, arret: threading.Event | None = None) -> None:
        """Build the transport with its session and delay floor.

        Args:
            delai: Floor for the pause between two requests, in seconds.
            arret: Shared event that cuts pending requests. Created on
                demand if not provided.
        """
        self.delai = delai
        self.arret = arret or threading.Event()
        self.session = requests.Session()
        self.session.headers["User-Agent"] = UA

    def verifier_arret(self) -> None:
        """Raise :class:`Interrompu` if ``self.arret`` was set.

        Raises:
            Interrompu: If a cooperative stop was requested.
        """
        if self.arret.is_set():
            raise Interrompu()

    def pause(self, secondes: float | None = None) -> None:
        """Fragmented wait that reacts quickly to a stop request.

        Args:
            secondes: Duration to wait. Uses ``self.delai`` when ``None``.

        Raises:
            Interrompu: If a cooperative stop is requested during the
                wait.
        """
        fin = time.monotonic() + (self.delai if secondes is None else secondes)
        while time.monotonic() < fin:
            self.verifier_arret()
            time.sleep(min(0.1, max(0.0, fin - time.monotonic())))

    def get_json(
        self,
        url: str,
        params: dict | None = None,
        essais: int = 3,
        fin_si: frozenset[int] = frozenset(),
    ) -> tuple[object | None, Mapping]:
        """GET JSON with retries.

        A code listed in ``fin_si`` is treated as a normal end: the
        result is ``(None, headers)`` without raising. WordPress passes
        ``fin_si={400}`` to say "page beyond the last one".

        Args:
            url: Absolute URL to query.
            params: Query parameters passed to ``requests``.
            essais: Maximum number of attempts (linear backoff:
                2s, 4s, 6s, ...).
            fin_si: HTTP codes interpreted as a normal end.

        Returns:
            Tuple ``(data, headers)``. ``data`` is ``None`` when the
            response code belongs to ``fin_si``.

        Raises:
            RuntimeError: After the ``essais`` attempts are exhausted
                without success.
            Interrompu: If a cooperative stop is requested.
        """
        derniere: Exception | None = None
        for tentative in range(essais):
            self.verifier_arret()
            try:
                r = self.session.get(url, params=params, timeout=30)
                if r.status_code in fin_si:
                    return None, r.headers
                r.raise_for_status()
                return r.json(), r.headers
            except requests.RequestException as e:
                derniere = e
                self.pause(2 * (tentative + 1))
        raise RuntimeError(f"L'API ne répond pas ({derniere})")


class Source(ABC):
    """Adapter from a site type to ``Element`` values.

    An adapter receives its base (site URL), the shared transport, its
    settings (free-form dictionary — the adapter finds for example the
    chosen image format there) and a progression callback for its long
    inventory phases.
    """

    type: ClassVar[str]
    classements: ClassVar[frozenset[str]]

    def __init__(
        self,
        base: str,
        transport: Transport,
        reglages: dict,
        journal: Callable[[str], None] | None = None,
        progression: Callable[[int, int, str], None] | None = None,
    ) -> None:
        """Instantiate the adapter with its shared transport.

        Args:
            base: Source site URL, without trailing slash.
            transport: :class:`Transport` provided by the engine.
            reglages: Free-form dictionary (for example
                ``{"format_image": "Large"}`` for Djangoplicity).
            journal: Text callback for user-facing messages. ``None`` =
                mute.
            progression: ``(done, total, label)`` callback for long
                inventory phases. ``None`` = mute.
        """
        self.base = base.rstrip("/")
        self.transport = transport
        self.reglages = reglages or {}
        self._journal = journal or (lambda msg: None)
        self._progression = progression or (lambda fait, total, etiquette: None)

    @abstractmethod
    def inventaire(
        self, depuis: str | None, jusqua: str | None,
    ) -> Iterator[Element]:
        """Iterate the catalogue in chronological order when possible.

        Args:
            depuis: Lower bound in the source's own format
                (see :meth:`convertir_depuis`). ``None`` = no lower bound.
            jusqua: Upper bound. ``None`` = no upper bound.

        Yields:
            The :class:`Element` values, in chronological order when the
            source allows it.
        """

    def resoudre_groupes(
        self, cles: set[str], connus: dict[str, str] | None = None,
    ) -> dict[str, str]:
        """Resolve group identifiers into folder names.

        Default implementation: return ``connus`` as-is — no additional
        grouping. Sources that expose a ``galerie`` sort mode (see
        :attr:`classements`) override this to query the missing titles.

        Args:
            cles: Group identifiers to resolve.
            connus: Already-resolved table (from the cache, typically).

        Returns:
            A ``{key -> cleaned title}`` table, ready to be passed to
            :meth:`Glaneur.engine.core.Moteur.dossier_pour`.
        """
        return dict(connus or {})

    def convertir_depuis(self, iso: str | None) -> str | None:
        """Translate an ISO date from the cache into the source's format.

        Default: leave it as-is. Sources that want, like Djangoplicity,
        ``YYYYMMDDhhmmss`` override this.

        Args:
            iso: Date in ISO 8601 format, or ``None``.

        Returns:
            The converted date, or ``None``.
        """
        return iso
