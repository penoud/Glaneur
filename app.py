#!/usr/bin/env python3
"""PySide6 interface for the WordPress image downloader.

The UI contains no network logic: it builds an ``Options``, runs an
``Engine`` in a ``QThread`` and receives its messages through Qt
signals — which are automatically marshalled to the main thread, so no
widget is ever touched from the worker thread.

Parameters are grouped in a "Préférences" dialog reachable from the
menu bar; the main window shows only the actions, the progression and
the journal.
"""

from __future__ import annotations

import os
import sys
import threading
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from PySide6.QtCore import (
    QAbstractTableModel,
    QCoreApplication,
    QModelIndex,
    QSize,
    Qt,
    QThread,
    QTimer,
    QUrl,
    Signal,
)
from PySide6.QtGui import (
    QAction,
    QColor,
    QDesktopServices,
    QFont,
    QIcon,
    QKeySequence,
    QPainter,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSystemTrayIcon,
    QTableView,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from Glaneur import __version__
from Glaneur.bug_report import (
    MAX_URL_LENGTH,
    build_issue_url,
    collect_context,
    is_url_too_long,
)
from Glaneur.config import (
    DJANGOPLICITY_FORMATS,
    GITHUB_OWNER,
    GITHUB_REPOSITORY,
    INTERVALS,
    SORT_MODES,
    SOURCE_TYPES,
    Config,
)
from Glaneur.engine import (
    Engine,
    EngineEvent,
    Options,
    RunResult,
    delete_image,
    format_bytes,
    list_deleted,
    restore,
)
from Glaneur.scheduler import Scheduler
from Glaneur.scheduler_labels import next_run_text
from Glaneur.sources import sort_modes_for
from Glaneur.system import (
    advance_slideshow,
    autostart,
    autostart_active,
    current_wallpaper,
    open_dir,
    set_slideshow_dir,
)
from Glaneur.updater.qt_threads import (
    UpdateCheck,
    UpdateDownload,
)

GRENAT = "#471625"
PERIODE_ECHEANCE = 30_000   # ms between two due-time checks
PERIODE_AFFICHAGE = 1_000   # ms between two countdown refreshes

DEPOT_URL = "https://github.com/penoud/Glaneur"


# --------------------------------------------------------------------------- #
# Engine event rendering
# --------------------------------------------------------------------------- #

def _render_ui(event: EngineEvent) -> str:
    """Render a structured engine event for the UI (English source strings).

    The context ``UiJournal`` is intentionally new: it isolates these
    translations from the historical ``Moteur`` context (removed by
    US-VERIF-04) so old ``.qm`` files never accidentally resolve stale
    keys against the new codes.

    Each ``translate()`` call passes literal context and source so that
    ``lupdate`` can extract them; a dict lookup would be more compact but
    would break the translation extractor.

    Unknown codes fall back to ``"<code> <params>"`` — a missing entry
    never silently drops information.
    """
    p = event.params
    match event.code:
        case "source-message":
            # Source adapters still emit already-French free text; pass
            # it through unchanged (their migration is a future US).
            return str(p.get("text", ""))
        case "manifest-unreadable":
            return QCoreApplication.translate(
                "UiJournal", "Manifest unreadable, full rebuild.")
        case "already-known":
            return QCoreApplication.translate(
                "UiJournal", "{count} image(s) already known.").format(**p)
        case "cache-since-date":
            return QCoreApplication.translate(
                "UiJournal",
                "Cache: only asking the API for media newer than {date}.",
            ).format(**p)
        case "discarded-below-min-width":
            return QCoreApplication.translate(
                "UiJournal",
                "{count} thumbnail(s)/logo(s) discarded (below {min_width} px).",
            ).format(**p)
        case "nothing-matches":
            return QCoreApplication.translate(
                "UiJournal", "No image matches the criteria.")
        case "known-and-todo":
            return QCoreApplication.translate(
                "UiJournal",
                "{known} already up-to-date, {todo} to process.",
            ).format(**p)
        case "n-files-erased-locally":
            return QCoreApplication.translate(
                "UiJournal",
                "{count} image(s) erased from disk, will not be re-downloaded.",
            ).format(**p)
        case "all-up-to-date":
            return QCoreApplication.translate(
                "UiJournal", "Everything is already up to date.")
        case "identifying-galleries":
            return QCoreApplication.translate(
                "UiJournal", "Identifying galleries…")
        case "file-not-found":
            return QCoreApplication.translate(
                "UiJournal", "{filename}: not found").format(**p)
        case "file-failed":
            return QCoreApplication.translate(
                "UiJournal", "{filename}: {error}").format(**p)
        case "n-new-images":
            return QCoreApplication.translate(
                "UiJournal",
                "{count} new image(s), {size} downloaded.",
            ).format(**p)
        case "interrupted":
            return QCoreApplication.translate(
                "UiJournal", "Interrupted — the resume will start here.")
        case "runtime-error":
            return QCoreApplication.translate(
                "UiJournal", "Error: {error}").format(**p)
        case "write-problem":
            return QCoreApplication.translate(
                "UiJournal", "Write problem: {error}").format(**p)
        case "defer-with-time":
            return QCoreApplication.translate(
                "UiJournal",
                "Server unavailable or quota reached — resume after {until}.",
            ).format(**p)
        case "defer-no-time":
            return QCoreApplication.translate(
                "UiJournal",
                "Server unavailable or quota reached — resume deferred.",
            )
        case _:
            return f"{event.code} {dict(p)}"


# --------------------------------------------------------------------------- #
# Profile list (lot 5.0 E2)
#
# The main window's "Site / Folder" banner used to be two QLabels. It is
# now a one-row QTableView fed by ``ProfileTableModel``. With a single
# implicit profile, the user sees the same information laid out in a
# table; the model is the shape lot 5.1 (multiple profiles) will
# populate.
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class ProfileRow:
    """One row of the profile list: what the user sees at a glance."""

    name: str
    source_type: str
    site: str
    folder: str
    last_run: str
    status: str


def _profile_row_from(profile, status: str = "") -> ProfileRow:
    """Build the display row for one :class:`Glaneur.config.Profile`.

    Args:
        profile: The profile to render.
        status: The status string to show in the last column. Empty by
            default so an idle app shows an em dash.

    Returns:
        A frozen :class:`ProfileRow`. Empty fields become an em dash so
        the table looks intentional even before the user has entered
        anything.
    """
    tiret = "—"
    site = profile.site or ""
    # Fall back to the display name when the site is empty — a profile
    # can carry a name (e.g. "gallery-2") even before its URL is set.
    nom = urlparse(site).netloc or site or profile.name or tiret
    # Reverse lookup of the display label for the source type.
    type_label = next(
        (label for label, val in SOURCE_TYPES.items()
         if val == profile.source_type),
        profile.source_type or tiret,
    )
    # `last_run` is an ISO 8601 string with second precision; keep the
    # minute for display and drop seconds/timezone.
    dernier = (profile.last_run or "")[:16].replace("T", " ") or tiret
    return ProfileRow(
        name=nom,
        source_type=type_label,
        site=site or tiret,
        folder=profile.target_dir or tiret,
        last_run=dernier,
        status=status or tiret,
    )


def _profile_row(cfg: Config, status: str = "") -> ProfileRow:
    """Build the display row for the default (index 0) profile.

    Thin forward-compat wrapper — most callers now go through
    :func:`_profile_row_from` on the whole ``cfg.profiles()`` list.
    """
    return _profile_row_from(cfg.default_profile(), status)


class ProfileTableModel(QAbstractTableModel):
    """Read-only model for the profile list.

    Six columns matching :class:`ProfileRow` (name, type, site, folder,
    last run, status) and one row today. When lot 5.1 lands, the
    single-row hardcoding is replaced by a real ``list[Profile]``.
    """

    #: Column order matches ``ProfileRow`` field order.
    _COLONNES: tuple[str, ...] = (
        "name", "source_type", "site", "folder", "last_run", "status",
    )

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._rows: list[ProfileRow] = []

    # -- Qt read API --------------------------------------------------------

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: ARG002, B008
        return len(self._COLONNES)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid() or role != Qt.DisplayRole:
            return None
        if not 0 <= index.row() < len(self._rows):
            return None
        row = self._rows[index.row()]
        return getattr(row, self._COLONNES[index.column()])

    def headerData(self, section: int, orientation: Qt.Orientation,
                   role: int = Qt.DisplayRole):
        if role != Qt.DisplayRole or orientation != Qt.Horizontal:
            return None
        # Translation happens at display time via QCoreApplication so
        # lupdate picks up the literals. Same "UiTable" context is used
        # for every header of this model.
        libelles = {
            "name": QCoreApplication.translate("UiTable", "Name"),
            "source_type": QCoreApplication.translate("UiTable", "Type"),
            "site": QCoreApplication.translate("UiTable", "Site"),
            "folder": QCoreApplication.translate("UiTable", "Folder"),
            "last_run": QCoreApplication.translate("UiTable", "Last run"),
            "status": QCoreApplication.translate("UiTable", "Status"),
        }
        return libelles.get(self._COLONNES[section])

    # -- mutators -----------------------------------------------------------

    def set_single_row(self, row: ProfileRow) -> None:
        """Replace the (single) row with ``row``.

        Emits ``layoutChanged`` when the row is added for the first
        time; otherwise ``dataChanged`` across every column so the view
        repaints in place.
        """
        self.set_rows([row])

    def set_rows(self, rows: list[ProfileRow]) -> None:
        """Replace the full list of rows with ``rows``.

        Emits ``modelReset`` when the row count changes (a profile was
        added or removed); otherwise ``dataChanged`` across every cell
        so the view repaints in place. That distinction matters for
        the ``QTableView`` — a reset scrolls to the top and drops the
        selection, an in-place update does not.
        """
        if len(rows) != len(self._rows):
            self.beginResetModel()
            self._rows = list(rows)
            self.endResetModel()
            return
        self._rows = list(rows)
        if self._rows:
            haut = self.index(0, 0)
            bas = self.index(len(self._rows) - 1, self.columnCount() - 1)
            self.dataChanged.emit(haut, bas, [Qt.DisplayRole])

    def set_status(self, status: str, row: int = 0) -> None:
        """Update the status column of ``row`` without rebuilding it.

        Args:
            status: Text to show in the ``Status`` column.
            row: Row index to update. Defaults to 0 (the default
                profile — the one the engine runs today).
        """
        if not 0 <= row < len(self._rows):
            return
        self._rows[row] = replace(self._rows[row], status=status)
        cell = self.index(row, self.columnCount() - 1)
        self.dataChanged.emit(cell, cell, [Qt.DisplayRole])


# --------------------------------------------------------------------------- #
# Icon
# --------------------------------------------------------------------------- #

def icone_application() -> QIcon:
    """Load ``build/Glaneur.ico`` if present, otherwise draw a garnet fallback."""
    for base in (Path(__file__).resolve().parent, Path(getattr(sys, "_MEIPASS", "."))):
        fichier = base / "build" / "Glaneur.ico"
        if fichier.exists():
            return QIcon(str(fichier))

    icone = QIcon()
    for taille in (16, 32, 64, 256):
        pixmap = QPixmap(taille, taille)
        pixmap.fill(Qt.transparent)
        p = QPainter(pixmap)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor(GRENAT))
        p.setPen(Qt.NoPen)
        p.drawEllipse(0, 0, taille, taille)
        p.setPen(QColor("white"))
        police = QFont("Segoe UI", int(taille * 0.55), QFont.Bold)
        p.setFont(police)
        p.drawText(pixmap.rect(), Qt.AlignCenter, "W")
        p.end()
        icone.addPixmap(pixmap)
    return icone


# --------------------------------------------------------------------------- #
# Worker thread
# --------------------------------------------------------------------------- #

class Travailleur(QThread):
    """Run the engine off the UI thread."""

    #: Structured engine event to render in the journal widget. Emitted
    #: with the raw :class:`EngineEvent` so the UI (main thread) is the
    #: one that calls :func:`_render_ui`, i.e. Qt's translation stack is
    #: only touched from the main thread.
    journal_event = Signal(object)
    progres = Signal(int, int, str)
    fini = Signal(object)

    def __init__(self, options: Options, stop_event: threading.Event) -> None:
        """Prepare the thread with its ``options`` and shared stop event.

        Args:
            options: Engine parameters (folder, site, filters, ...).
            stop_event: ``threading.Event`` set from the UI to interrupt
                the run cooperatively.
        """
        super().__init__()
        self.options = options
        self.stop_event = stop_event

    def run(self) -> None:
        """Instantiate the engine and start the run; emit ``fini(RunResult)`` on exit."""
        moteur = Engine(
            self.options,
            journal=self.journal_event.emit,
            progression=lambda fait, total, etq: self.progres.emit(fait, total, etq),
            stop_event=self.stop_event,
        )
        self.fini.emit(moteur.run())


# --------------------------------------------------------------------------- #
# Deleted images dialog
# --------------------------------------------------------------------------- #

class DialogueSupprimees(QDialog):
    """List the images erased from disk and offer to re-queue them."""

    def __init__(self, parent, entrees: list[dict]) -> None:
        """Build the dialog from the list of deleted entries.

        Args:
            parent: Qt parent widget.
            entrees: List of entries as returned by
                :func:`Glaneur.engine.list_deleted`.
        """
        super().__init__(parent)
        self.setWindowTitle(self.tr("Deleted images"))
        self.resize(540, 380)
        self.entrees = entrees

        colonne = QVBoxLayout(self)
        colonne.addWidget(QLabel(self.tr(
            "These images were downloaded then erased from the folder.\n"
            "Tick the ones to re-download at the next update.")))

        self.liste = QListWidget()
        for e in entrees:
            item = QListWidgetItem(self.tr("{filename}    (deleted on {date})").format(
                filename=e.get("filename", "?"),
                date=e.get("deleted", "")[:10]))
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.liste.addItem(item)
        colonne.addWidget(self.liste, 1)

        boutons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        boutons.addButton(self.tr("Tick all"), QDialogButtonBox.ActionRole).clicked.connect(
            self._tout_cocher)
        boutons.accepted.connect(self.accept)
        boutons.rejected.connect(self.reject)
        colonne.addWidget(boutons)

    def _tout_cocher(self) -> None:
        for i in range(self.liste.count()):
            self.liste.item(i).setCheckState(Qt.Checked)

    def choix(self) -> list[str]:
        """Return the identifiers of the rows the user has ticked.

        Returns:
            The ``id`` (in the manifest sense) of the entries to restore.
        """
        return [self.entrees[i]["id"] for i in range(self.liste.count())
                if self.liste.item(i).checkState() == Qt.Checked]


# --------------------------------------------------------------------------- #
# Preferences dialog
# --------------------------------------------------------------------------- #

class DialoguePreferences(QDialog):
    """Edit the configuration. Values are only written to ``cfg`` when the
    user validates, through ``appliquer()``. Cancel = everything is discarded."""

    def __init__(self, parent, cfg: Config) -> None:
        """Build the dialog and initialise fields from ``cfg``.

        Args:
            parent: Qt parent widget.
            cfg: :class:`Glaneur.config.Config` instance to edit. Will
                only be modified on the call to :meth:`appliquer`.
        """
        super().__init__(parent)
        self.setWindowTitle(self.tr("Preferences"))
        self.setMinimumSize(560, 420)
        self.cfg = cfg

        colonne = QVBoxLayout(self)
        colonne.setContentsMargins(14, 14, 14, 14)
        colonne.setSpacing(10)

        # Tabbed layout, keyed off `Glaneur.config.PROFILE_FIELDS`. The
        # "General" tab holds application-level preferences; the "Site"
        # tab holds every field listed in PROFILE_FIELDS. "Filters" and
        # "Images" are created hidden — they get their widgets in E5
        # (lot 11.2) and E6 (lot 11.5). See design docs
        # `evolution-multi-sources.md` §3.2 and `roadmap.md` §5.0.
        self.onglets = QTabWidget(self)
        self.onglets.addTab(self._build_general_tab(), self.tr("General"))
        self.onglets.addTab(self._build_site_tab(), self.tr("Site"))
        self._idx_filters = self.onglets.addTab(
            self._build_filters_tab(), self.tr("Filters"))
        self._idx_images = self.onglets.addTab(
            self._build_images_tab(), self.tr("Images"))
        self.onglets.setTabVisible(self._idx_filters, False)
        self.onglets.setTabVisible(self._idx_images, False)
        colonne.addWidget(self.onglets, 1)

        # `_sur_changement_type` needs both combos in place; run it once
        # now that every widget has been created.
        self._sur_changement_type(self.combo_type.currentText())

        # --- buttons ------------------------------------------------------
        boutons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        boutons.accepted.connect(self.accept)
        boutons.rejected.connect(self.reject)
        colonne.addWidget(boutons)

    # -- tabs ---------------------------------------------------------------

    def _build_general_tab(self) -> QWidget:
        """Application-level preferences: cadence, system integration,
        notification-area behaviour, updates check, language.

        Every field in this tab lives outside :data:`Glaneur.config.PROFILE_FIELDS`,
        so it survives the v1 → v2 migration (roadmap §5.1) as an
        application-level key.
        """
        cfg = self.cfg
        page = QWidget()
        form = QFormLayout(page)
        form.setLabelAlignment(Qt.AlignLeft)

        self.combo_intervalle = QComboBox()
        self.combo_intervalle.addItems(list(INTERVALS))
        self.combo_intervalle.setCurrentText(cfg.interval_label)
        form.addRow(self.tr("Update:"), self.combo_intervalle)

        self.case_diaporama = QCheckBox(self.tr(
            "Use this folder for the Windows slideshow"))
        self.case_diaporama.setChecked(cfg.slideshow_dir)
        self.case_diaporama.setEnabled(sys.platform == "win32")
        self.case_diaporama.setToolTip(self.tr(
            "Configures the Windows wallpaper slideshow to pick from\n"
            "the download folder."))
        form.addRow("", self.case_diaporama)

        self.case_barre = QCheckBox(self.tr("Minimise to the notification area when closed"))
        self.case_barre.setChecked(cfg.close_to_tray)
        form.addRow("", self.case_barre)

        self.case_demarrage = QCheckBox(self.tr("Run at Windows startup"))
        self.case_demarrage.setChecked(autostart_active())
        self.case_demarrage.setEnabled(sys.platform == "win32")
        form.addRow("", self.case_demarrage)

        self.case_maj_demarrage = QCheckBox(self.tr("Check for updates at startup"))
        self.case_maj_demarrage.setChecked(cfg.check_updates_on_start)
        self.case_maj_demarrage.setEnabled(sys.platform == "win32")
        self.case_maj_demarrage.setToolTip(self.tr(
            "Queries GitHub in the background at application launch\n"
            "to offer the latest stable version if it is newer."))
        form.addRow("", self.case_maj_demarrage)

        from Glaneur.i18n import AVAILABLE_LANGUAGES
        self.combo_langue = QComboBox()
        self.combo_langue.addItem(self.tr("System language"), "")
        for code, libelle in AVAILABLE_LANGUAGES.items():
            self.combo_langue.addItem(libelle, code)
        for i in range(self.combo_langue.count()):
            if self.combo_langue.itemData(i) == cfg.language:
                self.combo_langue.setCurrentIndex(i)
                break
        self.combo_langue.setToolTip(self.tr(
            "Language change takes effect at the next launch."))
        form.addRow(self.tr("Language:"), self.combo_langue)

        return page

    def _build_site_tab(self) -> QWidget:
        """Per-profile preferences — the fields in
        :data:`Glaneur.config.PROFILE_FIELDS`.

        Today one implicit profile is stored flat on :class:`Config`.
        When the v1 → v2 migration lands (roadmap §5.1), everything in
        this tab moves into a `Profile` entry.
        """
        cfg = self.cfg
        page = QWidget()
        form = QFormLayout(page)
        form.setLabelAlignment(Qt.AlignLeft)

        self.combo_type = QComboBox()
        self.combo_type.addItems(list(SOURCE_TYPES))
        libelle_type_courant = next(
            (libelle for libelle, val in SOURCE_TYPES.items()
             if val == cfg.source_type),
            next(iter(SOURCE_TYPES)),
        )
        self.combo_type.setCurrentText(libelle_type_courant)
        self.combo_type.setToolTip(self.tr(
            "Site type to query. WordPress reads the /wp-json REST API,\n"
            "Djangoplicity reads the /images/d2d/ JSON feed (ESO, ESA/Hubble…)."))
        form.addRow(self.tr("Type:"), self.combo_type)

        self.champ_site = QLineEdit(cfg.site)
        self.champ_site.setPlaceholderText(self.tr("https://example.com"))
        self.champ_site.setToolTip(self.tr(
            "Base URL of the site (without /wp-json or /images/d2d depending on the type)."))
        form.addRow(self.tr("URL:"), self.champ_site)

        # Format visible only for Djangoplicity: `Original` files are
        # TIFFs of several hundred MB, the warning lives in the option
        # label.
        self.combo_format = QComboBox()
        self.combo_format.addItems(list(DJANGOPLICITY_FORMATS))
        libelle_format_courant = next(
            (libelle for libelle, val in DJANGOPLICITY_FORMATS.items()
             if val == cfg.image_format),
            next(iter(DJANGOPLICITY_FORMATS)),
        )
        self.combo_format.setCurrentText(libelle_format_courant)
        self.combo_format.setToolTip(self.tr(
            "Resolution downloaded from Djangoplicity. Original = TIFF (often >100 MB)."))
        self.label_format = QLabel(self.tr("Format:"))
        form.addRow(self.label_format, self.combo_format)

        self.combo_type.currentTextChanged.connect(self._sur_changement_type)

        # --- destination (inline row, not a group) -------------------------
        ligne_dest = QHBoxLayout()
        self.champ_dossier = QLineEdit(cfg.target_dir)
        ligne_dest.addWidget(self.champ_dossier, 1)
        bouton = QPushButton(self.tr("Browse…"))
        bouton.clicked.connect(self._choisir_dossier)
        ligne_dest.addWidget(bouton)
        form.addRow(self.tr("Destination:"), ligne_dest)

        self.combo_classement = QComboBox()
        self.combo_classement.addItems(list(SORT_MODES))
        self.combo_classement.setCurrentText(cfg.sort_mode_label)
        self.combo_classement.setToolTip(self.tr(
            "Changes the destination of new images. Images already\n"
            "downloaded stay where they are."))
        form.addRow(self.tr("Sort:"), self.combo_classement)

        self.spin_largeur = QSpinBox()
        self.spin_largeur.setRange(0, 10000)
        self.spin_largeur.setSingleStep(100)
        self.spin_largeur.setSuffix(self.tr(" px"))
        self.spin_largeur.setValue(cfg.min_width)
        self.spin_largeur.setToolTip(self.tr(
            "Discard logos and thumbnails below this width. 0 to keep everything."))
        form.addRow(self.tr("Minimum width:"), self.spin_largeur)

        self.case_verifier = QCheckBox(self.tr("Verify integrity of existing files"))
        self.case_verifier.setChecked(cfg.verify_integrity)
        self.case_verifier.setToolTip(self.tr(
            "Queries the server for each known file (304 response if identical).\n"
            "Slower, reserve for a one-off check."))
        form.addRow("", self.case_verifier)

        return page

    def _build_filters_tab(self) -> QWidget:
        """Placeholder for the filter fields introduced by E5 / lot 11.2.

        Created hidden today so the migration to the widgets landing
        there does not need to touch the outer :class:`QTabWidget`.
        """
        return QWidget()

    def _build_images_tab(self) -> QWidget:
        """Placeholder for the image-resizing fields introduced by E6 /
        lot 11.5.

        Created hidden today for the same reason as
        :meth:`_build_filters_tab`.
        """
        return QWidget()

    def _choisir_dossier(self) -> None:
        choix = QFileDialog.getExistingDirectory(
            self, self.tr("Where to save the images?"),
            self.champ_dossier.text() or str(Path.home()))
        if choix:
            self.champ_dossier.setText(choix)

    def _sur_changement_type(self, libelle: str) -> None:
        """The format only matters for Djangoplicity; sort modes not
        supported by the chosen source are greyed out in the combo (and if
        the one selected was just greyed out, we fall back to
        "Par date")."""
        type_courant = SOURCE_TYPES.get(libelle, "wordpress")
        est_djangoplicity = type_courant == "djangoplicity"
        # To avoid importing the adapters in the UI, the engine exposes
        # `sort_modes_for(type)`.
        supportes = sort_modes_for(type_courant)

        # Image format: only for Djangoplicity.
        for widget in (self.label_format, self.combo_format):
            widget.setVisible(est_djangoplicity)

        # Greying of unsupported sort modes.
        modele = self.combo_classement.model()
        for i in range(self.combo_classement.count()):
            libelle_item = self.combo_classement.itemText(i)
            valeur = SORT_MODES.get(libelle_item)
            item = modele.item(i)
            if item is not None:
                item.setEnabled(valeur in supportes)

        # If the current selection was just disabled, fall back to
        # "By date" (consistent default across all sources).
        valeur_courante = SORT_MODES.get(self.combo_classement.currentText())
        if valeur_courante not in supportes:
            for libelle_item, valeur in SORT_MODES.items():
                if valeur == "date":
                    self.combo_classement.setCurrentText(libelle_item)
                    break

    def appliquer(self) -> str | None:
        """Push entered values onto the config, validate them, save them,
        and propagate to system integrations. Returns a non-blocking
        error message or None."""
        c = self.cfg
        c.site = self.champ_site.text().strip()
        c.target_dir = self.champ_dossier.text()
        c.interval_hours = INTERVALS.get(self.combo_intervalle.currentText(), 24)
        c.sort_mode = SORT_MODES.get(self.combo_classement.currentText(), "gallery")
        c.source_type = SOURCE_TYPES.get(self.combo_type.currentText(), "wordpress")
        c.image_format = DJANGOPLICITY_FORMATS.get(
            self.combo_format.currentText(), "Large")
        c.min_width = self.spin_largeur.value()
        c.verify_integrity = self.case_verifier.isChecked()
        c.slideshow_dir = self.case_diaporama.isChecked()
        c.close_to_tray = self.case_barre.isChecked()
        c.check_updates_on_start = self.case_maj_demarrage.isChecked()
        c.language = self.combo_langue.currentData() or ""
        c.validate()
        c.save()

        problemes: list[str] = []
        if sys.platform == "win32":
            # auto-start
            voulu = self.case_demarrage.isChecked()
            obtenu = autostart(voulu)
            if obtenu != voulu:
                problemes.append(self.tr(
                    "Cannot change Windows autostart."))
            c.run_at_startup = obtenu
            c.save()

            # slideshow: only attempt configuration if the user explicitly
            # asks for it, and create it beforehand, otherwise an empty
            # directory would prevent building the image array.
            if c.slideshow_dir:
                dossier = Path(c.target_dir).expanduser()
                try:
                    dossier.mkdir(parents=True, exist_ok=True)
                except OSError as e:
                    problemes.append(
                        self.tr("Destination folder unavailable: {error}").format(error=e))
                else:
                    if not set_slideshow_dir(dossier):
                        problemes.append(self.tr(
                            "Cannot configure the Windows slideshow "
                            "(empty folder or COM unavailable)."))
                        c.slideshow_dir = False
                        c.save()
        return "\n".join(problemes) if problemes else None


# --------------------------------------------------------------------------- #
# "About" dialog
# --------------------------------------------------------------------------- #

class DialogueSignalerBug(QDialog):
    """Minimal form that composes a GitHub issue-opening URL.

    No GitHub token is embedded (sprint §38): on validation, the user
    is redirected to their browser with title and body already filled
    in — they only need to click "Submit new issue".
    """

    def __init__(self, parent, chemin_log: Path | None) -> None:
        """Build the form, pre-filling the technical context.

        Args:
            parent: Qt parent widget.
            chemin_log: Path of the log file to attach to the bug
                report, or ``None`` to attach nothing.
        """
        super().__init__(parent)
        self.setWindowTitle(self.tr("Report a bug"))
        self.setMinimumSize(560, 460)
        self._chemin_log = chemin_log

        colonne = QVBoxLayout(self)
        colonne.setContentsMargins(14, 14, 14, 14)
        colonne.setSpacing(8)

        intro = QLabel(self.tr(
            "Describe the problem below. “Open on GitHub” will "
            "compose the issue and open it in your browser: you will only "
            "need to click “Submit new issue” on the GitHub page.\n\n"
            "A GitHub account is required to submit the issue. If you do "
            "not have one yet, you can create one for free at the "
            "“Sign in” step from the same page."))
        intro.setWordWrap(True)
        colonne.addWidget(intro)

        self.champ_titre = QLineEdit()
        self.champ_titre.setPlaceholderText(self.tr("Short summary of the problem"))
        colonne.addWidget(QLabel(self.tr("Title:")))
        colonne.addWidget(self.champ_titre)

        self.zone_desc = QTextEdit()
        self.zone_desc.setPlaceholderText(self.tr(
            "What happens, what you expected, how to reproduce."))
        colonne.addWidget(QLabel(self.tr("Description:")))
        colonne.addWidget(self.zone_desc, 1)

        self.case_contexte = QCheckBox(self.tr(
            "Attach the version, platform and the last 50 log lines"))
        self.case_contexte.setChecked(True)
        colonne.addWidget(self.case_contexte)

        boutons = QDialogButtonBox(self)
        bouton_go = boutons.addButton(self.tr("Open on GitHub"), QDialogButtonBox.AcceptRole)
        boutons.addButton(QDialogButtonBox.Cancel)
        bouton_go.clicked.connect(self._envoyer)
        boutons.rejected.connect(self.reject)
        colonne.addWidget(boutons)

    def _envoyer(self) -> None:
        titre = self.champ_titre.text().strip() or self.tr("Bug report")
        description = self.zone_desc.toPlainText().strip()
        if not description:
            QMessageBox.warning(
                self, self.tr("Report a bug"),
                self.tr("Please add a description before opening the issue."))
            return
        corps = description
        contexte_joint = self.case_contexte.isChecked()
        if contexte_joint:
            corps = f"{description}\n\n{collect_context(__version__, self._chemin_log)}"
        url = build_issue_url(GITHUB_OWNER, GITHUB_REPOSITORY, titre, corps)
        if is_url_too_long(url):
            piste = (
                self.tr("Uncheck “Attach the version, platform and the last "
                        "50 log lines” (you can paste the log in a comment), "
                        "or shorten the description.")
                if contexte_joint
                else self.tr("Shorten the description before trying again.")
            )
            QMessageBox.warning(
                self, self.tr("Report a bug"),
                self.tr("Your report is too long to be pre-filled via the "
                        "GitHub URL ({length} characters, maximum {cap}).\n\n"
                        "{hint}").format(
                    length=len(url), cap=MAX_URL_LENGTH, hint=piste))
            return
        QDesktopServices.openUrl(QUrl(url))
        self.accept()


class DialogueAPropos(QDialog):
    """Application information window."""

    def __init__(self, parent) -> None:
        """Build the fixed-size "About" dialog.

        Args:
            parent: Qt parent widget.
        """
        super().__init__(parent)
        self.setWindowTitle(self.tr("About Glaneur"))
        self.setFixedSize(440, 320)

        colonne = QVBoxLayout(self)
        colonne.setContentsMargins(20, 20, 20, 16)
        colonne.setSpacing(8)

        icone = QLabel()
        icone.setPixmap(icone_application().pixmap(72, 72))
        icone.setAlignment(Qt.AlignCenter)
        colonne.addWidget(icone)

        titre = QLabel("Glaneur")
        titre.setStyleSheet(f"font-size: 17px; font-weight: 700; color: {GRENAT};")
        titre.setAlignment(Qt.AlignCenter)
        colonne.addWidget(titre)

        version = QLabel(self.tr("Version {version}").format(version=__version__))
        version.setStyleSheet("color: #666;")
        version.setAlignment(Qt.AlignCenter)
        colonne.addWidget(version)

        colonne.addSpacing(6)

        desc = QLabel(self.tr(
            "Downloads and locally syncs images published by a remote "
            "site (WordPress, Djangoplicity…)."))
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignCenter)
        colonne.addWidget(desc)

        lien = QLabel(f'<a href="{DEPOT_URL}">{DEPOT_URL}</a>')
        lien.setOpenExternalLinks(True)
        lien.setAlignment(Qt.AlignCenter)
        colonne.addWidget(lien)

        licence = QLabel(self.tr(
            "Distributed under the GNU GPL v3 licence. See the LICENSE file."))
        licence.setStyleSheet("color: #666; font-size: 11px;")
        licence.setAlignment(Qt.AlignCenter)
        licence.setWordWrap(True)
        colonne.addWidget(licence)

        colonne.addStretch(1)

        boutons = QDialogButtonBox(QDialogButtonBox.Close, self)
        boutons.rejected.connect(self.accept)
        boutons.button(QDialogButtonBox.Close).clicked.connect(self.accept)
        colonne.addWidget(boutons)


# --------------------------------------------------------------------------- #
# Main window
# --------------------------------------------------------------------------- #

class Fenetre(QMainWindow):
    """Main application window.

    Orchestrates the configuration, the engine (through
    :class:`Travailleur`), the scheduler, the notification-area icon
    and the startup update check. All business logic lives elsewhere:
    this class only assembles the widgets and relays signals between
    them.
    """

    def __init__(self) -> None:
        """Load the config, build the UI, and start the deadline timer."""
        super().__init__()
        self.setWindowTitle(self.tr("Glaneur — Image downloader {version}").format(
            version=__version__))
        self.setWindowIcon(icone_application())
        self.resize(760, 520)
        self.setMinimumSize(QSize(600, 400))

        self.cfg = Config.load()
        self.planificateur = Scheduler(self.cfg)
        self.stop_event = threading.Event()
        self.travailleur: Travailleur | None = None
        self.auto_en_cours = False
        #: Index of the profile row the engine is currently updating.
        #: Set by :meth:`_lancer`; consumed by :meth:`_terminer`.
        self._row_en_cours: int = 0
        self._quitter_demande = False
        self.verification_mise_a_jour: UpdateCheck | None = None
        self.telechargement_mise_a_jour: UpdateDownload | None = None

        self._avertissement_tray_montre = False

        self._construire_menu()
        self._construire()
        self._construire_barre_notification()
        self._appliquer_diaporama_au_demarrage()

        self.minuteur_echeance = QTimer(self)
        self.minuteur_echeance.timeout.connect(self._verifier_echeance)
        self.minuteur_echeance.start(PERIODE_ECHEANCE)

        self.minuteur_affichage = QTimer(self)
        self.minuteur_affichage.timeout.connect(self._rafraichir_echeance)
        self.minuteur_affichage.start(PERIODE_AFFICHAGE)
        self._rafraichir_echeance()

        if sys.platform == "win32" and self.cfg.check_updates_on_start:
            QTimer.singleShot(3000, self._verifier_mise_a_jour)

    # ------------------------------------------------------------------ UI --

    def _construire_menu(self) -> None:
        barre = self.menuBar()

        menu_fichier = barre.addMenu(self.tr("&File"))
        self.action_maj = menu_fichier.addAction(self.tr("&Update now"))
        self.action_maj.setShortcut(QKeySequence("Ctrl+R"))
        self.action_maj.triggered.connect(self._lancer)

        self.action_arreter_menu = menu_fichier.addAction(self.tr("&Stop"))
        self.action_arreter_menu.setEnabled(False)
        self.action_arreter_menu.triggered.connect(self._arreter)

        menu_fichier.addSeparator()
        action_ouvrir = menu_fichier.addAction(self.tr("&Open the folder"))
        action_ouvrir.triggered.connect(self._ouvrir_dossier)

        menu_fichier.addSeparator()
        action_supprimees = menu_fichier.addAction(self.tr("&Deleted images…"))
        action_supprimees.triggered.connect(self._gerer_supprimees)

        self.action_supprimer_fond = menu_fichier.addAction(self.tr("Remove this &wallpaper"))
        self.action_supprimer_fond.triggered.connect(self._supprimer_fond)
        self.action_supprimer_fond.setEnabled(sys.platform == "win32")

        menu_fichier.addSeparator()
        action_quitter = menu_fichier.addAction(self.tr("&Quit"))
        action_quitter.setShortcut(QKeySequence("Ctrl+Q"))
        action_quitter.triggered.connect(self._quitter)

        menu_conf = barre.addMenu(self.tr("&Configuration"))
        action_prefs = menu_conf.addAction(self.tr("&Preferences…"))
        action_prefs.setShortcut(QKeySequence("Ctrl+,"))
        action_prefs.triggered.connect(self._ouvrir_preferences)

        menu_aide = barre.addMenu(self.tr("&Help"))
        action_check_maj = menu_aide.addAction(self.tr("&Check for updates…"))
        action_check_maj.triggered.connect(
            lambda: self._verifier_mise_a_jour(manuel=True))
        action_check_maj.setEnabled(sys.platform == "win32")
        action_signaler = menu_aide.addAction(self.tr("&Report a bug…"))
        action_signaler.triggered.connect(self._ouvrir_signaler_bug)
        action_apropos = menu_aide.addAction(self.tr("&About…"))
        action_apropos.triggered.connect(self._ouvrir_apropos)

    def _construire(self) -> None:
        self.setStyleSheet(f"""
            QPushButton#principal {{
                background: {GRENAT};
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 18px;
                font-weight: 600;
            }}
            QPushButton#principal:hover  {{ background: #5c1d30; }}
            QPushButton#principal:disabled {{ background: #b9a5ab; }}
            QProgressBar {{
                border: 1px solid #d0d0d0;
                border-radius: 4px;
                height: 18px;
                text-align: center;
            }}
            QProgressBar::chunk {{ background: {GRENAT}; border-radius: 3px; }}
            QGroupBox {{
                font-weight: 600;
                border: 1px solid #d0d0d0;
                border-radius: 6px;
                margin-top: 10px;
                padding: 12px 10px 10px 10px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
                color: {GRENAT};
            }}
        """)

        central = QWidget()
        self.setCentralWidget(central)
        racine = QVBoxLayout(central)
        racine.setContentsMargins(14, 14, 14, 14)
        racine.setSpacing(10)

        titre = QLabel(self.tr("Glaneur — Image downloader"))
        titre.setStyleSheet(f"font-size: 17px; font-weight: 700; color: {GRENAT};")
        racine.addWidget(titre)

        # Profile list (lot 5.0 E2): one row today, keyed off the flat
        # `Config`. Lot 5.1 promotes it to a real per-profile list.
        self.profils_model = ProfileTableModel(self)
        self.table_profils = QTableView()
        self.table_profils.setModel(self.profils_model)
        self.table_profils.setToolTip(self.tr("Editable via Configuration → Preferences…"))
        self.table_profils.setSelectionMode(QTableView.SingleSelection)
        self.table_profils.setSelectionBehavior(QTableView.SelectRows)
        self.table_profils.setEditTriggers(QTableView.NoEditTriggers)
        self.table_profils.verticalHeader().setVisible(False)
        self.table_profils.horizontalHeader().setStretchLastSection(True)
        # Height range: enough for one row plus header (typical case),
        # capped so several extra profiles do not eat the journal area
        # — the internal scrollbar kicks in beyond the cap.
        self.table_profils.setMinimumHeight(60)
        self.table_profils.setMaximumHeight(160)
        racine.addWidget(self.table_profils)

        # Legacy aliases kept as None so any stray reference to the old
        # labels raises AttributeError instead of silently going through
        # a leftover widget. (`_rafraichir_bandeau` alias still routes
        # updates to the model.)
        self.label_site = None
        self.label_dossier = None

        # --- actions -------------------------------------------------------
        ligne = QHBoxLayout()
        self.bouton_lancer = QPushButton(self.tr("Update now"))
        self.bouton_lancer.setObjectName("principal")
        self.bouton_lancer.clicked.connect(self._lancer)
        ligne.addWidget(self.bouton_lancer)

        self.bouton_arreter = QPushButton(self.tr("Stop"))
        self.bouton_arreter.setEnabled(False)
        self.bouton_arreter.clicked.connect(self._arreter)
        ligne.addWidget(self.bouton_arreter)

        self.bouton_supprimer_fond = QPushButton(self.tr("Remove current wallpaper"))
        self.bouton_supprimer_fond.setToolTip(self.tr(
            "Erases the image currently shown by the Windows slideshow\n"
            "and excludes it from future updates."))
        self.bouton_supprimer_fond.clicked.connect(self._supprimer_fond)
        self.bouton_supprimer_fond.setEnabled(sys.platform == "win32")
        ligne.addWidget(self.bouton_supprimer_fond)

        self.bouton_supprimees = QPushButton(self.tr("Deleted images…"))
        self.bouton_supprimees.setToolTip(self.tr(
            "Images erased from the folder that the application will no longer re-download."))
        self.bouton_supprimees.clicked.connect(self._gerer_supprimees)
        ligne.addWidget(self.bouton_supprimees)
        ligne.addStretch(1)

        self.label_echeance = QLabel()
        self.label_echeance.setStyleSheet("color: #666;")
        ligne.addWidget(self.label_echeance)
        racine.addLayout(ligne)

        # --- progression ---------------------------------------------------
        self.barre = QProgressBar()
        self.barre.setRange(0, 100)
        self.barre.setValue(0)
        racine.addWidget(self.barre)

        self.label_statut = QLabel(self.tr("Ready."))
        racine.addWidget(self.label_statut)

        # --- journal -------------------------------------------------------
        boite = QGroupBox(self.tr("Journal"))
        colonne = QVBoxLayout(boite)
        self.journal = QPlainTextEdit()
        self.journal.setReadOnly(True)
        self.journal.setMaximumBlockCount(2000)   # caps memory across long runs
        self.journal.setFont(QFont("Consolas", 9))
        colonne.addWidget(self.journal)
        racine.addWidget(boite, 1)

        self._rafraichir_bandeau()

    def _construire_barre_notification(self) -> None:
        # Actions referenced elsewhere (setEnabled during/after a run): we
        # create them in every case, even if we do not attach them to a
        # menu when no tray is available.
        self.action_afficher = QAction(self.tr("Show window"), self)
        self.action_afficher.triggered.connect(self._afficher)
        self.action_maj_tray = QAction(self.tr("Update now"), self)
        self.action_maj_tray.triggered.connect(self._lancer)
        self.action_supprimer_fond_tray = QAction(self.tr("Remove this wallpaper"), self)
        self.action_supprimer_fond_tray.triggered.connect(self._supprimer_fond)
        self.action_supprimer_fond_tray.setEnabled(sys.platform == "win32")

        # On Linux without a tray host (GNOME without AppIndicator, minimal
        # WM…), calling QSystemTrayIcon.show() triggers the D-Bus error
        # `org.freedesktop.DBus.Error.ServiceUnknown` and the icon never
        # shows. We detect the case and simply do not install a tray:
        # `main()` then switches to QuitOnLastWindowClosed(True), and
        # `closeEvent` warns the user on the first close.
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = None
            return

        self.tray = QSystemTrayIcon(icone_application(), self)
        self.tray.setToolTip(self.tr("Glaneur — Image downloader"))

        menu = QMenu()
        menu.addAction(self.action_afficher)
        menu.addAction(self.action_maj_tray)
        menu.addAction(self.action_supprimer_fond_tray)

        action = QAction(self.tr("Open the folder"), self)
        action.triggered.connect(self._ouvrir_dossier)
        menu.addAction(action)
        menu.addSeparator()

        action = QAction(self.tr("Preferences…"), self)
        action.triggered.connect(self._ouvrir_preferences)
        menu.addAction(action)
        menu.addSeparator()

        action = QAction(self.tr("Quit"), self)
        action.triggered.connect(self._quitter)
        menu.addAction(action)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._clic_barre)
        self.tray.show()

    def _rafraichir_table_profils(self, status: str | None = None) -> None:
        """Push fresh :class:`ProfileRow` entries for every profile.

        The default profile is at row 0; extra profiles land in the
        order :meth:`Glaneur.config.Config.profiles` returns them.

        Args:
            status: Optional status override for the default (row-0)
                profile. When ``None`` (default), the current row-0
                status column is preserved so a background refresh
                does not clobber an in-flight run label. Extra
                profiles are always shown with an em-dash status
                today — the engine only runs the default one.
        """
        if status is None and self.profils_model.rowCount() > 0:
            current = self.profils_model.data(
                self.profils_model.index(0, 5), Qt.DisplayRole)
            status = current if current and current != "—" else ""
        profiles = self.cfg.profiles()
        rows = [_profile_row_from(profiles[0], status or "")]
        rows.extend(_profile_row_from(p) for p in profiles[1:])
        self.profils_model.set_rows(rows)

    def _rafraichir_bandeau(self) -> None:
        """Kept as a single-line forwarder so existing callers
        (``_ouvrir_preferences``) do not have to know about the table
        rename. Will be dropped once every caller uses the new name."""
        self._rafraichir_table_profils()

    @staticmethod
    def _status_from_result(res: RunResult) -> str:
        """Terminal status derived from a :class:`RunResult`.

        Args:
            res: The result the engine emitted.

        Returns:
            A short translated string ready for the ``Status`` column of
            the profile list.
        """
        if res.deferred:
            if res.retry_after:
                return QCoreApplication.translate(
                    "UiTable", "Deferred until {until}").format(
                    until=res.retry_after[:16].replace("T", " "))
            return QCoreApplication.translate("UiTable", "Deferred")
        if res.interrupted:
            return QCoreApplication.translate("UiTable", "Interrupted")
        if res.failures and not res.downloaded:
            return QCoreApplication.translate("UiTable", "Failed")
        return QCoreApplication.translate(
            "UiTable", "Done — {n} downloaded").format(n=res.downloaded)

    def _appliquer_diaporama_au_demarrage(self) -> None:
        """Reconfigure the slideshow on every launch when the option is on
        — the folder contents may have changed since last time."""
        if sys.platform == "win32" and self.cfg.slideshow_dir:
            dossier = Path(self.cfg.target_dir).expanduser()
            if dossier.is_dir():
                set_slideshow_dir(dossier)

    # ------------------------------------------------------------ actions --


    def _ouvrir_preferences(self) -> None:
        dlg = DialoguePreferences(self, self.cfg)
        if dlg.exec() == QDialog.Accepted:
            probleme = dlg.appliquer()
            self._rafraichir_bandeau()
            self._rafraichir_echeance()
            if probleme:
                QMessageBox.warning(self, self.tr("Preferences"), probleme)

    def _ouvrir_apropos(self) -> None:
        DialogueAPropos(self).exec()

    def _ouvrir_signaler_bug(self) -> None:
        from Glaneur.config import config_dir
        chemin_log = config_dir() / "logs" / "app.log"
        DialogueSignalerBug(self, chemin_log if chemin_log.is_file() else None).exec()

    def _verifier_mise_a_jour(self, manuel: bool = False) -> None:
        if self._thread_maj_en_cours(self.verification_mise_a_jour):
            return
        thread = UpdateCheck(self)
        thread.available.connect(self._mise_a_jour_disponible)
        if manuel:
            thread.up_to_date.connect(self._aucune_mise_a_jour_manuel)
            thread.error.connect(self._erreur_verification_manuel)
        else:
            thread.error.connect(self._ecrire)
        thread.finished.connect(self._maj_verif_terminee)
        thread.finished.connect(thread.deleteLater)
        self.verification_mise_a_jour = thread
        thread.start()

    def _maj_verif_terminee(self) -> None:
        # Release the reference before deleteLater removes the C++ QThread,
        # otherwise the attribute would point to a dead wrapper and the
        # next click on "Check for updates…" would raise RuntimeError.
        self.verification_mise_a_jour = None

    @staticmethod
    def _thread_maj_en_cours(thread) -> bool:
        """True if ``thread`` is not None, not a dead wrapper, and still running."""
        if thread is None:
            return False
        try:
            return thread.isRunning()
        except RuntimeError:
            return False

    def _aucune_mise_a_jour_manuel(self, info) -> None:
        QMessageBox.information(
            self,
            self.tr("Check for updates"),
            self.tr("You are already on the latest version ({version}).").format(
                version=info.current),
        )

    def _erreur_verification_manuel(self, message: str) -> None:
        self._ecrire(message)
        QMessageBox.warning(self, self.tr("Check for updates"), message)

    def _mise_a_jour_disponible(self, info) -> None:
        release = info.latest
        reponse = QMessageBox.question(
            self,
            self.tr("Update available"),
            self.tr("A new version is available.\n\n"
                    "Current version: {current}\n"
                    "New version: {new}\n\n"
                    "Download and install now?").format(
                current=info.current, new=release.version),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if reponse != QMessageBox.Yes:
            self._ecrire(self.tr("Update {version} deferred.").format(
                version=release.version))
            return
        self._ecrire(self.tr("Downloading update {version}…").format(
            version=release.version))
        self.telechargement_mise_a_jour = UpdateDownload(release)
        self.telechargement_mise_a_jour.completed.connect(self._mise_a_jour_telechargee)
        self.telechargement_mise_a_jour.error.connect(self._ecrire)
        self.telechargement_mise_a_jour.finished.connect(
            self.telechargement_mise_a_jour.deleteLater)
        self.telechargement_mise_a_jour.start()

    def _mise_a_jour_telechargee(self, installer: Path, _dossier: str) -> None:
        import logging
        import subprocess
        log = logging.getLogger("Glaneur.app.update")
        # Launch Inno Setup directly, detached, without going through a
        # separate updater: the old intermediary ran from the install
        # directory, RestartManager detected it as a process locking
        # target files, and Setup gave up
        # ("Some applications could not be shut down"). Here, the app
        # itself is targeted by /CLOSEAPPLICATIONS via RestartManager —
        # which works fine since it is NOT the process launching Setup —
        # then Inno replaces the files and relaunches the app via [Run]
        # at the end of install.
        log_inno = installer.parent / "inno-setup.log"
        cmd = [
            str(installer),
            "/VERYSILENT",
            "/SUPPRESSMSGBOXES",
            "/CLOSEAPPLICATIONS",
            "/CLOSEAPPLICATIONSFILTER=Glaneur.exe",
            f"/LOG={log_inno}",
        ]
        log.info("Lancement de l'installateur (détaché) : %r", cmd)
        creationflags = 0
        if sys.platform == "win32":
            creationflags = (getattr(subprocess, "DETACHED_PROCESS", 0)
                             | getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0)
                             | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
        try:
            subprocess.Popen(
                cmd,
                close_fds=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )
        except OSError as error:
            log.exception("Lancement de l'installateur impossible")
            self._ecrire(self.tr("Cannot launch the installer: {error}").format(
                error=error))
            return
        log.info("Installateur lancé, log Inno attendu ici : %s. Fermeture de l'app.", log_inno)
        self._ecrire(self.tr("Update launched, closing for installation…"))
        self._quitter_demande = True
        self.close()

    def _ouvrir_dossier(self) -> None:
        try:
            open_dir(Path(self.cfg.target_dir))
        except OSError as e:
            QMessageBox.warning(self, self.tr("Folder unavailable"), str(e))

    def _gerer_supprimees(self) -> None:
        dossier = Path(self.cfg.target_dir).expanduser()
        entrees = list_deleted(dossier)
        if not entrees:
            QMessageBox.information(
                self, self.tr("Deleted images"),
                self.tr("No deleted image is recorded for this folder."))
            return
        dialogue = DialogueSupprimees(self, entrees)
        if dialogue.exec() != QDialog.Accepted or not dialogue.choix():
            return
        n = restore(dossier, dialogue.choix())
        self._ecrire(self.tr("{n} image(s) will be re-downloaded at the next update.").format(n=n))

    def _supprimer_fond(self) -> None:
        fond = current_wallpaper()
        if fond is None:
            QMessageBox.information(
                self, self.tr("Wallpaper"),
                self.tr("Cannot determine the image currently shown.\n"
                        "Feature only available on Windows, with an\n"
                        "active wallpaper slideshow."))
            return
        dossier = Path(self.cfg.target_dir).expanduser()
        # simple ownership check for the message; the engine will run
        # its own check again before erasing anything
        try:
            base = os.path.normcase(os.path.realpath(str(dossier)))
            cible = os.path.normcase(os.path.realpath(str(fond)))
            interne = os.path.commonpath([base, cible]) == base
        except (OSError, ValueError):
            interne = False
        if not interne:
            QMessageBox.information(
                self, self.tr("Wallpaper outside the tracked folder"),
                self.tr("The displayed image does not belong to the tracked folder:\n{wallpaper}\n\n"
                        "Nothing was deleted.").format(wallpaper=fond))
            return
        reponse = QMessageBox.question(
            self, self.tr("Remove current wallpaper"),
            self.tr("Permanently delete this image?\n{wallpaper}\n\n"
                    "It will no longer be re-downloaded by future updates.").format(
                wallpaper=fond))
        if reponse != QMessageBox.Yes:
            return
        if delete_image(dossier, fond):
            advance_slideshow()
            self._ecrire(self.tr("Wallpaper removed: {wallpaper}").format(wallpaper=fond))
        else:
            self._ecrire(self.tr("Wallpaper removal failed: {wallpaper}").format(wallpaper=fond))

    def _selected_profile_row(self) -> int:
        """Return the row index of the currently selected profile.

        Falls back to row 0 (the default profile) when no row is
        selected or the selection is out of bounds. Auto-triggered
        runs (:meth:`_verifier_echeance`) also come through here and
        get the default profile, matching the pre-multi-profile
        behaviour every existing scheduled setup depends on.
        """
        rows_ok = self.profils_model.rowCount()
        if rows_ok <= 0:
            return 0
        indexes = self.table_profils.selectionModel().selectedRows()
        if indexes and 0 <= indexes[0].row() < rows_ok:
            return indexes[0].row()
        return 0

    def _lancer(self, auto: bool = False) -> None:
        if self.travailleur and self.travailleur.isRunning():
            return
        # Pick the profile to run: an auto-triggered run stays on the
        # default profile (index 0) so scheduled cadence keeps matching
        # today's behaviour; a user click respects the table selection.
        row = 0 if auto else self._selected_profile_row()
        profile = self.cfg.profiles()[row]
        defaults = self.cfg.defaults()
        dossier = Path(profile.target_dir).expanduser()
        try:
            dossier.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            message = self.tr("Cannot use this folder:\n{error}").format(error=e)
            if auto:
                self._ecrire(message.replace("\n", " "))
                return
            QMessageBox.critical(self, self.tr("Invalid folder"), message)
            return

        self.auto_en_cours = bool(auto)
        self._row_en_cours = row
        self.stop_event.clear()
        self.bouton_lancer.setEnabled(False)
        self.action_maj.setEnabled(False)
        self.action_maj_tray.setEnabled(False)
        self.bouton_arreter.setEnabled(True)
        self.action_arreter_menu.setEnabled(True)
        self.barre.setRange(0, 0)          # indeterminate during inventory
        self._ecrire(self.tr("--- {timestamp} — update started").format(
            timestamp=f"{datetime.now():%d/%m/%Y %H:%M}"))

        # Per-profile fields go through the picked profile; the two
        # inheritable settings (min_width, verify_integrity) resolve
        # via the None-inheritance rule against `defaults()`. The
        # request delay is application-level and stays on `cfg`.
        options = Options(
            target_dir=dossier,
            site=profile.site,
            sort_mode=profile.sort_mode,
            min_width=profile.effective_min_width(defaults),
            delay=self.cfg.request_delay,
            verify=profile.effective_verify_integrity(defaults),
            source_type=profile.source_type,
            image_format=profile.image_format,
        )
        self.travailleur = Travailleur(options, self.stop_event)
        self.travailleur.journal_event.connect(self._journal_evenement)
        self.travailleur.progres.connect(self._progres)
        self.travailleur.fini.connect(self._terminer)
        self.profils_model.set_status(
            QCoreApplication.translate("UiTable", "Running…"),
            row=self._row_en_cours)
        self.travailleur.start()

    def _journal_evenement(self, event: EngineEvent) -> None:
        """Render an engine event and append it to the journal widget."""
        self._ecrire(_render_ui(event))

    def _arreter(self) -> None:
        self.stop_event.set()
        self.bouton_arreter.setEnabled(False)
        self.action_arreter_menu.setEnabled(False)
        self.label_statut.setText(self.tr("Stopping…"))

    def _quitter(self) -> None:
        self._quitter_demande = True
        self.close()

    def _afficher(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _clic_barre(self, raison) -> None:
        if raison == QSystemTrayIcon.DoubleClick:
            self._afficher()

    # ---------------------------------------------------------- responses --

    def _progres(self, fait: int, total: int, etiquette: str) -> None:
        self.barre.setRange(0, max(total, 1))
        self.barre.setValue(fait)
        self.label_statut.setText(self.tr("{done}/{total} — {label}").format(
            done=fait, total=total, label=etiquette))

    def _terminer(self, res: RunResult) -> None:
        self.bouton_lancer.setEnabled(True)
        self.action_maj.setEnabled(True)
        self.action_maj_tray.setEnabled(True)
        self.bouton_arreter.setEnabled(False)
        self.action_arreter_menu.setEnabled(False)
        self.barre.setRange(0, 100)
        self.barre.setValue(0 if res.interrupted else 100)

        # Prefer the structured event when the engine set one, so the
        # summary is translated on the fly rather than shown in English.
        rendu = _render_ui(res.message_event) if res.message_event else res.message
        self.label_statut.setText(rendu)
        self._ecrire(rendu)
        self.profils_model.set_status(self._status_from_result(res),
                                      row=self._row_en_cours)
        if res.already_present:
            self._ecrire(self.tr("{n} image(s) already present, not re-downloaded.").format(
                n=res.already_present))
        if res.skipped:
            self._ecrire(self.tr(
                "{n} image(s) that you had deleted, skipped — "
                "use the “Deleted images…” button to re-queue them.").format(n=res.skipped))
        if res.failures and not res.deferred:
            # On defer, `res.message` already explains the cut and gives
            # the deadline — no redundant/misleading "will be retried".
            self._ecrire(self.tr("{n} failure(s) — will be retried at the next update.").format(
                n=res.failures))

        if res.deferred:
            self.planificateur.defer(res)
        elif not res.interrupted:
            self.planificateur.mark_run()
        self._rafraichir_echeance()

        # info bubble only if the user was not watching
        if (self.tray and self.auto_en_cours and self.cfg.notifications
                and res.downloaded and not self.isVisible()):
            self.tray.showMessage(
                "Glaneur",
                self.tr("{n} new image(s) — {size}").format(
                    n=res.downloaded, size=format_bytes(res.bytes)),
                icone_application(), 5000)
        self.auto_en_cours = False

    def _verifier_echeance(self) -> None:
        if self.travailleur and self.travailleur.isRunning():
            return
        if self.planificateur.is_due():
            self._ecrire(self.tr("Automatic update triggered."))
            self._lancer(auto=True)

    def _rafraichir_echeance(self) -> None:
        texte = next_run_text(self.planificateur)
        self.label_echeance.setText(texte)
        if self.tray:
            self.tray.setToolTip(self.tr("Glaneur — {text}").format(text=texte))

    def _ecrire(self, message: str) -> None:
        self.journal.appendPlainText(f"{datetime.now():%H:%M:%S}  {message}")

    # -------------------------------------------------------------- exit ---

    def closeEvent(self, event) -> None:
        """Intercept close so we minimise to the notification area.

        Behaviour:

        - the close button minimises to the tray while
          :attr:`Config.close_to_tray` is true and a tray is
          available;
        - on Linux without a tray host, warn once per session before
          actually quitting;
        - if a run is in progress, ask for confirmation before
          interrupting.

        Args:
            event: :class:`QCloseEvent` provided by Qt.
        """
        # the close button minimizes to the notification area, unless requested otherwise
        if (not self._quitter_demande and self.cfg.close_to_tray
                and self.tray and self.tray.isVisible()):
            event.ignore()
            self.hide()
            self.tray.showMessage(
                "Glaneur",
                self.tr("The application keeps running in the background. Right-click the icon to quit."),
                icone_application(), 4000)
            return

        # On Linux without a tray host, the application cannot stay in the
        # background: we warn the user (once per session) before actually
        # quitting, and point to the extension to install.
        if (self.tray is None and sys.platform.startswith("linux")
                and not self._quitter_demande
                and self.cfg.close_to_tray
                and not self._avertissement_tray_montre):
            self._avertissement_tray_montre = True
            QMessageBox.information(
                self, self.tr("Closing Glaneur"),
                self.tr(
                    "No system tray indicator is available on this Linux session, "
                    "the application cannot stay in the background and will close.\n\n"
                    "For it to keep running as an icon in the system tray, install "
                    "the “AppIndicator and KStatusNotifierItem Support” extension "
                    "(GNOME Shell) or the equivalent for your environment, then relaunch "
                    "the application."))

        if self.travailleur and self.travailleur.isRunning():
            reponse = QMessageBox.question(
                self, self.tr("Quit"),
                self.tr("An update is running. It will resume at the next launch.\n"
                        "Quit now?"))
            if reponse != QMessageBox.Yes:
                self._quitter_demande = False
                event.ignore()
                return
            self.stop_event.set()
            self.travailleur.wait(5000)

        if self.tray:
            self.tray.hide()
        event.accept()
        # setQuitOnLastWindowClosed(False) prevents the app from quitting
        # when the window closes — essential to stay in the tray, but
        # blocking when we really want to exit (Quit menu, tray > Quit,
        # or handoff to the updater). We force the quit here for those cases.
        if self._quitter_demande:
            QApplication.quit()


# --------------------------------------------------------------------------- #

def main() -> int:
    """GUI application entry point.

    Runs in order:

    1. optional migration of a ``WpImageDownloader``-era config;
    2. file + console logging setup;
    3. creation of the :class:`QApplication`;
    4. installation of the Qt translator (before any widget);
    5. construction of the main :class:`Fenetre`, possibly hidden if
       ``--reduit`` is passed on the command line;
    6. Qt event loop.

    Returns:
        The exit code returned by ``QApplication.exec()``, ready to
        hand to ``sys.exit``.
    """
    if "--controle-bundle" in sys.argv:
        # Check of the PyInstaller bundle: import what the .spec might
        # forget, without opening a window. The exe is windowed
        # (`console=False`), so `sys.stdout` can be None and a `print`
        # would raise — we signal the result via the exit code alone.
        import Glaneur.engine
        import Glaneur.sources
        import Glaneur.updater
        sys.exit(0)

    from Glaneur.config import config_dir, migrate_from_legacy_name
    from Glaneur.i18n import install_translator
    from Glaneur.logsetup import configure_logging
    # First: if the user has an old WpImageDownloader install and no
    # Glaneur config yet, we recover the legacy config. Runs before
    # configure_logging() so the logs also inherit the directory.
    migrate_from_legacy_name()
    configure_logging(config_dir())

    app = QApplication(sys.argv)
    app.setApplicationName("Glaneur")
    app.setWindowIcon(icone_application())
    # the application survives the window close thanks to the tray icon
    app.setQuitOnLastWindowClosed(False)

    # Translator installed BEFORE any widget construction: self.tr() calls
    # evaluated inside __init__ then pick up the correct language.
    install_translator(app, Config.load().language)

    fenetre = Fenetre()
    # Without a tray (Linux without AppIndicator), staying open after the
    # window closes would leave the app orphaned: reinstate standard quit.
    # `--reduit` (start hidden) also makes no sense without a tray —
    # otherwise the app would be invisible and quit immediately.
    if fenetre.tray is None:
        app.setQuitOnLastWindowClosed(True)
        fenetre.show()
    elif "--reduit" not in sys.argv:
        fenetre.show()

    # catch-up: due time reached while the application was closed
    QTimer.singleShot(2000, fenetre._verifier_echeance)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
