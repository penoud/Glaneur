"""Modeles de donnees de l'updater."""

from __future__ import annotations

from dataclasses import dataclass

from .version import Version


@dataclass(frozen=True)
class ReleaseAsset:
    name: str
    download_url: str
    size: int = 0


@dataclass(frozen=True)
class Release:
    version: Version
    tag_name: str
    assets: tuple[ReleaseAsset, ...]
    html_url: str = ""

    def windows_installer(self) -> ReleaseAsset | None:
        expected = f"Glaneur-{self.version}-setup.exe"
        candidates = [asset for asset in self.assets if asset.name == expected]
        return candidates[0] if len(candidates) == 1 else None

    def checksum_for(self, asset: ReleaseAsset) -> ReleaseAsset | None:
        expected = f"{asset.name}.sha256"
        return next((item for item in self.assets if item.name == expected), None)


@dataclass(frozen=True)
class UpdateInfo:
    current: Version
    latest: Release | None

    @property
    def is_available(self) -> bool:
        return self.latest is not None and self.latest.version > self.current
