"""Tests de l'adaptateur Djangoplicity : pagination sur `Next`, `after`
inclusif (l'élément frontière n'est pas retéléchargé une deuxième fois),
sélection du format avec repli sur Small, désencapsulation des textes
`"b'…'"` mal encodés côté serveur.

Aucun accès réseau : `Transport.get_json` est mocké.
"""

from __future__ import annotations

import threading
from unittest.mock import patch

from WpImageDownloader.engine import Moteur, Options, lire_manifeste
from WpImageDownloader.sources import Transport
from WpImageDownloader.sources.djangoplicity import Djangoplicity


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _source(*, format_image="Large", base="https://www.eso.org/public"):
    return Djangoplicity(
        base=base,
        transport=Transport(delai=0, arret=threading.Event()),
        reglages={"format_image": format_image},
    )


def _ressource(rtype, url, taille=1234, dims=(1600, 900)):
    return {
        "ResourceType": rtype,
        "URL": url,
        "FileSize": taille,
        "Dimensions": list(dims),
    }


def _entree(ident, pubdate="2026-06-15T12:00:00",
            ressources=None, credit="ESO/Team", rights="CC BY 4.0",
            checksum=None):
    if ressources is None:
        ressources = [
            _ressource("Original", f"https://cdn.eso.org/original/{ident}.tif",
                       taille=50_000_000, dims=(4096, 2160)),
            _ressource("Large", f"https://cdn.eso.org/large/{ident}.jpg",
                       taille=3_500_000, dims=(1600, 900)),
            _ressource("Small", f"https://cdn.eso.org/small/{ident}.jpg",
                       taille=200_000, dims=(1280.0, 720.0)),
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
    """Serveur `d2d/` factice : associe URL → réponse JSON."""

    def __init__(self, pages: dict[str, dict]):
        self.pages = pages
        self.appels: list[str] = []

    def get_json(self, url, params=None, essais=3, fin_si=frozenset()):
        self.appels.append(url)
        cle = url
        if url in self.pages:
            return self.pages[url], {}
        raise AssertionError(f"URL non attendue : {url}")


# --------------------------------------------------------------------------- #
# Contrat de base
# --------------------------------------------------------------------------- #

class TestBase:
    def test_type_et_classements(self):
        assert Djangoplicity.type == "djangoplicity"
        # doc §3 : « galerie » n'a pas d'équivalent naturel
        assert "galerie" not in Djangoplicity.classements
        assert {"date", "plat"} <= Djangoplicity.classements

    def test_endpoint_derive_de_la_base(self):
        s = _source(base="https://www.eso.org/public/")
        assert s.endpoint == "https://www.eso.org/public/images/d2d/"

    def test_convertir_depuis(self):
        s = _source()
        assert s.convertir_depuis("2026-06-15T12:00:00") == "20260615120000"
        # tolérance : AAAA-MM-JJ suffit, l'heure est complétée en zéros
        assert s.convertir_depuis("2026-06-15") == "20260615000000"
        assert s.convertir_depuis(None) is None


# --------------------------------------------------------------------------- #
# Transformation en Element
# --------------------------------------------------------------------------- #

class TestToElement:
    def test_format_par_defaut_large(self):
        s = _source()
        e = s._to_element(_entree("eso1907a"))
        assert e.ident == "eso1907a:Large"
        assert e.url == "https://cdn.eso.org/large/eso1907a.jpg"
        assert e.nom_fichier == "eso1907a.jpg"
        assert e.mois == "2026-06"
        assert e.taille == 3_500_000

    def test_repli_sur_small_si_large_absent(self):
        s = _source()
        entree = _entree("eso1907a", ressources=[
            _ressource("Original", "https://cdn.eso.org/original/eso1907a.tif"),
            _ressource("Small", "https://cdn.eso.org/small/eso1907a.jpg",
                       taille=200_000, dims=(1280.0, 720.0)),
        ])
        e = s._to_element(entree)
        # l'ident garde le format effectivement téléchargé
        assert e.ident == "eso1907a:Small"
        assert e.url == "https://cdn.eso.org/small/eso1907a.jpg"
        # `Dimensions` flottantes → int
        assert e.largeur == 1280

    def test_aucun_format_disponible_url_none(self):
        s = _source()
        entree = _entree("eso1907a", ressources=[
            _ressource("Thumbnail", "https://cdn.eso.org/thumb/eso1907a.jpg"),
            _ressource("Icon", "https://cdn.eso.org/icon/eso1907a.jpg"),
        ])
        e = s._to_element(entree)
        assert e.url is None
        # l'ident conserve le format demandé (pas le format effectif)
        assert e.ident.endswith(":Large")

    def test_original_choisi_si_configure(self):
        s = _source(format_image="Original")
        e = s._to_element(_entree("eso1907a"))
        assert e.ident == "eso1907a:Original"
        assert e.url.endswith(".tif")

    def test_credit_et_rights_dans_extra(self):
        s = _source()
        e = s._to_element(_entree("eso1907a", credit="ESO/T. Preibisch",
                                  rights="CC BY 4.0"))
        assert e.extra["credit"] == "ESO/T. Preibisch"
        assert e.extra["rights"] == "CC BY 4.0"

    def test_checksum_reporte_dans_extra_si_present(self):
        s = _source()
        entree = _entree("eso1907a", ressources=[
            _ressource("Large", "https://cdn.eso.org/large/eso1907a.jpg"),
        ])
        entree["Assets"][0]["Resources"][0]["Checksum"] = "a" * 64
        e = s._to_element(entree)
        assert e.extra["checksum"] == "a" * 64

    def test_dimensions_manquantes_largeur_none(self):
        s = _source()
        entree = _entree("eso1907a", ressources=[{
            "ResourceType": "Large",
            "URL": "https://cdn.eso.org/large/eso1907a.jpg",
            "FileSize": 1000,
            "Dimensions": [],
        }])
        e = s._to_element(entree)
        assert e.largeur is None

    def test_sanitizer_byte_repr(self):
        # Bug connu (issue djangoplicity #147) : Credit rendu sous la forme
        # `"b'…'"` au lieu d'une chaîne propre.
        s = _source()
        e = s._to_element(_entree("eso1907a", credit="b'ESO/T. Preibisch'"))
        assert e.extra["credit"] == "ESO/T. Preibisch"

    def test_sanitizer_sur_id(self):
        # même bug appliqué à l'ID : le nom doit sortir intact.
        s = _source()
        entree = _entree("eso1907a")
        entree["ID"] = "b'eso1907a'"
        e = s._to_element(entree)
        assert e.ident == "eso1907a:Large"


# --------------------------------------------------------------------------- #
# Inventaire (pagination sur Next)
# --------------------------------------------------------------------------- #

class TestInventaire:
    def test_pagination_suit_next(self):
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
            r = list(s.inventaire(None, None))
        assert [e.ident for e in r] == ["a:Large", "b:Large", "c:Large"]
        # bien deux requêtes, pas trois
        assert len(faux.appels) == 2

    def test_arret_sur_absence_de_next_meme_page_courte(self):
        # page renvoyant moins d'entrées que `count` mais pas de `Next` :
        # l'adaptateur doit s'arrêter (doc §7).
        s = _source(base="https://x.example")
        page1 = _reponse([_entree("a")], next_url=None, count=100)
        faux = FauxServeur({"https://x.example/images/d2d/": page1})
        with patch.object(s.transport, "get_json", side_effect=faux.get_json):
            r = list(s.inventaire(None, None))
        assert [e.ident for e in r] == ["a:Large"]

    def test_deduplication_par_id(self):
        # doublon inter-pages : ignoré silencieusement
        s = _source(base="https://x.example")
        page1 = _reponse([_entree("a"), _entree("b")],
                         next_url="https://x.example/images/d2d/?page=2")
        page2 = _reponse([_entree("b"), _entree("c")], next_url=None)
        faux = FauxServeur({
            "https://x.example/images/d2d/": page1,
            "https://x.example/images/d2d/?page=2": page2,
        })
        with patch.object(s.transport, "get_json", side_effect=faux.get_json):
            r = list(s.inventaire(None, None))
        assert sorted(e.ident for e in r) == ["a:Large", "b:Large", "c:Large"]

    def test_after_est_transmis_en_params(self):
        s = _source(base="https://x.example")
        capture = {}

        def faux_get_json(url, params=None, essais=3, fin_si=frozenset()):
            capture["params"] = params
            return {"Count": 0, "Collections": []}, {}

        with patch.object(s.transport, "get_json", side_effect=faux_get_json):
            list(s.inventaire("20260615120000", None))
        assert capture["params"]["after"] == "20260615120000"


# --------------------------------------------------------------------------- #
# `after` inclusif — l'élément frontière ne doit pas être compté 2× dans les
# téléchargements par le moteur ; le manifeste le repère en « déjà à jour ».
# --------------------------------------------------------------------------- #

class TestAfterInclusif:
    def test_element_frontiere_non_retelecharge(self, tmp_path):
        # Simule : un run précédent a téléchargé `a` (id "a:Large"). Un second
        # run avec `after` inclusif renvoie `a` en tête, puis un `b` neuf.
        # Le manifeste doit dire `a` → déjà à jour (1 deja_presentes), pas
        # une deuxième copie en telechargees.
        fichier_a = tmp_path / "a.jpg"
        fichier_a.write_bytes(b"contenu-a-attendu")
        from WpImageDownloader.engine import ecrire_manifeste
        ecrire_manifeste(tmp_path, {
            "a:Large": {"fichier": "a.jpg",
                        "taille": len(b"contenu-a-attendu")},
        })

        options = Options(
            dossier=tmp_path, site="https://x.example", delai=0,
            classement="date", type_source="djangoplicity",
            format_image="Large",
        )
        moteur = Moteur(options)

        # Fabrique les entrées telles que le fake serveur les fournirait.
        entree_a = _entree("a", ressources=[
            _ressource("Large", "https://cdn.eso.org/large/a.jpg",
                       taille=len(b"contenu-a-attendu")),
        ])
        entree_b = _entree("b", ressources=[
            _ressource("Large", "https://cdn.eso.org/large/b.jpg",
                       taille=42),
        ])
        page = _reponse([entree_a, entree_b], next_url=None)
        faux = FauxServeur({"https://x.example/images/d2d/": page})

        with patch.object(moteur.transport, "get_json",
                          side_effect=faux.get_json), \
             patch.object(moteur, "telecharger",
                          return_value=("ok", {"taille": 42, "etag": "",
                                               "modifie": "", "url": "u"})):
            res = moteur.executer()

        # `a` reconnu comme déjà présent ; seule `b` téléchargée.
        assert res.deja_presentes == 1
        assert res.telechargees == 1
        # manifeste étoffé, mais l'entrée `a` n'a pas été recréée en double
        m = lire_manifeste(tmp_path)
        assert "a:Large" in m and "b:Large" in m


# --------------------------------------------------------------------------- #
# Ressource manquante → ignorée par le moteur
# --------------------------------------------------------------------------- #

class TestRessourceManquante:
    def test_element_sans_url_est_ignoree(self, tmp_path):
        options = Options(
            dossier=tmp_path, site="https://x.example", delai=0,
            classement="date", type_source="djangoplicity",
            format_image="Large",
        )
        moteur = Moteur(options)

        # deux entrées : une bonne, une sans format utilisable (uniquement
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
             patch.object(moteur, "telecharger",
                          return_value=("ok", {"taille": 3_500_000, "etag": "",
                                               "modifie": "", "url": "u"})):
            res = moteur.executer()
        # bon : téléchargé ; mauvaise : ignorée
        assert res.telechargees == 1
        assert res.ignorees == 1
