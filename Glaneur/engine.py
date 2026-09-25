"""Moteur de téléchargement générique.

Ce module ne connaît rien de l'interface : il communique par callbacks
(`journal`, `progression`) et s'interrompt proprement via un threading.Event.
Il peut donc servir aussi bien à l'UI PySide6 qu'à un script en ligne de commande.

Il ne connaît pas non plus WordPress ni Djangoplicity. Il consomme des
`Element` produits par un adaptateur de `Glaneur.sources`.

Seule dépendance Qt : `QCoreApplication.translate` pour localiser les
messages remontés au journal et à `res.message` — pas de widget, pas de
thread introduit, et `.translate()` retombe sur la source FR quand aucune
QCoreApplication n'existe (cas de la CLI et des tests unitaires).
"""

from __future__ import annotations

import html
import json
import os
import re
import threading
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import urlparse

import requests
from PySide6.QtCore import QCoreApplication

from .sources import SOURCES, Element, Interrompu, Transport

# lupdate n'extrait QCoreApplication.translate("Ctx", "src") que si contexte
# et source sont littéraux : on inline plutôt que d'aliaser un _tr().

# Réexport de `Interrompu` pour les appelants qui l'importent via `engine`.
Interrompu = Interrompu   # noqa: PLW0127 — alias explicite

UA = "Mozilla/5.0 (compatible; Glaneur/1.0)"


@dataclass
class Options:
    dossier: Path
    site: str = "https://example.com"
    classement: str = "galerie"       # "galerie", "date" ou "plat"
    largeur_min: int = 800
    delai: float = 0.5
    verifier: bool = False            # revalider les fichiers déjà présents
    force: bool = False               # ignorer le manifeste
    depuis: str | None = None         # AAAA-MM-JJ
    jusqua: str | None = None
    utiliser_cache: bool = True       # cache disque : date max et titres galeries
    type_source: str = "wordpress"    # clé de `sources.SOURCES`
    format_image: str = "Large"       # utilisé par Djangoplicity


@dataclass
class Resultat:
    telechargees: int = 0
    reprises: int = 0
    inchangees: int = 0
    deja_presentes: int = 0
    supprimees: int = 0      # constatées disparues du disque à ce passage
    ignorees: int = 0        # connues comme supprimées, plus retéléchargées
    echecs: int = 0
    octets: int = 0
    interrompu: bool = False
    message: str = ""
    details: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Utilitaires
# --------------------------------------------------------------------------- #

SIZE_SUFFIX = re.compile(r"-\d{2,5}x\d{2,5}(?=\.[A-Za-z]{3,4}$)")


def nettoyer(titre: str, defaut: str = "divers") -> str:
    """Transforme un titre HTML en nom de dossier sûr sur tous les systèmes."""
    texte = html.unescape(titre or "").strip()
    texte = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode("ascii")
    texte = re.sub(r"[^\w\s-]", "", texte).strip()
    texte = re.sub(r"[\s_]+", "-", texte).lower()
    texte = texte.strip(".-")            # Windows refuse les noms finissant par un point
    return texte[:80] or defaut


def format_octets(n: int) -> str:
    for unite in ("o", "Ko", "Mo", "Go"):
        if n < 1024 or unite == "Go":
            return f"{n:.0f} {unite}" if unite == "o" else f"{n:.1f} {unite}"
        n /= 1024
    return f"{n:.1f} Go"


# --------------------------------------------------------------------------- #
# Manifeste — fonctions libres, pour que l'UI le consulte sans instancier un moteur
# --------------------------------------------------------------------------- #

def chemin_manifeste(dossier: Path) -> Path:
    return dossier / ".etat.json"


def lire_manifeste(dossier: Path) -> dict:
    chemin = chemin_manifeste(dossier)
    if not chemin.exists():
        return {}
    try:
        with open(chemin, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def ecrire_manifeste(dossier: Path, manifeste: dict) -> None:
    chemin = chemin_manifeste(dossier)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    tmp = chemin.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(manifeste, f, ensure_ascii=False, indent=1)
    tmp.replace(chemin)


# --------------------------------------------------------------------------- #
# Cache API : date maximale des médias vus, titres des galeries résolues.
# Sert à accélérer les runs suivants — le manifeste dit ce qu'on a téléchargé,
# le cache dit ce qu'on a demandé à l'API pour éviter de le redemander.
# --------------------------------------------------------------------------- #

def chemin_cache(dossier: Path) -> Path:
    return dossier / ".cache.json"


def lire_cache(dossier: Path) -> dict:
    chemin = chemin_cache(dossier)
    if not chemin.exists():
        return {}
    try:
        with open(chemin, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def ecrire_cache(dossier: Path, cache: dict) -> None:
    chemin = chemin_cache(dossier)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    tmp = chemin.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=1)
    tmp.replace(chemin)


def lister_supprimees(dossier: Path) -> list[dict]:
    """Images téléchargées puis effacées du disque par l'utilisateur."""
    manifeste = lire_manifeste(dossier)
    entrees = [{"id": ident, **etat} for ident, etat in manifeste.items()
               if etat.get("supprime")]
    entrees.sort(key=lambda e: (e.get("supprime", ""), e.get("fichier", "")))
    return entrees


def restaurer(dossier: Path, ids: Iterable) -> int:
    """Lève la marque de suppression : ces images repasseront dans la file."""
    manifeste = lire_manifeste(dossier)
    retablies = 0
    for ident in ids:
        etat = manifeste.get(str(ident))
        if etat and etat.pop("supprime", None):
            # la marque ne tombe qu'au téléchargement réussi, qui réécrit
            # l'entrée : un échec réseau ne reclasse pas l'image en « supprimée »
            etat["restaure"] = True
            retablies += 1
    if retablies:
        ecrire_manifeste(dossier, manifeste)
    return retablies


def supprimer_image(dossier: Path, fichier: Path) -> bool:
    """Efface `fichier` du disque et pose la marque `supprime` dans le manifeste.

    Sans cette marque, la mise à jour suivante verrait l'image manquante et la
    retéléchargerait : la suppression disque seule ne suffit pas.

    Refuse (`False`) si `fichier` n'est pas à l'intérieur de `dossier` — une
    fonction qui efface ne fait pas confiance à son appelant. La comparaison
    passe par `realpath` + `normcase` puis `commonpath`, jamais par
    `startswith` qui matcherait un dossier voisin de préfixe identique.
    """
    try:
        base = os.path.normcase(os.path.realpath(str(dossier)))
        cible = os.path.normcase(os.path.realpath(str(fichier)))
    except OSError:
        return False
    try:
        commun = os.path.commonpath([base, cible])
    except ValueError:
        return False   # lecteurs différents sous Windows
    if commun != base or cible == base:
        return False

    # Chemin relatif à comparer aux entrées du manifeste. Un manifeste écrit
    # sous Windows contient des antislashs ; on ramène les deux formes à un
    # séparateur commun avant `normcase`.
    try:
        relatif = os.path.relpath(cible, base)
    except ValueError:
        return False
    aiguille = os.path.normcase(relatif.replace("\\", "/"))

    manifeste = lire_manifeste(dossier)
    ident_trouve: str | None = None
    for ident, etat in manifeste.items():
        stocke = etat.get("fichier")
        if not stocke:
            continue
        if os.path.normcase(str(stocke).replace("\\", "/")) == aiguille:
            ident_trouve = ident
            break

    try:
        Path(fichier).unlink()
    except FileNotFoundError:
        pass   # déjà absent : la marque est posée quand même
    except OSError:
        return False

    if ident_trouve is not None:
        entree = manifeste[ident_trouve]
        entree["supprime"] = datetime.now().isoformat(timespec="seconds")
        entree.pop("restaure", None)
        ecrire_manifeste(dossier, manifeste)
    return True


# --------------------------------------------------------------------------- #
# Moteur
# --------------------------------------------------------------------------- #

class Moteur:
    def __init__(
        self,
        options: Options,
        journal: Callable[[str], None] | None = None,
        progression: Callable[[int, int, str], None] | None = None,
        arret: threading.Event | None = None,
    ) -> None:
        self.o = options
        self.base = options.site.rstrip("/")
        self._journal = journal or (lambda msg: None)
        self._progression = progression or (lambda fait, total, etiquette: None)
        self.arret = arret or threading.Event()
        self.transport = Transport(delai=options.delai, arret=self.arret)
        # La session de téléchargement passe par le transport partagé : un
        # seul user-agent, un seul plancher de pause.
        self.session = self.transport.session
        classe = SOURCES.get(options.type_source) or SOURCES["wordpress"]
        self.source = classe(
            base=self.base,
            transport=self.transport,
            reglages={"format_image": options.format_image},
            journal=self._journal,
            progression=self._progression,
        )

    # -- plomberie ---------------------------------------------------------- #

    def _verifier_arret(self) -> None:
        if self.arret.is_set():
            raise Interrompu()

    def _pause(self, secondes: float) -> None:
        """Attente fractionnée, pour réagir vite à une demande d'arrêt."""
        self.transport.pause(secondes)

    # -- manifeste ---------------------------------------------------------- #

    def charger_manifeste(self) -> dict:
        if self.o.force or not chemin_manifeste(self.o.dossier).exists():
            return {}
        manifeste = lire_manifeste(self.o.dossier)
        if not manifeste:
            self._journal(QCoreApplication.translate("Moteur", "Manifeste illisible, reconstruction complète."))
        return manifeste

    def sauver_manifeste(self, manifeste: dict) -> None:
        ecrire_manifeste(self.o.dossier, manifeste)

    @staticmethod
    def fichier_complet(dest: Path, etat: dict | None, taille_api: int | None) -> bool:
        if not dest.exists():
            return False
        taille = dest.stat().st_size
        if taille == 0:
            return False
        attendue = (etat or {}).get("taille") or taille_api
        return not (attendue and taille != attendue)

    # -- cache API ---------------------------------------------------------- #

    def charger_cache(self) -> dict:
        """Lit le cache disque, ignoré en mode force ou si l'utilisation en est
        désactivée. Si le site enregistré diffère du site courant, ou si le
        type de source change (ex. WordPress → Djangoplicity), on repart de
        zéro pour ne pas mélanger deux espaces d'identifiants.

        Migration silencieuse : un cache écrit avant l'introduction de
        `type_source` (donc sans ce champ) est lu comme s'il correspondait
        au type courant, pour ne pas invalider les caches WordPress
        existants.
        """
        if self.o.force or not self.o.utiliser_cache:
            return {}
        cache = lire_cache(self.o.dossier)
        if cache.get("site") and cache["site"] != self.base:
            return {}
        type_cache = cache.get("type_source")
        if type_cache and type_cache != self.o.type_source:
            return {}
        return cache

    def sauver_cache(self, cache: dict) -> None:
        if self.o.force or not self.o.utiliser_cache:
            return
        ecrire_cache(self.o.dossier, {
            **cache, "site": self.base, "type_source": self.o.type_source,
        })

    # -- chemins ------------------------------------------------------------ #

    def dossier_pour(self, element: Element, titres: dict[str, str]) -> str:
        """Sous-dossier relatif ; chaîne vide en classement plat."""
        if self.o.classement == "plat":
            return ""
        if self.o.classement == "date" or not element.groupe:
            return element.mois or "divers"
        return titres.get(element.groupe) or f"contenu-{element.groupe}"

    def chemin_libre(self, dest: Path, ident: str, pris: set[str]) -> Path:
        """Un même nom de fichier peut apparaître dans deux mois différents
        (WordPress ne dédoublonne que par dossier d'upload) ou dans deux entrées
        Djangoplicity (variantes de langue) : on suffixe par l'ident pour ne
        pas écraser."""
        relatif = str(dest.relative_to(self.o.dossier))
        if relatif in pris:
            dest = dest.with_name(f"{dest.stem}-{ident}{dest.suffix}")
            relatif = str(dest.relative_to(self.o.dossier))
        pris.add(relatif)
        return dest

    # -- téléchargement ----------------------------------------------------- #

    def telecharger(self, url: str, dest: Path, etat: dict | None) -> tuple[str, dict | None]:
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        entetes: dict[str, str] = {}
        depuis = 0

        if dest.exists() and self.o.verifier and etat:
            if etat.get("etag"):
                entetes["If-None-Match"] = etat["etag"]
            elif etat.get("modifie"):
                entetes["If-Modified-Since"] = etat["modifie"]
        elif tmp.exists():
            depuis = tmp.stat().st_size
            if depuis > 0:
                entetes["Range"] = f"bytes={depuis}-"

        try:
            r = self.session.get(url, timeout=60, stream=True, headers=entetes)
            if r.status_code == 304:
                return "inchangé", etat
            if r.status_code == 404:
                return "introuvable", None
            if r.status_code == 416:
                tmp.unlink(missing_ok=True)
                depuis = 0
                r = self.session.get(url, timeout=60, stream=True)
            r.raise_for_status()

            reprise = depuis > 0 and r.status_code == 206
            with open(tmp, "ab" if reprise else "wb") as f:
                for bloc in r.iter_content(65536):
                    if self.arret.is_set():
                        f.flush()
                        raise Interrompu()   # le .part est conservé pour la reprise
                    f.write(bloc)
            tmp.replace(dest)

            infos = {
                "taille": dest.stat().st_size,
                "etag": r.headers.get("ETag", ""),
                "modifie": r.headers.get("Last-Modified", ""),
                "url": url,
            }
            self._pause(self.o.delai)
            return ("repris" if reprise else "ok"), infos

        except requests.RequestException as e:
            return QCoreApplication.translate("Moteur", "erreur : {erreur}").format(erreur=e), None

    # -- orchestration ------------------------------------------------------ #

    def executer(self) -> Resultat:
        res = Resultat()
        self.o.dossier.mkdir(parents=True, exist_ok=True)
        manifeste = self.charger_manifeste()
        cache = self.charger_cache()
        if manifeste:
            self._journal(QCoreApplication.translate("Moteur", "{n} image(s) déjà connues.").format(n=len(manifeste)))

        # Cache : on ne l'utilise que si l'utilisateur n'a pas déjà borné la
        # période — dans ce cas, ses bornes priment sur la mémoire du cache.
        depuis_cache = None
        if not (self.o.depuis or self.o.jusqua):
            depuis_cache = cache.get("derniere_date_media")
            if depuis_cache:
                self._journal(QCoreApplication.translate(
                    "Moteur",
                    "Cache : ne redemande à l'API que les médias postérieurs à {date}.").format(
                    date=depuis_cache[:19]))

        try:
            depuis = self.source.convertir_depuis(depuis_cache) or self.o.depuis
            elements = list(self.source.inventaire(depuis, self.o.jusqua))

            if self.o.largeur_min:
                avant = len(elements)
                elements = [
                    e for e in elements
                    if e.largeur is None or e.largeur >= self.o.largeur_min
                ]
                # Un `Element` sans URL (source qui n'a pas trouvé la ressource
                # demandée) ne peut plus être téléchargé : il file en `ignorees`.
                ecartees = avant - len(elements)
                if ecartees:
                    self._journal(QCoreApplication.translate(
                        "Moteur",
                        "{n} vignette(s) ou logo(s) écarté(s) (moins de {min} px).").format(
                        n=ecartees, min=self.o.largeur_min))

            if not elements:
                res.message = QCoreApplication.translate("Moteur", "Aucune image ne correspond aux critères.")
                return res

            # noms déjà attribués, pour qu'une image n'en écrase pas une autre
            pris = {e["fichier"] for e in manifeste.values() if e.get("fichier")}

            # tri : déjà sur le disque vs à traiter
            a_faire: list[tuple[Element, Path | None]] = []
            for e in elements:
                etat = manifeste.get(e.ident)
                connu = self.o.dossier / etat["fichier"] if etat and etat.get("fichier") else None

                if etat and etat.get("supprime"):
                    res.ignorees += 1
                    continue
                if e.url is None:
                    # La source n'a pas trouvé de ressource utilisable.
                    res.ignorees += 1
                    continue
                if (connu is not None and etat.get("taille") and not connu.exists()
                        and not etat.get("restaure")):
                    # déjà téléchargée puis disparue : l'utilisateur l'a effacée
                    etat["supprime"] = datetime.now().isoformat(timespec="seconds")
                    res.supprimees += 1
                    continue
                if connu and self.fichier_complet(connu, etat, e.taille) and not self.o.verifier:
                    etat.pop("restaure", None)
                    res.deja_presentes += 1
                    continue
                a_faire.append((e, connu))

            self._journal(QCoreApplication.translate("Moteur", "{connues} déjà à jour, {a_faire} à traiter.").format(
                connues=res.deja_presentes, a_faire=len(a_faire)))
            if res.supprimees:
                self._journal(QCoreApplication.translate(
                    "Moteur",
                    "{n} image(s) effacée(s) sur le disque, elles ne seront plus retéléchargées."
                ).format(n=res.supprimees))
            if not a_faire:
                res.message = QCoreApplication.translate("Moteur", "Tout est déjà à jour.")
                self._progression(1, 1, res.message)
                return res

            titres: dict[str, str] = {}
            titres_caches = {str(k): v
                             for k, v in (cache.get("titres_parents") or {}).items()}
            inconnus = {e.groupe for e, connu in a_faire
                        if e.groupe and connu is None}
            if (self.o.classement == "galerie"
                    and "galerie" in self.source.classements
                    and inconnus):
                self._progression(0, len(a_faire), QCoreApplication.translate("Moteur", "Identification des galeries…"))
                titres = self.source.resoudre_groupes(
                    inconnus, connus=titres_caches)

            for i, (e, connu) in enumerate(a_faire, 1):
                self._verifier_arret()
                url = e.url
                etat = manifeste.get(e.ident)
                if connu is not None:
                    fichier = connu
                else:
                    sous = self.dossier_pour(e, titres)
                    # nettoyer("") renverrait "divers" et créerait un dossier fantôme
                    dossier = (self.o.dossier / nettoyer(sous)) if sous else self.o.dossier
                    nom = e.nom_fichier or Path(urlparse(url).path).name
                    fichier = self.chemin_libre(dossier / nom, e.ident, pris)

                statut, infos = self.telecharger(url, fichier, etat)

                if infos:
                    infos["fichier"] = str(fichier.relative_to(self.o.dossier))
                    # Métadonnées de la source (crédit, checksum…) : on les
                    # copie dans le manifeste pour l'export catalogue à venir,
                    # sans que le moteur les interprète.
                    if e.extra:
                        infos.setdefault("extra", {}).update(e.extra)
                    manifeste[e.ident] = infos
                if statut == "ok":
                    res.telechargees += 1
                    res.octets += infos["taille"]
                elif statut == "repris":
                    res.reprises += 1
                    res.octets += infos["taille"]
                elif statut == "inchangé":
                    res.inchangees += 1
                else:
                    res.echecs += 1
                    # `statut` peut être un code interne ("introuvable") ou une
                    # phrase déjà traduite (voir télécharger()).
                    affiche = QCoreApplication.translate("Moteur", "introuvable") if statut == "introuvable" else statut
                    self._journal(f"{fichier.name} : {affiche}")

                self._progression(i, len(a_faire), f"{fichier.parent.name}/{fichier.name}")
                if i % 25 == 0:
                    self.sauver_manifeste(manifeste)

            res.message = QCoreApplication.translate("Moteur", "{n} nouvelle(s) image(s), {taille} téléchargés.").format(
                n=res.telechargees, taille=format_octets(res.octets))

            # Mise à jour du cache : date maximale et titres nouvellement résolus.
            # On ne l'écrit qu'en sortie normale, jamais après une interruption
            # ou une erreur, pour ne pas mémoriser un état incomplet.
            dates = [e.date for e in elements if e.date]
            if dates:
                ancienne = cache.get("derniere_date_media") or ""
                cache["derniere_date_media"] = max(ancienne, max(dates))
            if titres:
                cache.setdefault("titres_parents", {})
                cache["titres_parents"].update(
                    {str(k): v for k, v in titres.items() if v})
            self.sauver_cache(cache)

        except Interrompu:
            res.interrompu = True
            res.message = QCoreApplication.translate("Moteur", "Interrompu — la reprise repartira d'ici.")
        except RuntimeError as e:
            res.message = str(e)
            self._journal(QCoreApplication.translate("Moteur", "Erreur : {erreur}").format(erreur=e))
        except OSError as e:
            res.message = QCoreApplication.translate("Moteur", "Problème d'écriture : {erreur}").format(erreur=e)
            self._journal(res.message)
        finally:
            self.sauver_manifeste(manifeste)

        return res
