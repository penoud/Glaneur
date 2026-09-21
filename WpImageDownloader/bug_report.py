"""Composition d'une URL GitHub pour ouvrir une issue préremplie.

L'application n'embarque pas de token GitHub (cf. sprint §38) : on ne peut
donc pas POSTer l'issue en silence. On construit une URL
`https://github.com/OWNER/REPO/issues/new?title=…&body=…` que l'utilisateur
soumet lui-même depuis son navigateur (déjà authentifié).
"""

from __future__ import annotations

import platform
import sys
from pathlib import Path
from urllib.parse import urlencode

# GitHub tolère quelques kilo-octets en query string. On garde une marge
# confortable — au-delà, le body est tronqué et l'utilisateur reçoit une
# note à la fin du corps.
_MAX_BODY = 6000
_TRUNCATION_NOTICE = (
    "\n\n_[Log tronqué automatiquement — colle la suite dans un commentaire "
    "de l'issue si nécessaire.]_"
)


def collect_context(
    version: str,
    chemin_log: Path | None = None,
    nb_lignes: int = 50,
) -> str:
    """Renvoie un bloc Markdown avec version, plateforme et dernières lignes
    de log. `chemin_log=None` ou fichier absent = section log omise."""
    lignes = [
        "### Contexte",
        "",
        f"- **Version** : {version}",
        f"- **Plateforme** : {platform.platform()}",
        f"- **Python** : {sys.version.split()[0]}",
    ]
    tail = _tail_log(chemin_log, nb_lignes) if chemin_log else ""
    if tail:
        lignes += [
            "",
            f"### Dernières lignes de log ({nb_lignes} max)",
            "",
            "```",
            tail,
            "```",
        ]
    return "\n".join(lignes)


def _tail_log(chemin: Path, nb_lignes: int) -> str:
    try:
        with chemin.open("r", encoding="utf-8", errors="replace") as f:
            lignes = f.readlines()
    except OSError:
        return ""
    return "".join(lignes[-nb_lignes:]).rstrip()


def build_issue_url(
    owner: str,
    repository: str,
    title: str,
    body: str,
    max_body: int = _MAX_BODY,
) -> str:
    """Construit l'URL GitHub d'ouverture d'issue préremplie.

    `body` est tronqué au-delà de `max_body` caractères pour rester sous la
    limite de query string. Le titre n'est pas tronqué (rare qu'il dépasse).
    """
    if len(body) > max_body:
        keep = max_body - len(_TRUNCATION_NOTICE)
        body = body[:keep] + _TRUNCATION_NOTICE
    params = urlencode({"title": title, "body": body})
    return f"https://github.com/{owner}/{repository}/issues/new?{params}"
