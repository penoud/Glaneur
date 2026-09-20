"""Moteur de téléchargement des images d'un site WordPress.

Ce module ne connaît rien de l'interface : il communique par callbacks
(`journal`, `progression`) et s'interrompt proprement via un threading.Event.
Il peut donc servir aussi bien à l'UI Tkinter qu'à un script en ligne de commande.
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

PER_PAGE = 100
UA = "Mozilla/5.0 (compatible; ServetteDownloader/1.0)"


class Interrompu(Exception):
    """Levée quand l'utilisateur demande l'arrêt."""


@dataclass
class Options:
    dossier: Path
    site: str = "https://servettefc.ch"
    classement: str = "galerie"       # "galerie", "date" ou "plat"
    largeur_min: int = 800
    delai: float = 0.5
    verifier: bool = False            # revalider les fichiers déjà présents
    force: bool = False               # ignorer le manifeste
    depuis: str | None = None         # AAAA-MM-JJ
    jusqua: str | None = None


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
        self.api = f"{self.base}/wp-json/wp/v2"
        self._journal = journal or (lambda msg: None)
        self._progression = progression or (lambda fait, total, etiquette: None)
        self.arret = arret or threading.Event()
        self.session = requests.Session()
        self.session.headers["User-Agent"] = UA

    # -- plomberie ---------------------------------------------------------- #

    def _verifier_arret(self) -> None:
        if self.arret.is_set():
            raise Interrompu()

    def _pause(self, secondes: float) -> None:
        """Attente fractionnée, pour réagir vite à une demande d'arrêt."""
        fin = time.monotonic() + secondes
        while time.monotonic() < fin:
            self._verifier_arret()
            time.sleep(min(0.1, max(0.0, fin - time.monotonic())))

    def _api(self, chemin: str, params: dict | None = None, essais: int = 3):
        url = f"{self.api}/{chemin.lstrip('/')}"
        derniere = None
        for tentative in range(essais):
            self._verifier_arret()
            try:
                r = self.session.get(url, params=params, timeout=30)
                if r.status_code == 400:
                    return None, r.headers   # page au-delà du dernier résultat
                r.raise_for_status()
                return r.json(), r.headers
            except requests.RequestException as e:
                derniere = e
                self._pause(2 * (tentative + 1))
        raise RuntimeError(f"L'API ne répond pas ({derniere})")

    # -- manifeste ---------------------------------------------------------- #

    def charger_manifeste(self) -> dict:
        if self.o.force or not chemin_manifeste(self.o.dossier).exists():
            return {}
        manifeste = lire_manifeste(self.o.dossier)
        if not manifeste:
            self._journal("Manifeste illisible, reconstruction complète.")
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

    # -- inventaire --------------------------------------------------------- #

    def lister_medias(self) -> list[dict]:
        params = {
            "per_page": PER_PAGE,
            "media_type": "image",
            "orderby": "date",
            "order": "asc",
            "_fields": "id,date,source_url,mime_type,title,alt_text,post,media_details",
        }
        if self.o.depuis:
            params["after"] = f"{self.o.depuis}T00:00:00"
        if self.o.jusqua:
            params["before"] = f"{self.o.jusqua}T23:59:59"

        medias: list[dict] = []
        vus: set[int] = set()
        page, pages_totales, vides = 1, None, 0

        while True:
            lot, headers = self._api("media", {**params, "page": page})
            if pages_totales is None:
                total = headers.get("X-WP-Total", "?")
                pages_totales = int(headers.get("X-WP-TotalPages") or 0)
                self._journal(f"Catalogue : {total} image(s) sur {pages_totales or '?'} page(s)")
            if lot is None:
                break

            nouvelles = [m for m in lot if m["id"] not in vus]
            vus.update(m["id"] for m in nouvelles)
            medias.extend(nouvelles)
            self._progression(page, pages_totales or page,
                              f"Inventaire… {len(medias)} image(s)")

            vides = vides + 1 if not lot else 0
            if vides >= 2:
                break
            if pages_totales and page >= pages_totales:
                break
            if not pages_totales and not lot:
                break
            page += 1
            self._pause(self.o.delai)

        return medias

    def _bases_rest(self) -> list[str]:
        try:
            types, _ = self._api("types")
        except RuntimeError:
            return ["posts", "pages"]
        bases = [
            info.get("rest_base")
            for slug, info in (types or {}).items()
            if info.get("rest_base") and slug not in ("attachment", "wp_block", "nav_menu_item")
        ]
        bases.sort(key=lambda b: (0 if "galer" in b else 1, b))
        return bases or ["posts"]

    def resoudre_parents(self, ids: set[int]) -> dict[int, str]:
        restants = {i for i in ids if i}
        titres: dict[int, str] = {}
        if not restants:
            return titres

        for base in self._bases_rest():
            if not restants:
                break
            lot_ids = sorted(restants)
            for i in range(0, len(lot_ids), PER_PAGE):
                tranche = lot_ids[i: i + PER_PAGE]
                try:
                    items, _ = self._api(base, {
                        "include": ",".join(map(str, tranche)),
                        "per_page": PER_PAGE,
                        "_fields": "id,title,slug",
                    })
                except RuntimeError:
                    continue
                for item in items or []:
                    titres[item["id"]] = item.get("slug") or nettoyer(
                        item.get("title", {}).get("rendered", ""))
                    restants.discard(item["id"])
                self._pause(self.o.delai)

        if restants:
            self._journal(f"{len(restants)} galerie(s) non identifiée(s), classées par date.")
        return titres

    def dossier_pour(self, media: dict, titres: dict[int, str]) -> str:
        """Sous-dossier relatif ; chaîne vide en classement plat."""
        if self.o.classement == "plat":
            return ""
        if self.o.classement == "date" or not media.get("post"):
            m = re.search(r"/uploads/(\d{4})/(\d{2})/", urlparse(media["source_url"]).path)
            return f"{m.group(1)}-{m.group(2)}" if m else "divers"
        return titres.get(media["post"]) or f"contenu-{media['post']}"

    def chemin_libre(self, dest: Path, media_id: int, pris: set[str]) -> Path:
        """WordPress ne dédoublonne les noms que dans un même dossier d'upload :
        deux mois différents peuvent livrer un `match.jpg`, qui s'écraseraient
        l'un l'autre une fois réunis à plat."""
        relatif = str(dest.relative_to(self.o.dossier))
        if relatif in pris:
            dest = dest.with_name(f"{dest.stem}-{media_id}{dest.suffix}")
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
            return f"erreur : {e}", None

    # -- orchestration ------------------------------------------------------ #

    def executer(self) -> Resultat:
        res = Resultat()
        self.o.dossier.mkdir(parents=True, exist_ok=True)
        manifeste = self.charger_manifeste()
        if manifeste:
            self._journal(f"{len(manifeste)} image(s) déjà connues.")

        try:
            medias = self.lister_medias()

            if self.o.largeur_min:
                avant = len(medias)
                medias = [m for m in medias
                          if (m.get("media_details") or {}).get("width", 0) >= self.o.largeur_min]
                ecartees = avant - len(medias)
                if ecartees:
                    self._journal(f"{ecartees} vignette(s) ou logo(s) écarté(s) "
                                  f"(moins de {self.o.largeur_min} px).")

            if not medias:
                res.message = "Aucune image ne correspond aux critères."
                return res

            # noms déjà attribués, pour qu'une image n'en écrase pas une autre
            pris = {e["fichier"] for e in manifeste.values() if e.get("fichier")}

            # tri : déjà sur le disque vs à traiter
            a_faire: list[tuple[dict, Path | None]] = []
            for m in medias:
                etat = manifeste.get(str(m["id"]))
                taille_api = (m.get("media_details") or {}).get("filesize")
                connu = self.o.dossier / etat["fichier"] if etat and etat.get("fichier") else None

                if etat and etat.get("supprime"):
                    res.ignorees += 1
                    continue
                if (connu is not None and etat.get("taille") and not connu.exists()
                        and not etat.get("restaure")):
                    # déjà téléchargée puis disparue : l'utilisateur l'a effacée
                    etat["supprime"] = datetime.now().isoformat(timespec="seconds")
                    res.supprimees += 1
                    continue
                if connu and self.fichier_complet(connu, etat, taille_api) and not self.o.verifier:
                    etat.pop("restaure", None)
                    res.deja_presentes += 1
                    continue
                a_faire.append((m, connu))

            self._journal(f"{res.deja_presentes} déjà à jour, {len(a_faire)} à traiter.")
            if res.supprimees:
                self._journal(f"{res.supprimees} image(s) effacée(s) sur le disque, "
                              "elles ne seront plus retéléchargées.")
            if not a_faire:
                res.message = "Tout est déjà à jour."
                self._progression(1, 1, res.message)
                return res

            titres: dict[int, str] = {}
            inconnus = {m.get("post") for m, connu in a_faire if connu is None}
            if self.o.classement == "galerie" and inconnus:
                self._progression(0, len(a_faire), "Identification des galeries…")
                titres = self.resoudre_parents(inconnus)

            for i, (m, connu) in enumerate(a_faire, 1):
                self._verifier_arret()
                url = m["source_url"]
                etat = manifeste.get(str(m["id"]))
                if connu is not None:
                    fichier = connu
                else:
                    sous = self.dossier_pour(m, titres)
                    # nettoyer("") renverrait "divers" et créerait un dossier fantôme
                    dossier = (self.o.dossier / nettoyer(sous)) if sous else self.o.dossier
                    fichier = self.chemin_libre(
                        dossier / Path(urlparse(url).path).name, m["id"], pris)

                statut, infos = self.telecharger(url, fichier, etat)

                if infos:
                    infos["fichier"] = str(fichier.relative_to(self.o.dossier))
                    manifeste[str(m["id"])] = infos
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
                    self._journal(f"{fichier.name} : {statut}")

                self._progression(i, len(a_faire), f"{fichier.parent.name}/{fichier.name}")
                if i % 25 == 0:
                    self.sauver_manifeste(manifeste)

            res.message = (f"{res.telechargees} nouvelle(s) image(s), "
                           f"{format_octets(res.octets)} téléchargés.")

        except Interrompu:
            res.interrompu = True
            res.message = "Interrompu — la reprise repartira d'ici."
        except RuntimeError as e:
            res.message = str(e)
            self._journal(f"Erreur : {e}")
        except OSError as e:
            res.message = f"Problème d'écriture : {e}"
            self._journal(res.message)
        finally:
            self.sauver_manifeste(manifeste)

        return res
