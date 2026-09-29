"""Tests for the Djangoplicity adapter: `Next` pagination, `after`
inclusive (the boundary item is not re-downloaded a second time),
format selection with fallback to Small, and unwrapping of `"b'…'"`
strings mis-encoded server-side.

No network access: `Transport.get_json` is mocked.
"""

from __future__ import annotations

import threading
from unittest.mock import patch

from Glaneur.engine import Engine, Options, read_manifest
from Glaneur.sources import Transport
from Glaneur.sources.djangoplicity import Djangoplicity

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _source(*, format_image="Large", base="https://www.eso.org/public"):
    return Djangoplicity(
        base=base,
        transport=Transport(delay=0, stop_event=threading.Event()),
        settings={"format_image": format_image},
    )


def _ressource(rtype, url, size=1234, dims=(1600, 900)):
    return {
        "ResourceType": rtype,
        "URL": url,
        "FileSize": size,
        "Dimensions": list(dims),
    }


def _entree(ident, pubdate="2026-06-15T12:00:00",
            ressources=None, credit="ESO/Team", rights="CC BY 4.0",
            checksum=None):
    if ressources is None:
        ressources = [
            _ressource("Original", f"https://cdn.eso.org/original/{ident}.tif",
                       size=50_000_000, dims=(4096, 2160)),
            _ressource("Large", f"https://cdn.eso.org/large/{ident}.jpg",
                       size=3_500_000, dims=(1600, 900)),
            _ressource("Small", f"https://cdn.eso.org/small/{ident}.jpg",
                       size=200_000, dims=(1280.0, 720.0)),
        ]
    entree = {
        "ID": ident,
        "PublicationDate": pubdate,
        "Credit": credit,
        "Rights": rights,
        "Assets": [{"Type": "Image", "Resources": ressources}],
    }
    if checksum:
        entree["Checksum"] = checksum
    return entree


def _reponse(entrees, next_url=None, count=None):
    r = {"Count": count if count is not None else len(entrees),
         "Collections": entrees}
    if next_url:
        r["Next"] = next_url
    return r


class FauxServeur:
    """Fake `d2d/` server: maps URL → JSON response."""

    def __init__(self, pages: dict[str, dict]):
        self.pages = pages
        self.appels: list[str] = []

    def get_json(self, url, params=None, essais=3, fin_si=frozenset()):
        self.appels.append(url)
        cle = url
        if url in self.pages:
            return self.pages[url], {}
        raise AssertionError(f"URL non attendue : {url}")  # unexpected URL


# --------------------------------------------------------------------------- #
# Base contract
# --------------------------------------------------------------------------- #

class TestBase:
    def test_type_and_sort_modes(self):
        assert Djangoplicity.type == "djangoplicity"
        # doc §3: "galerie" has no natural equivalent
        assert "galerie" not in Djangoplicity.sort_modes
        assert {"date", "plat"} <= Djangoplicity.sort_modes

    def test_endpoint_derived_from_base(self):
        s = _source(base="https://www.eso.org/public/")
        assert s.endpoint == "https://www.eso.org/public/images/d2d/"

    def test_convert_from(self):
        s = _source()
        assert s.convert_from("2026-06-15T12:00:00") == "20260615120000"
        # tolerant: YYYY-MM-DD is enough, the time is zero-padded
        assert s.convert_from("2026-06-15") == "20260615000000"
        assert s.convert_from(None) is None


# --------------------------------------------------------------------------- #
# Transformation into Element
# --------------------------------------------------------------------------- #

class TestToElement:
    def test_default_format_is_large(self):
        s = _source()
        e = s._to_element(_entree("eso1907a"))
        assert e.ident == "eso1907a:Large"
        assert e.url == "https://cdn.eso.org/large/eso1907a.jpg"
        assert e.filename == "eso1907a.jpg"
        assert e.month == "2026-06"
        assert e.size == 3_500_000

    def test_falls_back_to_small_when_large_absent(self):
        s = _source()
        entree = _entree("eso1907a", ressources=[
            _ressource("Original", "https://cdn.eso.org/original/eso1907a.tif"),
            _ressource("Small", "https://cdn.eso.org/small/eso1907a.jpg",
                       size=200_000, dims=(1280.0, 720.0)),
        ])
        e = s._to_element(entree)
        # the ident keeps the format actually downloaded
        assert e.ident == "eso1907a:Small"
        assert e.url == "https://cdn.eso.org/small/eso1907a.jpg"
        # float `Dimensions` → int
        assert e.width == 1280

    def test_no_format_available_url_is_none(self):
        s = _source()
        entree = _entree("eso1907a", ressources=[
            _ressource("Thumbnail", "https://cdn.eso.org/thumb/eso1907a.jpg"),
            _ressource("Icon", "https://cdn.eso.org/icon/eso1907a.jpg"),
        ])
        e = s._to_element(entree)
        assert e.url is None
        # the ident keeps the requested format (not the effective one)
        assert e.ident.endswith(":Large")

    def test_original_chosen_when_configured(self):
        s = _source(format_image="Original")
        e = s._to_element(_entree("eso1907a"))
        assert e.ident == "eso1907a:Original"
        assert e.url.endswith(".tif")

    def test_credit_and_rights_in_extra(self):
        s = _source()
        e = s._to_element(_entree("eso1907a", credit="ESO/T. Preibisch",
                                  rights="CC BY 4.0"))
        assert e.extra["credit"] == "ESO/T. Preibisch"
        assert e.extra["rights"] == "CC BY 4.0"

    def test_checksum_carried_into_extra_when_present(self):
        s = _source()
        entree = _entree("eso1907a", ressources=[
            _ressource("Large", "https://cdn.eso.org/large/eso1907a.jpg"),
        ])
        entree["Assets"][0]["Resources"][0]["Checksum"] = "a" * 64
        e = s._to_element(entree)
        assert e.extra["checksum"] == "a" * 64

    def test_missing_dimensions_width_none(self):
        s = _source()
        entree = _entree("eso1907a", ressources=[{
            "ResourceType": "Large",
            "URL": "https://cdn.eso.org/large/eso1907a.jpg",
            "FileSize": 1000,
            "Dimensions": [],
        }])
        e = s._to_element(entree)
        assert e.width is None

    def test_sanitizer_byte_repr(self):
        # Known bug (djangoplicity issue #147): Credit rendered as
        # `"b'…'"` instead of a clean string.
        s = _source()
        e = s._to_element(_entree("eso1907a", credit="b'ESO/T. Preibisch'"))
        assert e.extra["credit"] == "ESO/T. Preibisch"

    def test_sanitizer_on_id(self):
        # same bug applied to the ID: the name must come out intact.
        s = _source()
        entree = _entree("eso1907a")
        entree["ID"] = "b'eso1907a'"
        e = s._to_element(entree)
        assert e.ident == "eso1907a:Large"


# --------------------------------------------------------------------------- #
# Inventory (pagination via Next)
# --------------------------------------------------------------------------- #

class TestInventory:
    def test_pagination_follows_next(self):
        s = _source(base="https://x.example")
        page1 = _reponse([_entree("a"), _entree("b")],
                         next_url="https://x.example/images/d2d/?page=2",
                         count=3)
        page2 = _reponse([_entree("c")], next_url=None, count=3)
        faux = FauxServeur({
            "https://x.example/images/d2d/": page1,
            "https://x.example/images/d2d/?page=2": page2,
        })
        with patch.object(s.transport, "get_json", side_effect=faux.get_json):
            r = list(s.inventory(None, None))
        assert [e.ident for e in r] == ["a:Large", "b:Large", "c:Large"]
        # exactly two requests, not three
        assert len(faux.appels) == 2

    def test_stop_on_missing_next_even_short_page(self):
        # page returning fewer entries than `count` but no `Next`:
        # the adapter must stop (doc §7).
        s = _source(base="https://x.example")
        page1 = _reponse([_entree("a")], next_url=None, count=100)
        faux = FauxServeur({"https://x.example/images/d2d/": page1})
        with patch.object(s.transport, "get_json", side_effect=faux.get_json):
            r = list(s.inventory(None, None))
        assert [e.ident for e in r] == ["a:Large"]

    def test_deduplication_by_id(self):
        # cross-page duplicate: silently ignored
        s = _source(base="https://x.example")
        page1 = _reponse([_entree("a"), _entree("b")],
                         next_url="https://x.example/images/d2d/?page=2")
        page2 = _reponse([_entree("b"), _entree("c")], next_url=None)
        faux = FauxServeur({
            "https://x.example/images/d2d/": page1,
            "https://x.example/images/d2d/?page=2": page2,
        })
        with patch.object(s.transport, "get_json", side_effect=faux.get_json):
            r = list(s.inventory(None, None))
        assert sorted(e.ident for e in r) == ["a:Large", "b:Large", "c:Large"]

    def test_after_is_passed_via_params(self):
        s = _source(base="https://x.example")
        capture = {}

        def faux_get_json(_url, params=None, essais=3, fin_si=frozenset()):
            capture["params"] = params
            return {"Count": 0, "Collections": []}, {}

        with patch.object(s.transport, "get_json", side_effect=faux_get_json):
            list(s.inventory("20260615120000", None))
        assert capture["params"]["after"] == "20260615120000"


# --------------------------------------------------------------------------- #
# inclusive `after` — the boundary element must not be counted twice among
# downloads by the engine; the manifest flags it as "already up to date".
# --------------------------------------------------------------------------- #

class TestAfterInclusive:
    def test_boundary_element_not_redownloaded(self, tmp_path):
        # Simulate: a previous run downloaded `a` (id "a:Large"). A second
        # run with inclusive `after` returns `a` first, then a new `b`.
        # The manifest must report `a` → already up to date (1 deja_presentes),
        # not a second copy in telechargees.
        fichier_a = tmp_path / "a.jpg"
        fichier_a.write_bytes(b"contenu-a-attendu")
        from Glaneur.engine import write_manifest
        write_manifest(tmp_path, {
            "a:Large": {"fichier": "a.jpg",
                        "taille": len(b"contenu-a-attendu")},
        })

        options = Options(
            target_dir=tmp_path, site="https://x.example", delay=0,
            sort_mode="date", source_type="djangoplicity",
            image_format="Large",
        )
        moteur = Engine(options)

        # Build the entries as the fake server would supply them.
        entree_a = _entree("a", ressources=[
            _ressource("Large", "https://cdn.eso.org/large/a.jpg",
                       size=len(b"contenu-a-attendu")),
        ])
        entree_b = _entree("b", ressources=[
            _ressource("Large", "https://cdn.eso.org/large/b.jpg",
                       size=42),
        ])
        page = _reponse([entree_a, entree_b], next_url=None)
        faux = FauxServeur({"https://x.example/images/d2d/": page})

        with patch.object(moteur.transport, "get_json",
                          side_effect=faux.get_json), \
             patch.object(moteur, "download",
                          return_value=("ok", {"taille": 42, "etag": "",
                                               "modifie": "", "url": "u"},
                                        None, None)):
            res = moteur.run()

        # `a` recognized as already present; only `b` downloaded.
        assert res.already_present == 1
        assert res.downloaded == 1
        # manifest extended, but entry `a` was not duplicated
        m = read_manifest(tmp_path)
        assert "a:Large" in m and "b:Large" in m


# --------------------------------------------------------------------------- #
# Missing resource → ignored by the engine
# --------------------------------------------------------------------------- #

class TestMissingResource:
    def test_element_without_url_is_ignored(self, tmp_path):
        options = Options(
            target_dir=tmp_path, site="https://x.example", delay=0,
            sort_mode="date", source_type="djangoplicity",
            image_format="Large",
        )
        moteur = Engine(options)

        # two entries: one good, one without a usable format (only
        # Icon / Thumbnail)
        bonne = _entree("bon")
        aucune = _entree("mauvaise", ressources=[
            _ressource("Thumbnail", "https://cdn.eso.org/thumb/mauvaise.jpg"),
            _ressource("Icon", "https://cdn.eso.org/icon/mauvaise.jpg"),
        ])
        page = _reponse([bonne, aucune], next_url=None)
        faux = FauxServeur({"https://x.example/images/d2d/": page})

        with patch.object(moteur.transport, "get_json",
                          side_effect=faux.get_json), \
             patch.object(moteur, "download",
                          return_value=("ok", {"taille": 3_500_000, "etag": "",
                                               "modifie": "", "url": "u"},
                                        None, None)):
            res = moteur.run()
        # good: downloaded; bad: ignored
        assert res.downloaded == 1
        assert res.skipped == 1
