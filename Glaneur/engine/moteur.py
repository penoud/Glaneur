"""Classe :class:`Moteur` — orchestration d'un run.

Ce module est le seul du paquet à dépendre de Qt : il utilise
``QCoreApplication.translate`` pour localiser les messages remontés à
l'utilisateur. Le reste du paquet reste indépendant de Qt.

lupdate only extracts QCoreApplication.translate("Ctx", "src") when
context and source are literals: we inline rather than aliasing a _tr().
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

import requests
from PySide6.QtCore import QCoreApplication

from ..sources import SOURCES, Element, Interrompu, Transport
from ..sources.base import Classification, classer_erreur
from ._fusion import _fusionner_marques_ui
from ._verrous import _MANIFESTE_LOCK
from .chemin_manifeste import chemin_manifeste
from .ecrire_cache import ecrire_cache
from .ecrire_manifeste import ecrire_manifeste
from .format_octets import format_octets
from .lire_cache import lire_cache
from .lire_manifeste import lire_manifeste
from .nettoyer import nettoyer
from .options import Options
from .resultat import Resultat


class Moteur:
    """Orchestre un run : inventaire, tri, téléchargement, manifeste, cache.

    Le moteur ne connaît rien de l'UI. Il expose deux callbacks
    (``journal`` et ``progression``) et un :class:`threading.Event` pour
    l'interruption coopérative, si bien qu'il tourne aussi bien depuis un
    thread Qt que depuis la CLI ou un test unitaire.

    Il ne connaît rien non plus de WordPress ou Djangoplicity : le choix
    de la source est fait par ``Options.type_source``, résolu via
    ``Glaneur.sources.SOURCES``.
    """

    def __init__(
        self,
        options: Options,
        journal: Callable[[str], None] | None = None,
        progression: Callable[[int, int, str], None] | None = None,
        arret: threading.Event | None = None,
    ) -> None:
        """Instancie le moteur avec ses callbacks.

        Args:
            options: Paramètres du run (dossier, site, filtres, etc.).
            journal: Callback appelé pour chaque message texte destiné à
                l'utilisateur. Reçoit une chaîne déjà localisée. Peut être
                ``None`` (aucun affichage).
            progression: Callback appelé à chaque avancement du run.
                Reçoit ``(fait, total, etiquette)``. Peut être ``None``.
            arret: Event partagé qui coupe le run quand il est positionné.
                Créé à la demande si non fourni ; l'appelant peut le
                réutiliser pour synchroniser plusieurs moteurs.
        """
        self.o = options
        self.base = options.site.rstrip("/")
        self._journal = journal or (lambda msg: None)
        self._progression = progression or (lambda fait, total, etiquette: None)
        self.arret = arret or threading.Event()
        self.transport = Transport(delai=options.delai, arret=self.arret)
        # The download session goes through the shared transport: a single
        # user-agent, a single pause floor.
        self.session = self.transport.session
        classe = SOURCES.get(options.type_source) or SOURCES["wordpress"]
        self.source = classe(
            base=self.base,
            transport=self.transport,
            reglages={"format_image": options.format_image},
            journal=self._journal,
            progression=self._progression,
        )

    # -- plumbing ----------------------------------------------------------- #

    def _verifier_arret(self) -> None:
        if self.arret.is_set():
            raise Interrompu()

    def _pause(self, secondes: float) -> None:
        """Attente fractionnée, pour réagir vite à une demande d'arrêt."""
        self.transport.pause(secondes)

    # -- manifest ----------------------------------------------------------- #

    def charger_manifeste(self) -> dict:
        """Charge le manifeste du run précédent, ou ``{}`` en mode force.

        Journalise un avertissement si le fichier existe mais est
        illisible : le run repartira alors d'un état vide et refera un
        inventaire complet.

        Returns:
            Le manifeste courant, éventuellement vide.
        """
        if self.o.force or not chemin_manifeste(self.o.dossier).exists():
            return {}
        manifeste = lire_manifeste(self.o.dossier)
        if not manifeste:
            self._journal(QCoreApplication.translate("Moteur", "Manifeste illisible, reconstruction complète."))
        return manifeste

    def sauver_manifeste(self, manifeste: dict) -> None:
        """Persiste ``manifeste`` sur disque en fusionnant les gestes UI éventuels.

        Prend le verrou ``_MANIFESTE_LOCK``, relit le manifeste disque et
        applique la règle décrite dans ``_fusionner_marques_ui`` avant
        l'écriture atomique. Cette lecture-fusion-écriture protège les
        marques ``supprime``/``restaure`` que l'utilisateur peut poser
        via :func:`Glaneur.engine.supprimer_image.supprimer_image` ou
        :func:`Glaneur.engine.restaurer.restaurer` pendant qu'un run est
        en cours : sans elle, la sauvegarde périodique ou finale du
        moteur écraserait la modification faite entre-temps par l'UI.

        Args:
            manifeste: État en mémoire à persister.
        """
        with _MANIFESTE_LOCK:
            disque = lire_manifeste(self.o.dossier)
            ecrire_manifeste(
                self.o.dossier, _fusionner_marques_ui(manifeste, disque))

    @staticmethod
    def fichier_complet(dest: Path, etat: dict | None, taille_api: int | None) -> bool:
        """Indique si ``dest`` est un téléchargement complet, à la taille près.

        Args:
            dest: Chemin du fichier à vérifier.
            etat: Entrée manifeste correspondante, ou ``None`` si aucune.
            taille_api: Taille annoncée par la source, ou ``None`` si
                elle n'est pas connue à cette étape.

        Returns:
            ``True`` si le fichier existe, n'est pas vide, et sa taille
            correspond à celle attendue (manifeste ou API). ``False`` si
            l'une de ces conditions manque.
        """
        if not dest.exists():
            return False
        taille = dest.stat().st_size
        if taille == 0:
            return False
        attendue = (etat or {}).get("taille") or taille_api
        return not (attendue and taille != attendue)

    # -- API cache ---------------------------------------------------------- #

    def charger_cache(self) -> dict:
        """Lit le cache disque, en le vidant si le contexte a changé.

        Le cache est ignoré en mode force ou si l'utilisation en est
        désactivée. Si le site enregistré diffère du site courant, ou si
        le type de source change (ex. WordPress → Djangoplicity), on
        repart de zéro pour ne pas mélanger deux espaces d'identifiants.

        Migration silencieuse : un cache écrit avant l'introduction de
        ``Options.type_source`` (donc sans ce champ) est lu comme s'il
        correspondait au type courant, pour ne pas invalider les caches
        WordPress existants.

        Returns:
            Le cache utilisable pour ce run, éventuellement vide.
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
        """Persiste ``cache`` sur disque, sauf en mode force/cache désactivé.

        L'origine et le type de source du run courant sont réinjectés
        dans ``cache`` avant écriture pour que :meth:`charger_cache`
        puisse invalider automatiquement au run suivant si l'un ou
        l'autre change.

        Args:
            cache: État à sérialiser (peut être partiellement rempli).
        """
        if self.o.force or not self.o.utiliser_cache:
            return
        ecrire_cache(self.o.dossier, {
            **cache, "site": self.base, "type_source": self.o.type_source,
        })

    # -- paths -------------------------------------------------------------- #

    def dossier_pour(self, element: Element, titres: dict[str, str]) -> str:
        """Sous-dossier relatif où ranger ``element`` selon le classement retenu.

        Args:
            element: Élément à ranger.
            titres: Table {id_parent -> titre nettoyé} résolue en amont
                par la source, utilisée pour ``classement="galerie"``.

        Returns:
            Un nom de sous-dossier relatif, ou une chaîne vide en
            classement ``plat`` (tout au niveau racine).
        """
        if self.o.classement == "plat":
            return ""
        if self.o.classement == "date" or not element.groupe:
            return element.mois or "divers"
        return titres.get(element.groupe) or f"contenu-{element.groupe}"

    def chemin_libre(self, dest: Path, ident: str, pris: set[str]) -> Path:
        """Choisit un chemin de destination qui n'écrase aucun autre élément.

        Un même nom de fichier peut apparaître dans deux mois différents
        (WordPress ne dédoublonne que par dossier d'upload) ou dans deux
        entrées Djangoplicity (variantes de langue) : on suffixe par
        ``ident`` pour ne pas écraser.

        Args:
            dest: Chemin candidat, tel que déduit du sous-dossier et du
                nom de fichier de la source.
            ident: Identifiant de l'élément, utilisé comme suffixe si
                ``dest`` est déjà pris.
            pris: Ensemble des chemins relatifs déjà attribués pendant
                ce run. La méthode y ajoute le chemin choisi avant de
                le renvoyer.

        Returns:
            Un chemin absolu unique dans ``pris``.
        """
        relatif = str(dest.relative_to(self.o.dossier))
        if relatif in pris:
            dest = dest.with_name(f"{dest.stem}-{ident}{dest.suffix}")
            relatif = str(dest.relative_to(self.o.dossier))
        pris.add(relatif)
        return dest

    # -- download ----------------------------------------------------------- #

    def telecharger(
        self, url: str, dest: Path, etat: dict | None,
    ) -> tuple[str, dict | None, Classification | None]:
        """Télécharge ``url`` vers ``dest`` avec reprise et revalidation.

        Gère :

        - ``If-None-Match`` / ``If-Modified-Since`` en mode ``verifier`` ;
        - reprise via ``Range: bytes=...-`` sur un ``.part`` partiel ;
        - repli sur téléchargement complet en cas de ``416`` ;
        - interruption coopérative en cours de flux (préserve le ``.part``
          pour la reprise suivante).

        Args:
            url: URL à télécharger.
            dest: Chemin absolu du fichier final. Le dossier parent est
                créé si nécessaire.
            etat: Entrée manifeste précédente (ETag, Last-Modified,
                taille…) ou ``None``.

        Returns:
            Un tuple ``(statut, infos, classification)`` où
            ``statut`` est ``"ok"``, ``"repris"``, ``"inchangé"``,
            ``"introuvable"`` ou un message d'erreur localisé,
            ``infos`` est le nouvel état à écrire au manifeste
            (ou ``None`` si aucun contenu), et ``classification``
            est la :class:`Glaneur.sources.base.Classification` de
            l'erreur (``None`` en cas de succès). Le moteur consomme
            la ``classification`` dans :meth:`executer` pour décider
            d'un coupe-circuit.

        Raises:
            Interrompu: Propagé si ``self.arret`` est positionné pendant
                l'écriture du flux.
        """
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
                return "inchangé", etat, None
            if r.status_code == 404:
                return "introuvable", None, Classification("definitif", None)
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
                        raise Interrompu()   # the .part is kept for resume
                    f.write(bloc)
            tmp.replace(dest)

            infos = {
                "taille": dest.stat().st_size,
                "etag": r.headers.get("ETag", ""),
                "modifie": r.headers.get("Last-Modified", ""),
                "url": url,
            }
            self._pause(self.o.delai)
            return ("repris" if reprise else "ok"), infos, None

        except requests.RequestException as e:
            reponse = getattr(e, "response", None)
            classification = classer_erreur(e, reponse)
            return (
                QCoreApplication.translate("Moteur", "erreur : {erreur}").format(erreur=e),
                None,
                classification,
            )

    def _declencher_report(
        self,
        res: Resultat,
        classification: Classification | None,
        fait: int,
        total: int,
    ) -> None:
        """Marque ``res`` comme reporté et journalise un message actionnable.

        Renseigne ``res.retenter_apres`` (ISO 8601) uniquement si le
        serveur a fourni un ``Retry-After`` via ``classification``.
        Sans indication, on laisse le champ vide : c'est au
        planificateur d'appliquer son propre backoff (lot 3).
        """
        res.reporte = True
        cible: datetime | None = None
        if classification is not None and classification.retry_after:
            cible = datetime.now(timezone.utc) + timedelta(
                seconds=classification.retry_after)
            res.retenter_apres = cible.isoformat(timespec="seconds")
        if cible is not None:
            message = QCoreApplication.translate(
                "Moteur",
                "Serveur indisponible ou quota atteint — reprise après {heure}.",
            ).format(heure=cible.astimezone().strftime("%H:%M"))
        else:
            message = QCoreApplication.translate(
                "Moteur",
                "Serveur indisponible ou quota atteint — reprise différée.",
            )
        res.message = message
        self._journal(message)
        self._progression(fait, total, message)

    # -- orchestration ------------------------------------------------------ #

    def executer(self) -> Resultat:
        """Exécute le run complet et renvoie le ``Resultat`` agrégé.

        L'ordre est :

        1. lecture du manifeste et du cache ;
        2. inventaire via la source (filtre par date, largeur minimale) ;
        3. tri en trois listes (déjà à jour, à télécharger, supprimées) ;
        4. résolution des titres de galeries si nécessaire ;
        5. téléchargement séquentiel avec sauvegarde périodique du
           manifeste (toutes les 25 images) ;
        6. mise à jour du cache (date maximale, titres) en sortie normale.

        Une interruption coopérative renvoie un ``Resultat`` avec
        ``Resultat.interrompu`` vrai. Les erreurs réseau ou disque
        sont capturées et rapportées via ``res.message`` sans propager
        l'exception.

        Returns:
            Le résumé chiffré du run.
        """
        res = Resultat()
        self.o.dossier.mkdir(parents=True, exist_ok=True)
        manifeste = self.charger_manifeste()
        cache = self.charger_cache()
        if manifeste:
            self._journal(QCoreApplication.translate("Moteur", "{n} image(s) déjà connues.").format(n=len(manifeste)))

        # Cache: only used if the user has not already bounded the period —
        # in that case, their bounds override the cache's memory.
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
                # An `Element` without a URL (source that did not find the
                # requested resource) can no longer be downloaded: goes to `ignorees`.
                ecartees = avant - len(elements)
                if ecartees:
                    self._journal(QCoreApplication.translate(
                        "Moteur",
                        "{n} vignette(s) ou logo(s) écarté(s) (moins de {min} px).").format(
                        n=ecartees, min=self.o.largeur_min))

            if not elements:
                res.message = QCoreApplication.translate("Moteur", "Aucune image ne correspond aux critères.")
                return res

            # names already assigned, so an image does not overwrite another
            pris = {e["fichier"] for e in manifeste.values() if e.get("fichier")}

            # sort: already on disk vs to be processed
            a_faire: list[tuple[Element, Path | None]] = []
            for e in elements:
                etat = manifeste.get(e.ident)
                connu = self.o.dossier / etat["fichier"] if etat and etat.get("fichier") else None

                if etat and etat.get("supprime"):
                    res.ignorees += 1
                    continue
                if e.url is None:
                    # The source did not find any usable resource.
                    res.ignorees += 1
                    continue
                if (connu is not None and etat.get("taille") and not connu.exists()
                        and not etat.get("restaure")):
                    # already downloaded then gone: the user erased it
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

            echecs_consecutifs = 0
            for i, (e, connu) in enumerate(a_faire, 1):
                self._verifier_arret()
                url = e.url
                etat = manifeste.get(e.ident)
                if connu is not None:
                    fichier = connu
                else:
                    sous = self.dossier_pour(e, titres)
                    # nettoyer("") would return "divers" and create a phantom directory
                    dossier = (self.o.dossier / nettoyer(sous)) if sous else self.o.dossier
                    nom = e.nom_fichier or Path(urlparse(url).path).name
                    fichier = self.chemin_libre(dossier / nom, e.ident, pris)

                statut, infos, classification = self.telecharger(url, fichier, etat)

                if infos:
                    infos["fichier"] = str(fichier.relative_to(self.o.dossier))
                    # Source metadata (credit, checksum…): copied into the
                    # manifest for the upcoming catalog export, without the
                    # engine interpreting them.
                    if e.extra:
                        infos.setdefault("extra", {}).update(e.extra)
                    manifeste[e.ident] = infos
                if statut == "ok":
                    res.telechargees += 1
                    res.octets += infos["taille"]
                    echecs_consecutifs = 0
                elif statut == "repris":
                    res.reprises += 1
                    res.octets += infos["taille"]
                    echecs_consecutifs = 0
                elif statut == "inchangé":
                    res.inchangees += 1
                    echecs_consecutifs = 0
                else:
                    res.echecs += 1
                    # `statut` can be an internal code ("introuvable") or an
                    # already-translated phrase (see télécharger()).
                    affiche = QCoreApplication.translate("Moteur", "introuvable") if statut == "introuvable" else statut
                    self._journal(f"{fichier.name} : {affiche}")

                    categorie = classification.categorie if classification else "transitoire"
                    if categorie == "coupure":
                        self._declencher_report(res, classification, i, len(a_faire))
                        break
                    if categorie == "transitoire":
                        echecs_consecutifs += 1
                        if echecs_consecutifs >= 5:
                            self._declencher_report(res, None, i, len(a_faire))
                            break
                    else:  # "definitif" — a single 404/URL error stays local
                        echecs_consecutifs = 0

                self._progression(i, len(a_faire), f"{fichier.parent.name}/{fichier.name}")
                if i % 25 == 0:
                    self.sauver_manifeste(manifeste)

            if not res.reporte:
                res.message = QCoreApplication.translate("Moteur", "{n} nouvelle(s) image(s), {taille} téléchargés.").format(
                    n=res.telechargees, taille=format_octets(res.octets))

                # Cache update: max date and newly resolved titles.
                # Only written on normal exit, never after an interruption,
                # a report, or an error, to avoid remembering an incomplete state.
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
