"""Update services against GitHub Releases.

This sub-package compares the running version with the latest stable
release published by the repository (see :data:`Glaneur.config.GITHUB_OWNER`
and :data:`Glaneur.config.GITHUB_REPOSITORY`), downloads the Windows
installer and verifies its SHA-256 before offering the replacement to
the user.

Orchestration goes through two ``QThread`` classes documented in
:mod:`Glaneur.updater.qt_threads` so that the UI stays responsive
during the check and the download.
"""

from .github_release import GitHubReleaseProvider
from .models import Release, ReleaseAsset, UpdateInfo
from .version import Version

__all__ = ["GitHubReleaseProvider", "Release", "ReleaseAsset", "UpdateInfo", "Version"]
