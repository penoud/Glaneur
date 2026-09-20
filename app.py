#!/usr/bin/env python3
"""Interface PySide6 du téléchargeur d'images du Servette FC.

L'UI ne contient aucune logique réseau : elle construit un Options, lance un
Moteur dans un QThread et reçoit ses messages par signaux Qt — qui sont
automatiquement marshalés vers le thread principal, donc aucun widget n'est
touché depuis le thread de travail.
"""

from __future__ import annotations

import sys
import threading
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
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
    QVBoxLayout,
    QWidget,
)

from servette import __version__
from servette.config import CLASSEMENTS, INTERVALLES, Config
from servette.engine import (
    Moteur,
    Options,
    Resultat,
    format_octets,
    lister_supprimees,
    restaurer,
)
from servette.scheduler import Planificateur
from servette.systeme import (
    demarrage_automatique,
    demarrage_automatique_actif,
    ouvrir_dossier,
)

GRENAT = "#471625"
PERIODE_ECHEANCE = 30_000   # ms entre deux contrôles d'échéance
PERIODE_AFFICHAGE = 1_000   # ms entre deux rafraîchissements du compte à rebours


# --------------------------------------------------------------------------- #
# Icône
# --------------------------------------------------------------------------- #

def icone_application() -> QIcon:
    """Charge build/servette.ico si présent, sinon dessine un repli grenat."""
    for base in (Path(__file__).resolve().parent, Path(getattr(sys, "_MEIPASS", "."))):
        fichier = base / "build" / "servette.ico"
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
        p.drawText(pixmap.rect(), Qt.AlignCenter, "S")
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
        self.setWindowTitle("Images supprimées")
        self.resize(540, 380)
        self.entrees = entrees

        colonne = QVBoxLayout(self)
        colonne.addWidget(QLabel(
            "Ces images ont été téléchargées puis effacées du dossier.\n"
            "Cochez celles à retélécharger à la prochaine mise à jour."))

        self.liste = QListWidget()
        for e in entrees:
            item = QListWidgetItem(
                f"{e.get('fichier', '?')}    (effacée le {e.get('supprime', '')[:10]})")
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.liste.addItem(item)
        colonne.addWidget(self.liste, 1)

        boutons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        boutons.addButton("Tout cocher", QDialogButtonBox.ActionRole).clicked.connect(
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
# Fenêtre principale
# --------------------------------------------------------------------------- #

class Fenetre(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"Servette FC — Téléchargeur d'images {__version__}")
        self.setWindowIcon(icone_application())
        self.resize(760, 600)
        self.setMinimumSize(QSize(640, 500))

        self.cfg = Config.charger()
        self.planificateur = Planificateur(self.cfg)
        self.arret = threading.Event()
        self.travailleur: Travailleur | None = None
        self.auto_en_cours = False
        self._quitter_demande = False

        self._construire()
        self._charger_valeurs()
        self._construire_barre_notification()

        self.minuteur_echeance = QTimer(self)
        self.minuteur_echeance.timeout.connect(self._verifier_echeance)
        self.minuteur_echeance.start(PERIODE_ECHEANCE)

        self.minuteur_affichage = QTimer(self)
        self.minuteur_affichage.timeout.connect(self._rafraichir_echeance)
        self.minuteur_affichage.start(PERIODE_AFFICHAGE)
        self._rafraichir_echeance()

    # ------------------------------------------------------------------ UI --

    def _construire(self) -> None:
        self.setStyleSheet(f"""
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
        """)

        central = QWidget()
        self.setCentralWidget(central)
        racine = QVBoxLayout(central)
        racine.setContentsMargins(14, 14, 14, 14)
        racine.setSpacing(10)

        titre = QLabel("Téléchargeur d'images du Servette FC")
        titre.setStyleSheet(f"font-size: 17px; font-weight: 700; color: {GRENAT};")
        racine.addWidget(titre)

        # --- destination ---------------------------------------------------
        boite = QGroupBox("Destination")
        ligne = QHBoxLayout(boite)
        self.champ_dossier = QLineEdit()
        self.champ_dossier.editingFinished.connect(self._sauver)
        ligne.addWidget(self.champ_dossier, 1)
        bouton = QPushButton("Parcourir…")
        bouton.clicked.connect(self._choisir_dossier)
        ligne.addWidget(bouton)
        bouton = QPushButton("Ouvrir")
        bouton.clicked.connect(self._ouvrir_dossier)
        ligne.addWidget(bouton)
        racine.addWidget(boite)

        # --- options -------------------------------------------------------
        boite = QGroupBox("Options")
        form = QFormLayout(boite)
        form.setLabelAlignment(Qt.AlignLeft)

        self.combo_intervalle = QComboBox()
        self.combo_intervalle.addItems(list(INTERVALLES))
        self.combo_intervalle.currentIndexChanged.connect(self._sauver)
        form.addRow("Mise à jour :", self.combo_intervalle)

        self.combo_classement = QComboBox()
        self.combo_classement.addItems(list(CLASSEMENTS))
        self.combo_classement.setToolTip(
            "Change la destination des nouvelles images. Les images déjà\n"
            "téléchargées restent là où elles sont.")
        self.combo_classement.currentIndexChanged.connect(self._sauver)
        form.addRow("Classement :", self.combo_classement)

        self.spin_largeur = QSpinBox()
        self.spin_largeur.setRange(0, 10000)
        self.spin_largeur.setSingleStep(100)
        self.spin_largeur.setSuffix(" px")
        self.spin_largeur.setToolTip(
            "Écarte les logos et vignettes sous cette largeur. 0 pour tout garder.")
        self.spin_largeur.valueChanged.connect(self._sauver)
        form.addRow("Largeur minimale :", self.spin_largeur)

        self.case_verifier = QCheckBox("Vérifier l'intégrité des fichiers existants")
        self.case_verifier.setToolTip(
            "Interroge le serveur sur chaque fichier connu (réponse 304 si identique).\n"
            "Plus lent, à réserver à un contrôle ponctuel.")
        self.case_verifier.toggled.connect(self._sauver)
        form.addRow("", self.case_verifier)

        self.case_barre = QCheckBox("Réduire dans la zone de notification à la fermeture")
        self.case_barre.toggled.connect(self._sauver)
        form.addRow("", self.case_barre)

        self.case_demarrage = QCheckBox("Lancer au démarrage de Windows")
        self.case_demarrage.toggled.connect(self._basculer_demarrage)
        self.case_demarrage.setEnabled(sys.platform == "win32")
        form.addRow("", self.case_demarrage)

        racine.addWidget(boite)

        # --- actions -------------------------------------------------------
        ligne = QHBoxLayout()
        self.bouton_lancer = QPushButton("Mettre à jour maintenant")
        self.bouton_lancer.setObjectName("principal")
        self.bouton_lancer.clicked.connect(self._lancer)
        ligne.addWidget(self.bouton_lancer)

        self.bouton_arreter = QPushButton("Arrêter")
        self.bouton_arreter.setEnabled(False)
        self.bouton_arreter.clicked.connect(self._arreter)
        ligne.addWidget(self.bouton_arreter)

        self.bouton_supprimees = QPushButton("Images supprimées…")
        self.bouton_supprimees.setToolTip(
            "Images effacées du dossier, que l'application ne retélécharge plus.")
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

        self.label_statut = QLabel("Prêt.")
        racine.addWidget(self.label_statut)

        # --- journal -------------------------------------------------------
        boite = QGroupBox("Journal")
        colonne = QVBoxLayout(boite)
        self.journal = QPlainTextEdit()
        self.journal.setReadOnly(True)
        self.journal.setMaximumBlockCount(2000)   # borne la mémoire sur de longs runs
        self.journal.setFont(QFont("Consolas", 9))
        colonne.addWidget(self.journal)
        racine.addWidget(boite, 1)

    def _construire_barre_notification(self) -> None:
        self.tray = QSystemTrayIcon(icone_application(), self)
        self.tray.setToolTip("Servette FC — Téléchargeur d'images")

        menu = QMenu()
        self.action_afficher = QAction("Afficher la fenêtre", self)
        self.action_afficher.triggered.connect(self._afficher)
        menu.addAction(self.action_afficher)

        self.action_maj = QAction("Mettre à jour maintenant", self)
        self.action_maj.triggered.connect(self._lancer)
        menu.addAction(self.action_maj)

        action = QAction("Ouvrir le dossier", self)
        action.triggered.connect(self._ouvrir_dossier)
        menu.addAction(action)
        menu.addSeparator()

        action = QAction("Quitter", self)
        action.triggered.connect(self._quitter)
        menu.addAction(action)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._clic_barre)
        self.tray.show()

    # -------------------------------------------------------- persistance --

    def _charger_valeurs(self) -> None:
        c = self.cfg
        self._chargement = True
        self.champ_dossier.setText(c.dossier)
        self.combo_intervalle.setCurrentText(c.libelle_intervalle)
        self.combo_classement.setCurrentText(c.libelle_classement)
        self.spin_largeur.setValue(c.largeur_min)
        self.case_verifier.setChecked(c.verifier_integrite)
        self.case_barre.setChecked(c.fermer_dans_barre)
        self.case_demarrage.setChecked(demarrage_automatique_actif())
        self._chargement = False

    def _sauver(self) -> None:
        if getattr(self, "_chargement", False):
            return
        c = self.cfg
        c.dossier = self.champ_dossier.text()
        c.intervalle_heures = INTERVALLES.get(self.combo_intervalle.currentText(), 24)
        c.classement = CLASSEMENTS.get(self.combo_classement.currentText(), "galerie")
        c.largeur_min = self.spin_largeur.value()
        c.verifier_integrite = self.case_verifier.isChecked()
        c.fermer_dans_barre = self.case_barre.isChecked()
        c.valider()
        c.sauver()
        self._rafraichir_echeance()

    def _basculer_demarrage(self, actif: bool) -> None:
        if getattr(self, "_chargement", False):
            return
        obtenu = demarrage_automatique(actif)
        if obtenu != actif:
            self._chargement = True
            self.case_demarrage.setChecked(obtenu)
            self._chargement = False
            self._ecrire("Impossible de modifier le démarrage automatique.")
        self.cfg.lancer_au_demarrage = obtenu
        self.cfg.sauver()

    # ------------------------------------------------------------ actions --

    def _choisir_dossier(self) -> None:
        choix = QFileDialog.getExistingDirectory(
            self, "Où enregistrer les images ?",
            self.champ_dossier.text() or str(Path.home()))
        if choix:
            self.champ_dossier.setText(choix)
            self._sauver()

    def _ouvrir_dossier(self) -> None:
        try:
            ouvrir_dossier(Path(self.champ_dossier.text()))
        except OSError as e:
            QMessageBox.warning(self, "Dossier inaccessible", str(e))

    def _gerer_supprimees(self) -> None:
        dossier = Path(self.champ_dossier.text()).expanduser()
        entrees = lister_supprimees(dossier)
        if not entrees:
            QMessageBox.information(
                self, "Images supprimées",
                "Aucune image effacée n'est mémorisée pour ce dossier.")
            return
        dialogue = DialogueSupprimees(self, entrees)
        if dialogue.exec() != QDialog.Accepted or not dialogue.choix():
            return
        n = restaurer(dossier, dialogue.choix())
        self._ecrire(f"{n} image(s) seront retéléchargées à la prochaine mise à jour.")

    def _lancer(self, auto: bool = False) -> None:
        if self.travailleur and self.travailleur.isRunning():
            return
        dossier = Path(self.champ_dossier.text()).expanduser()
        try:
            dossier.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            message = f"Impossible d'utiliser ce dossier :\n{e}"
            if auto:
                self._ecrire(message.replace("\n", " "))
                return
            QMessageBox.critical(self, "Dossier invalide", message)
            return

        self._sauver()
        self.auto_en_cours = bool(auto)
        self.arret.clear()
        self.bouton_lancer.setEnabled(False)
        self.action_maj.setEnabled(False)
        # le moteur réécrit le manifeste en fin de course : restaurer pendant
        # qu'il tourne perdrait la modification
        self.bouton_supprimees.setEnabled(False)
        self.bouton_arreter.setEnabled(True)
        self.barre.setRange(0, 0)          # indéterminé pendant l'inventaire
        self._ecrire(f"--- {datetime.now():%d/%m/%Y %H:%M} — début de la mise à jour")

        options = Options(
            dossier=dossier,
            classement=self.cfg.classement,
            largeur_min=self.cfg.largeur_min,
            delai=self.cfg.delai_requetes,
            verifier=self.cfg.verifier_integrite,
        )
        self.travailleur = Travailleur(options, self.arret)
        self.travailleur.journal.connect(self._ecrire)
        self.travailleur.progres.connect(self._progres)
        self.travailleur.fini.connect(self._terminer)
        self.travailleur.start()

    def _arreter(self) -> None:
        self.arret.set()
        self.bouton_arreter.setEnabled(False)
        self.label_statut.setText("Arrêt en cours…")

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
        self.label_statut.setText(f"{fait}/{total} — {etiquette}")

    def _terminer(self, res: Resultat) -> None:
        self.bouton_lancer.setEnabled(True)
        self.action_maj.setEnabled(True)
        self.bouton_supprimees.setEnabled(True)
        self.bouton_arreter.setEnabled(False)
        self.barre.setRange(0, 100)
        self.barre.setValue(0 if res.interrompu else 100)

        self.label_statut.setText(res.message)
        self._ecrire(res.message)
        if res.deja_presentes:
            self._ecrire(f"{res.deja_presentes} image(s) déjà présentes, non retéléchargées.")
        if res.ignorees:
            self._ecrire(f"{res.ignorees} image(s) que vous aviez supprimée(s), ignorée(s) — "
                         "bouton « Images supprimées… » pour en recharger.")
        if res.echecs:
            self._ecrire(f"{res.echecs} échec(s) — seront retentés à la prochaine mise à jour.")

        if not res.interrompu:
            self.planificateur.marquer_execution()
        self._rafraichir_echeance()

        # bulle d'information seulement si l'utilisateur ne regardait pas
        if (self.auto_en_cours and self.cfg.notifications and res.telechargees
                and not self.isVisible()):
            self.tray.showMessage(
                "Servette FC",
                f"{res.telechargees} nouvelle(s) image(s) — {format_octets(res.octets)}",
                icone_application(), 5000)
        self.auto_en_cours = False

    def _verifier_echeance(self) -> None:
        if self.travailleur and self.travailleur.isRunning():
            return
        if self.planificateur.echeance_atteinte():
            self._ecrire("Mise à jour automatique déclenchée.")
            self._lancer(auto=True)

    def _rafraichir_echeance(self) -> None:
        texte = self.planificateur.texte_prochaine()
        self.label_echeance.setText(texte)
        self.tray.setToolTip(f"Servette FC — {texte}")

    def _ecrire(self, message: str) -> None:
        self.journal.appendPlainText(f"{datetime.now():%H:%M:%S}  {message}")

    # ------------------------------------------------------------ sortie ---

    def closeEvent(self, event) -> None:
        # la croix réduit dans la zone de notification, sauf demande explicite
        if (not self._quitter_demande and self.cfg.fermer_dans_barre
                and self.tray.isVisible()):
            event.ignore()
            self.hide()
            self.tray.showMessage(
                "Servette FC",
                "L'application continue en arrière-plan. Clic droit sur l'icône pour quitter.",
                icone_application(), 4000)
            return

        if self.travailleur and self.travailleur.isRunning():
            reponse = QMessageBox.question(
                self, "Quitter",
                "Une mise à jour est en cours. Elle reprendra au prochain lancement.\n"
                "Quitter maintenant ?")
            if reponse != QMessageBox.Yes:
                self._quitter_demande = False
                event.ignore()
                return
            self.arret.set()
            self.travailleur.wait(5000)

        self._sauver()
        self.tray.hide()
        event.accept()


# --------------------------------------------------------------------------- #

def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("ServetteDownloader")
    app.setWindowIcon(icone_application())
    # l'application survit à la fermeture de la fenêtre grâce à l'icône de barre
    app.setQuitOnLastWindowClosed(False)

    fenetre = Fenetre()
    if "--reduit" not in sys.argv:
        fenetre.show()

    # rattrapage : échéance dépassée pendant que l'application était fermée
    QTimer.singleShot(2000, fenetre._verifier_echeance)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
