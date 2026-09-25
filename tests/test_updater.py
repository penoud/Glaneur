from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from Glaneur.updater.downloader import verify_sha256
from Glaneur.updater.github_release import GitHubReleaseProvider
from Glaneur.updater.models import Release, ReleaseAsset
from Glaneur.updater.version import Version


def test_semver_comparison_and_v_prefix():
    assert Version.parse("1.0.4") < Version.parse("v1.0.5")
    assert Version.parse("1.0.5") == Version.parse("v1.0.5")
    assert Version.parse("1.1.0") > Version.parse("1.0.9")
    assert Version.parse("2.0.0") > Version.parse("1.9.9")
    assert Version.parse("1.0.5-rc.1") < Version.parse("1.0.5")


def test_invalid_version_rejected():
    with pytest.raises(ValueError):
        Version.parse("1.0")


def test_asset_selection_requires_exact_windows_pair():
    installer = ReleaseAsset("WpImagerDownloader-1.0.5-setup.exe", "https://x/installer")
    checksum = ReleaseAsset(f"{installer.name}.sha256", "https://x/checksum")
    release = Release(Version.parse("1.0.5"), "v1.0.5", (installer, checksum))
    assert release.windows_installer() == installer
    assert release.checksum_for(installer) == checksum


def test_asset_selection_rejects_ambiguous_installers():
    assets = tuple(ReleaseAsset(name, f"https://x/{name}") for name in (
        "WpImagerDownloader-1.0.5-setup.exe",
        "WpImagerDownloader-1.0.5-setup.exe",
    ))
    release = Release(Version.parse("1.0.5"), "v1.0.5", assets)
    assert release.windows_installer() is None


def test_checksum_correct_and_incorrect(tmp_path: Path):
    path = tmp_path / "installer.exe"
    path.write_bytes(b"payload")
    digest = hashlib.sha256(b"payload").hexdigest()
    assert verify_sha256(path, f"{digest}  installer.exe")
    assert not verify_sha256(path, "0" * 64)
    assert not verify_sha256(tmp_path / "missing.exe", digest)


def test_github_provider_ignores_prerelease_and_draft():
    session = MagicMock()
    response = MagicMock()
    response.json.return_value = [
        {"tag_name": "v1.0.6-beta.1", "prerelease": True, "draft": False, "assets": []},
        {"tag_name": "v1.0.7", "prerelease": False, "draft": True, "assets": []},
        {"tag_name": "v1.0.5", "prerelease": False, "draft": False, "assets": []},
    ]
    session.get.return_value = response
    info = GitHubReleaseProvider(session=session).check(Version.parse("1.0.4"))
    assert info.is_available
    assert str(info.latest.version) == "1.0.5"


def test_github_provider_invalid_json():
    session = MagicMock()
    response = MagicMock()
    response.json.return_value = {"message": "bad"}
    session.get.return_value = response
    with pytest.raises(ValueError):
        GitHubReleaseProvider(session=session).check(Version.parse("1.0.4"))
