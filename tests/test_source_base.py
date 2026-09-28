"""Unit tests for `classify_error` and `Transport.get_json`
(module `Glaneur.sources.base`).

Strict scope:

- classification of a `requests` exception and/or an HTTP response into
  the three categories (`transitoire`, `coupure`, `definitif`) and the
  extraction of the matching `Retry-After`;
- retry policy of `Transport.get_json`: definitive errors raise
  immediately, transient/cut errors retry with `Retry-After` honoured
  (capped at 120s), three attempts with pauses of 2s then 4s only.

No network access — the transport session is mocked.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from unittest.mock import MagicMock, patch

import pytest
import requests

from Glaneur.sources.base import ErrorClassification, Transport, classify_error

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
        assert c.category == "coupure"

    def test_dns_failed_to_resolve_est_une_coupure(self):
        """A lone 'Failed to resolve' message is enough to classify as `coupure`."""
        exc = requests.exceptions.ConnectionError(
            "Failed to resolve 'example.invalid'"
        )
        assert classify_error(exc).category == "coupure"

    def test_dns_getaddrinfo_failed_est_une_coupure(self):
        """A 'getaddrinfo failed' message is classified as `coupure`."""
        exc = requests.exceptions.ConnectionError(
            "socket.gaierror: [Errno -2] getaddrinfo failed"
        )
        assert classify_error(exc).category == "coupure"

    def test_max_retries_exceeded_est_une_coupure(self):
        """ConnectionError 'Max retries exceeded' is classified as `coupure`."""
        exc = requests.exceptions.ConnectionError(
            "HTTPSConnectionPool(host='x', port=443): "
            "Max retries exceeded with url: /"
        )
        assert classify_error(exc).category == "coupure"

    @pytest.mark.parametrize("status", [429, 502, 503, 504])
    def test_status_amont_est_une_coupure(self, status):
        """429 and upstream 5xx (502/503/504) are classified as `coupure`."""
        c = classify_error(None, _reponse(status))
        assert c.category == "coupure"


# --------------------------------------------------------------------------- #
# Transitoire: retry immediately, not a cut
# --------------------------------------------------------------------------- #


class TestTransitoire:
    def test_timeout_seul_est_transitoire(self):
        """`requests.exceptions.Timeout` alone is `transitoire`."""
        exc = requests.exceptions.Timeout("Read timed out.")
        assert classify_error(exc).category == "transitoire"

    def test_500_isole_est_transitoire(self):
        """An isolated 500 is not a cut: it stays `transitoire`."""
        assert classify_error(None, _reponse(500)).category == "transitoire"


# --------------------------------------------------------------------------- #
# Definitif: nothing to retry on the client side
# --------------------------------------------------------------------------- #


class TestDefinitif:
    @pytest.mark.parametrize("status", [401, 403, 404])
    def test_erreurs_client_sont_definitives(self, status):
        """401/403/404 are classified as `definitif` (nothing to retry)."""
        assert classify_error(None, _reponse(status)).category == "definitif"

    def test_missing_schema_est_definitif(self):
        """A malformed URL (`MissingSchema`) is `definitif`."""
        exc = requests.exceptions.MissingSchema("Invalid URL 'foo'")
        assert classify_error(exc).category == "definitif"


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
        assert c.category == "coupure"
        assert c.retry_after is None


# --------------------------------------------------------------------------- #
# Contract of the ErrorClassification dataclass
# --------------------------------------------------------------------------- #


class TestClassificationDataclass:
    def test_classification_est_gelee(self):
        """`ErrorClassification` is immutable (frozen dataclass)."""
        c = classify_error(None, _reponse(429, retry_after="1"))
        with pytest.raises((AttributeError, Exception)):
            c.category = "definitif"  # type: ignore[misc]

    def test_classification_expose_categorie_et_retry_after(self):
        """The returned object exposes at least `categorie` and `retry_after`."""
        c = classify_error(None, _reponse(500))
        assert isinstance(c, ErrorClassification)
        assert hasattr(c, "category")
        assert hasattr(c, "retry_after")


# --------------------------------------------------------------------------- #
# Transport.get_json — retry policy branched on classify_error
# --------------------------------------------------------------------------- #


class TestTransportGetJson:
    """Retry policy of `Transport.get_json`.

    These tests pin the behaviour targeted by US-VERIF-02: definitive
    client errors must raise immediately, transient/cut errors retry with
    `Retry-After` honoured up to a 120s cap, and three attempts spend
    exactly two pauses (2s then 4s) — never a third `sleep(6)`.
    """

    @pytest.mark.parametrize("status", [401, 403, 404])
    def test_erreurs_client_hors_fin_si_levent_sans_reessayer(self, status):
        """A definitive client error (401/403/404) raises at once, no retry, no sleep."""
        t = Transport(delay=0)
        t.session = MagicMock()
        rep = MagicMock(status_code=status, headers={})
        rep.raise_for_status = MagicMock(
            side_effect=requests.HTTPError(response=rep)
        )
        t.session.get.return_value = rep
        with patch.object(t, "sleep") as fake_sleep, \
                pytest.raises(requests.HTTPError):
            t.get_json("https://x/api")
        assert t.session.get.call_count == 1
        fake_sleep.assert_not_called()

    def test_retry_after_court_est_respecte(self):
        """A short `Retry-After` (below 120s) is used as the pause between retries."""
        t = Transport(delay=0)
        t.session = MagicMock()
        rep_429 = MagicMock(status_code=429, headers={"Retry-After": "3"})
        rep_429.raise_for_status = MagicMock(
            side_effect=requests.HTTPError(response=rep_429)
        )
        rep_ok = MagicMock(status_code=200, headers={})
        rep_ok.json.return_value = {"ok": True}
        rep_ok.raise_for_status = MagicMock()
        t.session.get.side_effect = [rep_429, rep_ok]
        with patch.object(t, "sleep") as fake_sleep:
            payload, _ = t.get_json("https://x/api")
        assert payload == {"ok": True}
        assert fake_sleep.call_count == 1
        assert fake_sleep.call_args.args[0] == 3.0

    def test_retry_after_long_est_plafonne_a_120s(self):
        """A `Retry-After` above 120s is capped at 120s before sleeping."""
        t = Transport(delay=0)
        t.session = MagicMock()
        rep_429 = MagicMock(status_code=429, headers={"Retry-After": "300"})
        rep_429.raise_for_status = MagicMock(
            side_effect=requests.HTTPError(response=rep_429)
        )
        rep_ok = MagicMock(status_code=200, headers={})
        rep_ok.json.return_value = {"ok": True}
        rep_ok.raise_for_status = MagicMock()
        t.session.get.side_effect = [rep_429, rep_ok]
        with patch.object(t, "sleep") as fake_sleep:
            payload, _ = t.get_json("https://x/api")
        assert payload == {"ok": True}
        assert fake_sleep.call_count == 1
        assert fake_sleep.call_args.args[0] == 120.0

    def test_trois_echecs_500_donnent_deux_pauses_2_puis_4(self):
        """Three 500 attempts pause 2s then 4s only — no third `sleep(6)`."""
        t = Transport(delay=0)
        t.session = MagicMock()
        rep_500 = MagicMock(status_code=500, headers={})
        rep_500.raise_for_status = MagicMock(
            side_effect=requests.HTTPError(response=rep_500)
        )
        t.session.get.return_value = rep_500
        with patch.object(t, "sleep") as fake_sleep, \
                pytest.raises(RuntimeError):
            t.get_json("https://x/api")
        assert t.session.get.call_count == 3
        assert fake_sleep.call_count == 2
        assert fake_sleep.call_args_list[0].args[0] == 2.0
        assert fake_sleep.call_args_list[1].args[0] == 4.0
