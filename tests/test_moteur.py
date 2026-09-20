"""Tests du moteur : utilitaires, manifeste, Moteur.executer et supprimer_image.

Aucun accès réseau : `Moteur.telecharger` et `_api` sont mockés via
`unittest.mock`. Les tests créent leur propre dossier temporaire avec
`tmp_path` et n'ont pas besoin des interfaces COM Windows.
"""

from __future__ import annotations

import io
import json
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from WpImageDownloader.engine import (
    Interrompu,
    Moteur,
    Options,
    chemin_cache,
    chemin_manifeste,
    ecrire_cache,
    ecrire_manifeste,
    format_octets,
    lire_cache,
    lire_manifeste,
    lister_supprimees,
    nettoyer,
    restaurer,
    supprimer_image,
)


# --------------------------------------------------------------------------- #
# Utilitaires libres
# --------------------------------------------------------------------------- #

class TestNettoyer:
    def test_titre_simple(self):
        assert nettoyer("Match WordPress") == "match-wordpress"

    def test_accents_supprimes(self):
        # unidecode sur NFKD : les accents disparaissent
        assert nettoyer("Été à Genève") == "ete-a-geneve"

    def test_html_entities(self):
        assert nettoyer("WordPress &amp; Bâle") == "wordpress-bale"

    def test_caracteres_dangereux(self):
        # Windows refuse < > : " / \ | ? *
        r = nettoyer('a<b>c:d"e/f\\g|h?i*j')
        for interdit in '<>:"/\\|?*':
            assert interdit not in r

    def test_espaces_multiples(self):
        assert nettoyer("  a   b\tc\nd  ") == "a-b-c-d"

    def test_defaut_sur_vide(self):
        assert nettoyer("") == "divers"
        assert nettoyer("   ") == "divers"
        assert nettoyer(None) == "divers"

    def test_defaut_personnalise(self):
        assert nettoyer("", defaut="nada") == "nada"

    def test_troncature_a_80(self):
        r = nettoyer("a" * 200)
        assert len(r) == 80

    def test_pas_de_point_final(self):
        # Windows refuse les noms terminant par un point
        assert not nettoyer("Titre.").endswith(".")
        assert not nettoyer("Titre...").endswith(".")


class TestFormatOctets:
    def test_octets(self):
        assert format_octets(0) == "0 o"
        assert format_octets(512) == "512 o"

    def test_kilo(self):
        assert format_octets(1024) == "1.0 Ko"
        assert format_octets(1536) == "1.5 Ko"

    def test_mega(self):
        assert format_octets(1024 * 1024) == "1.0 Mo"

    def test_giga(self):
        assert format_octets(1024 ** 3) == "1.0 Go"

    def test_au_dela_du_giga(self):
        # la boucle plafonne à « Go », les To restent exprimés en Go
        assert format_octets(1024 ** 4).endswith(" Go")


# --------------------------------------------------------------------------- #
# Manifeste — I/O de bas niveau
# --------------------------------------------------------------------------- #

class TestManifesteIO:
    def test_chemin(self, tmp_path):
        assert chemin_manifeste(tmp_path) == tmp_path / ".etat.json"

    def test_lire_absent(self, tmp_path):
        assert lire_manifeste(tmp_path) == {}

    def test_lire_json_invalide(self, tmp_path):
        chemin_manifeste(tmp_path).write_text("{ceci n'est pas du json")
        assert lire_manifeste(tmp_path) == {}

    def test_lire_json_valide(self, tmp_path):
        chemin_manifeste(tmp_path).write_text(
            json.dumps({"1": {"fichier": "a.jpg"}}), encoding="utf-8")
        assert lire_manifeste(tmp_path) == {"1": {"fichier": "a.jpg"}}

    def test_ecrire_puis_relire(self, tmp_path):
        m = {"7": {"fichier": "x/y.jpg", "taille": 42}}
        ecrire_manifeste(tmp_path, m)
        assert lire_manifeste(tmp_path) == m

    def test_ecriture_atomique(self, tmp_path):
        # après écriture, aucun fichier .tmp ne doit rester
        ecrire_manifeste(tmp_path, {"1": {}})
        assert not (tmp_path / ".etat.json.tmp").exists()
        assert (tmp_path / ".etat.json").exists()

    def test_ecriture_cree_dossier(self, tmp_path):
        sous = tmp_path / "nouveau"
        ecrire_manifeste(sous, {"1": {"fichier": "a.jpg"}})
        assert (sous / ".etat.json").exists()

    def test_utf8_preserve(self, tmp_path):
        m = {"1": {"fichier": "été/genève.jpg"}}
        ecrire_manifeste(tmp_path, m)
        assert lire_manifeste(tmp_path) == m


# --------------------------------------------------------------------------- #
# lister_supprimees, restaurer
# --------------------------------------------------------------------------- #

class TestListerSupprimees:
    def test_dossier_vide(self, tmp_path):
        assert lister_supprimees(tmp_path) == []

    def test_filtre_les_supprimees(self, tmp_path):
        ecrire_manifeste(tmp_path, {
            "1": {"fichier": "a.jpg"},
            "2": {"fichier": "b.jpg", "supprime": "2026-01-02T10:00:00"},
            "3": {"fichier": "c.jpg", "supprime": "2026-01-01T10:00:00"},
        })
        e = lister_supprimees(tmp_path)
        assert len(e) == 2
        # tri par horodatage : la plus ancienne d'abord
        assert e[0]["id"] == "3"
        assert e[1]["id"] == "2"

    def test_id_transporte(self, tmp_path):
        ecrire_manifeste(tmp_path, {
            "42": {"fichier": "x.jpg", "supprime": "2026-01-01"},
        })
        e = lister_supprimees(tmp_path)
        assert e[0]["id"] == "42"
        assert e[0]["fichier"] == "x.jpg"


class TestRestaurer:
    def test_retire_supprime_pose_restaure(self, tmp_path):
        ecrire_manifeste(tmp_path, {
            "1": {"fichier": "a.jpg", "supprime": "2026-01-01"},
        })
        assert restaurer(tmp_path, ["1"]) == 1
        entree = lire_manifeste(tmp_path)["1"]
        assert "supprime" not in entree
        assert entree["restaure"] is True

    def test_id_inconnu_ignore(self, tmp_path):
        ecrire_manifeste(tmp_path, {"1": {"fichier": "a.jpg"}})
        assert restaurer(tmp_path, ["999"]) == 0

    def test_entree_sans_supprime_ignoree(self, tmp_path):
        ecrire_manifeste(tmp_path, {"1": {"fichier": "a.jpg"}})
        assert restaurer(tmp_path, ["1"]) == 0

    def test_plusieurs_ids(self, tmp_path):
        ecrire_manifeste(tmp_path, {
            "1": {"fichier": "a.jpg", "supprime": "2026-01-01"},
            "2": {"fichier": "b.jpg", "supprime": "2026-01-02"},
            "3": {"fichier": "c.jpg"},
        })
        assert restaurer(tmp_path, ["1", "2", "3"]) == 2

    def test_id_entier_normalise(self, tmp_path):
        ecrire_manifeste(tmp_path, {
            "42": {"fichier": "a.jpg", "supprime": "2026-01-01"},
        })
        # restaurer accepte des ints, doit str() en interne
        assert restaurer(tmp_path, [42]) == 1


# --------------------------------------------------------------------------- #
# supprimer_image
# --------------------------------------------------------------------------- #

class TestSupprimerImage:
    def test_suppression_normale(self, tmp_path):
        (tmp_path / "galerie-a").mkdir()
        fichier = tmp_path / "galerie-a" / "match.jpg"
        fichier.write_bytes(b"x" * 42)
        autre = tmp_path / "galerie-a" / "podium.jpg"
        autre.write_bytes(b"y" * 10)
        ecrire_manifeste(tmp_path, {
            "111": {"fichier": "galerie-a/match.jpg", "taille": 42, "etag": "abc"},
            "222": {"fichier": "galerie-a/podium.jpg", "taille": 10, "etag": "def"},
        })

        assert supprimer_image(tmp_path, fichier) is True
        assert not fichier.exists()
        m = lire_manifeste(tmp_path)
        assert "supprime" in m["111"]
        assert "supprime" not in m["222"]
        assert m["222"]["etag"] == "def"

    def test_restaure_retire(self, tmp_path):
        fichier = tmp_path / "image.jpg"
        fichier.write_bytes(b"y")
        ecrire_manifeste(tmp_path, {
            "1": {"fichier": "image.jpg", "taille": 1, "restaure": True},
        })
        assert supprimer_image(tmp_path, fichier) is True
        entree = lire_manifeste(tmp_path)["1"]
        assert "restaure" not in entree
        assert "supprime" in entree

    def test_hors_dossier(self, tmp_path):
        interne = tmp_path / "interne"
        externe = tmp_path / "externe"
        interne.mkdir()
        externe.mkdir()
        intrus = externe / "photo.jpg"
        intrus.write_bytes(b"z")
        ecrire_manifeste(interne, {"1": {"fichier": "photo.jpg", "taille": 1}})
        assert supprimer_image(interne, intrus) is False
        assert intrus.exists()
        assert "supprime" not in lire_manifeste(interne)["1"]

    def test_dossier_voisin_meme_prefixe(self, tmp_path):
        """`commonpath` évite le piège d'un `startswith` naïf."""
        dossier = tmp_path / "photos"
        voisin = tmp_path / "photos-archives"
        dossier.mkdir()
        voisin.mkdir()
        intrus = voisin / "x.jpg"
        intrus.write_bytes(b"z")
        assert supprimer_image(dossier, intrus) is False
        assert intrus.exists()

    def test_antislash_manifeste(self, tmp_path):
        (tmp_path / "galerie-b").mkdir()
        fichier = tmp_path / "galerie-b" / "match.jpg"
        fichier.write_bytes(b"y")
        ecrire_manifeste(tmp_path, {"77": {"fichier": "galerie-b\\match.jpg"}})
        assert supprimer_image(tmp_path, fichier) is True
        assert "supprime" in lire_manifeste(tmp_path)["77"]

    def test_fichier_deja_absent(self, tmp_path):
        fantome = tmp_path / "disparu.jpg"
        ecrire_manifeste(tmp_path, {"9": {"fichier": "disparu.jpg", "taille": 5}})
        assert supprimer_image(tmp_path, fantome) is True
        assert "supprime" in lire_manifeste(tmp_path)["9"]

    def test_fichier_pas_dans_manifeste(self, tmp_path):
        # fichier valide dans le dossier mais inconnu du manifeste : effacement
        # réussi, rien à marquer
        fichier = tmp_path / "orphelin.jpg"
        fichier.write_bytes(b"o")
        ecrire_manifeste(tmp_path, {"1": {"fichier": "autre.jpg"}})
        assert supprimer_image(tmp_path, fichier) is True
        assert not fichier.exists()
        assert "supprime" not in lire_manifeste(tmp_path)["1"]

    def test_fichier_egale_dossier_refuse(self, tmp_path):
        # supprimer le dossier lui-même ne doit surtout pas être accepté
        assert supprimer_image(tmp_path, tmp_path) is False

    def test_realpath_qui_leve_renvoie_false(self, tmp_path, monkeypatch):
        # OSError sur realpath (chemin fantôme sous Windows par ex.) → False
        def boum(*_a, **_kw):
            raise OSError("no such")
        monkeypatch.setattr("os.path.realpath", boum)
        assert supprimer_image(tmp_path, tmp_path / "x.jpg") is False

    def test_commonpath_valueerror_renvoie_false(self, tmp_path, monkeypatch):
        # ValueError = deux lecteurs différents sous Windows
        def boum(_paths):
            raise ValueError("mixed drives")
        monkeypatch.setattr("os.path.commonpath", boum)
        assert supprimer_image(tmp_path, tmp_path / "x.jpg") is False

    def test_unlink_oserror_renvoie_false(self, tmp_path):
        # PermissionError descend d'OSError : le fichier reste, on renvoie False
        fichier = tmp_path / "verrouille.jpg"
        fichier.write_bytes(b"y")
        ecrire_manifeste(tmp_path, {"1": {"fichier": "verrouille.jpg"}})
        with patch("pathlib.Path.unlink",
                   side_effect=PermissionError("verrouille")):
            assert supprimer_image(tmp_path, fichier) is False
        # la marque n'a pas été posée puisque l'effacement a échoué
        assert "supprime" not in lire_manifeste(tmp_path)["1"]

    def test_entree_manifeste_sans_fichier_ignoree(self, tmp_path):
        # une entrée sans champ 'fichier' ne doit pas planter la recherche
        fichier = tmp_path / "cible.jpg"
        fichier.write_bytes(b"y")
        ecrire_manifeste(tmp_path, {
            "1": {"taille": 42},   # pas de fichier
            "2": {"fichier": "cible.jpg"},
        })
        assert supprimer_image(tmp_path, fichier) is True
        assert "supprime" in lire_manifeste(tmp_path)["2"]


# --------------------------------------------------------------------------- #
# Moteur : méthodes utilitaires (pas de I/O réseau)
# --------------------------------------------------------------------------- #

def _moteur(tmp_path, **kw):
    """Construit un Moteur avec un Options par défaut, surchargable."""
    options = Options(dossier=tmp_path, delai=0, **kw)
    return Moteur(options)


class TestFichierComplet:
    def test_fichier_absent(self, tmp_path):
        assert Moteur.fichier_complet(tmp_path / "absent.jpg", None, None) is False

    def test_taille_nulle(self, tmp_path):
        f = tmp_path / "vide.jpg"
        f.write_bytes(b"")
        assert Moteur.fichier_complet(f, None, None) is False

    def test_taille_correcte_via_etat(self, tmp_path):
        f = tmp_path / "ok.jpg"
        f.write_bytes(b"abcde")
        assert Moteur.fichier_complet(f, {"taille": 5}, None) is True

    def test_taille_erronee(self, tmp_path):
        f = tmp_path / "trop.jpg"
        f.write_bytes(b"abcde")
        assert Moteur.fichier_complet(f, {"taille": 999}, None) is False

    def test_repli_sur_taille_api(self, tmp_path):
        f = tmp_path / "sans-etat.jpg"
        f.write_bytes(b"abc")
        assert Moteur.fichier_complet(f, None, 3) is True
        assert Moteur.fichier_complet(f, {}, 3) is True
        assert Moteur.fichier_complet(f, {}, 42) is False

    def test_sans_taille_attendue_accepte(self, tmp_path):
        # ni état.taille ni taille_api : on croit ce qu'on a
        f = tmp_path / "x.jpg"
        f.write_bytes(b"a")
        assert Moteur.fichier_complet(f, None, None) is True


class TestDossierPour:
    def _media(self, url="https://x/wp-content/uploads/2025/03/img.jpg", post=None):
        return {"source_url": url, "post": post}

    def test_plat(self, tmp_path):
        m = _moteur(tmp_path, classement="plat")
        assert m.dossier_pour(self._media(), {}) == ""

    def test_date(self, tmp_path):
        m = _moteur(tmp_path, classement="date")
        assert m.dossier_pour(self._media(), {}) == "2025-03"

    def test_date_sans_match(self, tmp_path):
        m = _moteur(tmp_path, classement="date")
        assert m.dossier_pour(self._media("https://x/autre-chemin.jpg"), {}) == "divers"

    def test_galerie_avec_titre(self, tmp_path):
        m = _moteur(tmp_path, classement="galerie")
        media = self._media(post=17)
        assert m.dossier_pour(media, {17: "match-du-siecle"}) == "match-du-siecle"

    def test_galerie_sans_titre(self, tmp_path):
        m = _moteur(tmp_path, classement="galerie")
        media = self._media(post=17)
        assert m.dossier_pour(media, {}) == "contenu-17"

    def test_galerie_sans_post_bascule_date(self, tmp_path):
        m = _moteur(tmp_path, classement="galerie")
        media = self._media(post=None)
        assert m.dossier_pour(media, {}) == "2025-03"


class TestCheminLibre:
    def test_chemin_disponible(self, tmp_path):
        m = _moteur(tmp_path)
        dest = tmp_path / "sous" / "match.jpg"
        pris = set()
        r = m.chemin_libre(dest, 42, pris)
        assert r == dest
        assert "sous/match.jpg" in {p.replace("\\", "/") for p in pris}

    def test_conflit_suffixe_id(self, tmp_path):
        m = _moteur(tmp_path)
        pris = {"sous/match.jpg", "sous\\match.jpg"}
        dest = tmp_path / "sous" / "match.jpg"
        r = m.chemin_libre(dest, 42, pris)
        assert r.name == "match-42.jpg"


# --------------------------------------------------------------------------- #
# Moteur.telecharger — session HTTP mockée
# --------------------------------------------------------------------------- #

class FakeResponse:
    """Réponse HTTP factice, iterable comme celle de requests."""

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
        statut, infos = m.telecharger("https://x/f.jpg", dest, None)
        assert statut == "ok"
        assert dest.read_bytes() == b"payload"
        assert infos["taille"] == 7
        assert infos["etag"] == "e1"
        assert infos["modifie"] == "m1"

    def test_304_inchange(self, tmp_path):
        m = _moteur(tmp_path, verifier=True)
        m.session = MagicMock()
        m.session.get.return_value = FakeResponse(304)
        dest = tmp_path / "existe.jpg"
        dest.write_bytes(b"deja")
        statut, infos = m.telecharger("https://x/f.jpg", dest,
                                      {"etag": "e1", "taille": 4})
        assert statut == "inchangé"
        # l'état renvoyé est celui passé, sans altération
        assert infos == {"etag": "e1", "taille": 4}

    def test_404_introuvable(self, tmp_path):
        m = _moteur(tmp_path)
        m.session = MagicMock()
        m.session.get.return_value = FakeResponse(404)
        dest = tmp_path / "sortie.jpg"
        statut, infos = m.telecharger("https://x/f.jpg", dest, None)
        assert statut == "introuvable"
        assert infos is None
        assert not dest.exists()

    def test_reprise_depuis_part(self, tmp_path):
        # un .part existant déclenche un GET Range → 206
        m = _moteur(tmp_path)
        m.session = MagicMock()
        m.session.get.return_value = FakeResponse(206, {}, b"XYZ")
        dest = tmp_path / "reprise.jpg"
        (dest.with_suffix(dest.suffix + ".part")).write_bytes(b"AB")
        statut, infos = m.telecharger("https://x/f.jpg", dest, None)
        assert statut == "repris"
        # le contenu final concatène le .part et la suite téléchargée
        assert dest.read_bytes() == b"ABXYZ"
        # le Range a été envoyé
        _, kwargs = m.session.get.call_args
        assert kwargs["headers"].get("Range") == "bytes=2-"

    def test_416_relance_sans_range(self, tmp_path):
        # 416 (Range invalide) → suppression du .part et reprise à zéro
        m = _moteur(tmp_path)
        m.session = MagicMock()
        m.session.get.side_effect = [
            FakeResponse(416),
            FakeResponse(200, {"ETag": "e"}, b"neuf"),
        ]
        dest = tmp_path / "r.jpg"
        (dest.with_suffix(dest.suffix + ".part")).write_bytes(b"AB")
        statut, infos = m.telecharger("https://x/f.jpg", dest, None)
        assert statut == "ok"
        assert dest.read_bytes() == b"neuf"

    def test_if_modified_since_utilise(self, tmp_path):
        # etat sans etag mais avec modifie → header conditionnel autre
        m = _moteur(tmp_path, verifier=True)
        m.session = MagicMock()
        m.session.get.return_value = FakeResponse(304)
        dest = tmp_path / "x.jpg"
        dest.write_bytes(b"deja")
        m.telecharger("https://x/f.jpg", dest,
                      {"modifie": "Wed, 01 Jan 2026 00:00:00 GMT", "taille": 4})
        _, kw = m.session.get.call_args
        assert kw["headers"].get("If-Modified-Since") == \
            "Wed, 01 Jan 2026 00:00:00 GMT"

    def test_erreur_reseau(self, tmp_path):
        m = _moteur(tmp_path)
        m.session = MagicMock()
        m.session.get.side_effect = requests.ConnectionError("boum")
        dest = tmp_path / "s.jpg"
        statut, infos = m.telecharger("https://x/f.jpg", dest, None)
        assert statut.startswith("erreur")
        assert infos is None
        assert not dest.exists()

    def test_interruption_conserve_part(self, tmp_path):
        # l'arrêt en pleine lecture doit laisser le .part pour la reprise
        m = _moteur(tmp_path)
        m.arret.set()   # coupe dès le premier bloc

        class GrosseResponse(FakeResponse):
            def iter_content(self_, chunk_size):
                yield b"A" * chunk_size

        m.session = MagicMock()
        m.session.get.return_value = GrosseResponse(200, {}, b"")
        dest = tmp_path / "int.jpg"
        with pytest.raises(Interrompu):
            m.telecharger("https://x/f.jpg", dest, None)
        assert (dest.with_suffix(dest.suffix + ".part")).exists()
        assert not dest.exists()


# --------------------------------------------------------------------------- #
# Moteur.executer — orchestration
# --------------------------------------------------------------------------- #

def _media(id_, url="https://x/img.jpg", width=1600, post=None):
    return {
        "id": id_,
        "source_url": url,
        "media_details": {"width": width},
        "post": post,
        "date": "2026-01-01T00:00:00",
    }


class TestExecuter:
    def test_ignore_les_supprimees(self, tmp_path):
        ecrire_manifeste(tmp_path, {
            "42": {"fichier": "photo.jpg", "taille": 100,
                   "supprime": "2026-01-01T00:00:00"},
        })
        moteur = _moteur(tmp_path)
        with patch.object(moteur, "lister_medias", return_value=[_media(42)]), \
             patch.object(moteur, "telecharger") as tel:
            res = moteur.executer()
        assert res.ignorees == 1
        assert tel.call_count == 0
        assert "supprime" in lire_manifeste(tmp_path)["42"]

    def test_detecte_effacement_disque(self, tmp_path):
        # état complet mais fichier disparu → marquée supprime, pas de download
        ecrire_manifeste(tmp_path, {
            "8": {"fichier": "manquant.jpg", "taille": 10},
        })
        moteur = _moteur(tmp_path)
        with patch.object(moteur, "lister_medias", return_value=[_media(8)]), \
             patch.object(moteur, "telecharger") as tel:
            res = moteur.executer()
        assert res.supprimees == 1
        assert tel.call_count == 0
        assert "supprime" in lire_manifeste(tmp_path)["8"]

    def test_deja_present(self, tmp_path):
        f = tmp_path / "ok.jpg"
        f.write_bytes(b"1234567890")
        ecrire_manifeste(tmp_path, {
            "1": {"fichier": "ok.jpg", "taille": 10},
        })
        moteur = _moteur(tmp_path)
        with patch.object(moteur, "lister_medias", return_value=[_media(1)]), \
             patch.object(moteur, "telecharger") as tel:
            res = moteur.executer()
        assert res.deja_presentes == 1
        assert tel.call_count == 0

    def test_telechargement(self, tmp_path):
        moteur = _moteur(tmp_path, classement="date")
        with patch.object(moteur, "lister_medias",
                          return_value=[_media(5,
                                               url="https://x/wp-content/uploads/2026/03/f.jpg")]), \
             patch.object(moteur, "telecharger",
                          return_value=("ok", {"taille": 12, "etag": "e",
                                               "modifie": "m", "url": "u"})):
            res = moteur.executer()
        assert res.telechargees == 1
        assert res.octets == 12
        m = lire_manifeste(tmp_path)
        assert "5" in m
        assert m["5"]["fichier"].replace("\\", "/") == "2026-03/f.jpg"

    def test_reprise_incrementale(self, tmp_path):
        moteur = _moteur(tmp_path, classement="date")
        with patch.object(moteur, "lister_medias",
                          return_value=[_media(5,
                                               url="https://x/wp-content/uploads/2026/03/f.jpg")]), \
             patch.object(moteur, "telecharger",
                          return_value=("repris", {"taille": 3, "etag": "",
                                                   "modifie": "", "url": "u"})):
            res = moteur.executer()
        assert res.reprises == 1
        assert res.octets == 3

    def test_echec_reseau(self, tmp_path):
        moteur = _moteur(tmp_path, classement="date")
        with patch.object(moteur, "lister_medias",
                          return_value=[_media(5,
                                               url="https://x/wp-content/uploads/2026/03/f.jpg")]), \
             patch.object(moteur, "telecharger",
                          return_value=("erreur : boum", None)):
            res = moteur.executer()
        assert res.echecs == 1

    def test_aucune_image(self, tmp_path):
        moteur = _moteur(tmp_path)
        with patch.object(moteur, "lister_medias", return_value=[]):
            res = moteur.executer()
        assert "Aucune image" in res.message

    def test_filtre_largeur_min(self, tmp_path):
        moteur = _moteur(tmp_path, classement="date", largeur_min=1000)
        petits = _media(1, width=200)
        grand = _media(2, url="https://x/wp-content/uploads/2026/04/big.jpg",
                       width=2000)
        with patch.object(moteur, "lister_medias",
                          return_value=[petits, grand]), \
             patch.object(moteur, "telecharger",
                          return_value=("ok", {"taille": 1, "etag": "",
                                               "modifie": "", "url": "u"})):
            res = moteur.executer()
        assert res.telechargees == 1   # seul le grand a été traité

    def test_interruption(self, tmp_path):
        moteur = _moteur(tmp_path)
        moteur.arret.set()

        def leve(*_a, **_kw):
            raise Interrompu()

        with patch.object(moteur, "lister_medias", side_effect=leve):
            res = moteur.executer()
        assert res.interrompu is True
        assert "Interrompu" in res.message

    def test_erreur_api_capturee(self, tmp_path):
        moteur = _moteur(tmp_path)
        with patch.object(moteur, "lister_medias",
                          side_effect=RuntimeError("API HS")):
            res = moteur.executer()
        assert "API HS" in res.message
        assert res.echecs == 0   # RuntimeError ≠ échec par image

    def test_force_ignore_manifeste(self, tmp_path):
        # avec force, une image marquée supprime doit être retéléchargée
        ecrire_manifeste(tmp_path, {
            "1": {"fichier": "a.jpg", "taille": 100,
                  "supprime": "2026-01-01T00:00:00"},
        })
        moteur = _moteur(tmp_path, classement="date", force=True)
        with patch.object(moteur, "lister_medias",
                          return_value=[_media(1,
                                               url="https://x/wp-content/uploads/2026/03/a.jpg")]), \
             patch.object(moteur, "telecharger",
                          return_value=("ok", {"taille": 1, "etag": "",
                                               "modifie": "", "url": "u"})) as tel:
            res = moteur.executer()
        assert res.telechargees == 1
        assert tel.call_count == 1


# --------------------------------------------------------------------------- #
# lister_medias / _bases_rest / resoudre_parents : boucle sur _api mocké
# --------------------------------------------------------------------------- #

class TestListerMedias:
    def test_pagination(self, tmp_path):
        moteur = _moteur(tmp_path)
        page1 = [_media(1), _media(2)]
        page2 = [_media(3)]
        appels = []

        def faux_api(chemin, params=None):
            appels.append(params.get("page"))
            headers = {"X-WP-Total": "3", "X-WP-TotalPages": "2"}
            if params["page"] == 1:
                return page1, headers
            return page2, headers

        with patch.object(moteur, "_api", side_effect=faux_api):
            r = moteur.lister_medias()
        assert [m["id"] for m in r] == [1, 2, 3]
        assert appels == [1, 2]

    def test_deduplication(self, tmp_path):
        moteur = _moteur(tmp_path)

        def faux_api(chemin, params=None):
            headers = {"X-WP-Total": "3", "X-WP-TotalPages": "2"}
            if params["page"] == 1:
                return [_media(1), _media(2)], headers
            # page 2 renvoie l'id 2 en double + 3 nouveau
            return [_media(2), _media(3)], headers

        with patch.object(moteur, "_api", side_effect=faux_api):
            r = moteur.lister_medias()
        assert sorted(m["id"] for m in r) == [1, 2, 3]

    def test_arret_immediat_si_pas_de_pages_totales(self, tmp_path):
        # sans pages_totales et un lot vide, la boucle sort dès la 1ʳᵉ page
        moteur = _moteur(tmp_path)
        appels = []

        def faux_api(chemin, params=None):
            appels.append(params.get("page"))
            return [], {"X-WP-TotalPages": "0"}

        with patch.object(moteur, "_api", side_effect=faux_api):
            r = moteur.lister_medias()
        assert r == []
        assert len(appels) == 1

    def test_stop_sur_deux_pages_vides_apres_contenu(self, tmp_path):
        # une fois pages_totales connu, il faut deux vides consécutives
        moteur = _moteur(tmp_path)
        appels = []

        def faux_api(chemin, params=None):
            appels.append(params.get("page"))
            headers = {"X-WP-Total": "1", "X-WP-TotalPages": "9"}
            if params["page"] == 1:
                return [_media(1)], headers
            return [], headers   # pages 2 et 3 vides

        with patch.object(moteur, "_api", side_effect=faux_api):
            r = moteur.lister_medias()
        assert [m["id"] for m in r] == [1]
        assert appels == [1, 2, 3]

    def test_stop_sur_400_via_lot_none_page1(self, tmp_path):
        # première page = None (400) : sortie immédiate
        moteur = _moteur(tmp_path)
        with patch.object(moteur, "_api",
                          return_value=(None, {"X-WP-TotalPages": "0"})):
            r = moteur.lister_medias()
        assert r == []

    def test_borne_par_pages_totales(self, tmp_path):
        moteur = _moteur(tmp_path)
        appels = []

        def faux_api(chemin, params=None):
            appels.append(params.get("page"))
            return [_media(params["page"])], {"X-WP-TotalPages": "3"}

        with patch.object(moteur, "_api", side_effect=faux_api):
            moteur.lister_medias()
        assert appels == [1, 2, 3]   # ne va pas au-delà de la 3e page

    def test_filtre_depuis_et_jusqua(self, tmp_path):
        moteur = _moteur(tmp_path, depuis="2026-01-01", jusqua="2026-12-31")
        capture = {}

        def faux_api(chemin, params=None):
            capture.update(params)
            return [], {"X-WP-TotalPages": "0"}

        with patch.object(moteur, "_api", side_effect=faux_api):
            moteur.lister_medias()
        assert capture["after"].startswith("2026-01-01T")
        assert capture["before"].startswith("2026-12-31T")


class TestBasesRest:
    def test_replie_sur_defaut_si_api_ko(self, tmp_path):
        moteur = _moteur(tmp_path)
        with patch.object(moteur, "_api", side_effect=RuntimeError("HS")):
            assert moteur._bases_rest() == ["posts", "pages"]

    def test_ecarte_types_techniques(self, tmp_path):
        moteur = _moteur(tmp_path)
        types = {
            "post": {"rest_base": "posts"},
            "page": {"rest_base": "pages"},
            "galerie": {"rest_base": "galeries"},
            "attachment": {"rest_base": "media"},
            "wp_block": {"rest_base": "blocks"},
            "nav_menu_item": {"rest_base": "menu-items"},
        }
        with patch.object(moteur, "_api", return_value=(types, {})):
            bases = moteur._bases_rest()
        assert "media" not in bases
        assert "blocks" not in bases
        assert "menu-items" not in bases
        # les galeries passent en premier grâce au tri (« galer »)
        assert bases[0] == "galeries"


class TestResoudreParents:
    def test_lookup_titre(self, tmp_path):
        moteur = _moteur(tmp_path)

        def faux_api(chemin, params=None):
            if chemin == "types":
                return {"post": {"rest_base": "posts"}}, {}
            items = [{"id": 42, "slug": "match-du-siecle",
                      "title": {"rendered": "Match du siècle"}}]
            return items, {}

        with patch.object(moteur, "_api", side_effect=faux_api):
            titres = moteur.resoudre_parents({42})
        assert titres == {42: "match-du-siecle"}

    def test_non_trouve_journalise(self, tmp_path):
        journal = []
        moteur = _moteur(tmp_path)
        moteur._journal = journal.append

        def faux_api(chemin, params=None):
            if chemin == "types":
                return {"post": {"rest_base": "posts"}}, {}
            return [], {}   # pas de correspondance

        with patch.object(moteur, "_api", side_effect=faux_api):
            titres = moteur.resoudre_parents({99})
        assert titres == {}
        # un message signale les galeries non identifiées
        assert any("non identifi" in m for m in journal)

    def test_set_vide(self, tmp_path):
        moteur = _moteur(tmp_path)
        assert moteur.resoudre_parents(set()) == {}

    def test_arret_boucle_quand_restants_vides(self, tmp_path):
        # premier base trouve tout : le second n'est jamais interrogé
        moteur = _moteur(tmp_path)
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

        with patch.object(moteur, "_api", side_effect=faux_api):
            titres = moteur.resoudre_parents({42})
        assert titres == {42: "match"}
        assert "posts" not in appels

    def test_runtime_error_sur_un_base_continue(self, tmp_path):
        # RuntimeError sur une base → on saute et on tente la suivante
        moteur = _moteur(tmp_path)

        def faux_api(chemin, params=None):
            if chemin == "types":
                return {
                    "a": {"rest_base": "galeries"},
                    "b": {"rest_base": "posts"},
                }, {}
            if chemin == "galeries":
                raise RuntimeError("HS")
            return [{"id": 42, "slug": "trouve"}], {}

        with patch.object(moteur, "_api", side_effect=faux_api):
            titres = moteur.resoudre_parents({42})
        assert titres == {42: "trouve"}


# --------------------------------------------------------------------------- #
# Moteur.__init__ : rôles par défaut
# --------------------------------------------------------------------------- #

class TestMoteurInit:
    def test_callbacks_par_defaut_sont_no_op(self, tmp_path):
        # sans callbacks : le moteur n'explose pas quand il « journalise »
        m = Moteur(Options(dossier=tmp_path, delai=0))
        m._journal("un message")
        m._progression(1, 2, "étiquette")   # rien ne lève

    def test_arret_par_defaut(self, tmp_path):
        m = Moteur(Options(dossier=tmp_path))
        assert m.arret is not None
        assert m.arret.is_set() is False


# --------------------------------------------------------------------------- #
# _api : rejeux, cas 400, RuntimeError
# --------------------------------------------------------------------------- #

class TestPlomberieMoteur:
    def test_verifier_arret_leve_interrompu(self, tmp_path):
        m = _moteur(tmp_path)
        m.arret.set()
        with pytest.raises(Interrompu):
            m._verifier_arret()

    def test_verifier_arret_silencieux_sinon(self, tmp_path):
        m = _moteur(tmp_path)
        m._verifier_arret()   # rien ne lève

    def test_pause_dort_puis_rend_la_main(self, tmp_path):
        m = _moteur(tmp_path)
        # une très courte pause exerce la boucle sleep
        import time
        avant = time.monotonic()
        m._pause(0.01)
        assert time.monotonic() - avant >= 0.005


class TestApi:
    def test_reponse_400_renvoie_none(self, tmp_path):
        m = _moteur(tmp_path)
        m.session = MagicMock()
        m.session.get.return_value = FakeResponse(400, {"h": "1"})
        payload, headers = m._api("media", {"page": 999})
        assert payload is None
        assert headers.get("h") == "1"

    def test_reponse_normale(self, tmp_path):
        m = _moteur(tmp_path)
        rep = MagicMock(status_code=200, headers={"h": "1"})
        rep.json.return_value = [{"id": 1}]
        rep.raise_for_status = MagicMock()
        m.session = MagicMock()
        m.session.get.return_value = rep
        payload, _ = m._api("media")
        assert payload == [{"id": 1}]

    def test_rejeu_puis_succes(self, tmp_path):
        m = _moteur(tmp_path)
        m.session = MagicMock()
        bon = MagicMock(status_code=200, headers={})
        bon.json.return_value = {"ok": True}
        bon.raise_for_status = MagicMock()
        m.session.get.side_effect = [requests.ConnectionError("boum"), bon]
        with patch.object(m, "_pause"):   # évite les 2 secondes de vraie pause
            payload, _ = m._api("types")
        assert payload == {"ok": True}
        assert m.session.get.call_count == 2

    def test_echec_repete_leve_runtime(self, tmp_path):
        m = _moteur(tmp_path)
        m.session = MagicMock()
        m.session.get.side_effect = requests.ConnectionError("HS")
        with patch.object(m, "_pause"), pytest.raises(RuntimeError):
            m._api("media")


# --------------------------------------------------------------------------- #
# charger_manifeste : options force et repli sur vide
# --------------------------------------------------------------------------- #

class TestChargerManifeste:
    def test_force_efface_le_manifeste_en_memoire(self, tmp_path):
        ecrire_manifeste(tmp_path, {"1": {"fichier": "a.jpg"}})
        m = _moteur(tmp_path, force=True)
        assert m.charger_manifeste() == {}

    def test_absent_renvoie_vide(self, tmp_path):
        m = _moteur(tmp_path)
        assert m.charger_manifeste() == {}

    def test_illisible_journalise(self, tmp_path):
        chemin_manifeste(tmp_path).write_text("{invalid")
        journal = []
        m = _moteur(tmp_path)
        m._journal = journal.append
        assert m.charger_manifeste() == {}
        assert any("illisible" in j for j in journal)


# --------------------------------------------------------------------------- #
# executer : branches complémentaires (inchangé, résolution galerie, OSError…)
# --------------------------------------------------------------------------- #

class TestExecuterExtra:
    def test_site_configurable_et_slash_final_normalise(self, tmp_path):
        moteur = _moteur(tmp_path, site="https://example.test/")
        assert moteur.base == "https://example.test"
        assert moteur.api == "https://example.test/wp-json/wp/v2"

    def test_status_inchange_compte_dans_inchangees(self, tmp_path):
        # fichier connu à revérifier avec 304
        f = tmp_path / "ok.jpg"
        f.write_bytes(b"12345")
        ecrire_manifeste(tmp_path, {
            "1": {"fichier": "ok.jpg", "taille": 5, "etag": "e"},
        })
        moteur = _moteur(tmp_path, verifier=True)
        with patch.object(moteur, "lister_medias", return_value=[_media(1)]), \
             patch.object(moteur, "telecharger",
                          return_value=("inchangé",
                                        {"fichier": "ok.jpg", "taille": 5, "etag": "e"})):
            res = moteur.executer()
        assert res.inchangees == 1

    def test_resoudre_galeries_appele_en_mode_galerie(self, tmp_path):
        moteur = _moteur(tmp_path, classement="galerie")
        with patch.object(moteur, "lister_medias",
                          return_value=[_media(1, post=42)]), \
             patch.object(moteur, "resoudre_parents",
                          return_value={42: "match-42"}) as res_parents, \
             patch.object(moteur, "telecharger",
                          return_value=("ok", {"taille": 1, "etag": "",
                                               "modifie": "", "url": "u"})):
            res = moteur.executer()
        assert res.telechargees == 1
        res_parents.assert_called_once()
        # le fichier a bien été rangé dans le dossier « match-42 »
        m = lire_manifeste(tmp_path)
        assert m["1"]["fichier"].replace("\\", "/").startswith("match-42/")

    def test_oserror_capturee(self, tmp_path):
        moteur = _moteur(tmp_path)
        with patch.object(moteur, "lister_medias",
                          side_effect=OSError("disque plein")):
            res = moteur.executer()
        assert "disque plein" in res.message

    def test_journalise_filtrage_largeur(self, tmp_path):
        moteur = _moteur(tmp_path, classement="date", largeur_min=1000)
        journal = []
        moteur._journal = journal.append
        with patch.object(moteur, "lister_medias",
                          return_value=[_media(1, width=200), _media(2, width=300)]):
            moteur.executer()
        assert any("écarté" in m for m in journal)

    def test_sauvegarde_periodique(self, tmp_path):
        # 26 images : sauver_manifeste doit être appelé au moins à la 25ème
        # et une fois de plus dans finally
        moteur = _moteur(tmp_path, classement="date")
        medias = [_media(i, url=f"https://x/wp-content/uploads/2026/03/f{i}.jpg")
                  for i in range(1, 27)]
        with patch.object(moteur, "lister_medias", return_value=medias), \
             patch.object(moteur, "telecharger",
                          return_value=("ok", {"taille": 1, "etag": "",
                                               "modifie": "", "url": "u"})), \
             patch.object(moteur, "sauver_manifeste") as sauver:
            moteur.executer()
        # au moins 2 appels : périodique + finally
        assert sauver.call_count >= 2


# --------------------------------------------------------------------------- #
# Cache API : lire, écrire, effet sur les runs suivants
# --------------------------------------------------------------------------- #

class TestCacheAPI:
    def test_chemin(self, tmp_path):
        assert chemin_cache(tmp_path) == tmp_path / ".cache.json"

    def test_lire_absent(self, tmp_path):
        assert lire_cache(tmp_path) == {}

    def test_lire_json_invalide(self, tmp_path):
        chemin_cache(tmp_path).write_text("{pas du json")
        assert lire_cache(tmp_path) == {}

    def test_ecrire_puis_relire(self, tmp_path):
        cache = {"derniere_date_media": "2026-05-01T12:00:00",
                 "titres_parents": {"42": "match"}}
        ecrire_cache(tmp_path, cache)
        assert lire_cache(tmp_path) == cache

    def test_charger_cache_ignore_si_force(self, tmp_path):
        ecrire_cache(tmp_path, {"site": "https://x", "derniere_date_media": "2026"})
        m = _moteur(tmp_path, force=True)
        assert m.charger_cache() == {}

    def test_charger_cache_ignore_si_desactive(self, tmp_path):
        ecrire_cache(tmp_path, {"site": "https://x", "derniere_date_media": "2026"})
        m = _moteur(tmp_path, utiliser_cache=False)
        assert m.charger_cache() == {}

    def test_charger_cache_ignore_si_site_change(self, tmp_path):
        # cache écrit pour un autre site : pas d'exploitation croisée
        ecrire_cache(tmp_path, {"site": "https://autre.example",
                                "derniere_date_media": "2026"})
        m = _moteur(tmp_path, site="https://nouveau.example")
        assert m.charger_cache() == {}

    def test_charger_cache_meme_site(self, tmp_path):
        ecrire_cache(tmp_path, {"site": "https://x", "derniere_date_media": "2026"})
        m = _moteur(tmp_path, site="https://x")
        assert m.charger_cache()["derniere_date_media"] == "2026"

    def test_sauver_ajoute_le_site(self, tmp_path):
        m = _moteur(tmp_path, site="https://y")
        m.sauver_cache({"derniere_date_media": "2026-01-01T00:00:00"})
        stocke = lire_cache(tmp_path)
        assert stocke["site"] == "https://y"
        assert stocke["derniere_date_media"] == "2026-01-01T00:00:00"

    def test_sauver_no_op_si_force(self, tmp_path):
        m = _moteur(tmp_path, force=True)
        m.sauver_cache({"quelque": "chose"})
        assert not chemin_cache(tmp_path).exists()

    def test_executer_utilise_date_du_cache_comme_after(self, tmp_path):
        # Un cache pré-existant doit être passé à lister_medias comme override
        ecrire_cache(tmp_path, {
            "site": "https://x.example",
            "derniere_date_media": "2026-06-15T12:00:00",
        })
        m = _moteur(tmp_path, site="https://x.example", classement="date")
        capture = {}

        def faux_lister(depuis_override=None):
            capture["depuis"] = depuis_override
            return []

        with patch.object(m, "lister_medias", side_effect=faux_lister):
            m.executer()
        assert capture["depuis"] == "2026-06-15T12:00:00"

    def test_executer_prefere_depuis_utilisateur_au_cache(self, tmp_path):
        ecrire_cache(tmp_path, {"site": "https://x", "derniere_date_media": "2026"})
        m = _moteur(tmp_path, site="https://x", depuis="2020-01-01",
                    classement="date")
        capture = {}

        def faux_lister(depuis_override=None):
            capture["depuis"] = depuis_override
            return []

        with patch.object(m, "lister_medias", side_effect=faux_lister):
            m.executer()
        # avec `depuis` utilisateur, on n'injecte PAS la date du cache
        assert capture["depuis"] is None

    def test_executer_met_a_jour_la_date_max(self, tmp_path):
        m = _moteur(tmp_path, site="https://x", classement="date")
        medias = [
            _media(1, url="https://x/wp-content/uploads/2026/03/a.jpg"),
            _media(2, url="https://x/wp-content/uploads/2026/06/b.jpg"),
        ]
        medias[0]["date"] = "2026-03-10T08:00:00"
        medias[1]["date"] = "2026-06-20T09:30:00"
        with patch.object(m, "lister_medias", return_value=medias), \
             patch.object(m, "telecharger",
                          return_value=("ok", {"taille": 1, "etag": "",
                                               "modifie": "", "url": "u"})):
            m.executer()
        cache = lire_cache(tmp_path)
        assert cache["derniere_date_media"] == "2026-06-20T09:30:00"
        assert cache["site"] == "https://x"

    def test_executer_cache_les_titres_de_galeries(self, tmp_path):
        m = _moteur(tmp_path, site="https://x", classement="galerie")
        media = _media(1, url="https://x/wp-content/uploads/2026/03/a.jpg", post=42)
        with patch.object(m, "lister_medias", return_value=[media]), \
             patch.object(m, "resoudre_parents",
                          return_value={42: "match-a"}) as res_p, \
             patch.object(m, "telecharger",
                          return_value=("ok", {"taille": 1, "etag": "",
                                               "modifie": "", "url": "u"})):
            m.executer()
        assert lire_cache(tmp_path)["titres_parents"] == {"42": "match-a"}
        res_p.assert_called_once()

    def test_executer_reutilise_titres_caches(self, tmp_path):
        # Cache pré-rempli : le prochain run n'appelle plus l'API pour cet ID
        ecrire_cache(tmp_path, {
            "site": "https://x",
            "titres_parents": {"42": "match-cache"},
        })
        m = _moteur(tmp_path, site="https://x", classement="galerie")
        media = _media(1, url="https://x/wp-content/uploads/2026/03/a.jpg", post=42)
        with patch.object(m, "lister_medias", return_value=[media]), \
             patch.object(m, "_bases_rest") as bases, \
             patch.object(m, "telecharger",
                          return_value=("ok", {"taille": 1, "etag": "",
                                               "modifie": "", "url": "u"})):
            m.executer()
        # _bases_rest ne doit jamais avoir été appelé : le titre venait du cache
        bases.assert_not_called()
        # le fichier a été rangé dans « match-cache »
        assert lire_manifeste(tmp_path)["1"]["fichier"].replace("\\", "/") \
            .startswith("match-cache/")

    def test_resoudre_parents_court_circuite_sur_cache(self, tmp_path):
        m = _moteur(tmp_path)
        with patch.object(m, "_api") as api:
            r = m.resoudre_parents({42}, cache_titres={42: "deja-connu"})
        assert r == {42: "deja-connu"}
        api.assert_not_called()

    def test_interruption_ne_sauve_pas_le_cache(self, tmp_path):
        m = _moteur(tmp_path, site="https://x")
        with patch.object(m, "lister_medias", side_effect=Interrompu()):
            r = m.executer()
        assert r.interrompu is True
        # aucune écriture de cache : la date max n'a pas été validée
        assert not chemin_cache(tmp_path).exists()
