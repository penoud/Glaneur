"""Tests de l'adaptateur WordPress : pagination `X-WP-TotalPages`, sortie
sur 400 (page au-delà de la dernière), tri des bases REST galerie-first,
et extraction du mois depuis `/uploads/AAAA/MM/`.

Aucun accès réseau : `Transport.get_json` est mocké.
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
    transport = Transport(delai=0, arret=threading.Event())
    return WordPress(
        base=kw.pop("base", "https://x.example"),
        transport=transport,
        reglages={},
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
    def test_type_et_classements(self):
        assert WordPress.type == "wordpress"
        assert WordPress.classements == frozenset({"galerie", "date", "plat"})

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
        assert e.mois == "2025-03"

    def test_mois_none_si_pas_de_pattern(self):
        s = _wp()
        e = s._to_element(_media(1, url="https://x/autre-chemin.jpg"))
        assert e.mois is None

    def test_groupe_pris_du_champ_post(self):
        s = _wp()
        e = s._to_element(_media(1, post=17))
        assert e.groupe == "17"

    def test_groupe_none_si_pas_de_post(self):
        s = _wp()
        e = s._to_element(_media(1, post=None))
        assert e.groupe is None

    def test_largeur_et_taille_lues(self):
        s = _wp()
        media = _media(1, width=1234)
        media["media_details"]["filesize"] = 4242
        e = s._to_element(media)
        assert e.largeur == 1234
        assert e.taille == 4242

    def test_nom_fichier_dernier_segment_de_url(self):
        s = _wp()
        e = s._to_element(_media(1, url="https://x/wp-content/uploads/2026/01/match.jpg"))
        assert e.nom_fichier == "match.jpg"


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
            r = list(s.inventaire(None, None))
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
            r = list(s.inventaire(None, None))
        assert sorted(e.ident for e in r) == ["1", "2", "3"]

    def test_arret_immediat_si_pas_de_pages_totales(self):
        # without pages_totales and an empty batch, the loop exits on the 1st page
        s = _wp()
        appels = []

        def faux_api(chemin, params=None):
            appels.append(params.get("page"))
            return [], {"X-WP-TotalPages": "0"}

        with patch.object(s, "_api", side_effect=faux_api):
            r = list(s.inventaire(None, None))
        assert r == []
        assert len(appels) == 1

    def test_stop_sur_deux_pages_vides_apres_contenu(self):
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
            r = list(s.inventaire(None, None))
        assert [e.ident for e in r] == ["1"]
        assert appels == [1, 2, 3]

    def test_stop_sur_400_via_lot_none_page1(self):
        # first page = None (400): immediate exit
        s = _wp()
        with patch.object(s, "_api",
                          return_value=(None, {"X-WP-TotalPages": "0"})):
            r = list(s.inventaire(None, None))
        assert r == []

    def test_borne_par_pages_totales(self):
        s = _wp()
        appels = []

        def faux_api(chemin, params=None):
            appels.append(params.get("page"))
            return [_media(params["page"])], {"X-WP-TotalPages": "3"}

        with patch.object(s, "_api", side_effect=faux_api):
            list(s.inventaire(None, None))
        assert appels == [1, 2, 3]   # does not go past the 3rd page

    def test_filtre_depuis_et_jusqua(self):
        s = _wp()
        capture = {}

        def faux_api(chemin, params=None):
            capture.update(params)
            return [], {"X-WP-TotalPages": "0"}

        with patch.object(s, "_api", side_effect=faux_api):
            list(s.inventaire("2026-01-01", "2026-12-31"))
        assert capture["after"].startswith("2026-01-01T")
        assert capture["before"].startswith("2026-12-31T")


# --------------------------------------------------------------------------- #
# `_bases_rest`: discovery of the content types to query
# --------------------------------------------------------------------------- #

class TestBasesRest:
    def test_replie_sur_defaut_si_api_ko(self):
        s = _wp()
        with patch.object(s, "_api", side_effect=RuntimeError("HS")):
            assert s._bases_rest() == ["posts", "pages"]

    def test_ecarte_types_techniques(self):
        s = _wp()
        types = {
            "post": {"rest_base": "posts"},
            "page": {"rest_base": "pages"},
            "galerie": {"rest_base": "galeries"},
            "attachment": {"rest_base": "media"},
            "wp_block": {"rest_base": "blocks"},
            "nav_menu_item": {"rest_base": "menu-items"},
        }
        with patch.object(s, "_api", return_value=(types, {})):
            bases = s._bases_rest()
        assert "media" not in bases
        assert "blocks" not in bases
        assert "menu-items" not in bases
        # galleries come first thanks to the sort ("galer")
        assert bases[0] == "galeries"


# --------------------------------------------------------------------------- #
# `resoudre_groupes`: parent lookup (WP returns integer IDs)
# --------------------------------------------------------------------------- #

class TestResoudreGroupes:
    def test_lookup_titre(self):
        s = _wp()

        def faux_api(chemin, params=None):
            if chemin == "types":
                return {"post": {"rest_base": "posts"}}, {}
            items = [{"id": 42, "slug": "match-du-siecle",
                      "title": {"rendered": "Match du siècle"}}]
            return items, {}

        with patch.object(s, "_api", side_effect=faux_api):
            titres = s.resoudre_groupes({"42"})
        # result keys are strings to stay aligned with the manifest keys
        assert titres == {"42": "match-du-siecle"}

    def test_non_trouve_journalise(self):
        journal = []
        s = _wp(journal=journal.append)

        def faux_api(chemin, params=None):
            if chemin == "types":
                return {"post": {"rest_base": "posts"}}, {}
            return [], {}   # no match

        with patch.object(s, "_api", side_effect=faux_api):
            titres = s.resoudre_groupes({"99"})
        assert titres == {}
        # a message reports unidentified galleries
        assert any("non identifi" in m for m in journal)

    def test_set_vide(self):
        s = _wp()
        assert s.resoudre_groupes(set()) == {}

    def test_arret_boucle_quand_restants_vides(self):
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
            titres = s.resoudre_groupes({"42"})
        assert titres == {"42": "match"}
        assert "posts" not in appels

    def test_runtime_error_sur_un_base_continue(self):
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
            titres = s.resoudre_groupes({"42"})
        assert titres == {"42": "trouve"}

    def test_court_circuite_sur_cache_connus(self):
        s = _wp()
        with patch.object(s, "_api") as api:
            r = s.resoudre_groupes({"42"}, connus={"42": "deja-connu"})
        assert r == {"42": "deja-connu"}
        api.assert_not_called()


# --------------------------------------------------------------------------- #
# Transport.get_json: retries, end-of-pagination code, RuntimeError
# --------------------------------------------------------------------------- #

class TestTransportGetJson:
    def test_reponse_dans_fin_si_renvoie_none(self):
        t = Transport(delai=0)
        t.session = MagicMock()
        rep = MagicMock(status_code=400, headers={"h": "1"})
        t.session.get.return_value = rep
        payload, headers = t.get_json("https://x/api", fin_si=frozenset({400}))
        assert payload is None
        assert headers.get("h") == "1"

    def test_reponse_normale(self):
        t = Transport(delai=0)
        rep = MagicMock(status_code=200, headers={"h": "1"})
        rep.json.return_value = [{"id": 1}]
        rep.raise_for_status = MagicMock()
        t.session = MagicMock()
        t.session.get.return_value = rep
        payload, _ = t.get_json("https://x/api")
        assert payload == [{"id": 1}]

    def test_rejeu_puis_succes(self):
        t = Transport(delai=0)
        t.session = MagicMock()
        bon = MagicMock(status_code=200, headers={})
        bon.json.return_value = {"ok": True}
        bon.raise_for_status = MagicMock()
        t.session.get.side_effect = [requests.ConnectionError("boum"), bon]
        with patch.object(t, "pause"):   # avoids the 2 real seconds of pause
            payload, _ = t.get_json("https://x/api")
        assert payload == {"ok": True}
        assert t.session.get.call_count == 2

    def test_echec_repete_leve_runtime(self):
        t = Transport(delai=0)
        t.session = MagicMock()
        t.session.get.side_effect = requests.ConnectionError("HS")
        with patch.object(t, "pause"), pytest.raises(RuntimeError):
            t.get_json("https://x/api")

    def test_wordpress_passe_fin_si_400(self):
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
