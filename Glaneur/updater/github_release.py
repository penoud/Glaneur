"""Access to the official GitHub Releases API."""

from __future__ import annotations

import logging
from typing import Any

import requests
from PySide6.QtCore import QCoreApplication

from ..config import GITHUB_OWNER, GITHUB_REPOSITORY
from .models import Release, ReleaseAsset, UpdateInfo
from .version import Version

logger = logging.getLogger(__name__)


class GitHubReleaseProvider:
    """Release provider via the REST API ``/repos/{owner}/{repo}/releases``.

    Filters out releases marked ``draft`` or ``prerelease`` and returns
    the newest one compared with the current version.
    """

    def __init__(
        self,
        owner: str = GITHUB_OWNER,
        repository: str = GITHUB_REPOSITORY,
        timeout: float = 8.0,
        session: requests.Session | None = None,
    ) -> None:
        """Configure the provider.

        Args:
            owner: GitHub repository owner.
            repository: Repository name.
            timeout: HTTP timeout in seconds.
            session: ``requests`` session to reuse (a new one is created
                if ``None``).
        """
        self.owner = owner
        self.repository = repository
        self.timeout = timeout
        self.session = session or requests.Session()
        self.url = f"https://api.github.com/repos/{owner}/{repository}/releases"

    def check(self, current: Version) -> UpdateInfo:
        """Query GitHub and compare with ``current``.

        Args:
            current: Currently running version.

        Returns:
            A :class:`Glaneur.updater.models.UpdateInfo` with the best
            stable release found (``latest = None`` when none is usable).

        Raises:
            requests.HTTPError: If the API responds with an error code.
            ValueError: If the response has an unexpected shape (not a
                JSON list).
        """
        logger.info("Checking for updates: current=%s repo=%s/%s",
                    current, self.owner, self.repository)
        response = self.session.get(
            self.url,
            params={"per_page": 20},
            headers={"Accept": "application/vnd.github+json"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError(
                QCoreApplication.translate("Updater", "Réponse GitHub Releases invalide"))
        releases = [self._parse(item) for item in payload if self._is_stable(item)]
        releases = [release for release in releases if release is not None]
        latest = max((release for release in releases), default=None,
                     key=lambda release: release.version)
        logger.info("Latest stable release: %s",
                    latest.version if latest is not None else "none")
        return UpdateInfo(current, latest)

    @staticmethod
    def _is_stable(item: Any) -> bool:
        return isinstance(item, dict) and not item.get("draft") and not item.get("prerelease")

    @staticmethod
    def _parse(item: dict[str, Any]) -> Release | None:
        try:
            tag_name = str(item["tag_name"])
            version = Version.parse(tag_name)
            assets = tuple(
                ReleaseAsset(str(asset["name"]), str(asset["browser_download_url"]), int(asset.get("size", 0)))
                for asset in item.get("assets", [])
                if isinstance(asset, dict) and asset.get("name") and asset.get("browser_download_url")
            )
            return Release(version, tag_name, assets, str(item.get("html_url", "")))
        except (KeyError, TypeError, ValueError):
            return None
