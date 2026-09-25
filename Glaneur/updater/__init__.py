"""Services de mise à jour depuis les GitHub Releases.

Ce sous-paquet compare la version en cours à la dernière release stable
publiée par le dépôt (voir :data:`Glaneur.config.GITHUB_OWNER` et
:data:`Glaneur.config.GITHUB_REPOSITORY`), télécharge l'installateur
Windows et vérifie son SHA-256 avant de proposer le remplacement à
l'utilisateur.

L'orchestration passe par deux ``QThread`` documentés dans
:mod:`Glaneur.updater.qt_threads` pour que l'UI reste réactive
pendant le check et le téléchargement.
"""

from .github_release import GitHubReleaseProvider
from .models import Release, ReleaseAsset, UpdateInfo
from .version import Version

__all__ = ["GitHubReleaseProvider", "Release", "ReleaseAsset", "UpdateInfo", "Version"]
