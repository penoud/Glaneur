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
    def test_pas_de_reponse_renvoie_none(self):
        assert _retry_after(None) is None

    def test_header_absent_renvoie_none(self):
        assert _retry_after(_reponse({})) is None

    def test_valeur_vide_renvoie_none(self):
        assert _retry_after(_reponse({"Retry-After": "  "})) is None

    def test_entier_secondes(self):
        assert _retry_after(_reponse({"Retry-After": "42"})) == 42.0

    def test_http_date_dans_le_futur(self):
        # A valid HTTP-date far in the future returns a positive delta.
        assert _retry_after(
            _reponse({"Retry-After": "Wed, 21 Oct 2099 07:28:00 GMT"}),
        ) > 0

    def test_http_date_dans_le_passe_donne_zero(self):
        # A past date clamps to 0 (never negative).
        assert _retry_after(
            _reponse({"Retry-After": "Wed, 21 Oct 1999 07:28:00 GMT"}),
        ) == 0.0

    def test_http_date_naive_est_traitee_comme_utc(self):
        # `parsedate_to_datetime` returns a naive datetime for a date
        # without a timezone: the branch that fills UTC must run.
        assert _retry_after(
            _reponse({"Retry-After": "Wed, 21 Oct 2099 07:28:00"}),
        ) > 0

    def test_http_date_invalide_renvoie_none(self):
        # `parsedate_to_datetime` raises `TypeError`/`ValueError` on
        # complete garbage: the except branch returns None.
        assert _retry_after(_reponse({"Retry-After": "pas une date"})) is None


# --------------------------------------------------------------------------- #
# base.classify_error
# --------------------------------------------------------------------------- #


class TestClasserErreur:
    def test_5xx_hors_liste_est_transitoire(self):
        c = classify_error(None, _reponse({}, status=500))
        assert c.category == "transitoire"

    def test_connection_error_generique_est_transitoire(self):
        # ConnectionError without a "coupure" keyword: transient retry.
        c = classify_error(requests.exceptions.ConnectionError("timeout doux"), None)
        assert c.category == "transitoire"

    def test_connection_error_avec_mot_cle_est_coupure(self):
        c = classify_error(
            requests.exceptions.ConnectionError(
                "NameResolutionError: unreachable",
            ), None,
        )
        assert c.category == "coupure"

    def test_url_invalide_est_definitif(self):
        c = classify_error(requests.exceptions.InvalidURL("no scheme"), None)
        assert c.category == "definitif"

    def test_ni_reponse_ni_exception_est_transitoire(self):
        # Extreme fallback: nothing to classify. Kept as transient so
        # the engine at least retries once.
        assert classify_error(None, None) == ErrorClassification("transitoire", None)


# --------------------------------------------------------------------------- #
# Transport: cooperative stop and pause
# --------------------------------------------------------------------------- #


class TestTransport:
    def test_verifier_arret_leve_si_arret_signale(self):
        arret = threading.Event()
        t = Transport(delay=0, arret=arret)
        arret.set()
        with pytest.raises(Interrupted):
            t.check_stop()

    def test_pause_dort_puis_revient(self):
        # Real pause: 0.2 s so the loop enters the sleep branch at least
        # twice (`min(0.1, ...)` cap). The test tolerates timing jitter.
        t = Transport(delay=0)
        debut = time.monotonic()
        t.sleep(0.2)
        assert time.monotonic() - debut >= 0.15

    def test_pause_interrompue_leve_interrompu(self):
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


class TestSourceDefaut:
    def test_resoudre_groupes_defaut_renvoie_connus(self):
        assert _stub().resolve_groups({"a", "b"}, connus={"a": "titre-a"}) == {
            "a": "titre-a",
        }

    def test_resoudre_groupes_defaut_sans_connus_renvoie_vide(self):
        assert _stub().resolve_groups({"a"}) == {}

    def test_convertir_depuis_defaut_identite(self):
        assert _stub().convert_from("2026-01-01T00:00:00") == "2026-01-01T00:00:00"
        assert _stub().convert_from(None) is None


# --------------------------------------------------------------------------- #
# djangoplicity._sanitized
# --------------------------------------------------------------------------- #


class TestSain:
    def test_none_donne_chaine_vide(self):
        assert _sanitized(None) == ""

    def test_bytes_utf8_decode(self):
        assert _sanitized("Nébuleuse".encode("utf-8")) == "Nébuleuse"

    def test_bytes_repr_dans_str_est_deballe(self):
        # The `d2d` feed sometimes serialises a `bytes` as `"b'...'"` in
        # a JSON string: the wrapper is stripped.
        assert _sanitized("b'Nebula'") == "Nebula"
        assert _sanitized('b"Nebula"') == "Nebula"

    def test_chaine_normale_passe_telle_quelle(self):
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
    def test_dimensions_non_numeriques_donnent_largeur_none(self):
        el = _dj()._to_element(_entree(dimensions=["pas-un-int"]))
        assert el.largeur is None

    def test_filesize_non_numerique_donne_taille_none(self):
        el = _dj()._to_element(_entree(filesize="not-a-number"))
        assert el.taille is None

    def test_inventaire_borne_par_jusqua(self):
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


class TestNettoyer:
    def test_entities_html_sont_decodees(self):
        # `&`, `<`, `>` and `/` are stripped by the alphanumeric filter,
        # so `&amp;` disappears, and the tags collapse against their
        # neighbours: `<i>siecle</i>` → `isieclei`.
        assert _clean("Match &amp; the &lt;i&gt;siècle&lt;/i&gt;") == "match-the-isieclei"

    def test_accents_sont_supprimes(self):
        assert _clean("Nébuleuse") == "nebuleuse"

    def test_espaces_deviennent_tirets(self):
        assert _clean("Le grand voyage") == "le-grand-voyage"

    def test_chaine_vide_prend_le_defaut(self):
        assert _clean("") == "divers"
        assert _clean("   ") == "divers"
        assert _clean(None) == "divers"

    def test_defaut_personnalise(self):
        assert _clean("", defaut="sans-titre") == "sans-titre"

    def test_longueur_bornee_a_80(self):
        assert len(_clean("x" * 200)) == 80


# --------------------------------------------------------------------------- #
# sources.sort_modes_for
# --------------------------------------------------------------------------- #


class TestClassementsPour:
    def test_source_connue_renvoie_ses_classements(self):
        r = sort_modes_for("wordpress")
        # A known source declares at least the "date" mode.
        assert "date" in r

    def test_source_inconnue_renvoie_frozenset_vide(self):
        assert sort_modes_for("flickr") == frozenset()

    def test_registre_contient_les_deux_sources(self):
        assert "wordpress" in SOURCES
        assert "djangoplicity" in SOURCES
