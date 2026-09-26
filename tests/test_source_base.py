"""Tests unitaires de `classer_erreur` (module `Glaneur.sources.base`).

Périmètre strict : uniquement la classification d'une exception
`requests` et/ou d'une réponse HTTP en trois catégories
(`transitoire`, `coupure`, `definitif`) et l'extraction du
`Retry-After` associé. Aucun accès réseau, aucun mock de transport.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import pytest
import requests

from Glaneur.sources.base import Classification, classer_erreur

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _reponse(status: int, retry_after: str | None = None) -> requests.Response:
    """Build a bare `requests.Response` with a status and optional header."""
    r = requests.Response()
    r.status_code = status
    if retry_after is not None:
        r.headers["Retry-After"] = retry_after
    return r


# --------------------------------------------------------------------------- #
# Coupure : le serveur nous ferme la porte
# --------------------------------------------------------------------------- #


class TestCoupure:
    def test_dns_name_resolution_error_est_une_coupure(self):
        """DNS blackhole (NameResolutionError) est classé `coupure`."""
        exc = requests.exceptions.ConnectionError(
            "HTTPSConnectionPool(host='www.eso.org', port=443): "
            "Max retries exceeded with url: /images/d2d/ "
            "(Caused by NameResolutionError(\"<urllib3...>: "
            "Failed to resolve 'www.eso.org' ([Errno -2] "
            "Name or service not known)\"))"
        )
        c = classer_erreur(exc)
        assert c.categorie == "coupure"

    def test_dns_failed_to_resolve_est_une_coupure(self):
        """Un message 'Failed to resolve' seul suffit à classer `coupure`."""
        exc = requests.exceptions.ConnectionError(
            "Failed to resolve 'example.invalid'"
        )
        assert classer_erreur(exc).categorie == "coupure"

    def test_dns_getaddrinfo_failed_est_une_coupure(self):
        """Un message 'getaddrinfo failed' est classé `coupure`."""
        exc = requests.exceptions.ConnectionError(
            "socket.gaierror: [Errno -2] getaddrinfo failed"
        )
        assert classer_erreur(exc).categorie == "coupure"

    def test_max_retries_exceeded_est_une_coupure(self):
        """ConnectionError 'Max retries exceeded' est classé `coupure`."""
        exc = requests.exceptions.ConnectionError(
            "HTTPSConnectionPool(host='x', port=443): "
            "Max retries exceeded with url: /"
        )
        assert classer_erreur(exc).categorie == "coupure"

    @pytest.mark.parametrize("status", [429, 502, 503, 504])
    def test_status_amont_est_une_coupure(self, status):
        """429 et 5xx amont (502/503/504) sont classés `coupure`."""
        c = classer_erreur(None, _reponse(status))
        assert c.categorie == "coupure"


# --------------------------------------------------------------------------- #
# Transitoire : à réessayer immédiatement, pas une coupure
# --------------------------------------------------------------------------- #


class TestTransitoire:
    def test_timeout_seul_est_transitoire(self):
        """`requests.exceptions.Timeout` sans autre indice est `transitoire`."""
        exc = requests.exceptions.Timeout("Read timed out.")
        assert classer_erreur(exc).categorie == "transitoire"

    def test_500_isole_est_transitoire(self):
        """Un 500 isolé n'est pas une coupure : il reste `transitoire`."""
        assert classer_erreur(None, _reponse(500)).categorie == "transitoire"


# --------------------------------------------------------------------------- #
# Definitif : rien à réessayer côté client
# --------------------------------------------------------------------------- #


class TestDefinitif:
    @pytest.mark.parametrize("status", [401, 403, 404])
    def test_erreurs_client_sont_definitives(self, status):
        """401/403/404 sont classés `definitif` (rien à retenter)."""
        assert classer_erreur(None, _reponse(status)).categorie == "definitif"

    def test_missing_schema_est_definitif(self):
        """URL malformée (`MissingSchema`) est `definitif`."""
        exc = requests.exceptions.MissingSchema("Invalid URL 'foo'")
        assert classer_erreur(exc).categorie == "definitif"


# --------------------------------------------------------------------------- #
# Retry-After
# --------------------------------------------------------------------------- #


class TestRetryAfter:
    def test_retry_after_en_secondes_entieres(self):
        """`Retry-After: 120` est exposé comme `float(120.0)`."""
        c = classer_erreur(None, _reponse(429, retry_after="120"))
        assert c.retry_after == 120.0
        assert isinstance(c.retry_after, float)

    def test_retry_after_http_date_positif(self):
        """`Retry-After` au format HTTP-date donne un delta positif en secondes."""
        futur = datetime.now(timezone.utc) + timedelta(seconds=90)
        entete = format_datetime(futur, usegmt=True)
        c = classer_erreur(None, _reponse(503, retry_after=entete))
        assert c.retry_after is not None
        # tolerance de quelques secondes autour de 90s
        assert 80.0 <= c.retry_after <= 100.0

    def test_retry_after_absent_donne_none(self):
        """Sans en-tête `Retry-After`, `retry_after` vaut `None`."""
        c = classer_erreur(None, _reponse(503))
        assert c.retry_after is None

    def test_dns_error_pas_de_retry_after(self):
        """Une `coupure` DNS n'expose aucun `retry_after` par défaut."""
        exc = requests.exceptions.ConnectionError(
            "Failed to resolve 'example.invalid'"
        )
        c = classer_erreur(exc)
        assert c.categorie == "coupure"
        assert c.retry_after is None


# --------------------------------------------------------------------------- #
# Contrat de la dataclass Classification
# --------------------------------------------------------------------------- #


class TestClassificationDataclass:
    def test_classification_est_gelee(self):
        """`Classification` est immuable (dataclass gelée)."""
        c = classer_erreur(None, _reponse(429, retry_after="1"))
        with pytest.raises((AttributeError, Exception)):
            c.categorie = "definitif"  # type: ignore[misc]

    def test_classification_expose_categorie_et_retry_after(self):
        """L'objet retourné expose au moins `categorie` et `retry_after`."""
        c = classer_erreur(None, _reponse(500))
        assert isinstance(c, Classification)
        assert hasattr(c, "categorie")
        assert hasattr(c, "retry_after")
