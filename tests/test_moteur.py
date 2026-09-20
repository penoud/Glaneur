"""Tests du moteur, en particulier de `supprimer_image`.

Les tests emploient pytest (`tmp_path`, monkeypatch via `unittest.mock`)
et n'ont besoin ni du réseau, ni des interfaces COM Windows.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from servette.engine import (
    Moteur,
    Options,
    ecrire_manifeste,
    lire_manifeste,
    supprimer_image,
)


# --------------------------------------------------------------------------- #
# supprimer_image
# --------------------------------------------------------------------------- #

def test_suppression_normale(tmp_path: Path) -> None:
    """Suppression réussie : fichier effacé, `supprime` posé sur la bonne entrée."""
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
    manifeste = lire_manifeste(tmp_path)
    assert "supprime" in manifeste["111"]
    # les autres entrées ne bougent pas
    assert "supprime" not in manifeste["222"]
    assert manifeste["222"]["etag"] == "def"


def test_restaure_retire(tmp_path: Path) -> None:
    """La marque `restaure` disparaît en même temps que l'image est effacée."""
    fichier = tmp_path / "image.jpg"
    fichier.write_bytes(b"y")
    ecrire_manifeste(tmp_path, {
        "1": {"fichier": "image.jpg", "taille": 1, "restaure": True},
    })

    assert supprimer_image(tmp_path, fichier) is True
    entree = lire_manifeste(tmp_path)["1"]
    assert "restaure" not in entree
    assert "supprime" in entree


def test_fichier_hors_dossier(tmp_path: Path) -> None:
    """Un fichier hors du dossier suivi n'est pas touché."""
    interne = tmp_path / "interne"
    externe = tmp_path / "externe"
    interne.mkdir()
    externe.mkdir()
    intrus = externe / "photo.jpg"
    intrus.write_bytes(b"z")

    ecrire_manifeste(interne, {"1": {"fichier": "photo.jpg", "taille": 1}})

    assert supprimer_image(interne, intrus) is False
    assert intrus.exists()
    # le manifeste n'a pas été modifié
    assert "supprime" not in lire_manifeste(interne)["1"]


def test_dossier_voisin_avec_meme_prefixe(tmp_path: Path) -> None:
    """`commonpath` évite le piège d'un `startswith` naïf."""
    dossier = tmp_path / "photos"
    voisin = tmp_path / "photos-archives"
    dossier.mkdir()
    voisin.mkdir()
    intrus = voisin / "image.jpg"
    intrus.write_bytes(b"z")

    assert supprimer_image(dossier, intrus) is False
    assert intrus.exists()


def test_antislash_dans_manifeste(tmp_path: Path) -> None:
    """Manifeste écrit sous Windows : les antislashs matchent les slashs disque."""
    (tmp_path / "galerie-b").mkdir()
    fichier = tmp_path / "galerie-b" / "match.jpg"
    fichier.write_bytes(b"y")

    ecrire_manifeste(tmp_path, {
        "77": {"fichier": "galerie-b\\match.jpg", "taille": 1},
    })

    assert supprimer_image(tmp_path, fichier) is True
    assert "supprime" in lire_manifeste(tmp_path)["77"]


def test_fichier_deja_absent(tmp_path: Path) -> None:
    """Le manifeste est marqué même si le fichier a déjà disparu du disque."""
    fantome = tmp_path / "disparu.jpg"   # n'a jamais existé
    ecrire_manifeste(tmp_path, {"9": {"fichier": "disparu.jpg", "taille": 5}})

    assert supprimer_image(tmp_path, fantome) is True
    assert "supprime" in lire_manifeste(tmp_path)["9"]


# --------------------------------------------------------------------------- #
# Comportement du moteur après une suppression
# --------------------------------------------------------------------------- #

def test_moteur_ignore_les_supprimees(tmp_path: Path) -> None:
    """La mise à jour ne retélécharge pas une image marquée `supprime`."""
    ecrire_manifeste(tmp_path, {
        "42": {
            "fichier": "galerie-c/photo.jpg",
            "taille": 100,
            "supprime": "2026-01-01T00:00:00",
        },
    })

    faux_medias = [{
        "id": 42,
        "source_url": "https://exemple/photo.jpg",
        "media_details": {"width": 1600},
        "post": None,
        "date": "2026-01-01T00:00:00",
    }]

    options = Options(dossier=tmp_path, delai=0)
    moteur = Moteur(options)
    with patch.object(moteur, "lister_medias", return_value=faux_medias), \
         patch.object(moteur, "telecharger") as fausse_dl:
        res = moteur.executer()

    assert res.ignorees == 1
    assert res.telechargees == 0
    assert res.reprises == 0
    # zéro requête fichier : `telecharger` n'a pas été appelée
    assert fausse_dl.call_count == 0
    # la marque de suppression a survécu à la réécriture
    assert "supprime" in lire_manifeste(tmp_path)["42"]
