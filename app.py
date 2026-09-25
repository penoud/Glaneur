#!/usr/bin/env python3
"""Interface PySide6 du téléchargeur d'images WordPress.

L'UI ne contient aucune logique réseau : elle construit un Options, lance un
Moteur dans un QThread et reçoit ses messages par signaux Qt — qui sont
automatiquement marshalés vers le thread principal, donc aucun widget n'est
touché depuis le thread de travail.

Les paramètres sont regroupés dans un dialogue « Préférences » accessible
par la barre de menus ; la fenêtre principale ne montre que les actions,
la progression et le journal.
"""

from __future__ import annotations

import os
import sys
import threading
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QColor, QDesktopServices, QFont, QIcon, QKeySequence, QPainter, QPixmap
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
    CLASSEMENTS,
    FORMATS_DJANGOPLICITY,
    GITHUB_OWNER,
    GITHUB_REPOSITORY,
    INTERVALLES,
    TYPES_SOURCE,
    Config,
)
from Glaneur.sources import classements_pour
from Glaneur.engine import (
    Moteur,
    Options,
    Resultat,
    format_octets,
    lister_supprimees,
    restaurer,
    supprimer_image,
)
from Glaneur.scheduler import Planificateur
from Glaneur.systeme import (
    avancer_diaporama,
    demarrage_automatique,
    demarrage_automatique_actif,
    definir_dossier_diaporama,
    fond_ecran_actuel,
    ouvrir_dossier,
)
from Glaneur.updater.qt_threads import (
    TelechargementMiseAJour,
    VerificationMiseAJour,
)

GRENAT = "#471625"
PERIODE_ECHEANCE = 30_000   # ms entre deux contrôles d'échéance
PERIODE_AFFICHAGE = 1_000   # ms entre deux rafraîchissements du compte à rebours

DEPOT_URL = "https://github.com/penoud/Glaneur"


# --------------------------------------------------------------------------- #
# Icône
# --------------------------------------------------------------------------- #

def icone_application() -> QIcon:
    """Charge build/Glaneur.ico si présent, sinon dessine un repli grenat."""
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
# Thread de travail
# --------------------------------------------------------------------------- #

class Travailleur(QThread):
    """Exécute le moteur hors du thread d'interface."""

    journal = Signal(str)
    progres = Signal(int, int, str)
    fini = Signal(object)

    def __init__(self, options: Options, arret: threading.Event) -> None:
        super().__init__()
        self.options = options
        self.arret = arret

    def run(self) -> None:
        moteur = Moteur(
            self.options,
            journal=self.journal.emit,
            progression=lambda fait, total, etq: self.progres.emit(fait, total, etq),
            arret=self.arret,
        )
        self.fini.emit(moteur.executer())


# --------------------------------------------------------------------------- #
# Dialogue des images supprimées
# --------------------------------------------------------------------------- #

class DialogueSupprimees(QDialog):
    """Liste les images effacées du disque et propose de les remettre en file."""

    def __init__(self, parent, entrees: list[dict]) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Images supprimées"))
        self.resize(540, 380)
        self.entrees = entrees

        colonne = QVBoxLayout(self)
        colonne.addWidget(QLabel(self.tr(
            "Ces images ont été téléchargées puis effacées du dossier.\n"
            "Cochez celles à retélécharger à la prochaine mise à jour.")))

        self.liste = QListWidget()
        for e in entrees:
            item = QListWidgetItem(self.tr("{fichier}    (effacée le {date})").format(
                fichier=e.get("fichier", "?"),
                date=e.get("supprime", "")[:10]))
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.liste.addItem(item)
        colonne.addWidget(self.liste, 1)

        boutons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        boutons.addButton(self.tr("Tout cocher"), QDialogButtonBox.ActionRole).clicked.connect(
            self._tout_cocher)
        boutons.accepted.connect(self.accept)
        boutons.rejected.connect(self.reject)
        colonne.addWidget(boutons)

    def _tout_cocher(self) -> None:
        for i in range(self.liste.count()):
            self.liste.item(i).setCheckState(Qt.Checked)

    def choix(self) -> list[str]:
        return [self.entrees[i]["id"] for i in range(self.liste.count())
                if self.liste.item(i).checkState() == Qt.Checked]


# --------------------------------------------------------------------------- #
# Dialogue des préférences
# --------------------------------------------------------------------------- #

class DialoguePreferences(QDialog):
    """Édite la configuration. Les valeurs sont écrites sur `cfg` uniquement
    quand l'utilisateur valide, via `appliquer()`. Cancel = tout est jeté."""

    def __init__(self, parent, cfg: Config) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Préférences"))
        self.setMinimumSize(560, 420)
        self.cfg = cfg

        colonne = QVBoxLayout(self)
        colonne.setContentsMargins(14, 14, 14, 14)
        colonne.setSpacing(10)

        # --- site ---------------------------------------------------------
        boite = QGroupBox(self.tr("Site"))
        forme_site = QFormLayout(boite)
        forme_site.setLabelAlignment(Qt.AlignLeft)

        self.combo_type = QComboBox()
        self.combo_type.addItems(list(TYPES_SOURCE))
        libelle_type_courant = next(
            (libelle for libelle, val in TYPES_SOURCE.items()
             if val == cfg.type_source),
            next(iter(TYPES_SOURCE)),
        )
        self.combo_type.setCurrentText(libelle_type_courant)
        self.combo_type.setToolTip(self.tr(
            "Type de site à interroger. WordPress lit l'API REST /wp-json,\n"
            "Djangoplicity lit le flux JSON /images/d2d/ (ESO, ESA/Hubble…)."))
        forme_site.addRow(self.tr("Type :"), self.combo_type)

        self.champ_site = QLineEdit(cfg.site)
        self.champ_site.setPlaceholderText(self.tr("https://exemple.com"))
        self.champ_site.setToolTip(self.tr(
            "URL de base du site (sans /wp-json ni /images/d2d selon le type)."))
        forme_site.addRow(self.tr("URL :"), self.champ_site)

        # Format visible seulement pour Djangoplicity : les fichiers `Original`
        # sont des TIFF de plusieurs centaines de Mo, l'avertissement est
        # dans le libellé de l'option.
        self.combo_format = QComboBox()
        self.combo_format.addItems(list(FORMATS_DJANGOPLICITY))
        libelle_format_courant = next(
            (libelle for libelle, val in FORMATS_DJANGOPLICITY.items()
             if val == cfg.format_image),
            next(iter(FORMATS_DJANGOPLICITY)),
        )
        self.combo_format.setCurrentText(libelle_format_courant)
        self.combo_format.setToolTip(self.tr(
            "Résolution téléchargée pour Djangoplicity. Original = TIFF (souvent >100 Mo)."))
        self.label_format = QLabel(self.tr("Format :"))
        forme_site.addRow(self.label_format, self.combo_format)

        self.combo_type.currentTextChanged.connect(self._sur_changement_type)
        colonne.addWidget(boite)

        # --- destination ---------------------------------------------------
        boite = QGroupBox(self.tr("Destination"))
        ligne = QHBoxLayout(boite)
        self.champ_dossier = QLineEdit(cfg.dossier)
        ligne.addWidget(self.champ_dossier, 1)
        bouton = QPushButton(self.tr("Parcourir…"))
        bouton.clicked.connect(self._choisir_dossier)
        ligne.addWidget(bouton)
        colonne.addWidget(boite)

        # --- options -------------------------------------------------------
        boite = QGroupBox(self.tr("Options"))
        form = QFormLayout(boite)
        form.setLabelAlignment(Qt.AlignLeft)

        self.combo_intervalle = QComboBox()
        self.combo_intervalle.addItems(list(INTERVALLES))
        self.combo_intervalle.setCurrentText(cfg.libelle_intervalle)
        form.addRow(self.tr("Mise à jour :"), self.combo_intervalle)

        self.combo_classement = QComboBox()
        self.combo_classement.addItems(list(CLASSEMENTS))
        self.combo_classement.setCurrentText(cfg.libelle_classement)
        self.combo_classement.setToolTip(self.tr(
            "Change la destination des nouvelles images. Les images déjà\n"
            "téléchargées restent là où elles sont."))
        form.addRow(self.tr("Classement :"), self.combo_classement)

        # Ajuste la visibilité du format et le grisage du classement en
        # fonction du type initial.
        self._sur_changement_type(self.combo_type.currentText())

        self.spin_largeur = QSpinBox()
        self.spin_largeur.setRange(0, 10000)
        self.spin_largeur.setSingleStep(100)
        self.spin_largeur.setSuffix(self.tr(" px"))
        self.spin_largeur.setValue(cfg.largeur_min)
        self.spin_largeur.setToolTip(self.tr(
            "Écarte les logos et vignettes sous cette largeur. 0 pour tout garder."))
        form.addRow(self.tr("Largeur minimale :"), self.spin_largeur)

        self.case_verifier = QCheckBox(self.tr("Vérifier l'intégrité des fichiers existants"))
        self.case_verifier.setChecked(cfg.verifier_integrite)
        self.case_verifier.setToolTip(self.tr(
            "Interroge le serveur sur chaque fichier connu (réponse 304 si identique).\n"
            "Plus lent, à réserver à un contrôle ponctuel."))
        form.addRow("", self.case_verifier)

        self.case_diaporama = QCheckBox(self.tr(
            "Utiliser ce dossier pour le diaporama Windows"))
        self.case_diaporama.setChecked(cfg.diaporama_dossier)
        self.case_diaporama.setEnabled(sys.platform == "win32")
        self.case_diaporama.setToolTip(self.tr(
            "Configure le diaporama de fond d'écran Windows pour piocher\n"
            "dans le dossier de téléchargement."))
        form.addRow("", self.case_diaporama)

        self.case_barre = QCheckBox(self.tr("Réduire dans la zone de notification à la fermeture"))
        self.case_barre.setChecked(cfg.fermer_dans_barre)
        form.addRow("", self.case_barre)

        self.case_demarrage = QCheckBox(self.tr("Lancer au démarrage de Windows"))
        self.case_demarrage.setChecked(demarrage_automatique_actif())
        self.case_demarrage.setEnabled(sys.platform == "win32")
        form.addRow("", self.case_demarrage)

        self.case_maj_demarrage = QCheckBox(self.tr("Vérifier les mises à jour au démarrage"))
        self.case_maj_demarrage.setChecked(cfg.verifier_maj_demarrage)
        self.case_maj_demarrage.setEnabled(sys.platform == "win32")
        self.case_maj_demarrage.setToolTip(self.tr(
            "Interroge GitHub en arrière-plan au lancement de l'application\n"
            "pour proposer la dernière version stable si elle est plus récente."))
        form.addRow("", self.case_maj_demarrage)

        # --- langue --------------------------------------------------------
        from Glaneur.i18n import LANGUES_DISPONIBLES
        self.combo_langue = QComboBox()
        self.combo_langue.addItem(self.tr("Langue du système"), "")
        for code, libelle in LANGUES_DISPONIBLES.items():
            self.combo_langue.addItem(libelle, code)
        for i in range(self.combo_langue.count()):
            if self.combo_langue.itemData(i) == cfg.langue:
                self.combo_langue.setCurrentIndex(i)
                break
        self.combo_langue.setToolTip(self.tr(
            "Le changement de langue prend effet au prochain lancement."))
        form.addRow(self.tr("Langue :"), self.combo_langue)

        colonne.addWidget(boite)
        colonne.addStretch(1)

        # --- boutons -------------------------------------------------------
        boutons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        boutons.accepted.connect(self.accept)
        boutons.rejected.connect(self.reject)
        colonne.addWidget(boutons)

    def _choisir_dossier(self) -> None:
        choix = QFileDialog.getExistingDirectory(
            self, self.tr("Où enregistrer les images ?"),
            self.champ_dossier.text() or str(Path.home()))
        if choix:
            self.champ_dossier.setText(choix)

    def _sur_changement_type(self, libelle: str) -> None:
        """Le format n'a de sens que pour Djangoplicity ; les classements
        non supportés par la source choisie sont grisés dans le combo (et si
        celui qui était sélectionné vient d'être grisé, on retombe sur
        « Par date »)."""
        type_courant = TYPES_SOURCE.get(libelle, "wordpress")
        est_djangoplicity = type_courant == "djangoplicity"
        # Pour éviter d'importer les adaptateurs dans l'UI, le moteur expose
        # `classements_pour(type)`.
        supportes = classements_pour(type_courant)

        # Format image : seulement pour Djangoplicity.
        for widget in (self.label_format, self.combo_format):
            widget.setVisible(est_djangoplicity)

        # Grisage des classements non supportés.
        modele = self.combo_classement.model()
        for i in range(self.combo_classement.count()):
            libelle_item = self.combo_classement.itemText(i)
            valeur = CLASSEMENTS.get(libelle_item)
            item = modele.item(i)
            if item is not None:
                item.setEnabled(valeur in supportes)

        # Si la sélection courante vient d'être désactivée, bascule sur
        # « Par date » (défaut cohérent pour toutes les sources).
        valeur_courante = CLASSEMENTS.get(self.combo_classement.currentText())
        if valeur_courante not in supportes:
            for libelle_item, valeur in CLASSEMENTS.items():
                if valeur == "date":
                    self.combo_classement.setCurrentText(libelle_item)
                    break

    def appliquer(self) -> str | None:
        """Reporte les valeurs saisies sur la config, les valide, les sauve, et
        propage aux intégrations système. Renvoie un message d'erreur non
        bloquant ou None."""
        c = self.cfg
        c.site = self.champ_site.text().strip()
        c.dossier = self.champ_dossier.text()
        c.intervalle_heures = INTERVALLES.get(self.combo_intervalle.currentText(), 24)
        c.classement = CLASSEMENTS.get(self.combo_classement.currentText(), "galerie")
        c.type_source = TYPES_SOURCE.get(self.combo_type.currentText(), "wordpress")
        c.format_image = FORMATS_DJANGOPLICITY.get(
            self.combo_format.currentText(), "Large")
        c.largeur_min = self.spin_largeur.value()
        c.verifier_integrite = self.case_verifier.isChecked()
        c.diaporama_dossier = self.case_diaporama.isChecked()
        c.fermer_dans_barre = self.case_barre.isChecked()
        c.verifier_maj_demarrage = self.case_maj_demarrage.isChecked()
        c.langue = self.combo_langue.currentData() or ""
        c.valider()
        c.sauver()

        problemes: list[str] = []
        if sys.platform == "win32":
            # démarrage automatique
            voulu = self.case_demarrage.isChecked()
            obtenu = demarrage_automatique(voulu)
            if obtenu != voulu:
                problemes.append(self.tr(
                    "Impossible de modifier le démarrage automatique de Windows."))
            c.lancer_au_demarrage = obtenu
            c.sauver()

            # diaporama : on ne tente la configuration que si l'utilisateur le
            # demande explicitement, et le crée avant, sinon le dossier vide
            # empêcherait la construction du tableau d'images.
            if c.diaporama_dossier:
                dossier = Path(c.dossier).expanduser()
                try:
                    dossier.mkdir(parents=True, exist_ok=True)
                except OSError as e:
                    problemes.append(
                        self.tr("Dossier de destination inaccessible : {erreur}").format(erreur=e))
                else:
                    if not definir_dossier_diaporama(dossier):
                        problemes.append(self.tr(
                            "Impossible de configurer le diaporama Windows "
                            "(dossier vide ou COM indisponible)."))
                        c.diaporama_dossier = False
                        c.sauver()
        return "\n".join(problemes) if problemes else None


# --------------------------------------------------------------------------- #
# Dialogue « À propos »
# --------------------------------------------------------------------------- #

class DialogueSignalerBug(QDialog):
    """Formulaire minimal qui compose une URL GitHub d'ouverture d'issue.

    On n'embarque pas de token GitHub (sprint §38) : à la validation,
    l'utilisateur est redirigé vers son navigateur avec titre et corps
    déjà remplis, il n'a plus qu'à cliquer « Submit new issue ».
    """

    def __init__(self, parent, chemin_log: Path | None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Signaler un bug"))
        self.setMinimumSize(560, 460)
        self._chemin_log = chemin_log

        colonne = QVBoxLayout(self)
        colonne.setContentsMargins(14, 14, 14, 14)
        colonne.setSpacing(8)

        intro = QLabel(self.tr(
            "Décris le problème ci-dessous. « Ouvrir sur GitHub » composera "
            "l'issue et l'ouvrira dans ton navigateur : tu n'auras plus qu'à "
            "cliquer « Submit new issue » sur la page GitHub.\n\n"
            "Un compte GitHub est nécessaire pour soumettre l'issue. Si tu "
            "n'en as pas encore, tu pourras t'en créer un gratuitement à "
            "l'étape « Sign in » depuis la même page."))
        intro.setWordWrap(True)
        colonne.addWidget(intro)

        self.champ_titre = QLineEdit()
        self.champ_titre.setPlaceholderText(self.tr("Résumé court du problème"))
        colonne.addWidget(QLabel(self.tr("Titre :")))
        colonne.addWidget(self.champ_titre)

        self.zone_desc = QTextEdit()
        self.zone_desc.setPlaceholderText(self.tr(
            "Ce qui se passe, ce que tu attendais, comment reproduire."))
        colonne.addWidget(QLabel(self.tr("Description :")))
        colonne.addWidget(self.zone_desc, 1)

        self.case_contexte = QCheckBox(self.tr(
            "Joindre la version, la plateforme et les 50 dernières lignes de log"))
        self.case_contexte.setChecked(True)
        colonne.addWidget(self.case_contexte)

        boutons = QDialogButtonBox(self)
        bouton_go = boutons.addButton(self.tr("Ouvrir sur GitHub"), QDialogButtonBox.AcceptRole)
        boutons.addButton(QDialogButtonBox.Cancel)
        bouton_go.clicked.connect(self._envoyer)
        boutons.rejected.connect(self.reject)
        colonne.addWidget(boutons)

    def _envoyer(self) -> None:
        titre = self.champ_titre.text().strip() or self.tr("Rapport de bug")
        description = self.zone_desc.toPlainText().strip()
        if not description:
            QMessageBox.warning(
                self, self.tr("Signaler un bug"),
                self.tr("Merci d'ajouter une description avant d'ouvrir l'issue."))
            return
        corps = description
        contexte_joint = self.case_contexte.isChecked()
        if contexte_joint:
            corps = f"{description}\n\n{collect_context(__version__, self._chemin_log)}"
        url = build_issue_url(GITHUB_OWNER, GITHUB_REPOSITORY, titre, corps)
        if is_url_too_long(url):
            piste = (
                self.tr("Décoche « Joindre la version, la plateforme et les 50 dernières "
                        "lignes de log » (tu pourras coller le log dans un commentaire), "
                        "ou raccourcis la description.")
                if contexte_joint
                else self.tr("Raccourcis la description avant de réessayer.")
            )
            QMessageBox.warning(
                self, self.tr("Signaler un bug"),
                self.tr("Ton rapport est trop long pour être pré-rempli via l'URL "
                        "GitHub ({longueur} caractères, maximum {plafond}).\n\n"
                        "{piste}").format(
                    longueur=len(url), plafond=MAX_URL_LENGTH, piste=piste))
            return
        QDesktopServices.openUrl(QUrl(url))
        self.accept()


class DialogueAPropos(QDialog):
    """Fenêtre d'information sur l'application."""

    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("À propos de Glaneur"))
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
            "Télécharge et synchronise en local les images publiées par un site "
            "distant (WordPress, Djangoplicity…)."))
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignCenter)
        colonne.addWidget(desc)

        lien = QLabel(f'<a href="{DEPOT_URL}">{DEPOT_URL}</a>')
        lien.setOpenExternalLinks(True)
        lien.setAlignment(Qt.AlignCenter)
        colonne.addWidget(lien)

        licence = QLabel(self.tr(
            "Distribué sous licence GNU GPL v3. Voir le fichier LICENSE."))
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
# Fenêtre principale
# --------------------------------------------------------------------------- #

class Fenetre(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(self.tr("Glaneur — Téléchargeur d'images {version}").format(
            version=__version__))
        self.setWindowIcon(icone_application())
        self.resize(760, 520)
        self.setMinimumSize(QSize(600, 400))

        self.cfg = Config.charger()
        self.planificateur = Planificateur(self.cfg)
        self.arret = threading.Event()
        self.travailleur: Travailleur | None = None
        self.auto_en_cours = False
        self._quitter_demande = False
        self.verification_mise_a_jour: VerificationMiseAJour | None = None
        self.telechargement_mise_a_jour: TelechargementMiseAJour | None = None

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

        if sys.platform == "win32" and self.cfg.verifier_maj_demarrage:
            QTimer.singleShot(3000, self._verifier_mise_a_jour)

    # ------------------------------------------------------------------ UI --

    def _construire_menu(self) -> None:
        barre = self.menuBar()

        menu_fichier = barre.addMenu(self.tr("&Fichier"))
        self.action_maj = menu_fichier.addAction(self.tr("&Mettre à jour maintenant"))
        self.action_maj.setShortcut(QKeySequence("Ctrl+R"))
        self.action_maj.triggered.connect(self._lancer)

        self.action_arreter_menu = menu_fichier.addAction(self.tr("&Arrêter"))
        self.action_arreter_menu.setEnabled(False)
        self.action_arreter_menu.triggered.connect(self._arreter)

        menu_fichier.addSeparator()
        action_ouvrir = menu_fichier.addAction(self.tr("&Ouvrir le dossier"))
        action_ouvrir.triggered.connect(self._ouvrir_dossier)

        menu_fichier.addSeparator()
        action_supprimees = menu_fichier.addAction(self.tr("&Images supprimées…"))
        action_supprimees.triggered.connect(self._gerer_supprimees)

        self.action_supprimer_fond = menu_fichier.addAction(self.tr("Supprimer ce &fond d'écran"))
        self.action_supprimer_fond.triggered.connect(self._supprimer_fond)
        self.action_supprimer_fond.setEnabled(sys.platform == "win32")

        menu_fichier.addSeparator()
        action_quitter = menu_fichier.addAction(self.tr("&Quitter"))
        action_quitter.setShortcut(QKeySequence("Ctrl+Q"))
        action_quitter.triggered.connect(self._quitter)

        menu_conf = barre.addMenu(self.tr("&Configuration"))
        action_prefs = menu_conf.addAction(self.tr("&Préférences…"))
        action_prefs.setShortcut(QKeySequence("Ctrl+,"))
        action_prefs.triggered.connect(self._ouvrir_preferences)

        menu_aide = barre.addMenu(self.tr("&Aide"))
        action_check_maj = menu_aide.addAction(self.tr("&Rechercher des mises à jour…"))
        action_check_maj.triggered.connect(
            lambda: self._verifier_mise_a_jour(manuel=True))
        action_check_maj.setEnabled(sys.platform == "win32")
        action_signaler = menu_aide.addAction(self.tr("&Signaler un bug…"))
        action_signaler.triggered.connect(self._ouvrir_signaler_bug)
        action_apropos = menu_aide.addAction(self.tr("&À propos…"))
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

        titre = QLabel(self.tr("Glaneur — Téléchargeur d'images"))
        titre.setStyleSheet(f"font-size: 17px; font-weight: 700; color: {GRENAT};")
        racine.addWidget(titre)

        self.label_site = QLabel()
        self.label_site.setStyleSheet("color: #666;")
        self.label_site.setToolTip(self.tr("Modifiable dans Configuration → Préférences…"))
        racine.addWidget(self.label_site)

        self.label_dossier = QLabel()
        self.label_dossier.setStyleSheet("color: #666;")
        self.label_dossier.setToolTip(self.tr("Modifiable dans Configuration → Préférences…"))
        racine.addWidget(self.label_dossier)

        # --- actions -------------------------------------------------------
        ligne = QHBoxLayout()
        self.bouton_lancer = QPushButton(self.tr("Mettre à jour maintenant"))
        self.bouton_lancer.setObjectName("principal")
        self.bouton_lancer.clicked.connect(self._lancer)
        ligne.addWidget(self.bouton_lancer)

        self.bouton_arreter = QPushButton(self.tr("Arrêter"))
        self.bouton_arreter.setEnabled(False)
        self.bouton_arreter.clicked.connect(self._arreter)
        ligne.addWidget(self.bouton_arreter)

        self.bouton_supprimer_fond = QPushButton(self.tr("Supprimer le fond actuel"))
        self.bouton_supprimer_fond.setToolTip(self.tr(
            "Efface l'image actuellement affichée par le diaporama Windows\n"
            "et l'exclut des prochaines mises à jour."))
        self.bouton_supprimer_fond.clicked.connect(self._supprimer_fond)
        self.bouton_supprimer_fond.setEnabled(sys.platform == "win32")
        ligne.addWidget(self.bouton_supprimer_fond)

        self.bouton_supprimees = QPushButton(self.tr("Images supprimées…"))
        self.bouton_supprimees.setToolTip(self.tr(
            "Images effacées du dossier, que l'application ne retélécharge plus."))
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

        self.label_statut = QLabel(self.tr("Prêt."))
        racine.addWidget(self.label_statut)

        # --- journal -------------------------------------------------------
        boite = QGroupBox(self.tr("Journal"))
        colonne = QVBoxLayout(boite)
        self.journal = QPlainTextEdit()
        self.journal.setReadOnly(True)
        self.journal.setMaximumBlockCount(2000)   # borne la mémoire sur de longs runs
        self.journal.setFont(QFont("Consolas", 9))
        colonne.addWidget(self.journal)
        racine.addWidget(boite, 1)

        self._rafraichir_bandeau()

    def _construire_barre_notification(self) -> None:
        # Actions rappelées ailleurs (setEnabled pendant/après un run) : on les
        # crée dans tous les cas, quitte à ne pas les attacher à un menu si
        # aucun tray n'est disponible.
        self.action_afficher = QAction(self.tr("Afficher la fenêtre"), self)
        self.action_afficher.triggered.connect(self._afficher)
        self.action_maj_tray = QAction(self.tr("Mettre à jour maintenant"), self)
        self.action_maj_tray.triggered.connect(self._lancer)
        self.action_supprimer_fond_tray = QAction(self.tr("Supprimer ce fond d'écran"), self)
        self.action_supprimer_fond_tray.triggered.connect(self._supprimer_fond)
        self.action_supprimer_fond_tray.setEnabled(sys.platform == "win32")

        # Sur Linux sans tray host (GNOME sans AppIndicator, WM minimal…),
        # instancier QSystemTrayIcon.show() déclenche l'erreur D-Bus
        # `org.freedesktop.DBus.Error.ServiceUnknown` et l'icône ne s'affiche
        # pas. On détecte le cas et on n'installe simplement pas de tray :
        # `main()` bascule alors sur QuitOnLastWindowClosed(True), et
        # `closeEvent` avertit l'utilisateur au premier close.
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = None
            return

        self.tray = QSystemTrayIcon(icone_application(), self)
        self.tray.setToolTip(self.tr("Glaneur — Téléchargeur d'images"))

        menu = QMenu()
        menu.addAction(self.action_afficher)
        menu.addAction(self.action_maj_tray)
        menu.addAction(self.action_supprimer_fond_tray)

        action = QAction(self.tr("Ouvrir le dossier"), self)
        action.triggered.connect(self._ouvrir_dossier)
        menu.addAction(action)
        menu.addSeparator()

        action = QAction(self.tr("Préférences…"), self)
        action.triggered.connect(self._ouvrir_preferences)
        menu.addAction(action)
        menu.addSeparator()

        action = QAction(self.tr("Quitter"), self)
        action.triggered.connect(self._quitter)
        menu.addAction(action)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._clic_barre)
        self.tray.show()

    def _rafraichir_bandeau(self) -> None:
        """Rafraîchit les labels d'affichage du site et du dossier."""
        self.label_site.setText(self.tr("Site : {site}").format(site=self.cfg.site or "—"))
        self.label_dossier.setText(self.tr("Dossier : {dossier}").format(
            dossier=self.cfg.dossier or "—"))

    def _appliquer_diaporama_au_demarrage(self) -> None:
        """Reconfigure le diaporama à chaque lancement si l'option est active
        — le contenu du dossier peut avoir changé depuis la dernière fois."""
        if sys.platform == "win32" and self.cfg.diaporama_dossier:
            dossier = Path(self.cfg.dossier).expanduser()
            if dossier.is_dir():
                definir_dossier_diaporama(dossier)

    # ------------------------------------------------------------ actions --

    def _ouvrir_preferences(self) -> None:
        dlg = DialoguePreferences(self, self.cfg)
        if dlg.exec() == QDialog.Accepted:
            probleme = dlg.appliquer()
            self._rafraichir_bandeau()
            self._rafraichir_echeance()
            if probleme:
                QMessageBox.warning(self, self.tr("Préférences"), probleme)

    def _ouvrir_apropos(self) -> None:
        DialogueAPropos(self).exec()

    def _ouvrir_signaler_bug(self) -> None:
        from Glaneur.config import dossier_config
        chemin_log = dossier_config() / "logs" / "app.log"
        DialogueSignalerBug(self, chemin_log if chemin_log.is_file() else None).exec()

    def _verifier_mise_a_jour(self, manuel: bool = False) -> None:
        if self._thread_maj_en_cours(self.verification_mise_a_jour):
            return
        thread = VerificationMiseAJour(self)
        thread.disponible.connect(self._mise_a_jour_disponible)
        if manuel:
            thread.aucune_maj.connect(self._aucune_mise_a_jour_manuel)
            thread.erreur.connect(self._erreur_verification_manuel)
        else:
            thread.erreur.connect(self._ecrire)
        thread.finished.connect(self._maj_verif_terminee)
        thread.finished.connect(thread.deleteLater)
        self.verification_mise_a_jour = thread
        thread.start()

    def _maj_verif_terminee(self) -> None:
        # Libère la référence avant que deleteLater ne supprime le C++ QThread,
        # sinon l'attribut pointerait vers un wrapper mort et un clic suivant
        # sur « Rechercher des mises à jour… » lèverait RuntimeError.
        self.verification_mise_a_jour = None

    @staticmethod
    def _thread_maj_en_cours(thread) -> bool:
        """True si `thread` n'est ni None ni un wrapper mort et tourne encore."""
        if thread is None:
            return False
        try:
            return thread.isRunning()
        except RuntimeError:
            return False

    def _aucune_mise_a_jour_manuel(self, info) -> None:
        QMessageBox.information(
            self,
            self.tr("Rechercher des mises à jour"),
            self.tr("Vous utilisez déjà la dernière version ({version}).").format(
                version=info.current),
        )

    def _erreur_verification_manuel(self, message: str) -> None:
        self._ecrire(message)
        QMessageBox.warning(self, self.tr("Rechercher des mises à jour"), message)

    def _mise_a_jour_disponible(self, info) -> None:
        release = info.latest
        reponse = QMessageBox.question(
            self,
            self.tr("Mise à jour disponible"),
            self.tr("Une nouvelle version est disponible.\n\n"
                    "Version actuelle : {actuelle}\n"
                    "Nouvelle version : {nouvelle}\n\n"
                    "Télécharger et installer maintenant ?").format(
                actuelle=info.current, nouvelle=release.version),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if reponse != QMessageBox.Yes:
            self._ecrire(self.tr("Mise à jour {version} reportée.").format(
                version=release.version))
            return
        self._ecrire(self.tr("Téléchargement de la mise à jour {version}…").format(
            version=release.version))
        self.telechargement_mise_a_jour = TelechargementMiseAJour(release)
        self.telechargement_mise_a_jour.termine.connect(self._mise_a_jour_telechargee)
        self.telechargement_mise_a_jour.erreur.connect(self._ecrire)
        self.telechargement_mise_a_jour.finished.connect(
            self.telechargement_mise_a_jour.deleteLater)
        self.telechargement_mise_a_jour.start()

    def _mise_a_jour_telechargee(self, installer: Path, dossier: str) -> None:
        import logging
        import subprocess
        log = logging.getLogger("Glaneur.app.update")
        # Lancement direct d'Inno Setup en détaché, sans passer par un
        # updater séparé : l'ancien intermédiaire (GlaneurUpdater.exe)
        # tournait depuis le dossier d'install, RestartManager le détectait
        # comme process verrouillant des fichiers cibles, et Setup abandonnait
        # (« Some applications could not be shut down »). Ici, l'app elle-même
        # est visée par /CLOSEAPPLICATIONS via RestartManager — ça marche bien
        # puisqu'elle n'est PAS le process qui lance Setup — puis Inno remplace
        # les fichiers et relance l'app via [Run] en fin d'install.
        log_inno = installer.parent / "inno-setup.log"
        cmd = [
            str(installer),
            "/VERYSILENT",
            "/SUPPRESSMSGBOXES",
            "/CLOSEAPPLICATIONS",
            "/CLOSEAPPLICATIONSFILTER=WpImagerDownloader.exe",
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
            self._ecrire(self.tr("Lancement de l'installateur impossible : {erreur}").format(
                erreur=error))
            return
        log.info("Installateur lancé, log Inno attendu ici : %s. Fermeture de l'app.", log_inno)
        self._ecrire(self.tr("Mise à jour lancée, fermeture pour installation…"))
        self._quitter_demande = True
        self.close()

    def _ouvrir_dossier(self) -> None:
        try:
            ouvrir_dossier(Path(self.cfg.dossier))
        except OSError as e:
            QMessageBox.warning(self, self.tr("Dossier inaccessible"), str(e))

    def _gerer_supprimees(self) -> None:
        dossier = Path(self.cfg.dossier).expanduser()
        entrees = lister_supprimees(dossier)
        if not entrees:
            QMessageBox.information(
                self, self.tr("Images supprimées"),
                self.tr("Aucune image effacée n'est mémorisée pour ce dossier."))
            return
        dialogue = DialogueSupprimees(self, entrees)
        if dialogue.exec() != QDialog.Accepted or not dialogue.choix():
            return
        n = restaurer(dossier, dialogue.choix())
        self._ecrire(self.tr("{n} image(s) seront retéléchargées à la prochaine mise à jour.").format(n=n))

    def _supprimer_fond(self) -> None:
        fond = fond_ecran_actuel()
        if fond is None:
            QMessageBox.information(
                self, self.tr("Fond d'écran"),
                self.tr("Impossible de déterminer l'image actuellement affichée.\n"
                        "Fonction disponible uniquement sous Windows, avec un\n"
                        "diaporama de fond d'écran actif."))
            return
        dossier = Path(self.cfg.dossier).expanduser()
        # simple contrôle d'appartenance pour le message ; le moteur refera
        # sa propre vérification avant d'effacer quoi que ce soit
        try:
            base = os.path.normcase(os.path.realpath(str(dossier)))
            cible = os.path.normcase(os.path.realpath(str(fond)))
            interne = os.path.commonpath([base, cible]) == base
        except (OSError, ValueError):
            interne = False
        if not interne:
            QMessageBox.information(
                self, self.tr("Fond d'écran hors du dossier suivi"),
                self.tr("L'image affichée n'appartient pas au dossier suivi :\n{fond}\n\n"
                        "Rien n'a été supprimé.").format(fond=fond))
            return
        reponse = QMessageBox.question(
            self, self.tr("Supprimer le fond actuel"),
            self.tr("Supprimer définitivement cette image ?\n{fond}\n\n"
                    "Elle ne sera plus retéléchargée par les mises à jour suivantes.").format(
                fond=fond))
        if reponse != QMessageBox.Yes:
            return
        if supprimer_image(dossier, fond):
            avancer_diaporama()
            self._ecrire(self.tr("Fond d'écran supprimé : {fond}").format(fond=fond))
        else:
            self._ecrire(self.tr("Échec de suppression du fond : {fond}").format(fond=fond))

    def _lancer(self, auto: bool = False) -> None:
        if self.travailleur and self.travailleur.isRunning():
            return
        dossier = Path(self.cfg.dossier).expanduser()
        try:
            dossier.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            message = self.tr("Impossible d'utiliser ce dossier :\n{erreur}").format(erreur=e)
            if auto:
                self._ecrire(message.replace("\n", " "))
                return
            QMessageBox.critical(self, self.tr("Dossier invalide"), message)
            return

        self.auto_en_cours = bool(auto)
        self.arret.clear()
        self.bouton_lancer.setEnabled(False)
        self.action_maj.setEnabled(False)
        self.action_maj_tray.setEnabled(False)
        # le moteur réécrit le manifeste en fin de course : restaurer ou
        # supprimer pendant qu'il tourne perdrait la modification
        self.bouton_supprimees.setEnabled(False)
        self.bouton_supprimer_fond.setEnabled(False)
        self.action_supprimer_fond.setEnabled(False)
        self.action_supprimer_fond_tray.setEnabled(False)
        self.bouton_arreter.setEnabled(True)
        self.action_arreter_menu.setEnabled(True)
        self.barre.setRange(0, 0)          # indéterminé pendant l'inventaire
        self._ecrire(self.tr("--- {horodatage} — début de la mise à jour").format(
            horodatage=f"{datetime.now():%d/%m/%Y %H:%M}"))

        options = Options(
            dossier=dossier,
            site=self.cfg.site,
            classement=self.cfg.classement,
            largeur_min=self.cfg.largeur_min,
            delai=self.cfg.delai_requetes,
            verifier=self.cfg.verifier_integrite,
            type_source=self.cfg.type_source,
            format_image=self.cfg.format_image,
        )
        self.travailleur = Travailleur(options, self.arret)
        self.travailleur.journal.connect(self._ecrire)
        self.travailleur.progres.connect(self._progres)
        self.travailleur.fini.connect(self._terminer)
        self.travailleur.start()

    def _arreter(self) -> None:
        self.arret.set()
        self.bouton_arreter.setEnabled(False)
        self.action_arreter_menu.setEnabled(False)
        self.label_statut.setText(self.tr("Arrêt en cours…"))

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

    # ----------------------------------------------------------- réponses --

    def _progres(self, fait: int, total: int, etiquette: str) -> None:
        self.barre.setRange(0, max(total, 1))
        self.barre.setValue(fait)
        self.label_statut.setText(self.tr("{fait}/{total} — {etiquette}").format(
            fait=fait, total=total, etiquette=etiquette))

    def _terminer(self, res: Resultat) -> None:
        self.bouton_lancer.setEnabled(True)
        self.action_maj.setEnabled(True)
        self.action_maj_tray.setEnabled(True)
        self.bouton_supprimees.setEnabled(True)
        self.bouton_supprimer_fond.setEnabled(sys.platform == "win32")
        self.action_supprimer_fond.setEnabled(sys.platform == "win32")
        self.action_supprimer_fond_tray.setEnabled(sys.platform == "win32")
        self.bouton_arreter.setEnabled(False)
        self.action_arreter_menu.setEnabled(False)
        self.barre.setRange(0, 100)
        self.barre.setValue(0 if res.interrompu else 100)

        self.label_statut.setText(res.message)
        self._ecrire(res.message)
        if res.deja_presentes:
            self._ecrire(self.tr("{n} image(s) déjà présentes, non retéléchargées.").format(
                n=res.deja_presentes))
        if res.ignorees:
            self._ecrire(self.tr(
                "{n} image(s) que vous aviez supprimée(s), ignorée(s) — "
                "bouton « Images supprimées… » pour en recharger.").format(n=res.ignorees))
        if res.echecs:
            self._ecrire(self.tr("{n} échec(s) — seront retentés à la prochaine mise à jour.").format(
                n=res.echecs))

        if not res.interrompu:
            self.planificateur.marquer_execution()
        self._rafraichir_echeance()

        # bulle d'information seulement si l'utilisateur ne regardait pas
        if (self.tray and self.auto_en_cours and self.cfg.notifications
                and res.telechargees and not self.isVisible()):
            self.tray.showMessage(
                "Glaneur",
                self.tr("{n} nouvelle(s) image(s) — {taille}").format(
                    n=res.telechargees, taille=format_octets(res.octets)),
                icone_application(), 5000)
        self.auto_en_cours = False

    def _verifier_echeance(self) -> None:
        if self.travailleur and self.travailleur.isRunning():
            return
        if self.planificateur.echeance_atteinte():
            self._ecrire(self.tr("Mise à jour automatique déclenchée."))
            self._lancer(auto=True)

    def _rafraichir_echeance(self) -> None:
        texte = self.planificateur.texte_prochaine()
        self.label_echeance.setText(texte)
        if self.tray:
            self.tray.setToolTip(self.tr("Glaneur — {texte}").format(texte=texte))

    def _ecrire(self, message: str) -> None:
        self.journal.appendPlainText(f"{datetime.now():%H:%M:%S}  {message}")

    # ------------------------------------------------------------ sortie ---

    def closeEvent(self, event) -> None:
        # la croix réduit dans la zone de notification, sauf demande explicite
        if (not self._quitter_demande and self.cfg.fermer_dans_barre
                and self.tray and self.tray.isVisible()):
            event.ignore()
            self.hide()
            self.tray.showMessage(
                "Glaneur",
                self.tr("L'application continue en arrière-plan. Clic droit sur l'icône pour quitter."),
                icone_application(), 4000)
            return

        # Sur Linux sans tray host, l'application ne peut pas rester en fond :
        # on prévient l'utilisateur (une fois par session) avant de vraiment
        # quitter, en pointant vers l'extension à installer.
        if (self.tray is None and sys.platform.startswith("linux")
                and not self._quitter_demande
                and self.cfg.fermer_dans_barre
                and not self._avertissement_tray_montre):
            self._avertissement_tray_montre = True
            QMessageBox.information(
                self, self.tr("Fermeture de Glaneur"),
                self.tr(
                    "Aucun indicateur système n'est disponible sur cette session Linux, "
                    "l'application ne peut pas rester en arrière-plan et va se fermer.\n\n"
                    "Pour qu'elle continue à tourner icône dans la barre système, installer "
                    "l'extension « AppIndicator and KStatusNotifierItem Support » "
                    "(GNOME Shell) ou l'équivalent de votre environnement, puis relancer "
                    "l'application."))

        if self.travailleur and self.travailleur.isRunning():
            reponse = QMessageBox.question(
                self, self.tr("Quitter"),
                self.tr("Une mise à jour est en cours. Elle reprendra au prochain lancement.\n"
                        "Quitter maintenant ?"))
            if reponse != QMessageBox.Yes:
                self._quitter_demande = False
                event.ignore()
                return
            self.arret.set()
            self.travailleur.wait(5000)

        if self.tray:
            self.tray.hide()
        event.accept()
        # setQuitOnLastWindowClosed(False) empêche l'app de quitter à la
        # fermeture de la fenêtre — indispensable pour rester en tray, mais
        # bloquant quand on veut vraiment sortir (menu Quitter, tray > Quitter,
        # ou handoff à l'updater). On force le quit ici pour ces cas.
        if self._quitter_demande:
            QApplication.quit()


# --------------------------------------------------------------------------- #

def main() -> int:
    from Glaneur.config import dossier_config
    from Glaneur.i18n import installer_traducteur
    from Glaneur.logsetup import configure_logging
    configure_logging(dossier_config())

    app = QApplication(sys.argv)
    app.setApplicationName("Glaneur")
    app.setWindowIcon(icone_application())
    # l'application survit à la fermeture de la fenêtre grâce à l'icône de barre
    app.setQuitOnLastWindowClosed(False)

    # Traducteur installé AVANT toute construction de widget : les self.tr()
    # évalués dans les __init__ récupèrent alors la bonne langue.
    installer_traducteur(app, Config.charger().langue)

    fenetre = Fenetre()
    # Sans tray (Linux sans AppIndicator), rester ouvert après la fermeture de
    # la fenêtre laisserait l'appli orpheline : on rebranche le quit standard.
    # `--reduit` (démarrage sans fenêtre visible) n'a pas de sens non plus
    # sans tray — sinon l'appli serait invisible et quitterait aussitôt.
    if fenetre.tray is None:
        app.setQuitOnLastWindowClosed(True)
        fenetre.show()
    elif "--reduit" not in sys.argv:
        fenetre.show()

    # rattrapage : échéance dépassée pendant que l'application était fermée
    QTimer.singleShot(2000, fenetre._verifier_echeance)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
