"""Tests for the engine: utilities, manifest, Engine.run and delete_image.

No network access: `Engine.download` and the source adapter are mocked
via `unittest.mock`. The tests create their own temporary directory with
`tmp_path` and do not need the Windows COM interfaces.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
import requests

from Glaneur.engine import (
    Engine,
    EngineEvent,
    Interrupted,
    Options,
    cache_path,
    clean,
    delete_image,
    format_bytes,
    list_deleted,
    manifest_path,
    read_cache,
    read_manifest,
    restore,
    write_cache,
    write_manifest,
)
from Glaneur.sources import Element
from Glaneur.sources.base import ErrorClassification

# --------------------------------------------------------------------------- #
# Free-standing utilities
# --------------------------------------------------------------------------- #

class TestNettoyer:
    def test_titre_simple(self):
        assert clean("Match WordPress") == "match-wordpress"

    def test_accents_supprimes(self):
        # unidecode on NFKD: accents disappear
        assert clean("Été à Genève") == "ete-a-geneve"

    def test_html_entities(self):
        assert clean("WordPress &amp; Bâle") == "wordpress-bale"

    def test_caracteres_dangereux(self):
        # Windows rejects < > : " / \ | ? *
        r = clean('a<b>c:d"e/f\\g|h?i*j')
        for interdit in '<>:"/\\|?*':
            assert interdit not in r

    def test_espaces_multiples(self):
        assert clean("  a   b\tc\nd  ") == "a-b-c-d"

    def test_defaut_sur_vide(self):
        assert clean("") == "divers"
        assert clean("   ") == "divers"
        assert clean(None) == "divers"

    def test_defaut_personnalise(self):
        assert clean("", defaut="nada") == "nada"

    def test_troncature_a_80(self):
        r = clean("a" * 200)
        assert len(r) == 80

    def test_pas_de_point_final(self):
        # Windows rejects names ending with a dot
        assert not clean("Titre.").endswith(".")
        assert not clean("Titre...").endswith(".")


class TestFormatOctets:
    def test_octets(self):
        assert format_bytes(0) == "0 o"
        assert format_bytes(512) == "512 o"

    def test_kilo(self):
        assert format_bytes(1024) == "1.0 Ko"
        assert format_bytes(1536) == "1.5 Ko"

    def test_mega(self):
        assert format_bytes(1024 * 1024) == "1.0 Mo"

    def test_giga(self):
        assert format_bytes(1024 ** 3) == "1.0 Go"

    def test_au_dela_du_giga(self):
        # the loop caps at "Go", TB stays expressed in GB
        assert format_bytes(1024 ** 4).endswith(" Go")


# --------------------------------------------------------------------------- #
# Manifest — low-level I/O
# --------------------------------------------------------------------------- #

class TestManifesteIO:
    def test_chemin(self, tmp_path):
        assert manifest_path(tmp_path) == tmp_path / ".etat.json"

    def test_lire_absent(self, tmp_path):
        assert read_manifest(tmp_path) == {}

    def test_lire_json_invalide(self, tmp_path):
        manifest_path(tmp_path).write_text("{ceci n'est pas du json")
        assert read_manifest(tmp_path) == {}

    def test_lire_json_valide(self, tmp_path):
        manifest_path(tmp_path).write_text(
            json.dumps({"1": {"fichier": "a.jpg"}}), encoding="utf-8")
        assert read_manifest(tmp_path) == {"1": {"fichier": "a.jpg"}}

    def test_ecrire_puis_relire(self, tmp_path):
        m = {"7": {"fichier": "x/y.jpg", "taille": 42}}
        write_manifest(tmp_path, m)
        assert read_manifest(tmp_path) == m

    def test_ecriture_atomique(self, tmp_path):
        # after write, no .tmp file must remain
        write_manifest(tmp_path, {"1": {}})
        assert not (tmp_path / ".etat.json.tmp").exists()
        assert (tmp_path / ".etat.json").exists()

    def test_ecriture_cree_dossier(self, tmp_path):
        sous = tmp_path / "nouveau"
        write_manifest(sous, {"1": {"fichier": "a.jpg"}})
        assert (sous / ".etat.json").exists()

    def test_utf8_preserve(self, tmp_path):
        m = {"1": {"fichier": "été/genève.jpg"}}
        write_manifest(tmp_path, m)
        assert read_manifest(tmp_path) == m


# --------------------------------------------------------------------------- #
# list_deleted, restore
# --------------------------------------------------------------------------- #

class TestListerSupprimees:
    def test_dossier_vide(self, tmp_path):
        assert list_deleted(tmp_path) == []

    def test_filtre_les_supprimees(self, tmp_path):
        write_manifest(tmp_path, {
            "1": {"fichier": "a.jpg"},
            "2": {"fichier": "b.jpg", "supprime": "2026-01-02T10:00:00"},
            "3": {"fichier": "c.jpg", "supprime": "2026-01-01T10:00:00"},
        })
        e = list_deleted(tmp_path)
        assert len(e) == 2
        # sort by timestamp: oldest first
        assert e[0]["id"] == "3"
        assert e[1]["id"] == "2"

    def test_id_transporte(self, tmp_path):
        write_manifest(tmp_path, {
            "42": {"fichier": "x.jpg", "supprime": "2026-01-01"},
        })
        e = list_deleted(tmp_path)
        assert e[0]["id"] == "42"
        assert e[0]["fichier"] == "x.jpg"


class TestRestaurer:
    def test_retire_supprime_pose_restaure(self, tmp_path):
        write_manifest(tmp_path, {
            "1": {"fichier": "a.jpg", "supprime": "2026-01-01"},
        })
        assert restore(tmp_path, ["1"]) == 1
        entree = read_manifest(tmp_path)["1"]
        assert "supprime" not in entree
        assert entree["restaure"] is True

    def test_id_inconnu_ignore(self, tmp_path):
        write_manifest(tmp_path, {"1": {"fichier": "a.jpg"}})
        assert restore(tmp_path, ["999"]) == 0

    def test_entree_sans_supprime_ignoree(self, tmp_path):
        write_manifest(tmp_path, {"1": {"fichier": "a.jpg"}})
        assert restore(tmp_path, ["1"]) == 0

    def test_plusieurs_ids(self, tmp_path):
        write_manifest(tmp_path, {
            "1": {"fichier": "a.jpg", "supprime": "2026-01-01"},
            "2": {"fichier": "b.jpg", "supprime": "2026-01-02"},
            "3": {"fichier": "c.jpg"},
        })
        assert restore(tmp_path, ["1", "2", "3"]) == 2

    def test_id_entier_normalise(self, tmp_path):
        write_manifest(tmp_path, {
            "42": {"fichier": "a.jpg", "supprime": "2026-01-01"},
        })
        # restore accepts ints, must str() internally
        assert restore(tmp_path, [42]) == 1


# --------------------------------------------------------------------------- #
# delete_image
# --------------------------------------------------------------------------- #

class TestSupprimerImage:
    def test_suppression_normale(self, tmp_path):
        (tmp_path / "galerie-a").mkdir()
        fichier = tmp_path / "galerie-a" / "match.jpg"
        fichier.write_bytes(b"x" * 42)
        autre = tmp_path / "galerie-a" / "podium.jpg"
        autre.write_bytes(b"y" * 10)
        write_manifest(tmp_path, {
            "111": {"fichier": "galerie-a/match.jpg", "taille": 42, "etag": "abc"},
            "222": {"fichier": "galerie-a/podium.jpg", "taille": 10, "etag": "def"},
        })

        assert delete_image(tmp_path, fichier) is True
        assert not fichier.exists()
        m = read_manifest(tmp_path)
        assert "supprime" in m["111"]
        assert "supprime" not in m["222"]
        assert m["222"]["etag"] == "def"

    def test_restaure_retire(self, tmp_path):
        fichier = tmp_path / "image.jpg"
        fichier.write_bytes(b"y")
        write_manifest(tmp_path, {
            "1": {"fichier": "image.jpg", "taille": 1, "restaure": True},
        })
        assert delete_image(tmp_path, fichier) is True
        entree = read_manifest(tmp_path)["1"]
        assert "restaure" not in entree
        assert "supprime" in entree

    def test_hors_dossier(self, tmp_path):
        interne = tmp_path / "interne"
        externe = tmp_path / "externe"
        interne.mkdir()
        externe.mkdir()
        intrus = externe / "photo.jpg"
        intrus.write_bytes(b"z")
        write_manifest(interne, {"1": {"fichier": "photo.jpg", "taille": 1}})
        assert delete_image(interne, intrus) is False
        assert intrus.exists()
        assert "supprime" not in read_manifest(interne)["1"]

    def test_dossier_voisin_meme_prefixe(self, tmp_path):
        """`commonpath` avoids the trap of a naive `startswith`."""
        dossier = tmp_path / "photos"
        voisin = tmp_path / "photos-archives"
        dossier.mkdir()
        voisin.mkdir()
        intrus = voisin / "x.jpg"
        intrus.write_bytes(b"z")
        assert delete_image(dossier, intrus) is False
        assert intrus.exists()

    def test_antislash_manifeste(self, tmp_path):
        (tmp_path / "galerie-b").mkdir()
        fichier = tmp_path / "galerie-b" / "match.jpg"
        fichier.write_bytes(b"y")
        write_manifest(tmp_path, {"77": {"fichier": "galerie-b\\match.jpg"}})
        assert delete_image(tmp_path, fichier) is True
        assert "supprime" in read_manifest(tmp_path)["77"]

    def test_fichier_deja_absent(self, tmp_path):
        fantome = tmp_path / "disparu.jpg"
        write_manifest(tmp_path, {"9": {"fichier": "disparu.jpg", "taille": 5}})
        assert delete_image(tmp_path, fantome) is True
        assert "supprime" in read_manifest(tmp_path)["9"]

    def test_fichier_pas_dans_manifeste(self, tmp_path):
        # valid file in the directory but unknown to the manifest: deletion
        # succeeds, nothing to mark
        fichier = tmp_path / "orphelin.jpg"
        fichier.write_bytes(b"o")
        write_manifest(tmp_path, {"1": {"fichier": "autre.jpg"}})
        assert delete_image(tmp_path, fichier) is True
        assert not fichier.exists()
        assert "supprime" not in read_manifest(tmp_path)["1"]

    def test_fichier_egale_dossier_refuse(self, tmp_path):
        # deleting the directory itself must absolutely not be accepted
        assert delete_image(tmp_path, tmp_path) is False

    def test_realpath_qui_leve_renvoie_false(self, tmp_path, monkeypatch):
        # OSError on realpath (ghost path on Windows e.g.) → False
        def boum(*_a, **_kw):
            raise OSError("no such")
        monkeypatch.setattr("os.path.realpath", boum)
        assert delete_image(tmp_path, tmp_path / "x.jpg") is False

    def test_commonpath_valueerror_renvoie_false(self, tmp_path, monkeypatch):
        # ValueError = two different drives on Windows
        def boum(_paths):
            raise ValueError("mixed drives")
        monkeypatch.setattr("os.path.commonpath", boum)
        assert delete_image(tmp_path, tmp_path / "x.jpg") is False

    def test_unlink_oserror_renvoie_false(self, tmp_path):
        # PermissionError inherits from OSError: the file stays, we return False
        fichier = tmp_path / "verrouille.jpg"
        fichier.write_bytes(b"y")
        write_manifest(tmp_path, {"1": {"fichier": "verrouille.jpg"}})
        with patch("pathlib.Path.unlink",
                   side_effect=PermissionError("verrouille")):
            assert delete_image(tmp_path, fichier) is False
        # the mark was not set since the deletion failed
        assert "supprime" not in read_manifest(tmp_path)["1"]

    def test_entree_manifeste_sans_fichier_ignoree(self, tmp_path):
        # an entry without a 'fichier' field must not crash the lookup
        fichier = tmp_path / "cible.jpg"
        fichier.write_bytes(b"y")
        write_manifest(tmp_path, {
            "1": {"taille": 42},   # no file
            "2": {"fichier": "cible.jpg"},
        })
        assert delete_image(tmp_path, fichier) is True
        assert "supprime" in read_manifest(tmp_path)["2"]


# --------------------------------------------------------------------------- #
# Engine: utility methods (no network I/O)
# --------------------------------------------------------------------------- #

def _moteur(tmp_path, **kw):
    """Builds a Engine with a default Options, overridable.

    The engine builds a `wordpress` adapter by default; tests replace it
    with a fake as needed, or patch `moteur.source.inventory`
    / `moteur.source.resolve_groups`.
    """
    options = Options(target_dir=tmp_path, delay=0, **kw)
    return Engine(options)


def _element(ident, url="https://x/img.jpg", *, largeur=1600,
             groupe=None, mois="2026-01", date="2026-01-01T00:00:00",
             taille=None, nom_fichier=None, extra=None):
    """Builds an Element for orchestration tests.

    Defaults chosen to represent the average WordPress case; Djangoplicity
    tests have their own helper.
    """
    return Element(
        ident=str(ident),
        url=url,
        nom_fichier=nom_fichier if nom_fichier is not None
        else (url.rsplit("/", 1)[-1] if url else ""),
        date=date,
        mois=mois,
        largeur=largeur,
        taille=taille,
        groupe=str(groupe) if groupe is not None else None,
        extra=extra or {},
    )


class TestFichierComplet:
    def test_fichier_absent(self, tmp_path):
        assert Engine.file_complete(tmp_path / "absent.jpg", None, None) is False

    def test_taille_nulle(self, tmp_path):
        f = tmp_path / "vide.jpg"
        f.write_bytes(b"")
        assert Engine.file_complete(f, None, None) is False

    def test_taille_correcte_via_etat(self, tmp_path):
        f = tmp_path / "ok.jpg"
        f.write_bytes(b"abcde")
        assert Engine.file_complete(f, {"taille": 5}, None) is True

    def test_taille_erronee(self, tmp_path):
        f = tmp_path / "trop.jpg"
        f.write_bytes(b"abcde")
        assert Engine.file_complete(f, {"taille": 999}, None) is False

    def test_repli_sur_taille_api(self, tmp_path):
        f = tmp_path / "sans-etat.jpg"
        f.write_bytes(b"abc")
        assert Engine.file_complete(f, None, 3) is True
        assert Engine.file_complete(f, {}, 3) is True
        assert Engine.file_complete(f, {}, 42) is False

    def test_sans_taille_attendue_accepte(self, tmp_path):
        # neither an expected size nor an API-reported size: we trust what we have
        f = tmp_path / "x.jpg"
        f.write_bytes(b"a")
        assert Engine.file_complete(f, None, None) is True


class TestDossierPour:
    """`dossier_pour` is generic: it no longer speaks of WP URLs, it reads
    `element.mois` and `element.groupe`."""

    def test_plat(self, tmp_path):
        m = _moteur(tmp_path, sort_mode="plat")
        assert m.dossier_pour(_element(1), {}) == ""

    def test_date(self, tmp_path):
        m = _moteur(tmp_path, sort_mode="date")
        assert m.dossier_pour(_element(1, mois="2025-03"), {}) == "2025-03"

    def test_date_sans_mois(self, tmp_path):
        m = _moteur(tmp_path, sort_mode="date")
        assert m.dossier_pour(_element(1, mois=None), {}) == "divers"

    def test_galerie_avec_titre(self, tmp_path):
        m = _moteur(tmp_path, sort_mode="galerie")
        element = _element(1, groupe=17)
        assert m.dossier_pour(element, {"17": "match-du-siecle"}) == "match-du-siecle"

    def test_galerie_sans_titre(self, tmp_path):
        m = _moteur(tmp_path, sort_mode="galerie")
        element = _element(1, groupe=17)
        assert m.dossier_pour(element, {}) == "contenu-17"

    def test_galerie_sans_groupe_bascule_date(self, tmp_path):
        m = _moteur(tmp_path, sort_mode="galerie")
        element = _element(1, groupe=None, mois="2025-03")
        assert m.dossier_pour(element, {}) == "2025-03"


class TestCheminLibre:
    def test_chemin_disponible(self, tmp_path):
        m = _moteur(tmp_path)
        dest = tmp_path / "sous" / "match.jpg"
        pris = set()
        r = m.free_path(dest, "42", pris)
        assert r == dest
        assert "sous/match.jpg" in {p.replace("\\", "/") for p in pris}

    def test_conflit_suffixe_ident(self, tmp_path):
        m = _moteur(tmp_path)
        pris = {"sous/match.jpg", "sous\\match.jpg"}
        dest = tmp_path / "sous" / "match.jpg"
        r = m.free_path(dest, "42", pris)
        assert r.name == "match-42.jpg"


# --------------------------------------------------------------------------- #
# Engine.download — mocked HTTP session
# --------------------------------------------------------------------------- #

class FakeResponse:
    """Fake HTTP response, iterable like the one from requests."""

    def __init__(self, status_code=200, headers=None, content=b""):
        self.status_code = status_code
        self.headers = headers or {}
        self._content = content

    def iter_content(self, chunk_size):
        for i in range(0, len(self._content), chunk_size):
            yield self._content[i:i + chunk_size]

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class TestTelecharger:
    def test_ok(self, tmp_path):
        m = _moteur(tmp_path)
        m.session = MagicMock()
        m.session.get.return_value = FakeResponse(
            200, {"ETag": "e1", "Last-Modified": "m1"}, b"payload")
        dest = tmp_path / "out.jpg"
        statut, infos, _, _ = m.download("https://x/f.jpg", dest, None)
        assert statut == "ok"
        assert dest.read_bytes() == b"payload"
        assert infos["taille"] == 7
        assert infos["etag"] == "e1"
        assert infos["modifie"] == "m1"

    def test_304_inchange(self, tmp_path):
        m = _moteur(tmp_path, verify=True)
        m.session = MagicMock()
        m.session.get.return_value = FakeResponse(304)
        dest = tmp_path / "existe.jpg"
        dest.write_bytes(b"deja")
        statut, infos, _, _ = m.download("https://x/f.jpg", dest,
                                         {"etag": "e1", "taille": 4})
        assert statut == "inchangé"
        # the returned state is the one passed in, unaltered
        assert infos == {"etag": "e1", "taille": 4}

    def test_404_introuvable(self, tmp_path):
        m = _moteur(tmp_path)
        m.session = MagicMock()
        m.session.get.return_value = FakeResponse(404)
        dest = tmp_path / "sortie.jpg"
        statut, infos, _, _ = m.download("https://x/f.jpg", dest, None)
        assert statut == "introuvable"
        assert infos is None
        assert not dest.exists()

    def test_reprise_depuis_part(self, tmp_path):
        # an existing .part triggers a Range GET → 206
        m = _moteur(tmp_path)
        m.session = MagicMock()
        m.session.get.return_value = FakeResponse(206, {}, b"XYZ")
        dest = tmp_path / "reprise.jpg"
        (dest.with_suffix(dest.suffix + ".part")).write_bytes(b"AB")
        statut, _infos, _, _ = m.download("https://x/f.jpg", dest, None)
        assert statut == "repris"
        # the final content concatenates the .part and the downloaded remainder
        assert dest.read_bytes() == b"ABXYZ"
        # the Range was sent
        _, kwargs = m.session.get.call_args
        assert kwargs["headers"].get("Range") == "bytes=2-"

    def test_416_relance_sans_range(self, tmp_path):
        # 416 (invalid Range) → delete the .part and restart from scratch
        m = _moteur(tmp_path)
        m.session = MagicMock()
        m.session.get.side_effect = [
            FakeResponse(416),
            FakeResponse(200, {"ETag": "e"}, b"neuf"),
        ]
        dest = tmp_path / "r.jpg"
        (dest.with_suffix(dest.suffix + ".part")).write_bytes(b"AB")
        statut, _infos, _, _ = m.download("https://x/f.jpg", dest, None)
        assert statut == "ok"
        assert dest.read_bytes() == b"neuf"

    def test_if_modified_since_utilise(self, tmp_path):
        # state without etag but with modifie → other conditional header
        m = _moteur(tmp_path, verify=True)
        m.session = MagicMock()
        m.session.get.return_value = FakeResponse(304)
        dest = tmp_path / "x.jpg"
        dest.write_bytes(b"deja")
        _statut, _infos, _classification, _error = m.download(
            "https://x/f.jpg", dest,
            {"modifie": "Wed, 01 Jan 2026 00:00:00 GMT", "taille": 4})
        _, kw = m.session.get.call_args
        assert kw["headers"].get("If-Modified-Since") == \
            "Wed, 01 Jan 2026 00:00:00 GMT"

    def test_erreur_reseau(self, tmp_path):
        """Network exception yields status ``"erreur"`` and raw error text."""
        m = _moteur(tmp_path)
        m.session = MagicMock()
        m.session.get.side_effect = requests.ConnectionError("boum")
        dest = tmp_path / "s.jpg"
        statut, infos, classification, error_text = m.download(
            "https://x/f.jpg", dest, None)
        assert statut == "erreur"
        assert infos is None
        assert not dest.exists()
        assert classification is not None
        assert classification.category in {"coupure", "transitoire", "definitif"}
        # Error text carries the raw exception message for the ``file-failed``
        # event; no French translation happens inside ``Engine.download``.
        assert error_text is not None
        assert "boum" in error_text

    def test_interruption_conserve_part(self, tmp_path):
        # the stop mid-read must leave the .part for the resume
        m = _moteur(tmp_path)
        m.arret.set()   # cut off on the first block

        class GrosseResponse(FakeResponse):
            def iter_content(self_, chunk_size):
                yield b"A" * chunk_size

        m.session = MagicMock()
        m.session.get.return_value = GrosseResponse(200, {}, b"")
        dest = tmp_path / "int.jpg"
        with pytest.raises(Interrupted):
            m.download("https://x/f.jpg", dest, None)
        assert (dest.with_suffix(dest.suffix + ".part")).exists()
        assert not dest.exists()


# --------------------------------------------------------------------------- #
# Engine.run — orchestration
# --------------------------------------------------------------------------- #

def _patch_inventaire(moteur, elements):
    """Shortcut: patch `moteur.source.inventory` to return `elements`.

    The inventory adapter is what the engine consumes now; orchestration
    tests no longer test the raw API call, only the orchestration
    downstream of the `Element` contract.
    """
    return patch.object(moteur.source, "inventory",
                        return_value=iter(elements))


class TestExecuter:
    def test_ignore_les_supprimees(self, tmp_path):
        write_manifest(tmp_path, {
            "42": {"fichier": "photo.jpg", "taille": 100,
                   "supprime": "2026-01-01T00:00:00"},
        })
        moteur = _moteur(tmp_path)
        with _patch_inventaire(moteur, [_element(42)]), \
             patch.object(moteur, "download") as tel:
            res = moteur.run()
        assert res.skipped == 1
        assert tel.call_count == 0
        assert "supprime" in read_manifest(tmp_path)["42"]

    def test_ignore_les_elements_sans_url(self, tmp_path):
        # A source that did not find a resource at the requested format:
        # the engine must count it as ignoree, without crashing.
        moteur = _moteur(tmp_path, sort_mode="date")
        sans_url = _element(1, url=None, nom_fichier="", mois="2026-01")
        with _patch_inventaire(moteur, [sans_url]), \
             patch.object(moteur, "download") as tel:
            res = moteur.run()
        assert res.skipped == 1
        assert tel.call_count == 0

    def test_detecte_effacement_disque(self, tmp_path):
        # complete state but file gone → marked deleted, no download
        write_manifest(tmp_path, {
            "8": {"fichier": "manquant.jpg", "taille": 10},
        })
        moteur = _moteur(tmp_path)
        with _patch_inventaire(moteur, [_element(8, taille=10)]), \
             patch.object(moteur, "download") as tel:
            res = moteur.run()
        assert res.deleted == 1
        assert tel.call_count == 0
        assert "supprime" in read_manifest(tmp_path)["8"]

    def test_deja_present(self, tmp_path):
        f = tmp_path / "ok.jpg"
        f.write_bytes(b"1234567890")
        write_manifest(tmp_path, {
            "1": {"fichier": "ok.jpg", "taille": 10},
        })
        moteur = _moteur(tmp_path)
        with _patch_inventaire(moteur, [_element(1, taille=10)]), \
             patch.object(moteur, "download") as tel:
            res = moteur.run()
        assert res.already_present == 1
        assert tel.call_count == 0

    def test_telechargement(self, tmp_path):
        moteur = _moteur(tmp_path, sort_mode="date")
        el = _element(5, url="https://x/wp-content/uploads/2026/03/f.jpg",
                      mois="2026-03")
        with _patch_inventaire(moteur, [el]), \
             patch.object(moteur, "download",
                          return_value=("ok", {"taille": 12, "etag": "e",
                                               "modifie": "m", "url": "u"},
                                        None, None)):
            res = moteur.run()
        assert res.downloaded == 1
        assert res.bytes == 12
        m = read_manifest(tmp_path)
        assert "5" in m
        assert m["5"]["fichier"].replace("\\", "/") == "2026-03/f.jpg"

    def test_reprise_incrementale(self, tmp_path):
        moteur = _moteur(tmp_path, sort_mode="date")
        el = _element(5, url="https://x/wp-content/uploads/2026/03/f.jpg",
                      mois="2026-03")
        with _patch_inventaire(moteur, [el]), \
             patch.object(moteur, "download",
                          return_value=("repris", {"taille": 3, "etag": "",
                                                   "modifie": "", "url": "u"},
                                        None, None)):
            res = moteur.run()
        assert res.resumed == 1
        assert res.bytes == 3

    def test_echec_reseau(self, tmp_path):
        """A failed download counts as a failure and emits ``file-failed``."""
        moteur = _moteur(tmp_path, sort_mode="date")
        el = _element(5, url="https://x/wp-content/uploads/2026/03/f.jpg",
                      mois="2026-03")
        journal: list[EngineEvent] = []
        moteur._journal = journal.append
        with _patch_inventaire(moteur, [el]), \
             patch.object(moteur, "download",
                          return_value=("erreur", None, None, "boum")):
            res = moteur.run()
        assert res.failures == 1
        # The engine emits the failure through a structured event, no
        # translation happens on this path.
        failed = [ev for ev in journal if ev.code == "file-failed"]
        assert len(failed) == 1
        assert failed[0].params.get("error") == "boum"

    def test_aucune_image(self, tmp_path):
        """``nothing-matches`` is the structured summary when the inventory is empty."""
        moteur = _moteur(tmp_path)
        with _patch_inventaire(moteur, []):
            res = moteur.run()
        assert res.message_event is not None
        assert res.message_event.code == "nothing-matches"

    def test_filtre_largeur_min(self, tmp_path):
        moteur = _moteur(tmp_path, sort_mode="date", min_width=1000)
        petit = _element(1, largeur=200, mois="2026-04")
        grand = _element(2, url="https://x/wp-content/uploads/2026/04/big.jpg",
                         largeur=2000, mois="2026-04")
        with _patch_inventaire(moteur, [petit, grand]), \
             patch.object(moteur, "download",
                          return_value=("ok", {"taille": 1, "etag": "",
                                               "modifie": "", "url": "u"},
                                        None, None)):
            res = moteur.run()
        assert res.downloaded == 1   # only the big one was processed

    def test_interruption(self, tmp_path):
        """An ``Interrupted`` mid-run surfaces as ``message_event.code == "interrupted"``."""
        moteur = _moteur(tmp_path)
        moteur.arret.set()

        def leve(*_a, **_kw):
            raise Interrupted()

        with patch.object(moteur.source, "inventory", side_effect=leve):
            res = moteur.run()
        assert res.interrupted is True
        assert res.message_event is not None
        assert res.message_event.code == "interrupted"

    def test_erreur_api_capturee(self, tmp_path):
        """A ``RuntimeError`` from the source is journalled as ``runtime-error``."""
        moteur = _moteur(tmp_path)
        journal: list[EngineEvent] = []
        moteur._journal = journal.append
        with patch.object(moteur.source, "inventory",
                          side_effect=RuntimeError("API HS")):
            res = moteur.run()
        # ``res.message`` still carries the raw error text so historical
        # summary consumers keep working.
        assert "API HS" in res.message
        assert res.failures == 0   # RuntimeError ≠ per-image failure
        runtime_events = [ev for ev in journal if ev.code == "runtime-error"]
        assert len(runtime_events) == 1
        assert runtime_events[0].params.get("error") == "API HS"

    def test_force_ignore_manifeste(self, tmp_path):
        # with force, an image marked deleted must be re-downloaded
        write_manifest(tmp_path, {
            "1": {"fichier": "a.jpg", "taille": 100,
                  "supprime": "2026-01-01T00:00:00"},
        })
        moteur = _moteur(tmp_path, sort_mode="date", force=True)
        el = _element(1, url="https://x/wp-content/uploads/2026/03/a.jpg",
                      mois="2026-03")
        with _patch_inventaire(moteur, [el]), \
             patch.object(moteur, "download",
                          return_value=("ok", {"taille": 1, "etag": "",
                                               "modifie": "", "url": "u"},
                                        None, None)) as tel:
            res = moteur.run()
        assert res.downloaded == 1
        assert tel.call_count == 1


# --------------------------------------------------------------------------- #
# Engine.run — network circuit breaker and deferred retry (lot 2)
# --------------------------------------------------------------------------- #

class TestCoupeCircuit:
    """Engine circuit breaker: clean stop on ``coupure`` or 5 ``transitoire``.

    These tests mock :meth:`Engine.download` to inject the
    ``(statut, infos, ErrorClassification)`` triple directly — no network access,
    no real waiting on backoffs.
    """

    _OK = ("ok", {"taille": 1, "etag": "", "modifie": "", "url": "u"},
           None, None)

    @staticmethod
    def _elements(nombre):
        """Builds ``nombre`` Elements, all with a valid URL and month."""
        return [
            _element(i, url=f"https://x/wp-content/uploads/2026/03/f{i}.jpg",
                     mois="2026-03", date=f"2026-03-{i:02d}T00:00:00")
            for i in range(1, nombre + 1)
        ]

    def test_une_coupure_interrompt_le_run(self, tmp_path):
        """Une seule erreur ``coupure`` termine le run en report et stoppe la boucle."""
        moteur = _moteur(tmp_path, sort_mode="date")
        elements = self._elements(3)
        reponses = [
            self._OK,
            ("erreur", None, ErrorClassification("coupure", None), "coupure"),
        ]
        with _patch_inventaire(moteur, elements), \
             patch.object(moteur, "download", side_effect=reponses) as tel:
            res = moteur.run()
        assert res.deferred is True
        assert res.failures == 1
        assert res.downloaded == 1
        assert tel.call_count == 2

    def test_cinq_transitoires_consecutifs_interrompent(self, tmp_path):
        """Five consecutive ``transitoire`` failures trigger a defer."""
        moteur = _moteur(tmp_path, sort_mode="date")
        elements = self._elements(10)
        transitoire = ("erreur", None,
                       ErrorClassification("transitoire", None), "timeout")
        with _patch_inventaire(moteur, elements), \
             patch.object(moteur, "download",
                          side_effect=[transitoire] * 5) as tel:
            res = moteur.run()
        assert res.deferred is True
        assert res.failures == 5
        assert tel.call_count == 5

    def test_succes_reinitialise_le_compteur(self, tmp_path):
        """A success between two runs of ``transitoire`` failures resets the counter."""
        moteur = _moteur(tmp_path, sort_mode="date")
        elements = self._elements(10)
        transitoire = ("erreur", None,
                       ErrorClassification("transitoire", None), "timeout")
        reponses = [transitoire] * 4 + [self._OK] + [transitoire] * 4 + [self._OK]
        with _patch_inventaire(moteur, elements), \
             patch.object(moteur, "download", side_effect=reponses):
            res = moteur.run()
        assert res.deferred is False
        assert res.failures == 8
        assert res.downloaded == 2

    def test_definitif_ne_declenche_pas_le_coupe_circuit(self, tmp_path):
        """Une erreur ``definitif`` (404) ne fait pas monter le compteur de ``transitoire``."""
        moteur = _moteur(tmp_path, sort_mode="date")
        elements = self._elements(10)
        transitoire = ("erreur", None,
                       ErrorClassification("transitoire", None), "timeout")
        introuvable = ("introuvable", None,
                       ErrorClassification("definitif", None), None)
        reponses = ([transitoire] * 4 + [introuvable] + [transitoire] * 4
                    + [self._OK])
        with _patch_inventaire(moteur, elements), \
             patch.object(moteur, "download", side_effect=reponses):
            res = moteur.run()
        assert res.deferred is False

    def test_retry_after_alimente_retenter_apres(self, tmp_path):
        """A ``Retry-After`` of 3600 s produces an ISO 8601 about 1 h in the future."""
        moteur = _moteur(tmp_path, sort_mode="date")
        el = self._elements(1)[0]
        reponse = ("erreur", None,
                   ErrorClassification("coupure", 3600.0), "quota")
        avant = datetime.now(timezone.utc)
        with _patch_inventaire(moteur, [el]), \
             patch.object(moteur, "download", return_value=reponse):
            res = moteur.run()
        apres = datetime.now(timezone.utc)
        assert res.deferred is True
        assert res.retry_after
        cible = datetime.fromisoformat(res.retry_after)
        if cible.tzinfo is None:
            cible = cible.replace(tzinfo=timezone.utc)
        assert avant + timedelta(seconds=3540) <= cible
        assert cible <= apres + timedelta(seconds=3660)

    def test_sans_retry_after_retenter_apres_est_vide(self, tmp_path):
        """Without ``Retry-After``, ``res.retry_after`` stays empty: the scheduler decides."""
        moteur = _moteur(tmp_path, sort_mode="date")
        el = self._elements(1)[0]
        reponse = ("erreur", None,
                   ErrorClassification("coupure", None), "boum")
        with _patch_inventaire(moteur, [el]), \
             patch.object(moteur, "download", return_value=reponse):
            res = moteur.run()
        assert res.deferred is True
        assert res.retry_after == ""

    def test_manifeste_sauvegarde_meme_sur_report(self, tmp_path):
        """The on-disk manifest keeps the entries downloaded before the cut."""
        moteur = _moteur(tmp_path, sort_mode="date")
        elements = self._elements(3)
        coupure = ("erreur", None,
                   ErrorClassification("coupure", None), "coupure")
        with _patch_inventaire(moteur, elements), \
             patch.object(moteur, "download",
                          side_effect=[self._OK, coupure]):
            res = moteur.run()
        assert res.deferred is True
        m = read_manifest(tmp_path)
        assert "1" in m

    def test_cache_non_sauvegarde_sur_report(self, tmp_path):
        """A cut does not write the engine cache (same as ``Interrupted``)."""
        moteur = _moteur(tmp_path, site="https://x", sort_mode="date")
        elements = self._elements(3)
        coupure = ("erreur", None,
                   ErrorClassification("coupure", None), "coupure")
        with _patch_inventaire(moteur, elements), \
             patch.object(moteur, "download",
                          side_effect=[self._OK, coupure]):
            moteur.run()
        assert not cache_path(tmp_path).exists()


# --------------------------------------------------------------------------- #
# Engine.__init__: default roles
# --------------------------------------------------------------------------- #

class TestEngineInit:
    def test_callbacks_par_defaut_sont_no_op(self, tmp_path):
        """Default callbacks accept an :class:`EngineEvent` without raising."""
        # without callbacks: the engine does not explode when it "logs"
        m = Engine(Options(target_dir=tmp_path, delay=0))
        m._journal(EngineEvent("all-up-to-date"))
        m._progression(1, 2, "étiquette")   # nothing raises

    def test_arret_par_defaut(self, tmp_path):
        m = Engine(Options(target_dir=tmp_path))
        assert m.arret is not None
        assert m.arret.is_set() is False

    def test_source_par_defaut_est_wordpress(self, tmp_path):
        # Default Options: source_type == "wordpress"
        m = Engine(Options(target_dir=tmp_path, delay=0))
        assert m.source.type == "wordpress"

    def test_source_djangoplicity_choisi_via_options(self, tmp_path):
        m = Engine(Options(target_dir=tmp_path, delay=0,
                           source_type="djangoplicity",
                           image_format="Small"))
        assert m.source.type == "djangoplicity"
        # the format is forwarded to the adapter via `reglages`
        assert m.source.format_image == "Small"

    def test_type_inconnu_repli_sur_wordpress(self, tmp_path):
        # defensive: an unknown type (corrupt config) must not crash
        m = Engine(Options(target_dir=tmp_path, delay=0,
                           source_type="inconnu"))
        assert m.source.type == "wordpress"


# --------------------------------------------------------------------------- #
# Plumbing: cooperative stop
# --------------------------------------------------------------------------- #

class TestPlomberieEngine:
    def test_verifier_arret_leve_interrompu(self, tmp_path):
        m = _moteur(tmp_path)
        m.arret.set()
        with pytest.raises(Interrupted):
            m._check_stop()

    def test_verifier_arret_silencieux_sinon(self, tmp_path):
        m = _moteur(tmp_path)
        m._check_stop()   # nothing raises

    def test_pause_dort_puis_rend_la_main(self, tmp_path):
        m = _moteur(tmp_path)
        # a very short pause exercises the sleep loop
        import time
        avant = time.monotonic()
        m._pause(0.01)
        assert time.monotonic() - avant >= 0.005


# --------------------------------------------------------------------------- #
# load_manifest: force option and fallback to empty
# --------------------------------------------------------------------------- #

class TestChargerManifeste:
    def test_force_efface_le_manifeste_en_memoire(self, tmp_path):
        write_manifest(tmp_path, {"1": {"fichier": "a.jpg"}})
        m = _moteur(tmp_path, force=True)
        assert m.load_manifest() == {}

    def test_absent_renvoie_vide(self, tmp_path):
        m = _moteur(tmp_path)
        assert m.load_manifest() == {}

    def test_illisible_journalise(self, tmp_path):
        """An unreadable manifest emits a ``manifest-unreadable`` event."""
        manifest_path(tmp_path).write_text("{invalid")
        journal: list[EngineEvent] = []
        m = _moteur(tmp_path)
        m._journal = journal.append
        assert m.load_manifest() == {}
        assert any(ev.code == "manifest-unreadable" for ev in journal)


# --------------------------------------------------------------------------- #
# run: extra branches (unchanged, gallery resolution, OSError…)
# --------------------------------------------------------------------------- #

class TestExecuterExtra:
    def test_base_normalise_slash_final(self, tmp_path):
        # the engine's base strips the trailing slash; that is also what
        # the adapter sees.
        moteur = _moteur(tmp_path, site="https://example.test/")
        assert moteur.base == "https://example.test"
        assert moteur.source.base == "https://example.test"

    def test_status_inchange_compte_dans_inchangees(self, tmp_path):
        # known file to re-verify with 304
        f = tmp_path / "ok.jpg"
        f.write_bytes(b"12345")
        write_manifest(tmp_path, {
            "1": {"fichier": "ok.jpg", "taille": 5, "etag": "e"},
        })
        moteur = _moteur(tmp_path, verify=True)
        with _patch_inventaire(moteur, [_element(1, taille=5)]), \
             patch.object(moteur, "download",
                          return_value=("inchangé",
                                        {"fichier": "ok.jpg", "taille": 5,
                                         "etag": "e"}, None, None)):
            res = moteur.run()
        assert res.unchanged == 1

    def test_resoudre_groupes_appele_en_mode_galerie(self, tmp_path):
        moteur = _moteur(tmp_path, sort_mode="galerie")
        el = _element(1, groupe=42)
        with _patch_inventaire(moteur, [el]), \
             patch.object(moteur.source, "resolve_groups",
                          return_value={"42": "match-42"}) as res_parents, \
             patch.object(moteur, "download",
                          return_value=("ok", {"taille": 1, "etag": "",
                                               "modifie": "", "url": "u"},
                                        None, None)):
            res = moteur.run()
        assert res.downloaded == 1
        res_parents.assert_called_once()
        # the file was placed in the "match-42" directory
        m = read_manifest(tmp_path)
        assert m["1"]["fichier"].replace("\\", "/").startswith("match-42/")

    def test_resoudre_groupes_ignore_si_source_ne_les_supporte_pas(self, tmp_path):
        # Djangoplicity does not have "galerie" in its sort modes. Even if
        # the user left it in their options, the engine must not call
        # resoudre_groupes, and fall back to the by-date sort.
        moteur = _moteur(tmp_path, sort_mode="galerie",
                         source_type="djangoplicity")
        el = _element(1, groupe="42", mois="2026-03",
                      url="https://cdn.eso.org/large/potw.jpg")
        with _patch_inventaire(moteur, [el]), \
             patch.object(moteur.source, "resolve_groups") as res_g, \
             patch.object(moteur, "download",
                          return_value=("ok", {"taille": 1, "etag": "",
                                               "modifie": "", "url": "u"},
                                        None, None)):
            moteur.run()
        res_g.assert_not_called()

    def test_oserror_capturee(self, tmp_path):
        """An ``OSError`` becomes a ``write-problem`` structured event."""
        moteur = _moteur(tmp_path)
        journal: list[EngineEvent] = []
        moteur._journal = journal.append
        with patch.object(moteur.source, "inventory",
                          side_effect=OSError("disque plein")):
            res = moteur.run()
        assert res.message_event is not None
        assert res.message_event.code == "write-problem"
        assert res.message_event.params.get("error") == "disque plein"
        # same event is also emitted on the journal callback
        assert any(
            ev.code == "write-problem"
            and ev.params.get("error") == "disque plein"
            for ev in journal
        )

    def test_journalise_filtrage_largeur(self, tmp_path):
        """Width-filtered elements are reported as ``discarded-below-min-width``."""
        moteur = _moteur(tmp_path, sort_mode="date", min_width=1000)
        journal: list[EngineEvent] = []
        moteur._journal = journal.append
        with _patch_inventaire(moteur, [_element(1, largeur=200),
                                        _element(2, largeur=300)]):
            moteur.run()
        events = [ev for ev in journal
                  if ev.code == "discarded-below-min-width"]
        assert len(events) == 1
        assert events[0].params == {"count": 2, "min_width": 1000}

    def test_sauvegarde_periodique(self, tmp_path):
        # 26 images: save_manifest must be called at least at the 25th
        # and once more in finally
        moteur = _moteur(tmp_path, sort_mode="date")
        elements = [
            _element(i, url=f"https://x/wp-content/uploads/2026/03/f{i}.jpg",
                     mois="2026-03")
            for i in range(1, 27)
        ]
        with _patch_inventaire(moteur, elements), \
             patch.object(moteur, "download",
                          return_value=("ok", {"taille": 1, "etag": "",
                                               "modifie": "", "url": "u"},
                                        None, None)), \
             patch.object(moteur, "save_manifest") as sauver:
            moteur.run()
        # at least 2 calls: periodic + finally
        assert sauver.call_count >= 2

    def test_metadata_source_ecrite_dans_manifeste(self, tmp_path):
        # An adapter (Djangoplicity) can provide credit / rights / checksum
        # in `element.extra`: the engine copies them into the manifest
        # without interpreting them — useful for the upcoming catalog export.
        moteur = _moteur(tmp_path, sort_mode="date")
        el = _element(7, url="https://cdn.eso.org/large/eso1907a.jpg",
                      mois="2026-03",
                      extra={"credit": "ESO/T. Preibisch"})
        with _patch_inventaire(moteur, [el]), \
             patch.object(moteur, "download",
                          return_value=("ok", {"taille": 1, "etag": "",
                                               "modifie": "", "url": "u"},
                                        None, None)):
            moteur.run()
        stocke = read_manifest(tmp_path)["7"]
        assert stocke.get("extra", {}).get("credit") == "ESO/T. Preibisch"


# --------------------------------------------------------------------------- #
# API cache: read, write, effect on subsequent runs
# --------------------------------------------------------------------------- #

class TestCacheAPI:
    def test_chemin(self, tmp_path):
        assert cache_path(tmp_path) == tmp_path / ".cache.json"

    def test_lire_absent(self, tmp_path):
        assert read_cache(tmp_path) == {}

    def test_lire_json_invalide(self, tmp_path):
        cache_path(tmp_path).write_text("{pas du json")
        assert read_cache(tmp_path) == {}

    def test_ecrire_puis_relire(self, tmp_path):
        cache = {"derniere_date_media": "2026-05-01T12:00:00",
                 "titres_parents": {"42": "match"}}
        write_cache(tmp_path, cache)
        assert read_cache(tmp_path) == cache

    def test_charger_cache_ignore_si_force(self, tmp_path):
        write_cache(tmp_path, {"site": "https://x", "derniere_date_media": "2026"})
        m = _moteur(tmp_path, force=True)
        assert m.load_cache() == {}

    def test_charger_cache_ignore_si_desactive(self, tmp_path):
        write_cache(tmp_path, {"site": "https://x", "derniere_date_media": "2026"})
        m = _moteur(tmp_path, use_cache=False)
        assert m.load_cache() == {}

    def test_charger_cache_ignore_si_site_change(self, tmp_path):
        # cache written for another site: no cross-usage
        write_cache(tmp_path, {"site": "https://autre.example",
                                "derniere_date_media": "2026"})
        m = _moteur(tmp_path, site="https://nouveau.example")
        assert m.load_cache() == {}

    def test_charger_cache_meme_site(self, tmp_path):
        write_cache(tmp_path, {"site": "https://x", "derniere_date_media": "2026"})
        m = _moteur(tmp_path, site="https://x")
        assert m.load_cache()["derniere_date_media"] == "2026"

    def test_sauver_ajoute_le_site(self, tmp_path):
        m = _moteur(tmp_path, site="https://y")
        m.save_cache({"derniere_date_media": "2026-01-01T00:00:00"})
        stocke = read_cache(tmp_path)
        assert stocke["site"] == "https://y"
        assert stocke["derniere_date_media"] == "2026-01-01T00:00:00"

    def test_sauver_no_op_si_force(self, tmp_path):
        m = _moteur(tmp_path, force=True)
        m.save_cache({"quelque": "chose"})
        assert not cache_path(tmp_path).exists()

    def test_executer_utilise_date_du_cache_comme_after(self, tmp_path):
        # A pre-existing cache must be passed to `source.inventory` as `depuis`
        write_cache(tmp_path, {
            "site": "https://x.example",
            "derniere_date_media": "2026-06-15T12:00:00",
        })
        m = _moteur(tmp_path, site="https://x.example", sort_mode="date")
        capture = {}

        def faux_inventaire(depuis, _jusqua):
            capture["depuis"] = depuis
            return iter([])

        with patch.object(m.source, "inventory", side_effect=faux_inventaire):
            m.run()
        assert capture["depuis"] == "2026-06-15T12:00:00"

    def test_executer_prefere_depuis_utilisateur_au_cache(self, tmp_path):
        write_cache(tmp_path, {"site": "https://x", "derniere_date_media": "2026"})
        m = _moteur(tmp_path, site="https://x", since="2020-01-01",
                    sort_mode="date")
        capture = {}

        def faux_inventaire(depuis, _jusqua):
            capture["depuis"] = depuis
            return iter([])

        with patch.object(m.source, "inventory", side_effect=faux_inventaire):
            m.run()
        # with a user `depuis`, we do NOT inject the cache date
        assert capture["depuis"] == "2020-01-01"

    def test_executer_met_a_jour_la_date_max(self, tmp_path):
        m = _moteur(tmp_path, site="https://x", sort_mode="date")
        elements = [
            _element(1, url="https://x/wp-content/uploads/2026/03/a.jpg",
                     mois="2026-03", date="2026-03-10T08:00:00"),
            _element(2, url="https://x/wp-content/uploads/2026/06/b.jpg",
                     mois="2026-06", date="2026-06-20T09:30:00"),
        ]
        with _patch_inventaire(m, elements), \
             patch.object(m, "download",
                          return_value=("ok", {"taille": 1, "etag": "",
                                               "modifie": "", "url": "u"},
                                        None, None)):
            m.run()
        cache = read_cache(tmp_path)
        assert cache["derniere_date_media"] == "2026-06-20T09:30:00"
        assert cache["site"] == "https://x"

    def test_executer_cache_les_titres_de_galeries(self, tmp_path):
        m = _moteur(tmp_path, site="https://x", sort_mode="galerie")
        el = _element(1, url="https://x/wp-content/uploads/2026/03/a.jpg",
                      groupe=42, mois="2026-03")
        with _patch_inventaire(m, [el]), \
             patch.object(m.source, "resolve_groups",
                          return_value={"42": "match-a"}) as res_p, \
             patch.object(m, "download",
                          return_value=("ok", {"taille": 1, "etag": "",
                                               "modifie": "", "url": "u"},
                                        None, None)):
            m.run()
        assert read_cache(tmp_path)["titres_parents"] == {"42": "match-a"}
        res_p.assert_called_once()

    def test_executer_reutilise_titres_caches(self, tmp_path):
        # Pre-populated cache: the engine passes the cache to the adapter,
        # which must return the name without calling the API (contract
        # tested on WordPress in
        # `test_source_wordpress::TestResoudreGroupes::test_court_circuite_sur_cache_connus`).
        # Here we check the engine-side orchestration.
        write_cache(tmp_path, {
            "site": "https://x",
            "titres_parents": {"42": "match-cache"},
        })
        m = _moteur(tmp_path, site="https://x", sort_mode="galerie")
        el = _element(1, url="https://x/wp-content/uploads/2026/03/a.jpg",
                      groupe=42, mois="2026-03")
        appels = []

        def faux_resoudre(cles, connus=None):
            appels.append((cles, dict(connus or {})))
            # adapter behavior: known entries are kept as-is, no request
            # is made for them.
            return dict(connus or {})

        with _patch_inventaire(m, [el]), \
             patch.object(m.source, "resolve_groups", side_effect=faux_resoudre), \
             patch.object(m, "download",
                          return_value=("ok", {"taille": 1, "etag": "",
                                               "modifie": "", "url": "u"},
                                        None, None)):
            m.run()
        # the adapter received the cache: it's up to it to short-circuit.
        assert appels and appels[0][1] == {"42": "match-cache"}
        # the file was placed in "match-cache"
        assert read_manifest(tmp_path)["1"]["fichier"].replace("\\", "/") \
            .startswith("match-cache/")

    def test_interruption_ne_sauve_pas_le_cache(self, tmp_path):
        m = _moteur(tmp_path, site="https://x")
        with patch.object(m.source, "inventory", side_effect=Interrupted()):
            r = m.run()
        assert r.interrupted is True
        # no cache write: the max date was not committed
        assert not cache_path(tmp_path).exists()

    def test_charger_cache_ignore_si_type_change(self, tmp_path):
        # cache written under type "wordpress", engine created under type
        # "djangoplicity": two distinct identifier spaces, start from
        # scratch.
        write_cache(tmp_path, {
            "site": "https://x", "type_source": "wordpress",
            "derniere_date_media": "2026-06-01T00:00:00",
        })
        m = _moteur(tmp_path, site="https://x", source_type="djangoplicity")
        assert m.load_cache() == {}

    def test_charger_cache_migration_silencieuse_sans_type(self, tmp_path):
        # pre-existing cache without `type_source` field (config v1.0.38):
        # read as if it matched the current type, no loss.
        write_cache(tmp_path, {
            "site": "https://x",
            "derniere_date_media": "2026-06-01T00:00:00",
        })
        m = _moteur(tmp_path, site="https://x")   # default: wordpress
        assert m.load_cache()["derniere_date_media"] == "2026-06-01T00:00:00"

    def test_sauver_cache_ajoute_le_type_source(self, tmp_path):
        m = _moteur(tmp_path, site="https://y", source_type="djangoplicity")
        m.save_cache({"derniere_date_media": "2026-01-01T00:00:00"})
        stocke = read_cache(tmp_path)
        assert stocke["type_source"] == "djangoplicity"


# --------------------------------------------------------------------------- #
# Engine.save_manifest: read-merge-write fusion (UI vs engine race)
# --------------------------------------------------------------------------- #

class TestSauverManifesteFusion:
    """Write-merge: the UI mark wins over the engine's in-memory version.

    Non-regression against the last-writer-wins race between
    ``Engine.run()`` (loads the manifest on entry, rewrites everything
    in ``finally``) and ``delete_image``/``restore`` (read-mutate-write
    on the UI side).
    """

    def test_marque_supprime_ui_survit_a_sauvegarde_moteur(self, tmp_path):
        """A `supprime` mark set by the UI during a run survives the engine's `finally`."""
        # Disk state at run start; engine loads it into memory.
        write_manifest(tmp_path, {"1": {"fichier": "a.jpg", "taille": 42}})
        # File must exist for delete_image to succeed.
        (tmp_path / "a.jpg").write_bytes(b"x" * 42)
        moteur = _moteur(tmp_path)
        # In-memory version the engine will flush in its finally.
        manifeste = {"1": {"fichier": "a.jpg", "taille": 42}}
        # UI deletion happens mid-run: writes `supprime` directly to disk.
        assert delete_image(tmp_path, tmp_path / "a.jpg") is True
        # The engine's finally now flushes its in-memory copy, without the
        # `supprime` mark; the fusion must re-inject the disk mark.
        moteur.save_manifest(manifeste)
        assert "supprime" in read_manifest(tmp_path)["1"]

    def test_marque_restaure_ui_survit_a_sauvegarde_moteur(self, tmp_path):
        """A `restaure` mark set by the UI during a run survives the engine's `finally`."""
        # Disk starts with a `supprime` mark; engine loads it into memory.
        write_manifest(tmp_path, {
            "1": {"fichier": "a.jpg", "taille": 42,
                  "supprime": "2026-01-01T00:00:00"},
        })
        moteur = _moteur(tmp_path)
        # Engine's in-memory copy carries the same `supprime`.
        manifeste = {"1": {"fichier": "a.jpg", "taille": 42,
                           "supprime": "2026-01-01T00:00:00"}}
        # UI restore happens mid-run: replaces `supprime` with `restaure` on disk.
        assert restore(tmp_path, ["1"]) == 1
        # Engine's finally flushes memory (which still has `supprime`, no `restaure`);
        # fusion must let the UI's `restaure` win.
        moteur.save_manifest(manifeste)
        stocke = read_manifest(tmp_path)["1"]
        assert stocke.get("restaure") is True
        assert "supprime" not in stocke

    def test_entree_disque_hors_perimetre_preservee(self, tmp_path):
        """An entry present only on disk is not wiped by the merge."""
        # Ident "2" is on disk with a `supprime` mark but not in the engine's
        # inventory this run (e.g. filtered out); the fusion must keep it.
        write_manifest(tmp_path, {
            "1": {"fichier": "a.jpg"},
            "2": {"fichier": "b.jpg", "supprime": "2026-01-01"},
        })
        moteur = _moteur(tmp_path)
        moteur.save_manifest({"1": {"fichier": "a.jpg"}})
        m = read_manifest(tmp_path)
        assert "2" in m
        assert m["2"].get("supprime") == "2026-01-01"
        assert m["2"].get("fichier") == "b.jpg"

    def test_nouvelle_entree_moteur_ecrite(self, tmp_path):
        """An entry the engine just added in memory is persisted correctly."""
        write_manifest(tmp_path, {"1": {"fichier": "a.jpg"}})
        moteur = _moteur(tmp_path)
        moteur.save_manifest({
            "1": {"fichier": "a.jpg"},
            "3": {"fichier": "c.jpg", "taille": 10},
        })
        m = read_manifest(tmp_path)
        assert "3" in m
        assert m["3"]["fichier"] == "c.jpg"
        assert m["3"]["taille"] == 10

    def test_suppression_ui_pendant_reset_par_moteur(self, tmp_path):
        """UI deletion concurrent with a re-download: `supprime` wins, fresh fields preserved."""
        # Disk: user deleted the image just before the engine finished
        # re-downloading it (fresh size/etag in memory, no `supprime`).
        write_manifest(tmp_path, {
            "1": {"fichier": "a.jpg", "taille": 5, "supprime": "2026-01-01"},
        })
        moteur = _moteur(tmp_path)
        manifeste = {"1": {"fichier": "a.jpg", "taille": 42, "etag": "neuf"}}
        moteur.save_manifest(manifeste)
        stocke = read_manifest(tmp_path)["1"]
        # Last user gesture wins for the mark.
        assert "supprime" in stocke
        # Memory wins for every field that is not `supprime`/`restaure`.
        assert stocke["taille"] == 42
        assert stocke["etag"] == "neuf"

    def test_champ_supprime_en_memoire_ecrase_disque_normalement(self, tmp_path):
        """A `supprime` mark set by the engine in memory is written normally (asymmetric merge rule)."""
        # Engine set `supprime` itself (case "file disappeared during run",
        # engine.py branch around line 750-755). Disk has no `supprime`.
        write_manifest(tmp_path, {"1": {"fichier": "a.jpg"}})
        moteur = _moteur(tmp_path)
        manifeste = {"1": {"fichier": "a.jpg",
                           "supprime": "2026-01-05T00:00:00"}}
        moteur.save_manifest(manifeste)
        stocke = read_manifest(tmp_path)["1"]
        # The fusion rule only reinjects a mark when it is on disk AND absent
        # in memory; here it is the other way around, so memory wins.
        assert stocke.get("supprime") == "2026-01-05T00:00:00"

    def test_sauvegarde_periodique_non_regressee(self, tmp_path):
        """The merge does not miss the 25-tick: ``save_manifest`` is still called >= 2 times with 26 items."""
        # Mirror of TestExecuterExtra::test_sauvegarde_periodique to detect any
        # regression in the periodic save cadence once the fusion is added.
        moteur = _moteur(tmp_path, sort_mode="date")
        elements = [
            _element(i, url=f"https://x/wp-content/uploads/2026/03/f{i}.jpg",
                     mois="2026-03")
            for i in range(1, 27)
        ]
        with _patch_inventaire(moteur, elements), \
             patch.object(moteur, "download",
                          return_value=("ok", {"taille": 1, "etag": "",
                                               "modifie": "", "url": "u"},
                                        None, None)), \
             patch.object(moteur, "save_manifest") as sauver:
            moteur.run()
        assert sauver.call_count >= 2
