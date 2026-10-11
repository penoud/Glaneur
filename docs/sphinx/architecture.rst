Architecture overview
=====================

What Glaneur does
-----------------

Glaneur is a desktop image synchroniser. It walks the media catalogue of
a remote site (today a WordPress REST endpoint or a Djangoplicity gallery
such as ESO, ESA/Hubble or ESA/Webb), filters it against user settings
(minimum width, date window, sort mode), downloads what is missing, and
keeps a per-folder manifest so a second run only fetches what has
changed. It is distributed both as a PySide6 desktop application and as
a command-line tool backed by the same core.

Package layout
--------------

The code is a plain ``Glaneur`` Python package plus two thin entry
points at the repository root:

``Glaneur/engine/``
    Core orchestration. Pulls elements from an adapter, decides what to
    download, writes files, maintains the on-disk manifest and the API
    cache. Has no Qt dependency and no knowledge of specific sites.
``Glaneur/sources/``
    Site adapters. Each adapter turns a specific API (WordPress REST,
    Djangoplicity ``/images/`` listing with its ``Next`` pagination)
    into the same ``Element`` stream the engine consumes.
``Glaneur/config.py``
    Persistent configuration (profiles, defaults, scheduler state). JSON
    on disk, versioned schema with one-way v1 → v2 migration.
``Glaneur/scheduler.py``
    Due-date logic for automatic runs, per profile. Pure computation; no
    thread, no widget. ``Glaneur/scheduler_labels.py`` holds the
    localised label built from this state.
``Glaneur/updater/``
    Self-update: polls the GitHub release feed, parses it into typed
    values, downloads the installer and verifies it. Separate from the
    engine on purpose — a stuck update must never block a sync.
``Glaneur/bug_report.py``, ``i18n.py``, ``logsetup.py``, ``system.py``
    Supporting plumbing: diagnostics bundle, Qt translation glue, file
    logging, OS-specific helpers.
``app.py``
    PySide6 desktop UI: main window, preferences dialog, profile table,
    tray integration.
``cli.py``
    Command-line entry point. Builds ``Options`` from flags and drives
    the engine directly.

Layered view
------------

Three layers, each one depending only on those below it::

    ┌──────────────────────────────────────────────────────┐
    │  UI layer           app.py / cli.py                  │
    │                     scheduler_labels.py              │
    ├──────────────────────────────────────────────────────┤
    │  Orchestration      engine/        scheduler.py      │
    │  layer              updater/       config.py         │
    ├──────────────────────────────────────────────────────┤
    │  Transport & I/O    sources/base.py (Transport)      │
    │                     sources/wordpress.py             │
    │                     sources/djangoplicity.py         │
    └──────────────────────────────────────────────────────┘

The orchestration layer stays Qt-free. The only touch point is
``EngineEvent``, a value object the engine emits for every user-facing
message. The UI layer translates events through
``QCoreApplication.translate``; the CLI and the file log render them
via ``render_en``. This split means the engine can be driven and tested
without a display.

Core abstractions
-----------------

``Element``
    A single image described in a form the engine understands:
    identifier, URL, filename, publication date, pixel width, size,
    optional group (gallery/collection), and a free-form ``extra`` dict
    the engine copies verbatim into the manifest (credit, checksum, …).
``Source``
    Abstract adapter. Each subclass declares its ``type`` string, the
    sort modes it supports, and a streaming ``inventory`` that yields
    ``Element`` values in chronological order when possible.
``Transport``
    Shared HTTP plumbing: one ``requests.Session``, one minimum delay
    between calls, one cooperative stop event. Sources never create
    their own session, so the delay floor and the stop button apply
    everywhere without an adapter being able to forget.
``Options``
    Dataclass describing one run (target directory, origin, sort mode,
    width floor, date window, verify flag, force flag, cache flag,
    source type). Built by the UI or the CLI, passed to the engine.
``Engine``
    Orchestrator. Takes an ``Options``, instantiates the adapter for
    its ``source_type``, iterates the inventory, decides for each
    element whether to download / resume / skip / mark deleted, writes
    the manifest periodically, and returns a ``RunResult``.
``RunResult``
    Counters (downloaded, resumed, unchanged, already present, skipped,
    failures, bytes) plus flags (``interrupted``, ``deferred``,
    ``retry_after``) and the summary ``EngineEvent``. The scheduler
    reads ``deferred`` and ``retry_after`` to decide when the next
    automatic run may fire.

A typical run flow
------------------

1. ``cli.py`` or ``app.py`` builds an ``Options`` from the active
   ``Profile``.
2. ``Engine`` resolves ``source_type`` through ``Glaneur.sources.SOURCES``,
   falling back to WordPress for an unknown value (defensive: a corrupt
   config must never crash).
3. The engine loads the manifest (``.etat.json``) and the API cache
   (``.cache.json``) from the target directory, unless ``force=True``.
4. It calls ``source.inventory(depuis, jusqua)``. ``depuis`` comes from
   the API cache (``derniere_date_media``) so later runs only pull what
   is new; a well-behaved source honours it.
5. For each ``Element`` the engine runs the width filter, resolves
   groups when the sort mode is ``gallery``, computes the destination
   path, and compares the on-disk state with the manifest and the
   element metadata.
6. ``Engine.download`` performs the actual GET with conditional headers
   (``If-None-Match``, ``If-Modified-Since``, ``Range`` for resumes).
   The result is classified by ``classify_error`` into ``transient``,
   ``cut`` or ``definitive``.
7. A single ``cut`` error, or five consecutive ``transient`` errors,
   defers the run: the engine stops the loop, writes the manifest
   collected so far, and sets ``RunResult.deferred = True``. The
   scheduler reads this flag and applies the exponential backoff from
   ``Glaneur.scheduler.BACKOFFS_S``.

Persistence
-----------

Three files live in the target directory. The engine controls all of
them, nothing else writes there:

``.etat.json``
    The manifest — one entry per known element, keyed by ``ident``.
    Carries ``filename``, ``size``, ``etag``, ``modified``, the optional
    ``deleted`` timestamp, the ``restored`` flag and the untouched
    ``extra`` map. Written atomically; a legacy FR-key file is
    translated on read and migrated on next save.
``.cache.json``
    API cache. Holds ``derniere_date_media`` (most recent element seen),
    gallery titles for the ``gallery`` sort mode, and the fingerprint
    the next run will test against. Deleting it only costs one slower
    run; the manifest is the authoritative on-disk state.
``.lock``
    Per-folder OS lock. Prevents two Glaneur processes from racing on
    the same directory. See ``Glaneur/engine/_folder_lock.py``.

The application configuration itself lives outside the download tree,
at ``%APPDATA%\Glaneur\config.json`` on Windows and
``~/.config/glaneur/`` elsewhere. See ``Glaneur/config.py`` for the v1
→ v2 migration contract.

Multi-profile model
-------------------

A ``Config`` holds a ``defaults`` block and a list of ``Profile``
entries. Each profile is a complete run target (site, target directory,
source type, filters, scheduler interval) but any per-profile field
left as ``None`` inherits from the ``defaults`` block — the value is
**never** copied into the profile. This is the "None-inheritance"
invariant: changing a default retroactively updates every profile that
did not override it. See ``Profile.effective_min_width`` and
``Profile.effective_verify_integrity``.

Error handling
--------------

Three categories, chosen deliberately:

``transient``
    Timeout, isolated 5xx, generic connection error. Retried in place
    up to three times with a 2 s / 4 s backoff (or the server's
    ``Retry-After`` if present, capped at two minutes).
``cut``
    429, 502, 503, 504, or a ``ConnectionError`` whose text matches a
    DNS-blackhole fingerprint. The engine defers the whole run — one
    ``cut`` is enough — and the scheduler applies an exponential
    backoff before retrying.
``definitive``
    400, 401, 403, 404 (outside the source's own ``fin_si`` set), 405,
    410, malformed URL. Raised to the caller without retry. Retrying
    would only add noise.

See ``ErrorClassification`` and ``classify_error`` in
``Glaneur/sources/base.py``.

Where to look next
------------------

* ``Glaneur/engine/`` — engine entry points and public dataclasses.
* ``Glaneur/sources/`` — adapter contract and the two shipped adapters.
* ``Glaneur/config.py`` — persistent configuration and the profile
  model.
* ``Glaneur/scheduler.py`` — due-date logic and defer backoff.
* ``Glaneur/updater/`` — self-update machinery.
* ``CLAUDE.md`` in the repository root — invariants and conventions
  the code must respect across changes.
