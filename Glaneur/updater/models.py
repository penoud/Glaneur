"""Modèles de données de l'updater."""

from __future__ import annotations

from dataclasses import dataclass

from .version import Version


@dataclass(frozen=True)
class ReleaseAsset:
    """Un asset attaché à une release GitHub (installateur, checksum…)."""

    #: File name (for example ``Glaneur-1.1.0-setup.exe``).
    name: str
    #: Direct download URL provided by GitHub.
    download_url: str
    #: Announced size in bytes, or 0 if unknown.
    size: int = 0


@dataclass(frozen=True)
class Release:
    """Une release publiée sur GitHub avec ses assets et sa version SemVer."""

    #: SemVer version parsed from :attr:`tag_name`.
    version: Version
    #: Git tag (for example ``v1.1.0``).
    tag_name: str
    #: Assets attached to the release.
    assets: tuple[ReleaseAsset, ...]
    #: Human URL of the release page, if known.
    html_url: str = ""

    def windows_installer(self) -> ReleaseAsset | None:
        """Renvoie l'installateur Windows attendu pour cette release.

        Le nom est déterministe : ``Glaneur-<version>-setup.exe``. En
        cas d'absence ou d'homonymie (deux candidats), renvoie ``None``
        pour refuser de deviner.

        Returns:
            L'unique asset correspondant, ou ``None``.
        """
        expected = f"Glaneur-{self.version}-setup.exe"
        candidates = [asset for asset in self.assets if asset.name == expected]
        return candidates[0] if len(candidates) == 1 else None

    def checksum_for(self, asset: ReleaseAsset) -> ReleaseAsset | None:
        """Trouve le fichier ``.sha256`` associé à ``asset``.

        Args:
            asset: Asset dont on cherche le checksum.

        Returns:
            Le :class:`ReleaseAsset` nommé ``{asset.name}.sha256``, ou
            ``None`` s'il n'est pas dans la release.
        """
        expected = f"{asset.name}.sha256"
        return next((item for item in self.assets if item.name == expected), None)


@dataclass(frozen=True)
class UpdateInfo:
    """Résultat d'un check de mise à jour."""

    #: Currently installed version.
    current: Version
    #: Latest known stable release, or ``None`` (none, or error).
    latest: Release | None

    @property
    def is_available(self) -> bool:
        """Indique si :attr:`latest` propose une version strictement plus récente.

        Returns:
            ``True`` si une mise à jour est disponible.
        """
        return self.latest is not None and self.latest.version > self.current
