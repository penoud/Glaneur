"""Tests for `Glaneur.updater.downloader.download` and
`temporary_directory`. `verify_sha256` already has its coverage in
`tests/test_updater.py`.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests

from Glaneur.updater.downloader import (
    DownloadError,
    download,
    temporary_directory,
)
from Glaneur.updater.models import ReleaseAsset


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _asset(name: str = "Glaneur-1.1.7-setup.exe") -> ReleaseAsset:
    return ReleaseAsset(name=name, download_url=f"https://x.example/{name}")


def _session_with_chunks(chunks, *, status_ok: bool = True):
    """Build a `requests.Session` mock that streams the given chunks.

    Args:
        chunks: iterable of bytes returned by `response.iter_content`.
        status_ok: when False, `raise_for_status` raises an HTTPError.

    Returns:
        The mock session, ready to be passed to `download`.
    """
    response = MagicMock()
    response.iter_content.return_value = iter(chunks)
    if status_ok:
        response.raise_for_status = MagicMock()
    else:
        response.raise_for_status = MagicMock(
            side_effect=requests.HTTPError("HTTP 500"),
        )
    # `with client.get(...) as response:` needs the context-manager
    # protocol on the object `client.get(...)` returns.
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    session = MagicMock()
    session.get.return_value = response
    return session, response


# --------------------------------------------------------------------------- #
# Nominal path
# --------------------------------------------------------------------------- #


class TestDownloadOk:
    def test_writes_chunks_to_file(self, tmp_path):
        session, _ = _session_with_chunks([b"AAAA", b"BBBB", b"CCCC"])
        asset = _asset()
        result = download(asset, tmp_path, session=session)
        assert result == tmp_path / asset.name
        assert result.read_bytes() == b"AAAABBBBCCCC"

    def test_ignores_empty_chunks(self, tmp_path):
        # iter_content yields empty bytes to keep the connection alive;
        # they must not be written to disk (they would still be a no-op,
        # but the code branch is explicit).
        session, _ = _session_with_chunks([b"", b"X", b"", b"Y"])
        result = download(_asset(), tmp_path, session=session)
        assert result.read_bytes() == b"XY"

    def test_creates_destination_directory(self, tmp_path):
        session, _ = _session_with_chunks([b"data"])
        cible = tmp_path / "n1" / "n2"
        assert not cible.exists()
        result = download(_asset(), cible, session=session)
        assert result.exists()
        assert result.parent == cible

    def test_uses_provided_session(self, tmp_path):
        session, _ = _session_with_chunks([b"data"])
        asset = _asset()
        download(asset, tmp_path, session=session)
        # The session's `get` was called with the asset URL and stream=True.
        session.get.assert_called_once()
        args, kwargs = session.get.call_args
        assert args[0] == asset.download_url
        assert kwargs.get("stream") is True

    def test_creates_default_session(self, tmp_path, monkeypatch):
        session, _ = _session_with_chunks([b"data"])
        appel = {"n": 0}

        def faux_session():
            appel["n"] += 1
            return session

        # When no session is provided, `download` builds a new
        # `requests.Session()` — patch the constructor.
        monkeypatch.setattr(
            "Glaneur.updater.downloader.requests.Session", faux_session,
        )
        result = download(_asset(), tmp_path)
        assert appel["n"] == 1
        assert result.read_bytes() == b"data"


# --------------------------------------------------------------------------- #
# Failure paths
# --------------------------------------------------------------------------- #


class TestDownloadErrors:
    def test_network_error_raises_downloaderror_and_cleans_up(self, tmp_path):
        session = MagicMock()
        session.get.side_effect = requests.ConnectionError("boum")
        asset = _asset()
        with pytest.raises(DownloadError):
            download(asset, tmp_path, session=session)
        # No partial file left behind.
        assert not (tmp_path / asset.name).exists()

    def test_http_error_raises_downloaderror(self, tmp_path):
        session, _ = _session_with_chunks([b"partiel"], status_ok=False)
        asset = _asset()
        with pytest.raises(DownloadError):
            download(asset, tmp_path, session=session)
        # The partial write that happened before raise_for_status must
        # not leak — the destination has to be cleaned up.
        assert not (tmp_path / asset.name).exists()

    def test_disk_error_raises_downloaderror(self, tmp_path, monkeypatch):
        session, _ = _session_with_chunks([b"data"])
        # Force `Path.open` to raise an OSError on write.
        orig_open = Path.open

        def open_qui_leve(self, *a, **kw):
            if "w" in (a[0] if a else kw.get("mode", "")):
                raise OSError("disque plein")
            return orig_open(self, *a, **kw)

        monkeypatch.setattr(Path, "open", open_qui_leve)
        with pytest.raises(DownloadError):
            download(_asset(), tmp_path, session=session)

    def test_empty_file_raises_downloaderror_and_cleans_up(self, tmp_path):
        # An empty iter_content produces a zero-byte file: `download`
        # must reject and clean it up.
        session, _ = _session_with_chunks([])
        asset = _asset()
        with pytest.raises(DownloadError):
            download(asset, tmp_path, session=session)
        assert not (tmp_path / asset.name).exists()


# --------------------------------------------------------------------------- #
# temporary_directory
# --------------------------------------------------------------------------- #


class TestTemporaryDirectory:
    def test_returns_existing_folder_with_prefix(self):
        d = temporary_directory()
        try:
            assert d.is_dir()
            assert d.name.startswith("Glaneur-update-")
            assert d.is_absolute()
        finally:
            # cleanup: `temporary_directory` deliberately does not.
            d.rmdir()

    def test_multiple_creations_are_distinct(self):
        a = temporary_directory()
        b = temporary_directory()
        try:
            assert a != b
        finally:
            a.rmdir()
            b.rmdir()
