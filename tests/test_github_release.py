"""Tests for ``Glaneur.updater.github_release.GitHubReleaseProvider``.

No network access: HTTP calls are mocked via ``requests.Session``.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import requests

from Glaneur.updater.github_release import GitHubReleaseProvider
from Glaneur.updater.version import Version


class TestGitHubReleaseProviderParse:
    """Test the static ``_parse`` method with well-formed and malformed data."""

    def test_valid_release(self):
        """A clean release dict is parsed correctly."""
        item = {
            "tag_name": "1.2.3",
            "html_url": "https://example.com/releases/1.2.3",
            "draft": False,
            "prerelease": False,
            "assets": [
                {"name": "glaneur-1.2.3.exe", "browser_download_url": "https://cdn/x.exe", "size": 1024},
            ],
        }
        result = GitHubReleaseProvider._parse(item)
        assert result is not None
        assert result.version == Version.parse("1.2.3")
        assert result.tag_name == "1.2.3"
        assert result.html_url == "https://example.com/releases/1.2.3"
        assert len(result.assets) == 1
        assert result.assets[0].name == "glaneur-1.2.3.exe"

    def test_missing_tag_name(self):
        """Missing tag_name → None (KeyError)."""
        item = {"html_url": "https://example.com"}
        assert GitHubReleaseProvider._parse(item) is None

    def test_non_string_tag_name(self):
        """Non-string tag_name → None (ValueError)."""
        item = {"tag_name": 12345}
        assert GitHubReleaseProvider._parse(item) is None

    def test_invalid_version(self):
        """Unparseable version → None (ValueError)."""
        item = {"tag_name": "not-a-version"}
        assert GitHubReleaseProvider._parse(item) is None

    def test_missing_browser_download_url(self):
        """Asset without browser_download_url is skipped."""
        item = {
            "tag_name": "1.0.0",
            "assets": [
                {"name": "file.txt", "size": 100},
                {"name": "good.exe", "browser_download_url": "https://x/y.exe", "size": 200},
            ],
        }
        result = GitHubReleaseProvider._parse(item)
        assert result is not None
        assert len(result.assets) == 1
        assert result.assets[0].name == "good.exe"

    def test_mixed_valid_invalid_assets(self):
        """Some assets valid, some not — only valid ones are kept."""
        item = {
            "tag_name": "2.0.0",
            "assets": [
                {"name": "", "browser_download_url": "https://x/bad.exe"},
                {"name": "a.exe", "browser_download_url": ""},
                {"name": "good.exe", "browser_download_url": "https://x/good.exe"},
            ],
        }
        result = GitHubReleaseProvider._parse(item)
        assert result is not None
        assert len(result.assets) == 1

    def test_none_item(self):
        """None as item → None (TypeError)."""
        assert GitHubReleaseProvider._parse(None) is None

    def test_not_a_dict(self):
        """Non-dict item → None (TypeError)."""
        assert GitHubReleaseProvider._parse("string") is None

    def test_missing_html_url_defaults_empty(self):
        """Missing html_url falls back to empty string."""
        item = {"tag_name": "0.1.0"}
        result = GitHubReleaseProvider._parse(item)
        assert result is not None
        assert result.html_url == ""

    def test_missing_size_defaults_to_zero(self):
        """Asset without size defaults to 0."""
        item = {
            "tag_name": "1.0.0",
            "assets": [
                {"name": "x.exe", "browser_download_url": "https://x/x.exe"},
            ],
        }
        result = GitHubReleaseProvider._parse(item)
        assert result is not None
        assert result.assets[0].size == 0


class TestGitHubReleaseProviderCheck:
    """Test the ``check`` method with a mocked session."""

    def test_no_stable_release(self):
        """Only drafts and prereleases → latest is None."""
        session = MagicMock(spec=requests.Session)
        session.get.return_value.json.return_value = [
            {"tag_name": "2.0.0", "draft": True, "prerelease": False, "assets": []},
            {"tag_name": "1.9.0", "draft": False, "prerelease": True, "assets": []},
        ]
        session.get.return_value.raise_for_status.return_value = None

        provider = GitHubReleaseProvider(session=session)
        result = provider.check(Version.parse("1.8.0"))
        assert result.latest is None

    def test_stable_release_found(self):
        """A stable release is returned as latest."""
        session = MagicMock(spec=requests.Session)
        session.get.return_value.json.return_value = [
            {"tag_name": "2.0.0", "draft": False, "prerelease": False, "assets": []},
            {"tag_name": "1.0.0", "draft": False, "prerelease": False, "assets": []},
        ]
        session.get.return_value.raise_for_status.return_value = None

        provider = GitHubReleaseProvider(session=session)
        result = provider.check(Version.parse("1.8.0"))
        assert result.latest is not None
        assert str(result.latest.version) == "2.0.0"

    def test_invalid_payload_shape_raises(self):
        """Non-list response raises ValueError."""
        session = MagicMock(spec=requests.Session)
        session.get.return_value.json.return_value = {"not": "a list"}
        session.get.return_value.raise_for_status.return_value = None

        provider = GitHubReleaseProvider(session=session)
        try:
            provider.check(Version.parse("1.0.0"))
            assert False, "Expected ValueError"
        except ValueError:
            pass
