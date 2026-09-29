"""Tests for the WordPress adapter: `X-WP-TotalPages` pagination, exit on
400 (page past the last one), gallery-first ordering of the REST bases,
and month extraction from `/uploads/YYYY/MM/`.

No network access: `Transport.get_json` is mocked.
"""

from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

import pytest
import requests

from Glaneur.sources import Transport
from Glaneur.sources.wordpress import WordPress

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _wp(**kw):
    """Builds a WordPress source with a zero-delay transport."""
    transport = Transport(delay=0, stop_event=threading.Event())
    return WordPress(
        base=kw.pop("base", "https://x.example"),
        transport=transport,
        settings={},
        journal=kw.pop("journal", None),
        progression=kw.pop("progression", None),
    )


def _media(id_, url="https://x/wp-content/uploads/2026/01/img.jpg",
           width=1600, post=None):
    return {
        "id": id_,
        "source_url": url,
        "media_details": {"width": width},
        "post": post,
        "date": "2026-01-01T00:00:00",
    }


# --------------------------------------------------------------------------- #
# Construction and normalization
# --------------------------------------------------------------------------- #

class TestBase:
    def test_type_and_sort_modes(self):
        assert WordPress.type == "wordpress"
        assert WordPress.sort_modes == frozenset({"gallery", "date", "flat"})

    def test_base_normalise_slash_final(self):
        s = _wp(base="https://example.test/")
        assert s.base == "https://example.test"
        assert s.api == "https://example.test/wp-json/wp/v2"


# --------------------------------------------------------------------------- #
# Transformation into Element
# --------------------------------------------------------------------------- #

class TestToElement:
    def test_ident_str_id(self):
        s = _wp()
        e = s._to_element(_media(42))
        assert e.ident == "42"
        assert e.url.startswith("https://")

    def test_mois_extrait_du_chemin_uploads(self):
        s = _wp()
        e = s._to_element(_media(1, url="https://x/wp-content/uploads/2025/03/img.jpg"))
        assert e.month == "2025-03"

    def test_month_none_without_pattern(self):
        s = _wp()
        e = s._to_element(_media(1, url="https://x/autre-chemin.jpg"))
        assert e.month is None

    def test_groupe_pris_du_champ_post(self):
        s = _wp()
        e = s._to_element(_media(1, post=17))
        assert e.group == "17"

    def test_group_none_without_post(self):
        s = _wp()
        e = s._to_element(_media(1, post=None))
        assert e.group is None

    def test_largeur_et_taille_lues(self):
        s = _wp()
        media = _media(1, width=1234)
        media["media_details"]["filesize"] = 4242
        e = s._to_element(media)
        assert e.width == 1234
        assert e.size == 4242

    def test_filename_is_last_url_segment(self):
        s = _wp()
        e = s._to_element(_media(1, url="https://x/wp-content/uploads/2026/01/match.jpg"))
        assert e.filename == "match.jpg"


# --------------------------------------------------------------------------- #
# Inventory (pagination)
# --------------------------------------------------------------------------- #

class TestInventaire:
    def test_pagination(self):
        s = _wp()
        page1 = [_media(1), _media(2)]
        page2 = [_media(3)]
        appels = []

        def faux_api(chemin, params=None):
            appels.append(params.get("page"))
            headers = {"X-WP-Total": "3", "X-WP-TotalPages": "2"}
            if params["page"] == 1:
                return page1, headers
            return page2, headers

        with patch.object(s, "_api", side_effect=faux_api):
            r = list(s.inventory(None, None))
        assert [e.ident for e in r] == ["1", "2", "3"]
        assert appels == [1, 2]

    def test_deduplication(self):
        s = _wp()

        def faux_api(chemin, params=None):
            headers = {"X-WP-Total": "3", "X-WP-TotalPages": "2"}
            if params["page"] == 1:
                return [_media(1), _media(2)], headers
            # page 2 returns id 2 as a duplicate + a new 3
            return [_media(2), _media(3)], headers

        with patch.object(s, "_api", side_effect=faux_api):
            r = list(s.inventory(None, None))
        assert sorted(e.ident for e in r) == ["1", "2", "3"]

    def test_immediate_stop_when_no_total_pages(self):
        # without pages_totales and an empty batch, the loop exits on the 1st page
        s = _wp()
        appels = []

        def faux_api(chemin, params=None):
            appels.append(params.get("page"))
            return [], {"X-WP-TotalPages": "0"}

        with patch.object(s, "_api", side_effect=faux_api):
            r = list(s.inventory(None, None))
        assert r == []
        assert len(appels) == 1

    def test_stop_on_two_empty_pages_after_content(self):
        # once pages_totales is known, two consecutive empty pages are required
        s = _wp()
        appels = []

        def faux_api(chemin, params=None):
            appels.append(params.get("page"))
            headers = {"X-WP-Total": "1", "X-WP-TotalPages": "9"}
            if params["page"] == 1:
                return [_media(1)], headers
            return [], headers   # pages 2 and 3 empty

        with patch.object(s, "_api", side_effect=faux_api):
            r = list(s.inventory(None, None))
        assert [e.ident for e in r] == ["1"]
        assert appels == [1, 2, 3]

    def test_stop_on_400_via_none_batch_page1(self):
        # first page = None (400): immediate exit
        s = _wp()
        with patch.object(s, "_api",
                          return_value=(None, {"X-WP-TotalPages": "0"})):
            r = list(s.inventory(None, None))
        assert r == []

    def test_bounded_by_total_pages(self):
        s = _wp()
        appels = []

        def faux_api(chemin, params=None):
            appels.append(params.get("page"))
            return [_media(params["page"])], {"X-WP-TotalPages": "3"}

        with patch.object(s, "_api", side_effect=faux_api):
            list(s.inventory(None, None))
        assert appels == [1, 2, 3]   # does not go past the 3rd page

    def test_filters_since_and_until(self):
        s = _wp()
        capture = {}

        def faux_api(chemin, params=None):
            capture.update(params)
            return [], {"X-WP-TotalPages": "0"}

        with patch.object(s, "_api", side_effect=faux_api):
            list(s.inventory("2026-01-01", "2026-12-31"))
        assert capture["after"].startswith("2026-01-01T")
        assert capture["before"].startswith("2026-12-31T")


# --------------------------------------------------------------------------- #
# `_rest_bases`: discovery of the content types to query
# --------------------------------------------------------------------------- #

class TestBasesRest:
    def test_falls_back_to_default_when_api_fails(self):
        s = _wp()
        with patch.object(s, "_api", side_effect=RuntimeError("HS")):
            assert s._rest_bases() == ["posts", "pages"]

    def test_excludes_technical_types(self):
        s = _wp()
        types = {
            "post": {"rest_base": "posts"},
            "page": {"rest_base": "pages"},
            "gallery": {"rest_base": "galeries"},
            "attachment": {"rest_base": "media"},
            "wp_block": {"rest_base": "blocks"},
            "nav_menu_item": {"rest_base": "menu-items"},
        }
        with patch.object(s, "_api", return_value=(types, {})):
            bases = s._rest_bases()
        assert "media" not in bases
        assert "blocks" not in bases
        assert "menu-items" not in bases
        # galleries come first thanks to the sort ("galer")
        assert bases[0] == "galeries"


# --------------------------------------------------------------------------- #
# `resoudre_groupes`: parent lookup (WP returns integer IDs)
# --------------------------------------------------------------------------- #

class TestResolveGroups:
    def test_lookup_titre(self):
        s = _wp()

        def faux_api(chemin, params=None):
            if chemin == "types":
                return {"post": {"rest_base": "posts"}}, {}
            items = [{"id": 42, "slug": "match-du-siecle",
                      "title": {"rendered": "Match du siècle"}}]
            return items, {}

        with patch.object(s, "_api", side_effect=faux_api):
            titres = s.resolve_groups({"42"})
        # result keys are strings to stay aligned with the manifest keys
        assert titres == {"42": "match-du-siecle"}

    def test_not_found_journals(self):
        journal = []
        s = _wp(journal=journal.append)

        def faux_api(chemin, params=None):
            if chemin == "types":
                return {"post": {"rest_base": "posts"}}, {}
            return [], {}   # no match

        with patch.object(s, "_api", side_effect=faux_api):
            titres = s.resolve_groups({"99"})
        assert titres == {}
        # a message reports unidentified galleries
        assert any("not identified" in m for m in journal)

    def test_empty_set(self):
        s = _wp()
        assert s.resolve_groups(set()) == {}

    def test_loop_stops_when_remaining_empty(self):
        # the first base finds everything: the second is never queried
        s = _wp()
        appels = []

        def faux_api(chemin, params=None):
            appels.append(chemin)
            if chemin == "types":
                return {
                    "a": {"rest_base": "galeries"},
                    "b": {"rest_base": "posts"},
                }, {}
            if chemin == "galeries":
                return [{"id": 42, "slug": "match"}], {}
            return [], {}

        with patch.object(s, "_api", side_effect=faux_api):
            titres = s.resolve_groups({"42"})
        assert titres == {"42": "match"}
        assert "posts" not in appels

    def test_runtime_error_on_one_base_continues(self):
        # RuntimeError on a base → skip and try the next one
        s = _wp()

        def faux_api(chemin, params=None):
            if chemin == "types":
                return {
                    "a": {"rest_base": "galeries"},
                    "b": {"rest_base": "posts"},
                }, {}
            if chemin == "galeries":
                raise RuntimeError("HS")
            return [{"id": 42, "slug": "trouve"}], {}

        with patch.object(s, "_api", side_effect=faux_api):
            titres = s.resolve_groups({"42"})
        assert titres == {"42": "trouve"}

    def test_short_circuits_on_cached_known(self):
        s = _wp()
        with patch.object(s, "_api") as api:
            r = s.resolve_groups({"42"}, connus={"42": "deja-connu"})
        assert r == {"42": "deja-connu"}
        api.assert_not_called()


# --------------------------------------------------------------------------- #
# Transport.get_json: retries, end-of-pagination code, RuntimeError
# --------------------------------------------------------------------------- #

class TestTransportGetJson:
    def test_response_in_fin_si_returns_none(self):
        t = Transport(delay=0)
        t.session = MagicMock()
        rep = MagicMock(status_code=400, headers={"h": "1"})
        t.session.get.return_value = rep
        payload, headers = t.get_json("https://x/api", fin_si=frozenset({400}))
        assert payload is None
        assert headers.get("h") == "1"

    def test_reponse_normale(self):
        t = Transport(delay=0)
        rep = MagicMock(status_code=200, headers={"h": "1"})
        rep.json.return_value = [{"id": 1}]
        rep.raise_for_status = MagicMock()
        t.session = MagicMock()
        t.session.get.return_value = rep
        payload, _ = t.get_json("https://x/api")
        assert payload == [{"id": 1}]

    def test_retry_then_success(self):
        t = Transport(delay=0)
        t.session = MagicMock()
        bon = MagicMock(status_code=200, headers={})
        bon.json.return_value = {"ok": True}
        bon.raise_for_status = MagicMock()
        t.session.get.side_effect = [requests.ConnectionError("boum"), bon]
        with patch.object(t, "sleep"):   # avoids the 2 real seconds of pause
            payload, _ = t.get_json("https://x/api")
        assert payload == {"ok": True}
        assert t.session.get.call_count == 2

    def test_repeated_failure_raises_runtime(self):
        t = Transport(delay=0)
        t.session = MagicMock()
        t.session.get.side_effect = requests.ConnectionError("HS")
        with patch.object(t, "sleep"), pytest.raises(RuntimeError):
            t.get_json("https://x/api")

    def test_wordpress_passes_fin_si_400(self):
        # not an isolated case, but confirms the contract: it is the
        # WordPress adapter that carries the rule "400 = end of
        # pagination" via `fin_si={400}` — the engine does not force it
        # on the other sources.
        s = _wp()
        capture = {}

        def faux_get_json(url, params=None, essais=3, fin_si=frozenset()):
            capture["fin_si"] = fin_si
            return None, {}

        with patch.object(s.transport, "get_json", side_effect=faux_get_json):
            s._api("media", {"page": 1})
        assert 400 in capture["fin_si"]
