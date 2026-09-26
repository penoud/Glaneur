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

# NB: lupdate only extracts QCoreApplication.translate("Ctx", "src") calls
# with *literal* context AND source — a `_tr()` alias would not be
# detected. So we inline, with the fixed "BugReport" context.

# --------------------------------------------------------------------------- #
# Log line compaction — every char saved leaves more room
# for the user's text before the GitHub URL exceeds the cap.
# --------------------------------------------------------------------------- #

_APP_LOGGER_PREFIX = "Glaneur."

# Anchored on the log level so we do not clip the prefix if it appears
# inside a message (path, repository, etc.).
_LEVEL_PREFIX_RE = re.compile(
    r"(\b(?:DEBUG|INFO|WARNING|WARN|ERROR|CRITICAL)\s+)"
    + re.escape(_APP_LOGGER_PREFIX)
)
_TS_MS_RE = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d{3}")
_TS_YEAR_RE = re.compile(r"^\d{4}-(\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
_TS_DATE_RE = re.compile(r"^\d{2}-\d{2} (?=\d{2}:\d{2}:\d{2})")

# Order: most specific first (Temp before Local, Local before profile).
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

# GitHub returns a 500 "Whoops, something went wrong!" when the prefill
# URL exceeds ~7000 bytes (the threshold varies depending on encoded
# characters). We cap the *encoded* URL length, not the raw body size:
# Windows paths (`\` → `%5C`) and French accents inflate the encoding
# 2-3×. Above the cap we warn the user rather than silently truncating.
MAX_URL_LENGTH = 6000


def collect_context(
    version: str,
    chemin_log: Path | None = None,
    nb_lignes: int = 50,
) -> str:
    """Assemble un bloc Markdown à joindre à un rapport de bug.

    Contient version, plateforme, version Python, puis (optionnellement)
    les dernières lignes du log. Le log est compacté (préfixe logger,
    chemins Windows, timestamps) pour laisser de la place au texte
    utilisateur avant que l'URL GitHub ne dépasse ``MAX_URL_LENGTH``.
    Les en-têtes Markdown passent par ``QCoreApplication.translate`` :
    ils apparaissent dans l'issue GitHub dans la langue de l'application.

    Args:
        version: Version de l'application (typiquement ``__version__``).
        chemin_log: Chemin du fichier de log à extraire. ``None`` ou
            fichier absent : section log omise.
        nb_lignes: Nombre maximum de lignes de log à joindre.

    Returns:
        Le bloc Markdown, prêt à concaténer au body de l'issue.
    """
    lignes = [
        f"### {QCoreApplication.translate('BugReport', 'Contexte')}",
        "",
        f"- **{QCoreApplication.translate('BugReport', 'Version')}** : {version}",
        f"- **{QCoreApplication.translate('BugReport', 'Plateforme')}** : {platform.platform()}",
        f"- **{QCoreApplication.translate('BugReport', 'Python')}** : {sys.version.split()[0]}",
    ]
    tail, note = _tail_log(chemin_log, nb_lignes) if chemin_log else ("", "")
    if tail:
        entete = "### " + QCoreApplication.translate(
            "BugReport", "Dernières lignes de log ({n} max)").format(n=nb_lignes)
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
    note = (QCoreApplication.translate("BugReport", "date : {date}").format(date=date_commune)
            if date_commune else "")
    return "\n".join(compactees).rstrip(), note


def build_issue_url(
    owner: str,
    repository: str,
    title: str,
    body: str,
) -> str:
    """Construit l'URL GitHub d'ouverture d'issue préremplie.

    Ne tronque pas : le caller doit vérifier :func:`is_url_too_long`
    et avertir l'utilisateur avant d'ouvrir l'URL — sinon GitHub renvoie
    « Whoops, something went wrong! » sur les rapports trop longs.

    Args:
        owner: Propriétaire du dépôt GitHub.
        repository: Nom du dépôt.
        title: Titre suggéré pour l'issue.
        body: Contenu Markdown du corps de l'issue.

    Returns:
        L'URL ``https://github.com/OWNER/REPO/issues/new?title=…&body=…``.
    """
    params = urlencode({"title": title, "body": body})
    return f"https://github.com/{owner}/{repository}/issues/new?{params}"


def is_url_too_long(url: str, max_length: int = MAX_URL_LENGTH) -> bool:
    """Indique si l'URL dépasse le plafond de préremplissage GitHub.

    Args:
        url: URL à mesurer.
        max_length: Plafond, en octets ; par défaut ``MAX_URL_LENGTH``.

    Returns:
        ``True`` si ``url`` est trop longue, ``False`` sinon.
    """
    return len(url) > max_length
