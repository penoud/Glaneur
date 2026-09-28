# Multi-source evolution — stage 2: profiles, filters, resizing

> **Status (2026-09-28, revision 2).** Replaces the 2026-09-24 version (initial
> Djangoplicity study, kept in the git history). Incorporates the decisions of
> 2026-09-28 (§6) and follows `docs/feuille-de-route.md`: steps are now filed
> under its lots. Nothing is implemented here.

---

## 0. Summary

- The `Source` / `Transport` / `Element` contract and both adapters are
  shipped. What is still single-site: **configuration, UI and scheduler** —
  lot 5 of the roadmap.
- The UI is prepared **before** the configuration format changes (new sub-lot
  5.0), but **after** lot 2, which rewrites every `tr()` string and introduces
  the structured events the profile list needs.
- **Global interval**, profiles **started at staggered times** so the PC is not
  loaded in one block. **A single profile** feeds the Windows slideshow.
- **Filters**: an image is kept if it meets the filter; if the source does not
  provide the information, it is read from the file header. Changing a filter
  touches no existing file, but forces a full inventory.
- **Resizing** through server-provided variants only for now, set by the
  **longest edge**. An explicit "Reapply to folder" action replaces existing
  files, after a warning: irreversible, image quality changes.

---

## 1. Review: the initial study against the current code

**Read** = observed in the code or tests; **assumed** = not confirmed.

| Planned by the initial study | Status | Evidence |
|---|---|---|
| `sources/base.py`: `Element`, `Source`, `Transport` | Done. Methods in English (`inventory`, `resolve_groups`, `sort_modes`); `Element` fields still in French (known gap) | read |
| WordPress and Djangoplicity adapters | Done. `fin_si={400}` on the WordPress side; `ident = "<ID>:<format>"`, filename taken from the URL, `Credit`/`Rights`/`Checksum` in `extra`, `b'…'` texts cleaned on the Djangoplicity side | read |
| Static `SOURCES` registry, `sort_modes_for` | Done | read |
| `source_type`, `image_format`, validation, sort-mode fallback | Done; JSON keys already in English, legacy keys still read | read: `_LEGACY_FIELD_ALIASES` |
| UI: type, URL, conditional format, greyed-out sort modes | Done | read: `DialoguePreferences` |
| CLI `--type`, `--format` | Done, but choices hard-coded | read |
| Credit in the manifest | Done (`extra` copied as is) | read |
| "Detect" button | Missing → lot 7 | assumed |
| Q2 several sources | Settled: queued profiles → lot 5 | roadmap |
| Q3 default format | Settled: `Large`, fallback to `Small`, never `Original`; no usable resource: skipped | read; logging the fallback → lot 0.3 |
| Q4 subset of the catalogue | Becomes filters (§3.3) | — |
| Q5 grouping by category | Filter first (decision 7) | — |
| Q6 other sources | Yes, later (decision 13) | — |

### 1.1 State of the lots, as seen from this document

Without a full review, only what affects what follows:

| Lot | Observation | Evidence |
|---|---|---|
| 1 | Coverage floors in place (`tools/check_coverage.py`) | read |
| 2 | Identifiers and configuration keys in English; **`tr()` source strings still French, engine still translated through `QCoreApplication`** | read: known gaps in CLAUDE.md |
| 3 | Scheduler deferral and backoff present; `Transport.get_json` still retries 4xx and ignores `Retry-After` | read from an excerpt |
| 4 | Not done: `_locks.py` is an in-process `threading.Lock` | read |
| 0.2 | Host check on `Next`: missing according to the roadmap, not reviewed here | — |

### 1.2 Gaps between the roadmap and the code (fixed in the roadmap)

- **Lot 5.1 named the fields `folder` and `layout`**, and planned to switch the
  keys to English during the v2 migration. That is already done, under other
  names (`target_dir`, `sort_mode`). v2 keeps those names: a second rename
  would cost one more alias table for nothing.
- **Lot 5.1 put `interval_hours` in each profile.** Decision 1: it stays global
  (§3.1).
- **Lot 2 said "persisted formats unchanged"** whereas configuration keys
  changed during the renaming sprint. No consequence, but the sentence was
  wrong.

---

## 2. Small fixes revealed by the review (→ lot 0)

- **0.8** `cli.py`: choices for `--type`, `--format`, `--classement` derived
  from `SOURCE_TYPES`, `DJANGOPLICITY_FORMATS`, `SORT_MODES`. Boundary 3.
  *Read.*
- **0.9** Contract test "lower `min_width`, then run again". *Assumed*: the
  `after` delta does not re-read old images that were previously excluded. The
  test pins the current behaviour; the fix comes with filters (§3.3).

---

## 3. Target

### 3.1 Settings: application, defaults, profile

| Level | Content |
|---|---|
| Application | language, notification area, updates, run at startup, `request_delay` (0.2 s floor), **`interval_hours`**, **`schedule_anchor`** (`"HH:MM"`), **`slideshow_profile`** |
| Defaults | inherited values: minimum width, integrity check, filters, resizing |
| Profile | type, URL, format, folder, sort mode; overrides of the defaults (`None` = inherit); scheduler state |

Rule: **a profile field set to `None` inherits the default**, resolved by a
pure function in `config.py`. A default is never copied into a profile.

**Staggered runs (decisions 1, 3 and 14).** The interval is shared, and
profile start times are **spread across the interval**: with 24 h and three
profiles, one start every 8 h. Lot 5.2 already guarantees "one profile at a
time"; spreading additionally keeps the PC from being busy in one block.

Computation, entirely in `scheduler.py` (pure, no internal clock: the current
time is a parameter):

- `n` = number of scheduled profiles, `k` = rank of the profile in the list
  (0 to n-1), `I` = interval;
- each profile has a **grid** of slots:
  `anchor + k × I / n + m × I`, for every integer `m`;
- the **anchor** is a time of day, in naive local time like `retry_after`. It
  is recorded at the v2 migration from the time of the current `last_run`,
  which keeps today's rhythm for the first profile;
- due time of a profile = first slot of its grid **≥ `last_run` + I/2**, then
  `max(slot, retry_after)` when a deferral is active (lot 3). The I/2 margin is
  what makes the computation robust:
  - a run made on time lands on the next slot, exactly +I;
  - a late catch-up run (PC was off) realigns with the grid within 0.5 to 1.5
    intervals, without a double run;
  - adding, removing or reordering profiles changes the phases, without ever
    restarting a profile less than I/2 after its last run;
- empty `last_run` (new profile): due at the first slot of its grid, or
  immediately if the user starts the profile by hand;
- interval 0 (manual only): no grid.

Accepted edge case: if the PC was off for several slots, overdue profiles run
at startup **one after the other** in the queue, never at the same time. The
spread then restores itself thanks to the I/2 rule.

The CLI without `--profile` runs all profiles; with `--due` (lot 8), only those
whose slot has come. The hourly scheduled task of lot 8 is enough: with a
one-hour step, a slot is honoured at most one hour late.

**Slideshow (decision 2).** `slideshow_profile` holds the `id` of one profile.
Deleting that profile clears the setting; `validate()` does the same for an
unknown `id`.

### 3.2 Profile

```python
@dataclass
class Profile:
    """One sync job: a site, a source type, a target directory."""

    #: Stable ``uuid4().hex``; key of scheduler state, never the name.
    id: str
    name: str
    source_type: str = "wordpress"
    site: str = ""
    target_dir: str = ""
    sort_mode: str = "galerie"
    image_format: str = "Large"
    #: Overrides; ``None`` inherits from ``Config.defaults``.
    min_width: int | None = None
    verify_integrity: bool | None = None
    filters: FilterSpec | None = None
    resize: ResizeSpec | None = None
    #: Scheduler state, per profile (lot 5.1, lot 6).
    last_run: str = ""
    retry_after: str = ""
    backoff_level: int = 0
    full_check_every: int = 10
    runs_since_full_check: int = 0
```

Manifest and cache stay per folder; folders are unique and not nested
(lot 5.1).

### 3.3 Filters

Fixed fields, no mini-language (consistent with the rejected proposals):

```python
@dataclass(frozen=True)
class FilterSpec:
    """Selection criteria applied by the engine to each Element."""

    min_width: int | None = None
    min_height: int | None = None
    orientation: str | None = None     # "landscape" | "portrait" | "square"
    max_bytes: int | None = None
    since: str | None = None           # YYYY-MM-DD
    until: str | None = None
    categories: frozenset[str] = frozenset()

    def fingerprint(self) -> str:
        """Stable digest of every non-default criterion."""
```

- Pure module `Glaneur/filters.py`, 100 % branch coverage.
- `Element` gains the height (`media_details.height`, `Dimensions[1]`) and, for
  Djangoplicity, `Subject.Category` in `extra`. Renaming `Element` fields to
  English comes first: adding `hauteur` would widen the gap.
- Category is **a filter, not a sort mode** (decision 7). It arrives with
  lot 11.2, where the roadmap justifies source capabilities.

**Missing information: reading the header (decision 5).** If the source does
not give the dimensions, the engine reads them from the file:

1. request the beginning of the file (`Range: bytes=0-65535`); if the server
   answers 200, read the first 64 KiB of the stream and close. Same request,
   same delay floor, same retry policy (lot 3.1);
2. read the dimensions with the standard library, in the magic-bytes module of
   lot 3.3: PNG (`IHDR`), GIF, JPEG (`SOFn` segments), WebP;
3. if the header is not enough (TIFF with its IFD at the end of the file, JPEG
   with a large EXIF block): full download, measurement, and the file is
   removed if it does not meet the filter;
4. measured dimensions are **stored in the manifest**, with the `filtered`
   status when the image is excluded: a later filter change is re-evaluated
   without any new request.

Rare in practice: WordPress gives `media_details.width/height` and
Djangoplicity gives `Dimensions` almost always (*assumed* for WordPress on
non-image files, read for Djangoplicity). The manifest fields (`width`,
`height`, `status`) go into the **single manifest v2 migration of lot 6**, not
into an extra migration.

Rules:

1. The cache fingerprint includes `filters.fingerprint()`: any filter change
   forces a full inventory on the next run, then the delta resumes.
2. **Changing a filter touches no existing file** (decision 6), whether it
   tightens or loosens.
3. An image excluded by a filter is never marked `remote_missing_since`. That
   mark only applies to entries that meet the current filter.

### 3.4 Resizing

```python
@dataclass(frozen=True)
class ResizeSpec:
    """Target size for stored images, by longest edge."""

    enabled: bool = False
    #: Longest edge in pixels (decision 9).
    max_edge: int = 0
```

Presets in `config.py`, single source of the labels, expressed as the longest
edge: for example 1920, 2560, 3840 px. The label names the use ("HD screen",
"4K"), the value stays a longest edge so that portraits are handled like
landscapes.

**Server variants only.** The source picks the smallest variant whose longest
edge covers `max_edge`. No local computation, no dependency, and lot 3.3
validation stays exact since the stored file is the server's. Local resizing
is **deferred** (decision 12): it will be discussed again after this lot, based
on what the sites expose.

- **Djangoplicity (decision 11).** Resizing enabled: `max_edge` picks the
  variant and the UI greys out the format. Disabled: `image_format` as today.
  `max_edge` never picks `Original`.
- **WordPress.** Variants from `media_details.sizes`. *Assumed*, to be
  confirmed by `server-prober` on the club's site: presence of `sizes`,
  `filesize` per variant, cropped variants (to exclude: aspect ratio differs
  from the original), `source_url` already `-scaled` to 2560 px with
  `original_image` (WordPress ≥ 5.3).
- **Identifier.** WordPress keeps `str(id)` for the original, and uses
  `f"{id}:{size}"` for a variant. Djangoplicity already includes the format.
- **Changing the setting replaces nothing automatically** (decision 8): new
  images follow the setting, existing ones stay.

**Reapply to folder (decision 10).** Explicit action that replaces existing
files with the variant of the current setting.

- Before starting: warning dialog. The operation **cannot be undone** once
  started (replaced files are not kept) and **image quality changes**. The
  dialog shows the estimate: volume to download, space freed (announced sizes;
  same mechanism as the lot 10 estimate). Default button: Cancel.
- Per image: the new variant is downloaded to `.part`, validated (lot 3.3),
  renamed; **then** the manifest is updated and saved; **then** the old file is
  deleted. An interruption between the last two steps leaves a logged orphan
  file, never an entry pointing to nothing.
- "Cannot be undone" applies to the result, not to the run: the Stop button
  interrupts between two images, and running again resumes where it stopped
  (entries already at the right variant are skipped).
- Requires the lot 4 lock. CLI: `--reapply`, which requires `--yes` in silent
  mode.
- Images smaller than `max_edge` and images without a suitable variant are left
  untouched.

---

## 4. Steps, filed under the roadmap

| Step | Lot | Content | Validation |
|---|---|---|---|
| E0 | 0.8, 0.9 | §2 | `local` |
| — | 2 | End of the lot: `tr()` strings in English, **structured events** from the engine | `full` |
| — | 4 | Lock | `subsystem` |
| E1 | **5.0** (new) | Preferences in tabs | `module` |
| E2 | **5.0** | Banner → profile list | `module` |
| E3 | 5.1–5.3 | Profile model, v2 migration, start times spread across the interval | `full` |
| E4 | 5.1 | `None` inheritance | `module` |
| E5 | 11.2 widened | Filters | `subsystem` |
| E6 | **11.5** (new) | Resizing through server variants | source + contract |
| E7 | **11.6** (new) | Reapply to folder | `full` |

### 5.0 — Prepare the UI without changing the format

**E1 — Preferences in tabs.**

- `config.py`: `PROFILE_FIELDS`, single source of the application / profile
  split. The "Site" tab depends on it today, the v2 migration tomorrow.

  ```python
  #: Fields that belong to a sync profile rather than to the application.
  #: Drives the "Site" tab today and the v1 → v2 migration later.
  PROFILE_FIELDS: tuple[str, ...] = (
      "source_type", "site", "image_format", "target_dir",
      "sort_mode", "min_width", "verify_integrity",
  )
  ```
- `app.py`: `QTabWidget` "General" / "Site". The "Filters" and "Images" tabs are
  created hidden.
- System logic of `appliquer` (run at startup, slideshow) moved to
  `systeme.py` / `system.py`.
- Test: `config.json` unchanged byte for byte after OK without edits.

**E2 — One-row profile list.** The "Site / Folder" banner becomes a
`QTableView` with its model: name, type, site, folder, last run, status. The
status is built from the structured events of lot 2, hence the order. "Update
now" acts on the selection. With a single row, the user sees no difference.

### E3 to E7

- **E3** follows lot 5 as is, with the corrections of §1.2.
- **E5**: `filters.py`, height in `Element`, header reading (after lot 3.3 and
  the manifest v2 of lot 6), "Filters" tab visible. The lot 0.9 test changes
  its expected result.
- **E6**: prerequisite, the `server-prober` verdict on `media_details.sizes`.
- **E7**: prerequisites, E6 and the lot 10 volume estimate.

---

## 5. Invariants to add to CLAUDE.md

| Invariant | Why |
|---|---|
| The cache fingerprint includes the type, the site **and the filter fingerprint** | Otherwise loosening a filter never recovers old images |
| Changing a filter or a size setting moves, replaces or deletes no file | Same rule as the sort mode |
| `remote_missing_since` only applies to entries that meet the current filter | A filter is not a server-side deletion |
| A profile field set to `None` inherits the default; a default is never copied | Otherwise changing a default would have no effect |
| Only the "Reapply to folder" action replaces an existing file; the new version is validated and in the manifest **before** the old one is deleted | It is the only deletion initiated by the engine |
| Header reading goes through the `Transport` and reads at most 64 KiB | Delay floor and server load |
| A profile is never restarted automatically less than I/2 after its last run | Adding, removing or reordering profiles must not cause a double run |

---

## 6. Decisions of 2026-09-28

| # | Question | Decision |
|---|---|---|
| 1 | Interval per profile? | Global, with staggered profile runs to spare the PC |
| 2 | Slideshow | A single profile |
| 3 | CLI without `--profile` | All profiles, staggered |
| 4 | Structured events | Planned in lot 2, hence before 5.0 |
| 5 | Unknown value in a filter | Keep if the criterion is met; otherwise read the information from the image |
| 6 | Existing files when the filter changes | Leave them untouched |
| 7 | ESO category | Filter first |
| 8 | Automatic replacement when the size changes | No, not now |
| 9 | Unit of the setting | Longest edge |
| 10 | Reapply to folder | Yes, with a warning: irreversible, quality changes |
| 11 | `max_edge` and Djangoplicity format | `max_edge` picks the variant when enabled |
| 12 | Local resizing | Deferred |
| 13 | Other site types | Yes, later |
| 14 | Shape of the staggering | Start times spread across the interval (24 h, 3 profiles → every 8 h) |
| — | Confirmations | 4 in lot 2; 5 (header reading, dimensions in manifest v2); 10 (order validate → manifest → delete, stop between two images) |

Rejected alternatives, unchanged since revision 1: full copy of the settings
per profile (defaults become useless), comparing the strictness of two filters
(fragile), `QImage` in the engine (boundary 1).

---

## 7. Verified / assumed

**Assumed, to be confirmed before the relevant step:**

- cache delta and loosened `min_width` — local test, lot 0.9;
- `media_details.sizes`, `filesize` per variant, cropped variants,
  `-scaled` / `original_image` on the club's site — `server-prober`, E6;
- dimensions almost always present in both APIs — to be measured on one page of
  each source before writing the header reader;
- position of the dimensions in ESO TIFFs (start or end of file) — one `Range`
  request on an `Original`, 64 KiB only.

---

## 8. Open questions

1. **Future sources**: will they need authentication (API key)? The
   `Transport` carries none today, and where to store it would have to be
   decided. To be handled when a concrete site comes up.
