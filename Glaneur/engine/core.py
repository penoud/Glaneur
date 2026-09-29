"""Class :class:`Engine` — orchestration of a run.

The engine has no Qt dependency: user-facing messages leave it as
:class:`Glaneur.engine.events.EngineEvent` values (a stable ``code``
plus named ``params``). The Qt UI (``app.py``) translates them in
French under the ``UiJournal`` context; the CLI and the file log render
them in English via :func:`Glaneur.engine.events.render_en`.

See boundary 1 in ``CLAUDE.md`` and
``docs/sprints/2026-09-verifier-lots-1-4-avant-lot-5.md``.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

from ..sources import SOURCES, Element, Interrupted, Transport
from ..sources.base import ErrorClassification, classify_error
from ._folder_lock import FolderBusy, folder_lock
from ._locks import _MANIFEST_LOCK
from ._merge import _merge_ui_marks
from .events import EngineEvent, render_en
from .format_bytes import format_bytes
from .manifest_path import manifest_path
from .options import Options
from .read_cache import read_cache
from .read_manifest import read_manifest
from .result import RunResult
from .sanitize import clean
from .write_cache import write_cache
from .write_manifest import write_manifest


class Engine:
    """Orchestrate a run: inventory, sort, download, manifest, cache.

    The engine knows nothing about the UI. It exposes two callbacks
    (``journal`` and ``progression``) and a :class:`threading.Event` for
    cooperative interruption, so it runs equally well from a Qt thread,
    from the CLI, or from a unit test.

    It also knows nothing about WordPress or Djangoplicity: the source
    choice is driven by ``Options.source_type``, resolved through
    ``Glaneur.sources.SOURCES``.
    """

    def __init__(
        self,
        options: Options,
        journal: Callable[[EngineEvent], None] | None = None,
        progression: Callable[[int, int, str], None] | None = None,
        stop_event: threading.Event | None = None,
    ) -> None:
        """Instantiate the engine with its callbacks.

        Args:
            options: Run parameters (folder, site, filters, etc.).
            journal: Callback invoked for each user-facing message. It
                receives an :class:`~Glaneur.engine.events.EngineEvent`
                (stable ``code`` + ``params``). Rendering is the
                caller's job — the engine no longer builds translated
                strings. May be ``None`` (silent).
            progression: Callback invoked at each step of the run.
                Receives ``(done, total, label)`` — the label stays a
                plain string (English by default) so a Qt progress bar
                can display it directly. May be ``None``.
            stop_event: Shared event that cuts the run when set. Created
                on demand if not provided; the caller may reuse it to
                synchronise several engines.
        """
        self.o = options
        self.base = options.site.rstrip("/")
        self._journal: Callable[[EngineEvent], None] = journal or (
            lambda _event: None)
        self._progression = progression or (lambda _fait, _total, _etiquette: None)
        self.stop_event = stop_event or threading.Event()
        self.transport = Transport(delay=options.delay, stop_event=self.stop_event)
        # The download session goes through the shared transport: a single
        # user-agent, a single pause floor.
        self.session = self.transport.session
        classe = SOURCES.get(options.source_type) or SOURCES["wordpress"]
        # Source adapters still emit plain-text messages (their strings
        # are French today; migrating them is out of scope for this US).
        # Wrap them into a generic ``source-message`` event so the
        # engine's callback keeps a single type contract.
        self.source = classe(
            base=self.base,
            transport=self.transport,
            settings={"format_image": options.image_format},
            journal=self._relay_source_message,
            progression=self._progression,
        )

    def _relay_source_message(self, text: str) -> None:
        """Lift a free-form source message into a structured event."""
        self._journal(EngineEvent("source-message", {"text": text}))

    # -- plumbing ----------------------------------------------------------- #

    def _check_stop(self) -> None:
        if self.stop_event.is_set():
            raise Interrupted()

    def _pause(self, seconds: float) -> None:
        """Fragmented wait so we can react quickly to a stop request."""
        self.transport.sleep(seconds)

    # -- manifest ----------------------------------------------------------- #

    def load_manifest(self) -> dict:
        """Load the previous run's manifest, or ``{}`` in force mode.

        Journals a warning if the file exists but is unreadable: the run
        then starts from an empty state and redoes a full inventory.

        Returns:
            The current manifest, possibly empty.
        """
        if self.o.force or not manifest_path(self.o.target_dir).exists():
            return {}
        manifeste = read_manifest(self.o.target_dir)
        if not manifeste:
            self._journal(EngineEvent("manifest-unreadable"))
        return manifeste

    def save_manifest(self, manifeste: dict) -> None:
        """Persist ``manifeste`` on disk merging any UI actions.

        Takes the ``_MANIFEST_LOCK``, re-reads the manifest from disk
        and applies the rule described in ``_merge_ui_marks``
        before writing atomically. This read-merge-write protects the
        ``supprime`` / ``restaure`` marks the user may set via
        :func:`Glaneur.engine.delete_image.delete_image` or
        :func:`Glaneur.engine.restore.restore` while a run is in
        progress: without it, the engine's periodic or final save would
        overwrite the change the UI made in the meantime.

        Args:
            manifeste: In-memory state to persist.
        """
        with _MANIFEST_LOCK:
            disque = read_manifest(self.o.target_dir)
            write_manifest(
                self.o.target_dir, _merge_ui_marks(manifeste, disque))

    @staticmethod
    def file_complete(dest: Path, etat: dict | None, taille_api: int | None) -> bool:
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

    def load_cache(self) -> dict:
        """Read the on-disk cache, wiping it when the context has changed.

        The cache is ignored in force mode or when its use is disabled.
        If the recorded site differs from the current site, or if the
        source type changes (e.g. WordPress → Djangoplicity), we start
        from scratch so as not to mix two identifier spaces.

        Silent migration: a cache written before ``Options.source_type``
        was introduced (i.e. without that field) is read as if it
        matched the current type, so existing WordPress caches remain
        valid.

        Returns:
            The cache usable for this run, possibly empty.
        """
        if self.o.force or not self.o.use_cache:
            return {}
        cache = read_cache(self.o.target_dir)
        if cache.get("site") and cache["site"] != self.base:
            return {}
        type_cache = cache.get("type_source")
        if type_cache and type_cache != self.o.source_type:
            return {}
        return cache

    def save_cache(self, cache: dict) -> None:
        """Persist ``cache`` on disk, except in force / cache-disabled mode.

        The current run's origin and source type are re-injected into
        ``cache`` before writing so that :meth:`load_cache` can
        automatically invalidate the next run when either changes.

        Args:
            cache: State to serialise (may be partially populated).
        """
        if self.o.force or not self.o.use_cache:
            return
        write_cache(self.o.target_dir, {
            **cache, "site": self.base, "type_source": self.o.source_type,
        })

    # -- paths -------------------------------------------------------------- #

    def folder_for(self, element: Element, titres: dict[str, str]) -> str:
        """Relative sub-folder where ``element`` should land under the chosen sort.

        Args:
            element: Element to place.
            titres: ``{parent_id -> cleaned title}`` table resolved
                upstream by the source, used for ``classement="galerie"``.

        Returns:
            A relative sub-folder name, or an empty string in ``plat``
            mode (everything at the root level).
        """
        if self.o.sort_mode == "plat":
            return ""
        if self.o.sort_mode == "date" or not element.group:
            return element.month or "divers"
        return titres.get(element.group) or f"contenu-{element.group}"

    def free_path(self, dest: Path, ident: str, pris: set[str]) -> Path:
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
        relatif = str(dest.relative_to(self.o.target_dir))
        if relatif in pris:
            dest = dest.with_name(f"{dest.stem}-{ident}{dest.suffix}")
            relatif = str(dest.relative_to(self.o.target_dir))
        pris.add(relatif)
        return dest

    # -- download ----------------------------------------------------------- #

    def download(
        self, url: str, dest: Path, etat: dict | None,
    ) -> tuple[str, dict | None, ErrorClassification | None, str | None]:
        """Download ``url`` to ``dest`` with resume and revalidation.

        Handles:

        - ``If-None-Match`` / ``If-Modified-Since`` in ``verify`` mode;
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
            A four-tuple ``(status, infos, classification, error)``:

            - ``status`` is a stable code, one of ``"ok"``, ``"repris"``,
              ``"inchangé"``, ``"introuvable"`` or ``"erreur"``;
            - ``infos`` is the new state to write to the manifest, or
              ``None`` if nothing was fetched;
            - ``classification`` is the
              :class:`Glaneur.sources.base.ErrorClassification` of the
              error (``None`` on success), consumed by :meth:`run` to
              decide on a circuit-breaker trip;
            - ``error`` is ``str(exception)`` on the ``"erreur"`` path
              only, otherwise ``None`` — it lets the caller build a
              :class:`~Glaneur.engine.events.EngineEvent` for the
              per-file journal line.

        Raises:
            Interrupted: Propagated if ``self.stop_event`` is set while
                the stream is being written.
        """
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        entetes: dict[str, str] = {}
        depuis = 0

        if dest.exists() and self.o.verify and etat:
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
                return "inchangé", etat, None, None
            if r.status_code == 404:
                return "introuvable", None, ErrorClassification("definitif", None), None
            if r.status_code == 416:
                tmp.unlink(missing_ok=True)
                depuis = 0
                r = self.session.get(url, timeout=60, stream=True)
            r.raise_for_status()

            reprise = depuis > 0 and r.status_code == 206
            with open(tmp, "ab" if reprise else "wb") as f:
                for bloc in r.iter_content(65536):
                    if self.stop_event.is_set():
                        f.flush()
                        raise Interrupted()   # the .part is kept for resume
                    f.write(bloc)
            tmp.replace(dest)

            infos = {
                "taille": dest.stat().st_size,
                "etag": r.headers.get("ETag", ""),
                "modifie": r.headers.get("Last-Modified", ""),
                "url": url,
            }
            self._pause(self.o.delay)
            return ("repris" if reprise else "ok"), infos, None, None

        except requests.RequestException as e:
            reponse = getattr(e, "response", None)
            classification = classify_error(e, reponse)
            return "erreur", None, classification, str(e)

    def _trigger_defer(
        self,
        res: RunResult,
        classification: ErrorClassification | None,
        fait: int,
        total: int,
    ) -> None:
        """Mark ``res`` as deferred and journal an actionable message.

        Fills ``res.retry_after`` (ISO 8601) only when the server
        provided a ``Retry-After`` via ``classification``. Without a
        hint, the field stays empty: it is up to the scheduler to apply
        its own backoff (lot 3).
        """
        res.deferred = True
        cible: datetime | None = None
        if classification is not None and classification.retry_after:
            cible = datetime.now(timezone.utc) + timedelta(
                seconds=classification.retry_after)
            res.retry_after = cible.isoformat(timespec="seconds")
        if cible is not None:
            event = EngineEvent(
                "defer-with-time",
                {"until": cible.astimezone().strftime("%H:%M")},
            )
        else:
            event = EngineEvent("defer-no-time")
        res.message_event = event
        res.message = render_en(event)
        self._journal(event)
        self._progression(fait, total, res.message)

    # -- orchestration ------------------------------------------------------ #

    def run(self) -> RunResult:
        """Run the whole thing under the per-folder OS lock.

        Acquires the lock via
        :func:`Glaneur.engine._folder_lock.folder_lock` and delegates the
        real work to :meth:`_run_locked`. If another process already
        holds the lock — application UI, scheduled task, legacy install
        still running — the method returns a bare
        ``RunResult(busy=True)`` immediately: nothing is written to
        disk, no HTTP session is opened, no source is called.

        Returns:
            The numeric summary of the run, or ``RunResult(busy=True)``
            when the folder is already in use.
        """
        self.o.target_dir.mkdir(parents=True, exist_ok=True)
        try:
            with folder_lock(self.o.target_dir):
                return self._run_locked()
        except FolderBusy:
            return RunResult(busy=True)

    def _run_locked(self) -> RunResult:
        """Execute the run body under the acquired folder lock.

        The order is:

        1. read the manifest and the cache;
        2. inventory via the source (date filter, minimum width);
        3. sort into three lists (already up to date, to download,
           deleted);
        4. resolve gallery titles if needed;
        5. sequential download with periodic manifest save (every 25
           images);
        6. cache update (maximum date, titles) on a normal exit.

        A cooperative interruption returns a ``RunResult`` with
        ``RunResult.interrupted`` set. Network or disk errors are caught
        and reported through ``res.message`` without propagating the
        exception.

        Returns:
            The numeric summary of the run.
        """
        res = RunResult()
        manifeste = self.load_manifest()
        cache = self.load_cache()
        if manifeste:
            self._journal(EngineEvent(
                "already-known", {"count": len(manifeste)}))

        # Cache: only used if the user has not already bounded the period —
        # in that case, their bounds override the cache's memory.
        depuis_cache = None
        if not (self.o.since or self.o.until):
            depuis_cache = cache.get("derniere_date_media")
            if depuis_cache:
                self._journal(EngineEvent(
                    "cache-since-date", {"date": depuis_cache[:19]}))

        try:
            depuis = self.source.convert_from(depuis_cache) or self.o.since
            elements = list(self.source.inventory(depuis, self.o.until))

            if self.o.min_width:
                avant = len(elements)
                elements = [
                    e for e in elements
                    if e.width is None or e.width >= self.o.min_width
                ]
                # An `Element` without a URL (source that did not find the
                # requested resource) can no longer be downloaded: goes to `skipped`.
                ecartees = avant - len(elements)
                if ecartees:
                    self._journal(EngineEvent(
                        "discarded-below-min-width",
                        {"count": ecartees, "min_width": self.o.min_width},
                    ))

            if not elements:
                res.message_event = EngineEvent("nothing-matches")
                res.message = render_en(res.message_event)
                return res

            # names already assigned, so an image does not overwrite another
            pris = {e["fichier"] for e in manifeste.values() if e.get("fichier")}

            # sort: already on disk vs to be processed
            a_faire: list[tuple[Element, Path | None]] = []
            for e in elements:
                etat = manifeste.get(e.ident)
                connu = self.o.target_dir / etat["fichier"] if etat and etat.get("fichier") else None

                if etat and etat.get("supprime"):
                    res.skipped += 1
                    continue
                if e.url is None:
                    # The source did not find any usable resource.
                    res.skipped += 1
                    continue
                if (connu is not None and etat.get("taille") and not connu.exists()
                        and not etat.get("restaure")):
                    # already downloaded then gone: the user erased it
                    etat["supprime"] = datetime.now().isoformat(timespec="seconds")
                    res.deleted += 1
                    continue
                if connu and self.file_complete(connu, etat, e.size) and not self.o.verify:
                    etat.pop("restaure", None)
                    res.already_present += 1
                    continue
                a_faire.append((e, connu))

            self._journal(EngineEvent(
                "known-and-todo",
                {"known": res.already_present, "todo": len(a_faire)},
            ))
            if res.deleted:
                self._journal(EngineEvent(
                    "n-files-erased-locally", {"count": res.deleted}))
            if not a_faire:
                res.message_event = EngineEvent("all-up-to-date")
                res.message = render_en(res.message_event)
                self._progression(1, 1, res.message)
                return res

            titres: dict[str, str] = {}
            titres_caches = {str(k): v
                             for k, v in (cache.get("titres_parents") or {}).items()}
            inconnus = {e.group for e, connu in a_faire
                        if e.group and connu is None}
            if (self.o.sort_mode == "galerie"
                    and "galerie" in self.source.sort_modes
                    and inconnus):
                self._progression(
                    0, len(a_faire),
                    render_en(EngineEvent("identifying-galleries")),
                )
                titres = self.source.resolve_groups(
                    inconnus, connus=titres_caches)

            echecs_consecutifs = 0
            for i, (e, connu) in enumerate(a_faire, 1):
                self._check_stop()
                url = e.url
                etat = manifeste.get(e.ident)
                if connu is not None:
                    file_path = connu
                else:
                    sous = self.folder_for(e, titres)
                    # clean("") would return "divers" and create a phantom directory
                    dossier = (self.o.target_dir / clean(sous)) if sous else self.o.target_dir
                    nom = e.filename or Path(urlparse(url).path).name
                    file_path = self.free_path(dossier / nom, e.ident, pris)

                statut, infos, classification, error_text = self.download(
                    url, file_path, etat)

                if infos:
                    infos["fichier"] = str(file_path.relative_to(self.o.target_dir))
                    # Source metadata (credit, checksum...): copied into the
                    # manifest for the upcoming catalog export, without the
                    # engine interpreting them.
                    if e.extra:
                        infos.setdefault("extra", {}).update(e.extra)
                    manifeste[e.ident] = infos
                if statut == "ok":
                    res.downloaded += 1
                    res.bytes += infos["taille"]
                    echecs_consecutifs = 0
                elif statut == "repris":
                    res.resumed += 1
                    res.bytes += infos["taille"]
                    echecs_consecutifs = 0
                elif statut == "inchangé":
                    res.unchanged += 1
                    echecs_consecutifs = 0
                else:
                    res.failures += 1
                    if statut == "introuvable":
                        self._journal(EngineEvent(
                            "file-not-found", {"filename": file_path.name}))
                    else:
                        self._journal(EngineEvent(
                            "file-failed",
                            {"filename": file_path.name,
                             "error": error_text or ""},
                        ))

                    categorie = classification.category if classification else "transitoire"
                    if categorie == "coupure":
                        self._trigger_defer(res, classification, i, len(a_faire))
                        break
                    if categorie == "transitoire":
                        echecs_consecutifs += 1
                        if echecs_consecutifs >= 5:
                            self._trigger_defer(res, None, i, len(a_faire))
                            break
                    else:  # "definitif" — a single 404/URL error stays local
                        echecs_consecutifs = 0

                self._progression(i, len(a_faire), f"{file_path.parent.name}/{file_path.name}")
                if i % 25 == 0:
                    self.save_manifest(manifeste)

            if not res.deferred:
                res.message_event = EngineEvent(
                    "n-new-images",
                    {"count": res.downloaded, "size": format_bytes(res.bytes)},
                )
                res.message = render_en(res.message_event)

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
                self.save_cache(cache)

        except Interrupted:
            res.interrupted = True
            res.message_event = EngineEvent("interrupted")
            res.message = render_en(res.message_event)
        except RuntimeError as e:
            res.message = str(e)
            self._journal(EngineEvent("runtime-error", {"error": str(e)}))
        except OSError as e:
            res.message_event = EngineEvent("write-problem", {"error": str(e)})
            res.message = render_en(res.message_event)
            self._journal(res.message_event)
        finally:
            self.save_manifest(manifeste)

        return res
