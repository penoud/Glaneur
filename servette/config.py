"""Configuration persistante de l'application.

Le fichier vit dans %APPDATA%\\ServetteDownloader\\config.json sous Windows,
dans ~/.config/servette-downloader/ ailleurs. Il est écrit de façon atomique
pour ne jamais se retrouver tronqué si l'application est tuée.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

NOM_APP = "ServetteDownloader"

# intervalles proposés dans l'interface : libellé -> heures (0 = manuel)
INTERVALLES: dict[str, int] = {
    "Manuel uniquement": 0,
    "Toutes les 6 heures": 6,
    "Toutes les 12 heures": 12,
    "Une fois par jour": 24,
    "Une fois par semaine": 168,
}

# classements proposés dans l'interface : libellé -> valeur stockée
CLASSEMENTS: dict[str, str] = {
    "Par galerie": "galerie",
    "Par date": "date",
    "Tout dans un dossier": "plat",
}


def dossier_config() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return base / NOM_APP
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / NOM_APP
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "servette-downloader"


def dossier_images_defaut() -> Path:
    for nom in ("Pictures", "Images"):
        candidat = Path.home() / nom
        if candidat.is_dir():
            return candidat / "Servette FC"
    return Path.home() / "Servette FC"


@dataclass
class Config:
    dossier: str = ""
    intervalle_heures: int = 24
    largeur_min: int = 800
    classement: str = "galerie"          # "galerie", "date" ou "plat"
    verifier_integrite: bool = False
    delai_requetes: float = 0.5
    derniere_execution: str = ""          # ISO 8601, alimenté par le planificateur
    lancer_au_demarrage: bool = False
    fermer_dans_barre: bool = True        # la croix réduit dans la zone de notification
    notifications: bool = True            # bulle après une mise à jour automatique

    _chemin: Path | None = field(default=None, repr=False, compare=False)

    # -- chargement / sauvegarde ------------------------------------------- #

    @classmethod
    def charger(cls, chemin: Path | None = None) -> "Config":
        chemin = chemin or (dossier_config() / "config.json")
        cfg = cls()
        cfg._chemin = chemin
        if chemin.exists():
            try:
                with open(chemin, encoding="utf-8") as f:
                    brut = json.load(f)
                connus = {f.name for f in fields(cls) if not f.name.startswith("_")}
                for cle, valeur in brut.items():
                    if cle in connus:
                        setattr(cfg, cle, valeur)
            except (json.JSONDecodeError, OSError, TypeError):
                pass  # config illisible : on repart sur les valeurs par défaut
        if not cfg.dossier:
            cfg.dossier = str(dossier_images_defaut())
        cfg.valider()
        return cfg

    def sauver(self) -> None:
        chemin = self._chemin or (dossier_config() / "config.json")
        chemin.parent.mkdir(parents=True, exist_ok=True)
        donnees = {k: v for k, v in asdict(self).items() if not k.startswith("_")}
        tmp = chemin.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(donnees, f, ensure_ascii=False, indent=2)
        tmp.replace(chemin)
        self._chemin = chemin

    # -- garde-fous --------------------------------------------------------- #

    def valider(self) -> None:
        """Ramène les valeurs aberrantes dans des bornes raisonnables."""
        if self.intervalle_heures not in INTERVALLES.values():
            self.intervalle_heures = 24
        self.largeur_min = max(0, min(int(self.largeur_min), 10000))
        if self.classement not in CLASSEMENTS.values():
            self.classement = "galerie"
        # un délai trop court martèlerait le serveur du club
        self.delai_requetes = max(0.2, min(float(self.delai_requetes), 10.0))

    @property
    def libelle_intervalle(self) -> str:
        for libelle, heures in INTERVALLES.items():
            if heures == self.intervalle_heures:
                return libelle
        return "Une fois par jour"

    @property
    def libelle_classement(self) -> str:
        for libelle, valeur in CLASSEMENTS.items():
            if valeur == self.classement:
                return libelle
        return "Par galerie"
