"""Edge-case tests to close small gaps in the source adapters.

The main behaviour of each source is covered by its dedicated test
file. This file drills into the remaining uncovered branches:

- `base._retry_after` on malformed HTTP-dates and naive datetimes,
- `base.classify_error` fallback branches,
- `base.Transport.pause` and `verifier_arret` cooperative stop,
- `base.Source.resolve_groups` / `convertir_depuis` default no-ops,
- `djangoplicity._sanitized` on `None` and `bytes`,
- `djangoplicity.Djangoplicity` handling of malformed
  `Dimensions`/`FileSize`,
- `djangoplicity.inventory` when a `jusqua` bound is set,
- `wordpress._clean` cleaning helper,
- `sources.sort_modes_for` for an unknown source type.
"""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

import pytest
import requests

from Glaneur.sources import SOURCES, sort_modes_for
from Glaneur.sources.base import (
    ErrorClassification,
    Interrupted,
    Source,
    Transport,
    _retry_after,
    classify_error,
)
from Glaneur.sources.djangoplicity import Djangoplicity, _sanitized
from Glaneur.sources.wordpress import _clean


# --------------------------------------------------------------------------- #
# base._retry_after
# --------------------------------------------------------------------------- #


def _reponse(headers=None, status=200):
    r = MagicMock(spec=requests.Response)
    r.headers = headers or {}
    r.status_code = status
    return r


class TestRetryAfter:
    def test_no_response_returns_none(self):
        assert _retry_after(None) is None

    def test_header_absent_returns_none(self):
        assert _retry_after(_reponse({})) is None

    def test_empty_value_returns_none(self):
        assert _retry_after(_reponse({"Retry-After": "  "})) is None

    def test_integer_seconds(self):
        assert _retry_after(_reponse({"Retry-After": "42"})) == 42.0

    def test_http_date_in_the_future(self):
        # A valid HTTP-date far in the future returns a positive delta.
        assert _retry_after(
            _reponse({"Retry-After": "Wed, 21 Oct 2099 07:28:00 GMT"}),
        ) > 0

    def test_http_date_in_the_past_yields_zero(self):
        # A past date clamps to 0 (never negative).
        assert _retry_after(
            _reponse({"Retry-After": "Wed, 21 Oct 1999 07:28:00 GMT"}),
        ) == 0.0

    def test_naive_http_date_treated_as_utc(self):
        # `parsedate_to_datetime` returns a naive datetime for a date
        # without a timezone: the branch that fills UTC must run.
        assert _retry_after(
            _reponse({"Retry-After": "Wed, 21 Oct 2099 07:28:00"}),
        ) > 0

    def test_invalid_http_date_returns_none(self):
        # `parsedate_to_datetime` raises `TypeError`/`ValueError` on
        # complete garbage: the except branch returns None.
        assert _retry_after(_reponse({"Retry-After": "pas une date"})) is None


# --------------------------------------------------------------------------- #
# base.classify_error
# --------------------------------------------------------------------------- #


class TestClassifyError:
    def test_5xx_outside_list_is_transient(self):
        c = classify_error(None, _reponse({}, status=500))
        assert c.category == "transitoire"

    def test_generic_connection_error_is_transient(self):
        # ConnectionError without a "coupure" keyword: transient retry.
        c = classify_error(requests.exceptions.ConnectionError("timeout doux"), None)
        assert c.category == "transitoire"

    def test_connection_error_with_keyword_is_a_cut(self):
        c = classify_error(
            requests.exceptions.ConnectionError(
                "NameResolutionError: unreachable",
            ), None,
        )
        assert c.category == "coupure"

    def test_invalid_url_is_definitive(self):
        c = classify_error(requests.exceptions.InvalidURL("no scheme"), None)
        assert c.category == "definitif"

    def test_neither_response_nor_exception_is_transient(self):
        # Extreme fallback: nothing to classify. Kept as transient so
        # the engine at least retries once.
        assert classify_error(None, None) == ErrorClassification("transitoire", None)


# --------------------------------------------------------------------------- #
# Transport: cooperative stop and pause
# --------------------------------------------------------------------------- #


class TestTransport:
    def test_check_stop_raises_when_stop_signalled(self):
        arret = threading.Event()
        t = Transport(delay=0, arret=arret)
        arret.set()
        with pytest.raises(Interrupted):
            t.check_stop()

    def test_pause_sleeps_then_returns(self):
        # Real pause: 0.2 s so the loop enters the sleep branch at least
        # twice (`min(0.1, ...)` cap). The test tolerates timing jitter.
        t = Transport(delay=0)
        debut = time.monotonic()
        t.sleep(0.2)
        assert time.monotonic() - debut >= 0.15

    def test_interrupted_pause_raises_interrupted(self):
        arret = threading.Event()
        t = Transport(delay=0, arret=arret)
        arret.set()
        with pytest.raises(Interrupted):
            t.sleep(1.0)


# --------------------------------------------------------------------------- #
# Source: default implementations of resoudre_groupes / convertir_depuis
# --------------------------------------------------------------------------- #


class _SourceStub(Source):
    """Concrete `Source` that only implements `inventory` so the
    default no-op methods on the base class can be tested.
    """

    type = "stub"
    sort_modes = frozenset({"date"})

    def inventory(self, depuis, jusqua):
        return iter([])


def _stub():
    return _SourceStub(
        base="https://x.example", transport=Transport(delay=0), settings={},
    )


class TestSourceDefault:
    def test_resolve_groups_default_returns_known(self):
        assert _stub().resolve_groups({"a", "b"}, connus={"a": "titre-a"}) == {
            "a": "titre-a",
        }

    def test_resolve_groups_default_without_known_returns_empty(self):
        assert _stub().resolve_groups({"a"}) == {}

    def test_convert_from_default_is_identity(self):
        assert _stub().convert_from("2026-01-01T00:00:00") == "2026-01-01T00:00:00"
        assert _stub().convert_from(None) is None


# --------------------------------------------------------------------------- #
# djangoplicity._sanitized
# --------------------------------------------------------------------------- #


class TestClean:
    def test_none_yields_empty_string(self):
        assert _sanitized(None) == ""

    def test_bytes_utf8_decode(self):
        assert _sanitized("Nébuleuse".encode("utf-8")) == "Nébuleuse"

    def test_bytes_repr_inside_str_is_unwrapped(self):
        # The `d2d` feed sometimes serialises a `bytes` as `"b'...'"` in
        # a JSON string: the wrapper is stripped.
        assert _sanitized("b'Nebula'") == "Nebula"
        assert _sanitized('b"Nebula"') == "Nebula"

    def test_normal_string_passes_through(self):
        assert _sanitized("Nébuleuse") == "Nébuleuse"


# --------------------------------------------------------------------------- #
# djangoplicity.Djangoplicity: malformed Dimensions/FileSize + jusqua
# --------------------------------------------------------------------------- #


def _dj(settings=None):
    """Build a Djangoplicity source with a dummy transport."""
    return Djangoplicity(
        base="https://x.example",
        transport=Transport(delay=0),
        settings=settings or {"format_image": "Large"},
    )


def _entree(dimensions=None, filesize=None):
    """Build a d2d record shaped as `Djangoplicity._to_element` expects."""
    ressource = {"ResourceType": "Large", "URL": "https://x/img.jpg"}
    if dimensions is not None:
        ressource["Dimensions"] = dimensions
    if filesize is not None:
        ressource["FileSize"] = filesize
    return {
        "ID": "id42",
        "PublicationDate": "2026-09-21T13:00:00",
        "Assets": [{"Resources": [ressource]}],
    }


class TestDjangoplicityConversion:
    def test_non_numeric_dimensions_yield_width_none(self):
        el = _dj()._to_element(_entree(dimensions=["pas-un-int"]))
        assert el.largeur is None

    def test_non_numeric_filesize_yields_size_none(self):
        el = _dj()._to_element(_entree(filesize="not-a-number"))
        assert el.taille is None

    def test_inventory_bounded_by_until(self):
        # The `before` parameter is only added when `jusqua` is set;
        # cover that branch by capturing the first request's params.
        s = _dj()
        captured = {}

        def faux_get_json(url, params=None, essais=3, fin_si=frozenset()):
            captured["params"] = dict(params or {})
            return {"Count": 0, "Collections": []}, {}

        with patch.object(s.transport, "get_json", side_effect=faux_get_json):
            list(s.inventory("20260101000000", "20260630000000"))
        assert captured["params"].get("before") == "20260630000000"


# --------------------------------------------------------------------------- #
# wordpress._clean
# --------------------------------------------------------------------------- #


class TestSanitize:
    def test_html_entities_are_decoded(self):
        # `&`, `<`, `>` and `/` are stripped by the alphanumeric filter,
        # so `&amp;` disappears, and the tags collapse against their
        # neighbours: `<i>siecle</i>` → `isieclei`.
        assert _clean("Match &amp; the &lt;i&gt;siècle&lt;/i&gt;") == "match-the-isieclei"

    def test_accents_are_stripped(self):
        assert _clean("Nébuleuse") == "nebuleuse"

    def test_spaces_become_hyphens(self):
        assert _clean("Le grand voyage") == "le-grand-voyage"

    def test_empty_string_takes_default(self):
        assert _clean("") == "divers"
        assert _clean("   ") == "divers"
        assert _clean(None) == "divers"

    def test_custom_default(self):
        assert _clean("", defaut="sans-titre") == "sans-titre"

    def test_length_capped_at_80(self):
        assert len(_clean("x" * 200)) == 80


# --------------------------------------------------------------------------- #
# sources.sort_modes_for
# --------------------------------------------------------------------------- #


class TestSortModesFor:
    def test_known_source_returns_its_sort_modes(self):
        r = sort_modes_for("wordpress")
        # A known source declares at least the "date" mode.
        assert "date" in r

    def test_unknown_source_returns_empty_frozenset(self):
        assert sort_modes_for("flickr") == frozenset()

    def test_registry_contains_both_sources(self):
        assert "wordpress" in SOURCES
        assert "djangoplicity" in SOURCES
