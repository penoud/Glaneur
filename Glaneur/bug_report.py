"""Build a GitHub URL that opens a pre-filled issue.

The application does not embed a GitHub token (see sprint §38): we cannot
POST the issue silently. Instead we build a
``https://github.com/OWNER/REPO/issues/new?title=...&body=...`` URL that
the user submits from their already-authenticated browser.
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
    """Compact a log line: milliseconds, timestamp year, logger prefix,
    Windows paths. If ``drop_date`` is true, also strip the ``MM-DD``
    (redundant when every line shares the same day)."""
    line = _TS_MS_RE.sub(r"\1", line)
    line = _TS_YEAR_RE.sub(r"\1", line)
    if drop_date:
        line = _TS_DATE_RE.sub("", line)
    line = _LEVEL_PREFIX_RE.sub(r"\1", line)
    for pattern, repl in _PATH_SUBSTITUTIONS:
        line = pattern.sub(repl, line)
    return line


def _all_same_date(lignes: list[str]) -> str | None:
    """Return the common YYYY-MM-DD if every dated line shares it, else ``None``."""
    dates = set()
    for l in lignes:
        m = re.match(r"(\d{4}-\d{2}-\d{2}) \d{2}:\d{2}:\d{2}", l)
        if m:
            dates.add(m.group(1))
    return dates.pop() if len(dates) == 1 else None

# GitHub returns a 500 "Whoops, something went wrong!" when the prefill
# URL exceeds ~7000 bytes (the threshold varies depending on encoded
# characters). We cap the *encoded* URL length, not the raw body size:
# Windows paths (`\` -> `%5C`) and French accents inflate the encoding
# 2-3x. Above the cap we warn the user rather than silently truncating.
MAX_URL_LENGTH = 6000


def collect_context(
    version: str,
    chemin_log: Path | None = None,
    nb_lignes: int = 50,
) -> str:
    """Assemble a Markdown block to attach to a bug report.

    Contains the version, platform, Python version and (optionally) the
    latest log lines. The log is compacted (logger prefix, Windows paths,
    timestamps) to leave room for user text before the GitHub URL
    exceeds ``MAX_URL_LENGTH``. Markdown headings go through
    ``QCoreApplication.translate``: they appear in the GitHub issue in
    the application language.

    Args:
        version: Application version (typically ``__version__``).
        chemin_log: Path of the log file to extract from. ``None`` or a
            missing file: the log section is omitted.
        nb_lignes: Maximum number of log lines to attach.

    Returns:
        The Markdown block, ready to append to the issue body.
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
    """Return ``(compacted log, note to display in the header)``.

    The note flags the substitutions performed (common date pulled to
    the header, for instance) so the reader of the bug report understands
    the formatting."""
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
    """Build the GitHub URL that opens a pre-filled issue.

    Does not truncate: the caller must check :func:`is_url_too_long`
    and warn the user before opening the URL — otherwise GitHub returns
    "Whoops, something went wrong!" on reports that exceed the cap.

    Args:
        owner: GitHub repository owner.
        repository: Repository name.
        title: Suggested issue title.
        body: Markdown content of the issue body.

    Returns:
        The ``https://github.com/OWNER/REPO/issues/new?title=...&body=...`` URL.
    """
    params = urlencode({"title": title, "body": body})
    return f"https://github.com/{owner}/{repository}/issues/new?{params}"


def is_url_too_long(url: str, max_length: int = MAX_URL_LENGTH) -> bool:
    """Report whether the URL exceeds the GitHub prefill cap.

    Args:
        url: URL to measure.
        max_length: Cap, in bytes; defaults to ``MAX_URL_LENGTH``.

    Returns:
        ``True`` if ``url`` is too long, ``False`` otherwise.
    """
    return len(url) > max_length
