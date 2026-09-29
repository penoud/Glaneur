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

class TestClean:
    def test_simple_title(self):
        assert clean("Match WordPress") == "match-wordpress"

    def test_accents_removed(self):
        # unidecode on NFKD: accents disappear
        assert clean("Été à Genève") == "ete-a-geneve"

    def test_html_entities(self):
        assert clean("WordPress &amp; Bâle") == "wordpress-bale"

    def test_dangerous_characters(self):
        # Windows rejects < > : " / \ | ? *
        r = clean('a<b>c:d"e/f\\g|h?i*j')
        for interdit in '<>:"/\\|?*':
            assert interdit not in r

    def test_multiple_spaces(self):
        assert clean("  a   b\tc\nd  ") == "a-b-c-d"

    def test_default_on_empty(self):
        assert clean("") == "divers"
        assert clean("   ") == "divers"
        assert clean(None) == "divers"

    def test_custom_default(self):
        assert clean("", defaut="nada") == "nada"

    def test_truncated_at_80(self):
        r = clean("a" * 200)
        assert len(r) == 80

    def test_no_trailing_period(self):
        # Windows rejects names ending with a dot
        assert not clean("Titre.").endswith(".")
        assert not clean("Titre...").endswith(".")


class TestFormatBytes:
    def test_bytes(self):
        assert format_bytes(0) == "0 o"
        assert format_bytes(512) == "512 o"

    def test_kilo(self):
        assert format_bytes(1024) == "1.0 Ko"
        assert format_bytes(1536) == "1.5 Ko"

    def test_mega(self):
        assert format_bytes(1024 * 1024) == "1.0 Mo"

    def test_giga(self):
        assert format_bytes(1024 ** 3) == "1.0 Go"

    def test_beyond_giga(self):
        # the loop caps at "Go", TB stays expressed in GB
        assert format_bytes(1024 ** 4).endswith(" Go")


# --------------------------------------------------------------------------- #
# Manifest — low-level I/O
# --------------------------------------------------------------------------- #

class TestManifestIO:
    def test_path(self, tmp_path):
        assert manifest_path(tmp_path) == tmp_path / ".etat.json"

    def test_read_absent(self, tmp_path):
        assert read_manifest(tmp_path) == {}

    def test_read_invalid_json(self, tmp_path):
        manifest_path(tmp_path).write_text("{ceci n'est pas du json")
        assert read_manifest(tmp_path) == {}

    def test_read_valid_json(self, tmp_path):
        manifest_path(tmp_path).write_text(
            json.dumps({"1": {"fichier": "a.jpg"}}), encoding="utf-8")
        assert read_manifest(tmp_path) == {"1": {"fichier": "a.jpg"}}

    def test_write_then_read(self, tmp_path):
        m = {"7": {"fichier": "x/y.jpg", "taille": 42}}
        write_manifest(tmp_path, m)
        assert read_manifest(tmp_path) == m

    def test_atomic_write(self, tmp_path):
        # after write, no .tmp file must remain
        write_manifest(tmp_path, {"1": {}})
        assert not (tmp_path / ".etat.json.tmp").exists()
        assert (tmp_path / ".etat.json").exists()

    def test_write_creates_directory(self, tmp_path):
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

class TestListDeleted:
    def test_empty_directory(self, tmp_path):
        assert list_deleted(tmp_path) == []

    def test_filters_deleted_entries(self, tmp_path):
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

    def test_id_is_carried(self, tmp_path):
        write_manifest(tmp_path, {
            "42": {"fichier": "x.jpg", "supprime": "2026-01-01"},
        })
        e = list_deleted(tmp_path)
        assert e[0]["id"] == "42"
        assert e[0]["fichier"] == "x.jpg"


class TestRestore:
    def test_removes_deleted_and_sets_restored(self, tmp_path):
        write_manifest(tmp_path, {
            "1": {"fichier": "a.jpg", "supprime": "2026-01-01"},
        })
        assert restore(tmp_path, ["1"]) == 1
        entree = read_manifest(tmp_path)["1"]
        assert "supprime" not in entree
        assert entree["restaure"] is True

    def test_unknown_id_ignored(self, tmp_path):
        write_manifest(tmp_path, {"1": {"fichier": "a.jpg"}})
        assert restore(tmp_path, ["999"]) == 0

    def test_entry_without_deleted_ignored(self, tmp_path):
        write_manifest(tmp_path, {"1": {"fichier": "a.jpg"}})
        assert restore(tmp_path, ["1"]) == 0

    def test_multiple_ids(self, tmp_path):
        write_manifest(tmp_path, {
            "1": {"fichier": "a.jpg", "supprime": "2026-01-01"},
            "2": {"fichier": "b.jpg", "supprime": "2026-01-02"},
            "3": {"fichier": "c.jpg"},
        })
        assert restore(tmp_path, ["1", "2", "3"]) == 2

    def test_integer_id_normalised(self, tmp_path):
        write_manifest(tmp_path, {
            "42": {"fichier": "a.jpg", "supprime": "2026-01-01"},
        })
        # restore accepts ints, must str() internally
        assert restore(tmp_path, [42]) == 1


# --------------------------------------------------------------------------- #
# delete_image
# --------------------------------------------------------------------------- #

class TestDeleteImage:
    def test_normal_deletion(self, tmp_path):
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

    def test_restored_flag_removed(self, tmp_path):
        fichier = tmp_path / "image.jpg"
        fichier.write_bytes(b"y")
        write_manifest(tmp_path, {
            "1": {"fichier": "image.jpg", "taille": 1, "restaure": True},
        })
        assert delete_image(tmp_path, fichier) is True
        entree = read_manifest(tmp_path)["1"]
        assert "restaure" not in entree
        assert "supprime" in entree

    def test_outside_directory(self, tmp_path):
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

    def test_sibling_directory_with_same_prefix(self, tmp_path):
        """`commonpath` avoids the trap of a naive `startswith`."""
        dossier = tmp_path / "photos"
        voisin = tmp_path / "photos-archives"
        dossier.mkdir()
        voisin.mkdir()
        intrus = voisin / "x.jpg"
        intrus.write_bytes(b"z")
        assert delete_image(dossier, intrus) is False
        assert intrus.exists()

    def test_backslash_in_manifest(self, tmp_path):
        (tmp_path / "galerie-b").mkdir()
        fichier = tmp_path / "galerie-b" / "match.jpg"
        fichier.write_bytes(b"y")
        write_manifest(tmp_path, {"77": {"fichier": "galerie-b\\match.jpg"}})
        assert delete_image(tmp_path, fichier) is True
        assert "supprime" in read_manifest(tmp_path)["77"]

    def test_file_already_absent(self, tmp_path):
        fantome = tmp_path / "disparu.jpg"
        write_manifest(tmp_path, {"9": {"fichier": "disparu.jpg", "taille": 5}})
        assert delete_image(tmp_path, fantome) is True
        assert "supprime" in read_manifest(tmp_path)["9"]

    def test_file_not_in_manifest(self, tmp_path):
        # valid file in the directory but unknown to the manifest: deletion
        # succeeds, nothing to mark
        fichier = tmp_path / "orphelin.jpg"
        fichier.write_bytes(b"o")
        write_manifest(tmp_path, {"1": {"fichier": "autre.jpg"}})
        assert delete_image(tmp_path, fichier) is True
        assert not fichier.exists()
        assert "supprime" not in read_manifest(tmp_path)["1"]

    def test_file_equal_to_directory_refused(self, tmp_path):
        # deleting the directory itself must absolutely not be accepted
        assert delete_image(tmp_path, tmp_path) is False

    def test_realpath_raising_returns_false(self, tmp_path, monkeypatch):
        # OSError on realpath (ghost path on Windows e.g.) → False
        def boum(*_a, **_kw):
            raise OSError("no such")
        monkeypatch.setattr("os.path.realpath", boum)
        assert delete_image(tmp_path, tmp_path / "x.jpg") is False

    def test_commonpath_valueerror_returns_false(self, tmp_path, monkeypatch):
        # ValueError = two different drives on Windows
        def boum(_paths):
            raise ValueError("mixed drives")
        monkeypatch.setattr("os.path.commonpath", boum)
        assert delete_image(tmp_path, tmp_path / "x.jpg") is False

    def test_unlink_oserror_returns_false(self, tmp_path):
        # PermissionError inherits from OSError: the file stays, we return False
        fichier = tmp_path / "verrouille.jpg"
        fichier.write_bytes(b"y")
        write_manifest(tmp_path, {"1": {"fichier": "verrouille.jpg"}})
        with patch("pathlib.Path.unlink",
                   side_effect=PermissionError("verrouille")):
            assert delete_image(tmp_path, fichier) is False
        # the mark was not set since the deletion failed
        assert "supprime" not in read_manifest(tmp_path)["1"]

    def test_manifest_entry_without_file_ignored(self, tmp_path):
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


def _element(ident, url="https://x/img.jpg", *, width=1600,
             group=None, month="2026-01", date="2026-01-01T00:00:00",
             size=None, filename=None, extra=None):
    """Builds an Element for orchestration tests.

    Defaults chosen to represent the average WordPress case; Djangoplicity
    tests have their own helper.
    """
    return Element(
        ident=str(ident),
        url=url,
        filename=filename if filename is not None
        else (url.rsplit("/", 1)[-1] if url else ""),
        date=date,
        month=month,
        width=width,
        size=size,
        group=str(group) if group is not None else None,
        extra=extra or {},
    )


class TestFileComplete:
    def test_file_absent(self, tmp_path):
        assert Engine.file_complete(tmp_path / "absent.jpg", None, None) is False

    def test_zero_size(self, tmp_path):
        f = tmp_path / "vide.jpg"
        f.write_bytes(b"")
        assert Engine.file_complete(f, None, None) is False

    def test_correct_size_via_state(self, tmp_path):
        f = tmp_path / "ok.jpg"
        f.write_bytes(b"abcde")
        assert Engine.file_complete(f, {"taille": 5}, None) is True

    def test_wrong_size(self, tmp_path):
        f = tmp_path / "trop.jpg"
        f.write_bytes(b"abcde")
        assert Engine.file_complete(f, {"taille": 999}, None) is False

    def test_fallback_to_api_size(self, tmp_path):
        f = tmp_path / "sans-etat.jpg"
        f.write_bytes(b"abc")
        assert Engine.file_complete(f, None, 3) is True
        assert Engine.file_complete(f, {}, 3) is True
        assert Engine.file_complete(f, {}, 42) is False

    def test_no_expected_size_accepted(self, tmp_path):
        # neither an expected size nor an API-reported size: we trust what we have
        f = tmp_path / "x.jpg"
        f.write_bytes(b"a")
        assert Engine.file_complete(f, None, None) is True


class TestFolderFor:
    """`folder_for` is generic: it no longer speaks of WP URLs, it reads
    `element.month` and `element.group`."""

    def test_flat(self, tmp_path):
        m = _moteur(tmp_path, sort_mode="flat")
        assert m.folder_for(_element(1), {}) == ""

    def test_date(self, tmp_path):
        m = _moteur(tmp_path, sort_mode="date")
        assert m.folder_for(_element(1, month="2025-03"), {}) == "2025-03"

    def test_date_without_month(self, tmp_path):
        m = _moteur(tmp_path, sort_mode="date")
        assert m.folder_for(_element(1, month=None), {}) == "divers"

    def test_gallery_with_title(self, tmp_path):
        m = _moteur(tmp_path, sort_mode="gallery")
        element = _element(1, group=17)
        assert m.folder_for(element, {"17": "match-du-siecle"}) == "match-du-siecle"

    def test_gallery_without_title(self, tmp_path):
        m = _moteur(tmp_path, sort_mode="gallery")
        element = _element(1, group=17)
        assert m.folder_for(element, {}) == "contenu-17"

    def test_gallery_without_group_falls_back_to_date(self, tmp_path):
        m = _moteur(tmp_path, sort_mode="gallery")
        element = _element(1, group=None, month="2025-03")
        assert m.folder_for(element, {}) == "2025-03"


class TestFreePath:
    def test_path_is_available(self, tmp_path):
        m = _moteur(tmp_path)
        dest = tmp_path / "sous" / "match.jpg"
        pris = set()
        r = m.free_path(dest, "42", pris)
        assert r == dest
        assert "sous/match.jpg" in {p.replace("\\", "/") for p in pris}

    def test_conflict_suffixed_with_ident(self, tmp_path):
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


class TestDownload:
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

    def test_304_unchanged(self, tmp_path):
        m = _moteur(tmp_path, verify=True)
        m.session = MagicMock()
        m.session.get.return_value = FakeResponse(304)
        dest = tmp_path / "existe.jpg"
        dest.write_bytes(b"deja")
        statut, infos, _, _ = m.download("https://x/f.jpg", dest,
                                         {"etag": "e1", "taille": 4})
        assert statut == "unchanged"
        # the returned state is the one passed in, unaltered
        assert infos == {"etag": "e1", "taille": 4}

    def test_404_not_found(self, tmp_path):
        m = _moteur(tmp_path)
        m.session = MagicMock()
        m.session.get.return_value = FakeResponse(404)
        dest = tmp_path / "sortie.jpg"
        statut, infos, _, _ = m.download("https://x/f.jpg", dest, None)
        assert statut == "not-found"
        assert infos is None
        assert not dest.exists()

    def test_resume_from_part(self, tmp_path):
        # an existing .part triggers a Range GET → 206
        m = _moteur(tmp_path)
        m.session = MagicMock()
        m.session.get.return_value = FakeResponse(206, {}, b"XYZ")
        dest = tmp_path / "reprise.jpg"
        (dest.with_suffix(dest.suffix + ".part")).write_bytes(b"AB")
        statut, _infos, _, _ = m.download("https://x/f.jpg", dest, None)
        assert statut == "resumed"
        # the final content concatenates the .part and the downloaded remainder
        assert dest.read_bytes() == b"ABXYZ"
        # the Range was sent
        _, kwargs = m.session.get.call_args
        assert kwargs["headers"].get("Range") == "bytes=2-"

    def test_416_restarts_without_range(self, tmp_path):
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

    def test_if_modified_since_used(self, tmp_path):
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

    def test_network_error(self, tmp_path):
        """Network exception yields status ``"error"`` and raw error text."""
        m = _moteur(tmp_path)
        m.session = MagicMock()
        m.session.get.side_effect = requests.ConnectionError("boum")
        dest = tmp_path / "s.jpg"
        statut, infos, classification, error_text = m.download(
            "https://x/f.jpg", dest, None)
        assert statut == "error"
        assert infos is None
        assert not dest.exists()
        assert classification is not None
        assert classification.category in {"cut", "transient", "definitive"}
        # Error text carries the raw exception message for the ``file-failed``
        # event; no French translation happens inside ``Engine.download``.
        assert error_text is not None
        assert "boum" in error_text

    def test_interrupt_keeps_part(self, tmp_path):
        # the stop mid-read must leave the .part for the resume
        m = _moteur(tmp_path)
        m.stop_event.set()   # cut off on the first block

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


class TestRun:
    def test_ignores_deleted_entries(self, tmp_path):
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

    def test_ignores_elements_without_url(self, tmp_path):
        # A source that did not find a resource at the requested format:
        # the engine must count it as ignoree, without crashing.
        moteur = _moteur(tmp_path, sort_mode="date")
        sans_url = _element(1, url=None, filename="", month="2026-01")
        with _patch_inventaire(moteur, [sans_url]), \
             patch.object(moteur, "download") as tel:
            res = moteur.run()
        assert res.skipped == 1
        assert tel.call_count == 0

    def test_detects_local_erasure(self, tmp_path):
        # complete state but file gone → marked deleted, no download
        write_manifest(tmp_path, {
            "8": {"fichier": "manquant.jpg", "taille": 10},
        })
        moteur = _moteur(tmp_path)
        with _patch_inventaire(moteur, [_element(8, size=10)]), \
             patch.object(moteur, "download") as tel:
            res = moteur.run()
        assert res.deleted == 1
        assert tel.call_count == 0
        assert "supprime" in read_manifest(tmp_path)["8"]

    def test_already_present(self, tmp_path):
        f = tmp_path / "ok.jpg"
        f.write_bytes(b"1234567890")
        write_manifest(tmp_path, {
            "1": {"fichier": "ok.jpg", "taille": 10},
        })
        moteur = _moteur(tmp_path)
        with _patch_inventaire(moteur, [_element(1, size=10)]), \
             patch.object(moteur, "download") as tel:
            res = moteur.run()
        assert res.already_present == 1
        assert tel.call_count == 0

    def test_download(self, tmp_path):
        moteur = _moteur(tmp_path, sort_mode="date")
        el = _element(5, url="https://x/wp-content/uploads/2026/03/f.jpg",
                      month="2026-03")
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

    def test_incremental_resume(self, tmp_path):
        moteur = _moteur(tmp_path, sort_mode="date")
        el = _element(5, url="https://x/wp-content/uploads/2026/03/f.jpg",
                      month="2026-03")
        with _patch_inventaire(moteur, [el]), \
             patch.object(moteur, "download",
                          return_value=("resumed", {"taille": 3, "etag": "",
                                                   "modifie": "", "url": "u"},
                                        None, None)):
            res = moteur.run()
        assert res.resumed == 1
        assert res.bytes == 3

    def test_network_failure(self, tmp_path):
        """A failed download counts as a failure and emits ``file-failed``."""
        moteur = _moteur(tmp_path, sort_mode="date")
        el = _element(5, url="https://x/wp-content/uploads/2026/03/f.jpg",
                      month="2026-03")
        journal: list[EngineEvent] = []
        moteur._journal = journal.append
        with _patch_inventaire(moteur, [el]), \
             patch.object(moteur, "download",
                          return_value=("error", None, None, "boum")):
            res = moteur.run()
        assert res.failures == 1
        # The engine emits the failure through a structured event, no
        # translation happens on this path.
        failed = [ev for ev in journal if ev.code == "file-failed"]
        assert len(failed) == 1
        assert failed[0].params.get("error") == "boum"

    def test_no_image(self, tmp_path):
        """``nothing-matches`` is the structured summary when the inventory is empty."""
        moteur = _moteur(tmp_path)
        with _patch_inventaire(moteur, []):
            res = moteur.run()
        assert res.message_event is not None
        assert res.message_event.code == "nothing-matches"

    def test_min_width_filter(self, tmp_path):
        moteur = _moteur(tmp_path, sort_mode="date", min_width=1000)
        petit = _element(1, width=200, month="2026-04")
        grand = _element(2, url="https://x/wp-content/uploads/2026/04/big.jpg",
                         width=2000, month="2026-04")
        with _patch_inventaire(moteur, [petit, grand]), \
             patch.object(moteur, "download",
                          return_value=("ok", {"taille": 1, "etag": "",
                                               "modifie": "", "url": "u"},
                                        None, None)):
            res = moteur.run()
        assert res.downloaded == 1   # only the big one was processed

    def test_interrupted(self, tmp_path):
        """An ``Interrupted`` mid-run surfaces as ``message_event.code == "interrupted"``."""
        moteur = _moteur(tmp_path)
        moteur.stop_event.set()

        def leve(*_a, **_kw):
            raise Interrupted()

        with patch.object(moteur.source, "inventory", side_effect=leve):
            res = moteur.run()
        assert res.interrupted is True
        assert res.message_event is not None
        assert res.message_event.code == "interrupted"

    def test_api_error_is_caught(self, tmp_path):
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

    def test_force_ignores_manifest(self, tmp_path):
        # with force, an image marked deleted must be re-downloaded
        write_manifest(tmp_path, {
            "1": {"fichier": "a.jpg", "taille": 100,
                  "supprime": "2026-01-01T00:00:00"},
        })
        moteur = _moteur(tmp_path, sort_mode="date", force=True)
        el = _element(1, url="https://x/wp-content/uploads/2026/03/a.jpg",
                      month="2026-03")
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

class TestCircuitBreaker:
    """Engine circuit breaker: clean stop on ``cut`` or 5 ``transient``.

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
                     month="2026-03", date=f"2026-03-{i:02d}T00:00:00")
            for i in range(1, nombre + 1)
        ]

    def test_one_cut_interrupts_the_run(self, tmp_path):
        """A single ``cut`` error defers the run and stops the loop."""
        moteur = _moteur(tmp_path, sort_mode="date")
        elements = self._elements(3)
        reponses = [
            self._OK,
            ("error", None, ErrorClassification("cut", None), "cut"),
        ]
        with _patch_inventaire(moteur, elements), \
             patch.object(moteur, "download", side_effect=reponses) as tel:
            res = moteur.run()
        assert res.deferred is True
        assert res.failures == 1
        assert res.downloaded == 1
        assert tel.call_count == 2

    def test_five_consecutive_transients_interrupt(self, tmp_path):
        """Five consecutive ``transient`` failures trigger a defer."""
        moteur = _moteur(tmp_path, sort_mode="date")
        elements = self._elements(10)
        transient = ("error", None,
                     ErrorClassification("transient", None), "timeout")
        with _patch_inventaire(moteur, elements), \
             patch.object(moteur, "download",
                          side_effect=[transient] * 5) as tel:
            res = moteur.run()
        assert res.deferred is True
        assert res.failures == 5
        assert tel.call_count == 5

    def test_success_resets_the_counter(self, tmp_path):
        """A success between two runs of ``transient`` failures resets the counter."""
        moteur = _moteur(tmp_path, sort_mode="date")
        elements = self._elements(10)
        transient = ("error", None,
                     ErrorClassification("transient", None), "timeout")
        reponses = [transient] * 4 + [self._OK] + [transient] * 4 + [self._OK]
        with _patch_inventaire(moteur, elements), \
             patch.object(moteur, "download", side_effect=reponses):
            res = moteur.run()
        assert res.deferred is False
        assert res.failures == 8
        assert res.downloaded == 2

    def test_definitive_does_not_trip_the_breaker(self, tmp_path):
        """A ``definitive`` error (404) does not increment the ``transient`` counter."""
        moteur = _moteur(tmp_path, sort_mode="date")
        elements = self._elements(10)
        transient = ("error", None,
                     ErrorClassification("transient", None), "timeout")
        not_found = ("not-found", None,
                     ErrorClassification("definitive", None), None)
        reponses = ([transient] * 4 + [not_found] + [transient] * 4
                    + [self._OK])
        with _patch_inventaire(moteur, elements), \
             patch.object(moteur, "download", side_effect=reponses):
            res = moteur.run()
        assert res.deferred is False

    def test_retry_after_feeds_retry_after(self, tmp_path):
        """A ``Retry-After`` of 3600 s produces an ISO 8601 about 1 h in the future."""
        moteur = _moteur(tmp_path, sort_mode="date")
        el = self._elements(1)[0]
        reponse = ("error", None,
                   ErrorClassification("cut", 3600.0), "quota")
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

    def test_without_retry_after_retry_field_is_empty(self, tmp_path):
        """Without ``Retry-After``, ``res.retry_after`` stays empty: the scheduler decides."""
        moteur = _moteur(tmp_path, sort_mode="date")
        el = self._elements(1)[0]
        reponse = ("error", None,
                   ErrorClassification("cut", None), "boum")
        with _patch_inventaire(moteur, [el]), \
             patch.object(moteur, "download", return_value=reponse):
            res = moteur.run()
        assert res.deferred is True
        assert res.retry_after == ""

    def test_manifest_saved_even_on_defer(self, tmp_path):
        """The on-disk manifest keeps the entries downloaded before the cut."""
        moteur = _moteur(tmp_path, sort_mode="date")
        elements = self._elements(3)
        cut = ("error", None,
               ErrorClassification("cut", None), "cut")
        with _patch_inventaire(moteur, elements), \
             patch.object(moteur, "download",
                          side_effect=[self._OK, cut]):
            res = moteur.run()
        assert res.deferred is True
        m = read_manifest(tmp_path)
        assert "1" in m

    def test_cache_not_saved_on_defer(self, tmp_path):
        """A cut does not write the engine cache (same as ``Interrupted``)."""
        moteur = _moteur(tmp_path, site="https://x", sort_mode="date")
        elements = self._elements(3)
        cut = ("error", None,
               ErrorClassification("cut", None), "cut")
        with _patch_inventaire(moteur, elements), \
             patch.object(moteur, "download",
                          side_effect=[self._OK, cut]):
            moteur.run()
        assert not cache_path(tmp_path).exists()


# --------------------------------------------------------------------------- #
# Engine.__init__: default roles
# --------------------------------------------------------------------------- #

class TestEngineInit:
    def test_default_callbacks_are_noop(self, tmp_path):
        """Default callbacks accept an :class:`EngineEvent` without raising."""
        # without callbacks: the engine does not explode when it "logs"
        m = Engine(Options(target_dir=tmp_path, delay=0))
        m._journal(EngineEvent("all-up-to-date"))
        m._progression(1, 2, "étiquette")   # nothing raises

    def test_default_stop_event(self, tmp_path):
        m = Engine(Options(target_dir=tmp_path))
        assert m.stop_event is not None
        assert m.stop_event.is_set() is False

    def test_default_source_is_wordpress(self, tmp_path):
        # Default Options: source_type == "wordpress"
        m = Engine(Options(target_dir=tmp_path, delay=0))
        assert m.source.type == "wordpress"

    def test_djangoplicity_source_picked_via_options(self, tmp_path):
        m = Engine(Options(target_dir=tmp_path, delay=0,
                           source_type="djangoplicity",
                           image_format="Small"))
        assert m.source.type == "djangoplicity"
        # the format is forwarded to the adapter via `reglages`
        assert m.source.format_image == "Small"

    def test_unknown_type_falls_back_to_wordpress(self, tmp_path):
        # defensive: an unknown type (corrupt config) must not crash
        m = Engine(Options(target_dir=tmp_path, delay=0,
                           source_type="inconnu"))
        assert m.source.type == "wordpress"


# --------------------------------------------------------------------------- #
# Plumbing: cooperative stop
# --------------------------------------------------------------------------- #

class TestEnginePlumbing:
    def test_check_stop_raises_interrupted(self, tmp_path):
        m = _moteur(tmp_path)
        m.stop_event.set()
        with pytest.raises(Interrupted):
            m._check_stop()

    def test_check_stop_is_silent_otherwise(self, tmp_path):
        m = _moteur(tmp_path)
        m._check_stop()   # nothing raises

    def test_pause_sleeps_then_returns(self, tmp_path):
        m = _moteur(tmp_path)
        # a very short pause exercises the sleep loop
        import time
        avant = time.monotonic()
        m._pause(0.01)
        assert time.monotonic() - avant >= 0.005


# --------------------------------------------------------------------------- #
# load_manifest: force option and fallback to empty
# --------------------------------------------------------------------------- #

class TestLoadManifest:
    def test_force_clears_in_memory_manifest(self, tmp_path):
        write_manifest(tmp_path, {"1": {"fichier": "a.jpg"}})
        m = _moteur(tmp_path, force=True)
        assert m.load_manifest() == {}

    def test_absent_returns_empty(self, tmp_path):
        m = _moteur(tmp_path)
        assert m.load_manifest() == {}

    def test_unreadable_journals(self, tmp_path):
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

class TestRunExtra:
    def test_base_normalises_trailing_slash(self, tmp_path):
        # the engine's base strips the trailing slash; that is also what
        # the adapter sees.
        moteur = _moteur(tmp_path, site="https://example.test/")
        assert moteur.base == "https://example.test"
        assert moteur.source.base == "https://example.test"

    def test_unchanged_status_counts_as_unchanged(self, tmp_path):
        # known file to re-verify with 304
        f = tmp_path / "ok.jpg"
        f.write_bytes(b"12345")
        write_manifest(tmp_path, {
            "1": {"fichier": "ok.jpg", "taille": 5, "etag": "e"},
        })
        moteur = _moteur(tmp_path, verify=True)
        with _patch_inventaire(moteur, [_element(1, size=5)]), \
             patch.object(moteur, "download",
                          return_value=("unchanged",
                                        {"fichier": "ok.jpg", "taille": 5,
                                         "etag": "e"}, None, None)):
            res = moteur.run()
        assert res.unchanged == 1

    def test_resolve_groups_called_in_gallery_mode(self, tmp_path):
        moteur = _moteur(tmp_path, sort_mode="gallery")
        el = _element(1, group=42)
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

    def test_resolve_groups_skipped_when_source_does_not_support(self, tmp_path):
        # Djangoplicity does not have "gallery" in its sort modes. Even if
        # the user left it in their options, the engine must not call
        # resoudre_groupes, and fall back to the by-date sort.
        moteur = _moteur(tmp_path, sort_mode="gallery",
                         source_type="djangoplicity")
        el = _element(1, group="42", month="2026-03",
                      url="https://cdn.eso.org/large/potw.jpg")
        with _patch_inventaire(moteur, [el]), \
             patch.object(moteur.source, "resolve_groups") as res_g, \
             patch.object(moteur, "download",
                          return_value=("ok", {"taille": 1, "etag": "",
                                               "modifie": "", "url": "u"},
                                        None, None)):
            moteur.run()
        res_g.assert_not_called()

    def test_oserror_is_caught(self, tmp_path):
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

    def test_journals_width_filtering(self, tmp_path):
        """Width-filtered elements are reported as ``discarded-below-min-width``."""
        moteur = _moteur(tmp_path, sort_mode="date", min_width=1000)
        journal: list[EngineEvent] = []
        moteur._journal = journal.append
        with _patch_inventaire(moteur, [_element(1, width=200),
                                        _element(2, width=300)]):
            moteur.run()
        events = [ev for ev in journal
                  if ev.code == "discarded-below-min-width"]
        assert len(events) == 1
        assert events[0].params == {"count": 2, "min_width": 1000}

    def test_periodic_save(self, tmp_path):
        # 26 images: save_manifest must be called at least at the 25th
        # and once more in finally
        moteur = _moteur(tmp_path, sort_mode="date")
        elements = [
            _element(i, url=f"https://x/wp-content/uploads/2026/03/f{i}.jpg",
                     month="2026-03")
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

    def test_source_metadata_written_to_manifest(self, tmp_path):
        # An adapter (Djangoplicity) can provide credit / rights / checksum
        # in `element.extra`: the engine copies them into the manifest
        # without interpreting them — useful for the upcoming catalog export.
        moteur = _moteur(tmp_path, sort_mode="date")
        el = _element(7, url="https://cdn.eso.org/large/eso1907a.jpg",
                      month="2026-03",
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
    def test_path(self, tmp_path):
        assert cache_path(tmp_path) == tmp_path / ".cache.json"

    def test_cache_read_absent(self, tmp_path):
        assert read_cache(tmp_path) == {}

    def test_cache_read_invalid_json(self, tmp_path):
        cache_path(tmp_path).write_text("{pas du json")
        assert read_cache(tmp_path) == {}

    def test_write_then_read(self, tmp_path):
        cache = {"derniere_date_media": "2026-05-01T12:00:00",
                 "titres_parents": {"42": "match"}}
        write_cache(tmp_path, cache)
        assert read_cache(tmp_path) == cache

    def test_load_cache_ignored_on_force(self, tmp_path):
        write_cache(tmp_path, {"site": "https://x", "derniere_date_media": "2026"})
        m = _moteur(tmp_path, force=True)
        assert m.load_cache() == {}

    def test_load_cache_ignored_when_disabled(self, tmp_path):
        write_cache(tmp_path, {"site": "https://x", "derniere_date_media": "2026"})
        m = _moteur(tmp_path, use_cache=False)
        assert m.load_cache() == {}

    def test_load_cache_ignored_when_site_changes(self, tmp_path):
        # cache written for another site: no cross-usage
        write_cache(tmp_path, {"site": "https://autre.example",
                                "derniere_date_media": "2026"})
        m = _moteur(tmp_path, site="https://nouveau.example")
        assert m.load_cache() == {}

    def test_load_cache_same_site(self, tmp_path):
        write_cache(tmp_path, {"site": "https://x", "derniere_date_media": "2026"})
        m = _moteur(tmp_path, site="https://x")
        assert m.load_cache()["derniere_date_media"] == "2026"

    def test_save_records_the_site(self, tmp_path):
        m = _moteur(tmp_path, site="https://y")
        m.save_cache({"derniere_date_media": "2026-01-01T00:00:00"})
        stocke = read_cache(tmp_path)
        assert stocke["site"] == "https://y"
        assert stocke["derniere_date_media"] == "2026-01-01T00:00:00"

    def test_save_noop_on_force(self, tmp_path):
        m = _moteur(tmp_path, force=True)
        m.save_cache({"quelque": "chose"})
        assert not cache_path(tmp_path).exists()

    def test_run_uses_cache_date_as_after(self, tmp_path):
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

    def test_run_prefers_user_since_over_cache(self, tmp_path):
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

    def test_run_updates_max_date(self, tmp_path):
        m = _moteur(tmp_path, site="https://x", sort_mode="date")
        elements = [
            _element(1, url="https://x/wp-content/uploads/2026/03/a.jpg",
                     month="2026-03", date="2026-03-10T08:00:00"),
            _element(2, url="https://x/wp-content/uploads/2026/06/b.jpg",
                     month="2026-06", date="2026-06-20T09:30:00"),
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

    def test_run_caches_gallery_titles(self, tmp_path):
        m = _moteur(tmp_path, site="https://x", sort_mode="gallery")
        el = _element(1, url="https://x/wp-content/uploads/2026/03/a.jpg",
                      group=42, month="2026-03")
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

    def test_run_reuses_cached_titles(self, tmp_path):
        # Pre-populated cache: the engine passes the cache to the adapter,
        # which must return the name without calling the API (contract
        # tested on WordPress in
        # `test_source_wordpress::TestResoudreGroupes::test_court_circuite_sur_cache_connus`).
        # Here we check the engine-side orchestration.
        write_cache(tmp_path, {
            "site": "https://x",
            "titres_parents": {"42": "match-cache"},
        })
        m = _moteur(tmp_path, site="https://x", sort_mode="gallery")
        el = _element(1, url="https://x/wp-content/uploads/2026/03/a.jpg",
                      group=42, month="2026-03")
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

    def test_interruption_does_not_save_cache(self, tmp_path):
        m = _moteur(tmp_path, site="https://x")
        with patch.object(m.source, "inventory", side_effect=Interrupted()):
            r = m.run()
        assert r.interrupted is True
        # no cache write: the max date was not committed
        assert not cache_path(tmp_path).exists()

    def test_load_cache_ignored_when_type_changes(self, tmp_path):
        # cache written under type "wordpress", engine created under type
        # "djangoplicity": two distinct identifier spaces, start from
        # scratch.
        write_cache(tmp_path, {
            "site": "https://x", "type_source": "wordpress",
            "derniere_date_media": "2026-06-01T00:00:00",
        })
        m = _moteur(tmp_path, site="https://x", source_type="djangoplicity")
        assert m.load_cache() == {}

    def test_load_cache_silent_migration_without_type(self, tmp_path):
        # pre-existing cache without `type_source` field (config v1.0.38):
        # read as if it matched the current type, no loss.
        write_cache(tmp_path, {
            "site": "https://x",
            "derniere_date_media": "2026-06-01T00:00:00",
        })
        m = _moteur(tmp_path, site="https://x")   # default: wordpress
        assert m.load_cache()["derniere_date_media"] == "2026-06-01T00:00:00"

    def test_save_cache_records_source_type(self, tmp_path):
        m = _moteur(tmp_path, site="https://y", source_type="djangoplicity")
        m.save_cache({"derniere_date_media": "2026-01-01T00:00:00"})
        stocke = read_cache(tmp_path)
        assert stocke["type_source"] == "djangoplicity"


# --------------------------------------------------------------------------- #
# Engine.save_manifest: read-merge-write fusion (UI vs engine race)
# --------------------------------------------------------------------------- #

class TestSaveManifestMerge:
    """Write-merge: the UI mark wins over the engine's in-memory version.

    Non-regression against the last-writer-wins race between
    ``Engine.run()`` (loads the manifest on entry, rewrites everything
    in ``finally``) and ``delete_image``/``restore`` (read-mutate-write
    on the UI side).
    """

    def test_ui_deleted_mark_survives_engine_save(self, tmp_path):
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

    def test_ui_restored_mark_survives_engine_save(self, tmp_path):
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

    def test_out_of_scope_disk_entry_is_preserved(self, tmp_path):
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

    def test_new_engine_entry_is_written(self, tmp_path):
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

    def test_ui_deletion_during_engine_reset(self, tmp_path):
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

    def test_in_memory_deleted_field_overwrites_disk(self, tmp_path):
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

    def test_periodic_save_not_regressed(self, tmp_path):
        """The merge does not miss the 25-tick: ``save_manifest`` is still called >= 2 times with 26 items."""
        # Mirror of TestExecuterExtra::test_sauvegarde_periodique to detect any
        # regression in the periodic save cadence once the fusion is added.
        moteur = _moteur(tmp_path, sort_mode="date")
        elements = [
            _element(i, url=f"https://x/wp-content/uploads/2026/03/f{i}.jpg",
                     month="2026-03")
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
