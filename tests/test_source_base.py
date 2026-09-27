"""Unit tests for `classify_error` (module `Glaneur.sources.base`).

Strict scope: only the classification of a `requests` exception
and/or an HTTP response into three categories
(`transitoire`, `coupure`, `definitif`) and the extraction of the
matching `Retry-After`. No network access, no transport mock.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import pytest
import requests

from Glaneur.sources.base import Classification, classify_error

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
        """A DNS blackhole (NameResolutionError) is classified as `coupure`."""
        exc = requests.exceptions.ConnectionError(
            "HTTPSConnectionPool(host='www.eso.org', port=443): "
            "Max retries exceeded with url: /images/d2d/ "
            "(Caused by NameResolutionError(\"<urllib3...>: "
            "Failed to resolve 'www.eso.org' ([Errno -2] "
            "Name or service not known)\"))"
        )
        c = classify_error(exc)
        assert c.categorie == "coupure"

    def test_dns_failed_to_resolve_est_une_coupure(self):
        """A lone 'Failed to resolve' message is enough to classify as `coupure`."""
        exc = requests.exceptions.ConnectionError(
            "Failed to resolve 'example.invalid'"
        )
        assert classify_error(exc).categorie == "coupure"

    def test_dns_getaddrinfo_failed_est_une_coupure(self):
        """A 'getaddrinfo failed' message is classified as `coupure`."""
        exc = requests.exceptions.ConnectionError(
            "socket.gaierror: [Errno -2] getaddrinfo failed"
        )
        assert classify_error(exc).categorie == "coupure"

    def test_max_retries_exceeded_est_une_coupure(self):
        """ConnectionError 'Max retries exceeded' is classified as `coupure`."""
        exc = requests.exceptions.ConnectionError(
            "HTTPSConnectionPool(host='x', port=443): "
            "Max retries exceeded with url: /"
        )
        assert classify_error(exc).categorie == "coupure"

    @pytest.mark.parametrize("status", [429, 502, 503, 504])
    def test_status_amont_est_une_coupure(self, status):
        """429 and upstream 5xx (502/503/504) are classified as `coupure`."""
        c = classify_error(None, _reponse(status))
        assert c.categorie == "coupure"


# --------------------------------------------------------------------------- #
# Transitoire: retry immediately, not a cut
# --------------------------------------------------------------------------- #


class TestTransitoire:
    def test_timeout_seul_est_transitoire(self):
        """`requests.exceptions.Timeout` alone is `transitoire`."""
        exc = requests.exceptions.Timeout("Read timed out.")
        assert classify_error(exc).categorie == "transitoire"

    def test_500_isole_est_transitoire(self):
        """An isolated 500 is not a cut: it stays `transitoire`."""
        assert classify_error(None, _reponse(500)).categorie == "transitoire"


# --------------------------------------------------------------------------- #
# Definitif: nothing to retry on the client side
# --------------------------------------------------------------------------- #


class TestDefinitif:
    @pytest.mark.parametrize("status", [401, 403, 404])
    def test_erreurs_client_sont_definitives(self, status):
        """401/403/404 are classified as `definitif` (nothing to retry)."""
        assert classify_error(None, _reponse(status)).categorie == "definitif"

    def test_missing_schema_est_definitif(self):
        """A malformed URL (`MissingSchema`) is `definitif`."""
        exc = requests.exceptions.MissingSchema("Invalid URL 'foo'")
        assert classify_error(exc).categorie == "definitif"


# --------------------------------------------------------------------------- #
# Retry-After
# --------------------------------------------------------------------------- #


class TestRetryAfter:
    def test_retry_after_en_secondes_entieres(self):
        """`Retry-After: 120` is exposed as `float(120.0)`."""
        c = classify_error(None, _reponse(429, retry_after="120"))
        assert c.retry_after == 120.0
        assert isinstance(c.retry_after, float)

    def test_retry_after_http_date_positif(self):
        """`Retry-After` as an HTTP-date yields a positive delta in seconds."""
        futur = datetime.now(timezone.utc) + timedelta(seconds=90)
        entete = format_datetime(futur, usegmt=True)
        c = classify_error(None, _reponse(503, retry_after=entete))
        assert c.retry_after is not None
        # a few seconds of tolerance around 90s
        assert 80.0 <= c.retry_after <= 100.0

    def test_retry_after_absent_donne_none(self):
        """Without a `Retry-After` header, `retry_after` is `None`."""
        c = classify_error(None, _reponse(503))
        assert c.retry_after is None

    def test_dns_error_pas_de_retry_after(self):
        """A DNS `coupure` exposes no `retry_after` by default."""
        exc = requests.exceptions.ConnectionError(
            "Failed to resolve 'example.invalid'"
        )
        c = classify_error(exc)
        assert c.categorie == "coupure"
        assert c.retry_after is None


# --------------------------------------------------------------------------- #
# Contract of the Classification dataclass
# --------------------------------------------------------------------------- #


class TestClassificationDataclass:
    def test_classification_est_gelee(self):
        """`Classification` is immutable (frozen dataclass)."""
        c = classify_error(None, _reponse(429, retry_after="1"))
        with pytest.raises((AttributeError, Exception)):
            c.categorie = "definitif"  # type: ignore[misc]

    def test_classification_expose_categorie_et_retry_after(self):
        """The returned object exposes at least `categorie` and `retry_after`."""
        c = classify_error(None, _reponse(500))
        assert isinstance(c, Classification)
        assert hasattr(c, "categorie")
        assert hasattr(c, "retry_after")
