"""Data models of the updater."""

from __future__ import annotations

from dataclasses import dataclass

from .version import Version


@dataclass(frozen=True)
class ReleaseAsset:
    """An asset attached to a GitHub release (installer, checksum, ...)."""

    #: File name (for example ``Glaneur-1.1.0-setup.exe``).
    name: str
    #: Direct download URL provided by GitHub.
    download_url: str
    #: Announced size in bytes, or 0 if unknown.
    size: int = 0


@dataclass(frozen=True)
class Release:
    """A release published on GitHub with its assets and SemVer version."""

    #: SemVer version parsed from :attr:`tag_name`.
    version: Version
    #: Git tag (for example ``v1.1.0``).
    tag_name: str
    #: Assets attached to the release.
    assets: tuple[ReleaseAsset, ...]
    #: Human URL of the release page, if known.
    html_url: str = ""

    def windows_installer(self) -> ReleaseAsset | None:
        """Return the Windows installer expected for this release.

        The name is deterministic: ``Glaneur-<version>-setup.exe``. If
        missing or ambiguous (two candidates), returns ``None`` to refuse
        to guess.

        Returns:
            The single matching asset, or ``None``.
        """
        expected = f"Glaneur-{self.version}-setup.exe"
        candidates = [asset for asset in self.assets if asset.name == expected]
        return candidates[0] if len(candidates) == 1 else None

    def checksum_for(self, asset: ReleaseAsset) -> ReleaseAsset | None:
        """Find the ``.sha256`` file associated with ``asset``.

        Args:
            asset: Asset whose checksum is being looked up.

        Returns:
            The :class:`ReleaseAsset` named ``{asset.name}.sha256``, or
            ``None`` if it is not in the release.
        """
        expected = f"{asset.name}.sha256"
        return next((item for item in self.assets if item.name == expected), None)


@dataclass(frozen=True)
class UpdateInfo:
    """Result of an update check."""

    #: Currently installed version.
    current: Version
    #: Latest known stable release, or ``None`` (none, or error).
    latest: Release | None

    @property
    def is_available(self) -> bool:
        """Report whether :attr:`latest` proposes a strictly newer version.

        Returns:
            ``True`` if an update is available.
        """
        return self.latest is not None and self.latest.version > self.current
