# Glaneur — roadmap

> To be placed in `docs/feuille-de-route.md`. Replaces the document
> "Propositions d'amélioration — WpImageDownloader". Narrative documents are
> written in English, like the code, comments, docstrings and logs (lot 2).

Each lot ships on its own, passes the tests, and does not change `__version__`
without an explicit decision. Order matters: each lot is the safety net for the
next one.

**Legend.** *Verified*: read in the code or observed. *Assumed*: to be
confirmed, usually by a real-server test (lot 1.3).

---

## Lot 0 — Immediate fixes

Small independent fixes, found while reading the code.

| # | Fix | Rationale |
|---|---|---|
| 0.1 | Read `Checksum` at the level where the feed actually puts it | The code reads `ressource["Checksum"]`, the fixture puts it on the entry. One of them is wrong (*verified*). The right level will be settled by the real test of lot 1.3. |
| 0.2 | Stop with an error if `Next` changes host or scheme relative to the base | Required by `evolution-multi-sources.md` §8, missing from the code (*verified*). Following `Next` as is remains the rule, but not towards another site. |
| 0.3 | Format fallback: never to `Original`, and every fallback is logged | Today, asking for `Small` can yield `Large` silently (*verified*). A fallback must be visible. |
| 0.4 | `Element.url: str \| None` | Djangoplicity already returns `None` (*verified*). |
| 0.5 | Djangoplicity tests plugged under the `Transport`, not in place of `get_json` | By patching `get_json`, the tests check neither the 0.2 s floor, nor the retries, nor the stop. |
| 0.6 | Clean up leftovers of the old name (README "Tkinter" and "Application Windows", `hdiutil -volname "WP Image Downloader"`), set `GITHUB_REPOSITORY` to the new repository name | Repository renamed. The GitHub redirect is a safety net, not a configuration. |
| 0.7 | Uninstall the old application by hand, then remove `migrer_depuis_ancien_nom` and its tests | There is no other user: the transition code has no reason to exist after your own migration. As long as both are installed, they sync the same folder (see lot 4). |
| 0.8 | Choices of `--type`, `--format` and `--classement` in `cli.py` derived from `SOURCE_TYPES`, `DJANGOPLICITY_FORMATS` and `SORT_MODES` | Hard-coded today (*verified*), against boundary 3. With profiles and filters, these lists would drift apart. |
| 0.9 | Contract test "lower `min_width`, then run again" | *Assumed*: the `after` delta does not re-read old images that were previously excluded. The test pins the current behaviour; the fix comes with filters (lot 11.2). |

---

## Lot 1 — Safety net: tests, coverage, tooling

To be done before lots 2 and 5, which touch all the code.

### 1.1 Branch coverage, with a ratchet

- Add `pytest-cov` as a development dependency and measure **branch**
  coverage, not only line coverage.
- Targets:
  - 100 % on `sources/`, `scheduler.py` and `config.py`, migrations included;
  - at least 95 % on `engine.py`;
  - `app.py` measured but not blocking.
- `fail_under` starts at the measured value and can only go up: every PR that
  raises it updates the threshold.

**Rationale.** "Maximum coverage" taken literally leads to testing accessors
and excluding code to inflate the number. The project's bugs are rare network
branches: that is where branch coverage pays off. The ratchet prevents
regression without imposing an arbitrary number on day one.

### 1.2 Local HTTP server

- Pytest fixture starting an `http.server.ThreadingHTTPServer` on
  `127.0.0.1:0`, standard library only, driven by scenario.
- Scenarios:
  - `Range` honoured (206);
  - `Range` ignored (200): the `.part` must restart from zero;
  - 416;
  - connection cut mid-body;
  - lying `Content-Length`;
  - 304 on `If-None-Match`;
  - 429 with `Retry-After`;
  - transient 503 then 200;
  - invalid JSON;
  - slow response (timeout);
  - WordPress pagination with 96 entries for `per_page=100`;
  - absolute `Next`, then missing.
- The **five contract tests** are parametrised over both sources against this
  server, in addition to the existing unit tests.

**Rationale.** A fake session does not see what happens at the socket level.
Yet that is where every real bug happened. This server adds no dependency.

### 1.3 Tests against real servers, as a last resort

- `@pytest.mark.network` marker, excluded by default (`addopts = -m "not
  network"`). Run by hand, or through a separate `workflow_dispatch` workflow
  that never blocks a release.
- Minimal content, respecting the delay between requests:
  - `d2d/?count=1` on ESO and ESA/Hubble: shape of the response, level of
    `Checksum`;
  - one `Range` request on a small resource (`Thumbnail`): 206;
  - one conditional request: 304 (open question 1 of the multi-source doc);
  - download of a `Thumbnail` that has a `Checksum`, compared with SHA-256 then
    MD5: confirms the algorithm (*assumed* SHA-256);
  - WordPress: `/wp-json/` of the club's site, one page of media.
- Each real test documents in its docstring the assumption it checks.

**Rationale.** Fake servers encode our assumptions. A few real tests confront
them with reality without hitting the sites on a regular basis.

### 1.4 Lint and audit

- **ruff** as linter (rules `E`, `F`, `W`, `I`, `B`, `UP`, `D`). No
  `ruff format` at first: mass reformatting would pollute the lot 2 history.
- **pip-audit** on `requirements.txt` in CI.
- **Dependabot** for GitHub actions and `pip`.
- Rejected: **mypy** (few annotations today, high cost for little gain; to be
  reconsidered after lot 2) and **bandit** (mostly false positives on
  `subprocess`, already reviewed by hand).

### 1.5 Sphinx-compatible docstrings

- **Google convention**, read by `sphinx.ext.napoleon`, shipped with Sphinx.
  It stays readable in the code, unlike reST field lists.
- **Format check**: `ruff` `D` rules with
  `[tool.ruff.lint.pydocstyle] convention = "google"`. Every public function,
  class or module is documented.
- **Reference check**: `sphinx-build -W --keep-going -n docs/api
  docs/api/_build` in CI. A broken reference or a malformed docstring fails
  the job.
- **Configuration**: `docs/api/conf.py` with `autodoc`, `napoleon` and
  `viewcode`, and the default theme (alabaster) to avoid a theme dependency.
  Existing Markdown files (`docs/*.md`) stay outside Sphinx: including them
  would require `myst-parser`.
- **Development dependencies**: a `requirements-dev.txt` (`pytest`,
  `pytest-qt`, `pytest-cov`, `ruff`, `sphinx`, `pip-audit`), never bundled by
  PyInstaller.

**Rationale.** The format is checked statically and the rendering by a strict
build. One without the other lets through either missing docstrings or dead
references.

---

## Lot 2 — Code in English, without format changes

- Identifiers, comments, docstrings (lot 1.5 convention), UI log and file log
  messages in English.
- Module by module, one green commit each, tests following in the same commit.
- **UI strings**: English becomes the source language of `tr()`, and French
  moves to `translations/glaneur_fr.ts`. Regenerated with `lupdate`, keeping
  literal contexts, as today.
- **Engine log shown in the UI**: the engine emits structured events (`code` +
  parameters, for example `("catalog_size", {"count": 15741})`), which the UI
  translates. The file log writes them in English.
- **CLI**: English names, old names kept as hidden aliases (argparse accepts
  several names for one option). This is essential for `--reduit`, written in
  the registry and in the startup shortcut.
- **Persisted formats unchanged** in this lot: manifest and cache keys, and
  values (`"galerie"`, `"plat"`). Configuration keys already moved to English
  during the renaming sprint, with legacy keys still read
  (`_LEGACY_FIELD_ALIASES`).

**Rationale.** Renaming must come before profiles (lot 5), which rewrite
`config.py`, the scheduler and the UI. In the reverse order, we would fight
the same conflicts twice. Manifest keys move to English in lot 6, where the
file changes structure anyway. Structured events also come before lot 5.0: the
profile list builds the status of each row from them.

---

## Lot 3 — Network reliability and integrity

### 3.1 Single retry policy

- It lives in `Transport` and also applies to file downloads: `telecharger`
  borrows the policy along with the session.
- Transient errors retried: timeout, connection error, 500, 502, 503, 504 and
  429. **Three attempts** in total, with pauses of 2 s then 4 s.
- `Retry-After` is honoured but capped at 120 s. Beyond that, the item fails
  for this run. Every wait stays interruptible by the stop `Event`.
- 4xx (except 429) are not retried.
- After three failures, the image counts as failed. It is retried **on the
  next run**, never abandoned for good. The manifest keeps `error_count` and
  `last_error` for display only.
- A download retry resumes from the `.part` via `Range`. The 206 invariant
  applies on every attempt.
- No jitter: a single sequential client creates no thundering herd.

### 3.2 Explicit fatal errors

A 404, 401 or 403 response on the API root (`/wp-json/`, `d2d/`) produces a
fatal source error, with a clear message: "API missing or disabled by the site
operator". It is converted into a `Resultat` before leaving the engine.

**Rationale.** This is known weakness no. 1. Today, it would look like an empty
inventory.

### 3.3 Validation before renaming the `.part`

- **Size**: equal to the announced size when there is one.
- **Magic bytes**: JPEG, PNG, GIF, TIFF, WebP, standard library only. An HTML
  error page served with 200 is rejected.
- **Checksum**: if the source provides one and the algorithm is confirmed
  (lot 1.3), the hash is computed **during** the stream. On resume, the
  existing `.part` is hashed first, which is still only one extra disk read.
  On mismatch, the `.part` is deleted and the image counts as failed. The
  checksum is kept in the manifest.
- Rejected:
  - MIME type: CDNs serve TIFFs as `application/octet-stream`;
  - decoding the image: it would require Pillow, or Qt in the engine.

### 3.4 Batched manifest saves

- Every 50 images **or** every 30 s, whichever comes first, plus at the end of
  the run and on interruption.
- The invariant does not change: an interruption writes the manifest, never the
  cache nor `last_run`.
- Load test: saving a 20,000-entry manifest, timed in CI, without a blocking
  threshold, to document the margin.

**Rationale.** Saving after each image becomes quadratic on a first ESO run.
Saving only at the end of the run loses everything on a crash. The timing will
tell whether SQLite ever becomes necessary.

---

## Lot 4 — Lock per target folder

- `.glaneur.lock` file in the target folder, locked by the operating system
  (`msvcrt.locking` on Windows, `fcntl.flock` elsewhere). It contains the PID,
  the host and the time, for diagnostics only.
- Lock held: the run stops cleanly with a "busy" result (exit code 3 in the
  CLI).

**Rationale.** An OS lock is released when the process dies. No stale lock to
detect, unlike a plain PID file. It is essential as soon as two triggers can
coincide: profiles, scheduled task, open application, old installation still
present.

---

## Lot 5 — Profiles

Detailed design: `docs/design/evolution-multi-sources.md` (§3.1 to §3.2).

### 5.0 Prepare the UI without changing the format

- Preferences in "General" / "Site" tabs. The split is driven by
  `PROFILE_FIELDS` in `config.py`, which will also drive the v2 migration. The
  "Filters" and "Images" tabs are created hidden.
- "Site / Folder" banner of the main window replaced by a one-row profile list
  (`QTableView` and its model), fed by the structured events of lot 2.
- System logic of `DialoguePreferences.appliquer()` (run at startup,
  slideshow) moved to `system.py`.
- `config.json` unchanged byte for byte.

**Rationale.** Separate the UI change from the format change: a widget diff
without a migration, then a migration without widgets.

### 5.1 Model

- Configuration v2: `schema_version: 2`, global preferences (`language`, run
  at startup, notifications, `interval_hours`, `schedule_anchor`,
  `slideshow_profile`), inheritable defaults (`defaults`) and a `profiles`
  list.
- Each profile contains:
  - `id`: `uuid4().hex`, stable, key of the scheduler state and of the logs,
    never the name;
  - `name`, `source_type`, `site`, `target_dir`, `image_format`, `sort_mode`;
  - the overrides `min_width`, `verify_integrity`, `filters`, `resize`:
    `None` = inherit from `defaults`, a default is never copied into a
    profile;
  - `last_run`, `retry_after`, `backoff_level`, `full_check_every`,
    `runs_since_full_check`.
- `interval_hours` stays **global**; profile start times are spread across the
  interval (5.2).
- The Windows slideshow follows **a single** profile (`slideshow_profile`, an
  `id`); `validate()` clears an unknown `id`.
- `validate()` per profile, plus two global rules: **unique folders** and
  **non-nested folders**. Resolved paths are compared, case-insensitively on
  Windows.
- **v1 → v2 migration**: one profile built from the single current
  configuration, keys kept (already in English), inheritable fields placed in
  `defaults`, `schedule_anchor` initialised from the time of the current
  `last_run` to keep today's rhythm, a `config.v1.json` copy kept. A v2
  configuration containing an unknown key still loads.

### 5.2 Execution

- `scheduler.py` stays pure: it computes the due time of each profile. Start
  times are spread across the global interval (24 h, three profiles → one start
  every 8 h): grid `anchor + k × I/n + m × I`, due time = first slot
  ≥ `last_run` + I/2, then `retry_after` if a deferral is active. Details and
  edge cases: `design/evolution-multi-sources.md` §3.1.
- **New invariant**: a profile is never restarted automatically less than I/2
  after its last run, even after profiles are added, removed or reordered.
- A single worker runs a queue, **one profile at a time**.
- An interruption does not write `last_run` for the interrupted profile, and
  does not touch the others.
- Manifest and cache do not change: they are already per folder, and one
  profile equals one folder.

**Rationale.** Parallel runs on different hosts bring nothing to a background
tool. They do, however, complicate progress, stopping and locking. The "one
source per folder" rule, kept from the start, makes profiles cheap on the
engine side.

### 5.3 UI and CLI

- Profile list, and an edit dialog that reuses the current form.
- Notification-area menu: "Sync ▸ each profile / all".
- Notifications prefixed with the profile name.
- CLI: `--profile <name|id>`, `--all`, `--due`, `--list-profiles`. Without
  `--profile`, all profiles run, in queue order.

---

## Lot 6 — Periodic full check

- Every `full_check_every` runs (10 by default, 0 for "never", with the labels
  in `config.py`), the inventory is done without `after`.
- A manifest item missing from a full inventory is marked
  `remote_missing_since`. **The local file is never deleted.** If it
  reappears, the mark is removed.
- **New invariant**: the mark is only set after a full inventory, not
  interrupted, ended on the server's end signal. Otherwise a truncated
  inventory would wrongly mark half the catalogue.
- Manifest v2: `schema_version`, English keys, and the new fields
  (`checksum`, `credit`, `rights`, `error_count`, `last_error`,
  `remote_missing_since`, and for the filters of lot 11.2: `width`, `height`,
  `status` with the value `filtered`). A single migration, written against the
  current format, to be reviewed first.
- `remote_missing_since` only applies to entries that meet the current filter:
  an image excluded by a filter is not missing from the server.

**Rationale.** The date delta sees neither server-side deletions nor
replacements. The cost stays low: about 160 requests for ESO.

---

## Lot 7 — Automatic site type detection

- "Detect" button in the profile editor. The logic lives in
  `sources/detect.py`, on the engine side, and goes through a `Transport`
  (delay floor included). The UI runs it in a `QThread`.
- Steps:
  1. Normalise the URL: `https` scheme by default, strip a `/wp-json…` or
     `/images/d2d…` pasted by the user.
  2. WordPress, in this order:
     - `Link: <…>; rel="https://api.w.org/"` header of the home page, which
       gives the real API root, including for a site installed in a
       sub-folder (this is a header, not HTML parsing);
     - then `GET <base>/wp-json/`, which must return `namespaces` containing
       `wp/v2`;
     - then `?rest_route=/` for sites without permalinks (*assumed*, to be
       checked on a real site).
  3. Djangoplicity: `GET <base>/images/d2d/?count=1`, then
     `<base>/public/images/d2d/?count=1` (the ESO case). The JSON must contain
     `Collections`.
- Result: the type, the canonical base and, for Djangoplicity, `Count`. The
  latter feeds the volume estimate (lot 10). At most five requests.
- Failure: "no recognised API" message. The HTML fallback is never offered
  automatically.
- Detection never runs on every launch: the decision of
  `evolution-multi-sources.md` §5 stands.

---

## Lot 8 — Silent mode and Windows scheduled task

- `cli.py --silent --due --report result.json`:
  - no output except errors;
  - JSON report: duration, counters, bytes transferred, failures with their
    cause;
  - exit codes: 0 success, 1 partial failures, 2 fatal error, 3 lock busy,
    130 interruption.
- **A single** hourly `schtasks` task that runs `--due`, created and removed
  from the UI.

**Rationale.** One task per profile would duplicate the due-time logic in the
Windows Task Scheduler. With a single task, `scheduler.py` stays the only
judge, and the lock handles coincidence with the open application.

---

## Lot 9 — Windows code signing (start early, in parallel)

**Current dead end.** The workflow reads a `.pfx` from a secret. But since
June 2023, the key of a code-signing certificate must stay in a hardware
module: a new certificate can no longer be exported as `.pfx`.

| Option | Cost | Automatable | Publisher shown | Available |
|---|---|---|---|---|
| SignPath Foundation | free | yes, with manual approval of each release | SignPath Foundation | yes (GPL project, published, maintained) |
| Azure Artifact Signing | about $10/month | yes | you | **no** for individuals outside the US/Canada; yes through a Swiss organisation |
| Commercial OV certificate in a cloud HSM | a few hundred francs per year | yes | you | yes |

**Recommendation: SignPath Foundation.**

- Prepare a "Code signing policy" page in the repository and a download page
  describing the application, then submit the application. The review delay is
  the reason to start early.
- New release flow:
  1. the tag triggers the build;
  2. the signing request is sent;
  3. you approve;
  4. the release is published.

  "Push to `main` = release" becomes "push to `main` = release candidate".
- Then the updater checks the **Authenticode signature and the signer
  subject** of the installer before launching it (WinVerifyTrust through
  ctypes, no dependency). Authenticity is what is missing today: the `.sha256`
  comes from the same release, it only proves integrity.
- SmartScreen: reputation builds up with downloads; signing does not remove the
  warning immediately.

---

## Lot 10 — Sync UI

- Overall progress, current file, **throughput** (new bytes callback next to
  `progression`), failures of the run with their cause.
- **Volume estimate on the first run**: sum of the announced sizes, shown
  before downloading, with confirmation above a threshold. Essential with the
  `Original` format.

---

## Lot 11 — Features (backlog, order kept)

1. Built-in browsing gallery (`QListView` on `QFileSystemModel`).
2. Filters: minimum dimensions, orientation, maximum size, dates (finally in
   the UI), category (WordPress taxonomies, `Subject.Category` for
   Djangoplicity — a filter, not a sort mode). This is when a general notion of
   "source capabilities" becomes justified. Details:
   `design/evolution-multi-sources.md` §3.3.
   - An image is kept if it meets the filter. If the source does not provide
     the information, the engine reads it from the file header (64 KiB at
     most, through the `Transport`), next to the magic bytes of lot 3.3;
     measured dimensions go to manifest v2.
   - The cache fingerprint includes the filter fingerprint: changing a filter
     forces a full inventory on the next run.
   - Changing a filter touches no existing file.
3. CSV or HTML catalogue export from manifest v2, with credits. Images marked
   `remote_missing_since` are included.
4. Duplicates by SHA-256, only if the case really occurs on the club's site.
5. Resizing through server variants, set by the **longest edge** (global
   default, overridable per profile; presets in `config.py`). Djangoplicity:
   `max_edge` picks the variant when enabled, the format is then greyed out,
   `Original` is never picked. WordPress: `media_details.sizes`, after a
   `server-prober` check on the club's site. Changing the setting replaces no
   existing file. Local resizing deferred: it would require a dependency and
   separate remote and local state in the manifest. Details:
   `design/evolution-multi-sources.md` §3.4.
6. "Reapply to folder": replaces existing files with the variant of the current
   setting, after a warning (irreversible operation, quality changes) and a
   volume estimate (lot 10). Per image: new version validated, then manifest
   saved, then old one deleted. Can be stopped between two images, resumes
   when run again. Requires lot 4; CLI `--reapply`, with `--yes` in silent
   mode.

---

## Rejected proposals

| Proposal | Reason |
|---|---|
| Six services in the engine | The useful split (engine/sources) is done. Six files multiply the places where an invariant gets lost. |
| SQLite and `ManifestRepository` | JSON is enough at this scale. To be revisited if the lot 3.4 timing exceeds one second. |
| Persisted state machine | Transient states have no business on disk. The lot 6 fields are enough. |
| Extended exception hierarchy | Against the `Resultat` convention. Only fatal source and configuration errors are typed (lot 3.2). |
| `get_image_metadata`, `build_download_url` | `inventaire` already provides the URL. |
| Generic source capabilities | `classements` is enough until category filtering. |
| Naming templates | The three sort modes are enough (arbitration 12). |
| Filter mini-language | Fixed fields cover the need. |
| mypy, bandit | See lot 1.4. |
| Perceptual hashing | New dependency for a hypothetical need. |
| Updater rollback | Inno Setup does not support it cleanly. Signing (lot 9) addresses the real risk. |
| Jitter | Single sequential client. |

## On hold

macOS and Linux: jobs kept commented out, no packaging effort. The code stays
cross-platform (lock, paths, XDG configuration) so as not to close the door.
