"""Class :class:`Moteur` — orchestration of a run.

This module is the only one in the package that depends on Qt: it uses
``QCoreApplication.translate`` to localise messages surfaced to the
user. The rest of the package stays Qt-independent.

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
    """Orchestrate a run: inventory, sort, download, manifest, cache.

    The engine knows nothing about the UI. It exposes two callbacks
    (``journal`` and ``progression``) and a :class:`threading.Event` for
    cooperative interruption, so it runs equally well from a Qt thread,
    from the CLI, or from a unit test.

    It also knows nothing about WordPress or Djangoplicity: the source
    choice is driven by ``Options.type_source``, resolved through
    ``Glaneur.sources.SOURCES``.
    """

    def __init__(
        self,
        options: Options,
        journal: Callable[[str], None] | None = None,
        progression: Callable[[int, int, str], None] | None = None,
        arret: threading.Event | None = None,
    ) -> None:
        """Instantiate the engine with its callbacks.

        Args:
            options: Run parameters (folder, site, filters, etc.).
            journal: Callback invoked for each user-facing text message.
                Receives an already-localised string. May be ``None`` (no
                display).
            progression: Callback invoked at each step of the run.
                Receives ``(done, total, label)``. May be ``None``.
            arret: Shared event that cuts the run when set. Created on
                demand if not provided; the caller may reuse it to
                synchronise several engines.
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
        """Fragmented wait so we can react quickly to a stop request."""
        self.transport.pause(secondes)

    # -- manifest ----------------------------------------------------------- #

    def charger_manifeste(self) -> dict:
        """Load the previous run's manifest, or ``{}`` in force mode.

        Journals a warning if the file exists but is unreadable: the run
        then starts from an empty state and redoes a full inventory.

        Returns:
            The current manifest, possibly empty.
        """
        if self.o.force or not chemin_manifeste(self.o.dossier).exists():
            return {}
        manifeste = lire_manifeste(self.o.dossier)
        if not manifeste:
            self._journal(QCoreApplication.translate("Moteur", "Manifeste illisible, reconstruction complète."))
        return manifeste

    def sauver_manifeste(self, manifeste: dict) -> None:
        """Persist ``manifeste`` on disk merging any UI actions.

        Takes the ``_MANIFESTE_LOCK``, re-reads the manifest from disk
        and applies the rule described in ``_fusionner_marques_ui``
        before writing atomically. This read-merge-write protects the
        ``supprime`` / ``restaure`` marks the user may set via
        :func:`Glaneur.engine.supprimer_image.supprimer_image` or
        :func:`Glaneur.engine.restaurer.restaurer` while a run is in
        progress: without it, the engine's periodic or final save would
        overwrite the change the UI made in the meantime.

        Args:
            manifeste: In-memory state to persist.
        """
        with _MANIFESTE_LOCK:
            disque = lire_manifeste(self.o.dossier)
            ecrire_manifeste(
                self.o.dossier, _fusionner_marques_ui(manifeste, disque))

    @staticmethod
    def fichier_complet(dest: Path, etat: dict | None, taille_api: int | None) -> bool:
        """Report whether ``dest`` is a complete download, size-wise.

        Args:
            dest: Path of the file to check.
            etat: Matching manifest entry, or ``None`` if none.
            taille_api: Size announced by the source, or ``None`` if not
                known at this step.

        Returns:
            ``True`` if the file exists, is non-empty and its size matches
            the expected one (manifest or API). ``False`` if any of these
            conditions is missing.
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
        """Read the on-disk cache, wiping it when the context has changed.

        The cache is ignored in force mode or when its use is disabled.
        If the recorded site differs from the current site, or if the
        source type changes (e.g. WordPress → Djangoplicity), we start
        from scratch so as not to mix two identifier spaces.

        Silent migration: a cache written before ``Options.type_source``
        was introduced (i.e. without that field) is read as if it
        matched the current type, so existing WordPress caches remain
        valid.

        Returns:
            The cache usable for this run, possibly empty.
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
        """Persist ``cache`` on disk, except in force / cache-disabled mode.

        The current run's origin and source type are re-injected into
        ``cache`` before writing so that :meth:`charger_cache` can
        automatically invalidate the next run when either changes.

        Args:
            cache: State to serialise (may be partially populated).
        """
        if self.o.force or not self.o.utiliser_cache:
            return
        ecrire_cache(self.o.dossier, {
            **cache, "site": self.base, "type_source": self.o.type_source,
        })

    # -- paths -------------------------------------------------------------- #

    def dossier_pour(self, element: Element, titres: dict[str, str]) -> str:
        """Relative sub-folder where ``element`` should land under the chosen sort.

        Args:
            element: Element to place.
            titres: ``{parent_id -> cleaned title}`` table resolved
                upstream by the source, used for ``classement="galerie"``.

        Returns:
            A relative sub-folder name, or an empty string in ``plat``
            mode (everything at the root level).
        """
        if self.o.classement == "plat":
            return ""
        if self.o.classement == "date" or not element.groupe:
            return element.mois or "divers"
        return titres.get(element.groupe) or f"contenu-{element.groupe}"

    def chemin_libre(self, dest: Path, ident: str, pris: set[str]) -> Path:
        """Pick a destination path that does not overwrite another element.

        The same file name can appear in two different months (WordPress
        only deduplicates per upload folder) or in two Djangoplicity
        entries (language variants): we suffix with ``ident`` to avoid
        overwriting.

        Args:
            dest: Candidate path, as derived from the sub-folder and
                the file name coming from the source.
            ident: Element identifier, used as a suffix when ``dest``
                is already taken.
            pris: Set of relative paths already assigned during this
                run. The method adds the chosen path to it before
                returning.

        Returns:
            An absolute path unique within ``pris``.
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
        """Download ``url`` to ``dest`` with resume and revalidation.

        Handles:

        - ``If-None-Match`` / ``If-Modified-Since`` in ``verifier`` mode;
        - resume through ``Range: bytes=...-`` on a partial ``.part``;
        - fallback to a full download on ``416``;
        - cooperative interruption mid-stream (preserves the ``.part``
          for the next resume).

        Args:
            url: URL to download.
            dest: Absolute path of the final file. The parent directory
                is created if needed.
            etat: Previous manifest entry (ETag, Last-Modified,
                size, ...) or ``None``.

        Returns:
            A tuple ``(status, infos, classification)`` where ``status``
            is ``"ok"``, ``"repris"``, ``"inchangé"``, ``"introuvable"``
            or a localised error message, ``infos`` is the new state to
            write to the manifest (or ``None`` if nothing was fetched),
            and ``classification`` is the
            :class:`Glaneur.sources.base.Classification` of the error
            (``None`` on success). The engine consumes
            ``classification`` in :meth:`executer` to decide on a
            circuit-breaker trip.

        Raises:
            Interrompu: Propagated if ``self.arret`` is set while the
                stream is being written.
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
        """Mark ``res`` as deferred and journal an actionable message.

        Fills ``res.retenter_apres`` (ISO 8601) only when the server
        provided a ``Retry-After`` via ``classification``. Without a
        hint, the field stays empty: it is up to the scheduler to apply
        its own backoff (lot 3).
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
        """Run the whole thing and return the aggregated ``Resultat``.

        The order is:

        1. read the manifest and the cache;
        2. inventory via the source (date filter, minimum width);
        3. sort into three lists (already up to date, to download,
           deleted);
        4. resolve gallery titles if needed;
        5. sequential download with periodic manifest save (every 25
           images);
        6. cache update (maximum date, titles) on a normal exit.

        A cooperative interruption returns a ``Resultat`` with
        ``Resultat.interrompu`` set. Network or disk errors are caught
        and reported through ``res.message`` without propagating the
        exception.

        Returns:
            The numeric summary of the run.
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
                    # Source metadata (credit, checksum...): copied into the
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
