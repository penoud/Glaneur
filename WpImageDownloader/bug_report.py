"""Composition d'une URL GitHub pour ouvrir une issue préremplie.

L'application n'embarque pas de token GitHub (cf. sprint §38) : on ne peut
donc pas POSTer l'issue en silence. On construit une URL
`https://github.com/OWNER/REPO/issues/new?title=…&body=…` que l'utilisateur
soumet lui-même depuis son navigateur (déjà authentifié).
"""

from __future__ import annotations

import platform
import re
import sys
from pathlib import Path
from urllib.parse import urlencode

from PySide6.QtCore import QCoreApplication


def _tr(source: str) -> str:
    """Alias court pour QCoreApplication.translate() avec le contexte fixe
    « BugReport » — utilisé par Qt Linguist pour regrouper ces chaînes."""
    return QCoreApplication.translate("BugReport", source)

# --------------------------------------------------------------------------- #
# Compactage des lignes de log — chaque char économisé laisse plus de place
# au texte de l'utilisateur avant que l'URL GitHub ne dépasse le plafond.
# --------------------------------------------------------------------------- #

_APP_LOGGER_PREFIX = "WpImageDownloader."

# Ancré sur le niveau de log pour ne pas rogner le préfixe s'il apparaît
# dans un message (chemin, dépôt, etc.).
_LEVEL_PREFIX_RE = re.compile(
    r"(\b(?:DEBUG|INFO|WARNING|WARN|ERROR|CRITICAL)\s+)"
    + re.escape(_APP_LOGGER_PREFIX)
)
_TS_MS_RE = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d{3}")
_TS_YEAR_RE = re.compile(r"^\d{4}-(\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
_TS_DATE_RE = re.compile(r"^\d{2}-\d{2} (?=\d{2}:\d{2}:\d{2})")

# Ordre : le plus spécifique d'abord (Temp avant Local, Local avant profil).
_PATH_SUBSTITUTIONS = [
    (re.compile(r"[Cc]:\\Users\\[^\\]+\\AppData\\Local\\Temp"), r"%TEMP%"),
    (re.compile(r"[Cc]:\\Users\\[^\\]+\\AppData\\Local"), r"%LOCALAPPDATA%"),
    (re.compile(r"[Cc]:\\Users\\[^\\]+\\AppData\\Roaming"), r"%APPDATA%"),
    (re.compile(r"[Cc]:\\Users\\[^\\]+"), r"%USERPROFILE%"),
]


def _compact_line(line: str, drop_date: bool = False) -> str:
    """Compacte une ligne de log : millisecondes, année du timestamp,
    préfixe logger, chemins Windows. Si `drop_date`, retire aussi le
    MM-DD (redondant quand toutes les lignes datent du même jour)."""
    line = _TS_MS_RE.sub(r"\1", line)
    line = _TS_YEAR_RE.sub(r"\1", line)
    if drop_date:
        line = _TS_DATE_RE.sub("", line)
    line = _LEVEL_PREFIX_RE.sub(r"\1", line)
    for pattern, repl in _PATH_SUBSTITUTIONS:
        line = pattern.sub(repl, line)
    return line


def _all_same_date(lignes: list[str]) -> str | None:
    """Renvoie la date commune YYYY-MM-DD si toutes les lignes datées la
    partagent, sinon None."""
    dates = set()
    for l in lignes:
        m = re.match(r"(\d{4}-\d{2}-\d{2}) \d{2}:\d{2}:\d{2}", l)
        if m:
            dates.add(m.group(1))
    return dates.pop() if len(dates) == 1 else None

# GitHub renvoie une 500 « Whoops, something went wrong! » quand l'URL de
# préremplissage dépasse ~7000 octets (le seuil bouge selon les caractères
# encodés). On plafonne la longueur de l'URL *encodée*, pas la taille brute
# du body : les chemins Windows (`\` → `%5C`) et les accents français gonflent
# l'encodage 2-3×. Au-delà du plafond on avertit l'utilisateur plutôt que de
# tronquer silencieusement.
MAX_URL_LENGTH = 6000


def collect_context(
    version: str,
    chemin_log: Path | None = None,
    nb_lignes: int = 50,
) -> str:
    """Renvoie un bloc Markdown avec version, plateforme et dernières lignes
    de log. `chemin_log=None` ou fichier absent = section log omise. Le log
    est compacté (préfixe logger + chemins Windows + timestamps) pour laisser
    de la place au texte de l'utilisateur. Les entêtes Markdown passent par
    Qt tr() : ils apparaissent dans l'issue GitHub dans la langue de l'app."""
    lignes = [
        f"### {_tr('Contexte')}",
        "",
        f"- **{_tr('Version')}** : {version}",
        f"- **{_tr('Plateforme')}** : {platform.platform()}",
        f"- **{_tr('Python')}** : {sys.version.split()[0]}",
    ]
    tail, note = _tail_log(chemin_log, nb_lignes) if chemin_log else ("", "")
    if tail:
        entete = f"### {_tr('Dernières lignes de log ({n} max)').format(n=nb_lignes)}"
        if note:
            entete += f" — {note}"
        lignes += ["", entete, "", "```", tail, "```"]
    return "\n".join(lignes)


def _tail_log(chemin: Path, nb_lignes: int) -> tuple[str, str]:
    """Renvoie (log compacté, note à afficher dans l'en-tête).

    La note signale les substitutions faites (date commune extraite en tête,
    par ex.) pour que le lecteur du bug report comprenne le formatage."""
    try:
        with chemin.open("r", encoding="utf-8", errors="replace") as f:
            lignes_brutes = f.readlines()
    except OSError:
        return "", ""
    lignes_recentes = [l.rstrip("\n") for l in lignes_brutes[-nb_lignes:]]
    date_commune = _all_same_date(lignes_recentes)
    compactees = [_compact_line(l, drop_date=bool(date_commune))
                  for l in lignes_recentes]
    note = _tr("date : {date}").format(date=date_commune) if date_commune else ""
    return "\n".join(compactees).rstrip(), note


def build_issue_url(
    owner: str,
    repository: str,
    title: str,
    body: str,
) -> str:
    """Construit l'URL GitHub d'ouverture d'issue préremplie.

    Ne tronque pas : le caller doit vérifier `is_url_too_long()` et avertir
    l'utilisateur avant d'ouvrir l'URL — sinon GitHub renvoie « Whoops,
    something went wrong! » sur les rapports trop longs.
    """
    params = urlencode({"title": title, "body": body})
    return f"https://github.com/{owner}/{repository}/issues/new?{params}"


def is_url_too_long(url: str, max_length: int = MAX_URL_LENGTH) -> bool:
    """Vrai si l'URL dépasse le seuil que GitHub accepte pour un préremplissage."""
    return len(url) > max_length
