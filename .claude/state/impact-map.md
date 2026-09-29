# Impact Map

<!--
Temporary scratchpad, one story at a time. Reset to this empty state
between two stories. Do not store copies of files, logs, bulky test
output, or information that already lives in CLAUDE.md. See CLAUDE.md
sections "Impact Map" and "Minimal context policy".
-->

## Task

**Lot 0.2 + 0.3 — Djangoplicity: `Next` origin check and format
fallback logging.**

Two small fixes from `docs/design/roadmap.md`'s lot 0, both in
`Glaneur/sources/djangoplicity.py`. Bundled because they share the
same file and test module and each is a few lines.

### Lot 0.2 — Stop if `Next` changes host or scheme

`Djangoplicity.inventory` today follows the `Next` URL as-is. If a
misbehaving or compromised feed returns a `Next` pointing to a
different host or scheme, we would happily crawl it. Per
`evolution-multi-sources.md` §8, we now stop with a
`RuntimeError` when scheme or netloc of `Next` disagree with `base`.

### Lot 0.3 — Log every format fallback, still never `Original`

`_select_resource` already excludes `Original` from the automatic
fallback list (that half of 0.3 is done). The other half is missing:
when the requested format is missing and we fall back to `Large` or
`Small`, we return the fallback silently. Now we emit a
``source-message`` journal entry so the user sees the fallback.

Also flips two French free-text strings still in `inventory`
(``Catalogue : …``, ``Inventaire… …``) to English, US-EN-08 residue
missed because they were f-strings, not `tr()` sources.

## Directly modified

- `Glaneur/sources/djangoplicity.py`:
  - New helper `_same_origin(base, other) -> bool` at module level.
  - `inventory()` verifies `_same_origin(self.base, suivante)` before
    following; raises `RuntimeError` on mismatch.
  - `_select_resource` becomes an instance method (already is) and
    journals a fallback message when the returned format differs
    from the requested one. Both element and journal go through the
    existing `self._journal` sink.
  - Two FR free-text strings translated to English.
- `tests/test_source_djangoplicity.py`:
  - New `TestNextOriginCheck` covering: `Next` on the same host is
    followed; `Next` on a different host raises;
    `Next` with a different scheme raises;
    a scheme-relative or path-relative `Next` (empty netloc) is
    treated as same-origin.
  - New `TestFormatFallback` covering: requested==effective emits no
    fallback journal; requested missing → effective is a fallback →
    the source-message journal fires with both the requested and the
    effective format; `Original` never picked as an automatic
    fallback (existing behaviour re-asserted).

## Direct dependencies

- `Glaneur/sources/base.py::Source` — unchanged; `_journal` and
  `_progression` sinks used the same way.
- Cache/manifest formats — unchanged.

## Explicitly out of scope

- The `Checksum` level (roadmap lot 0.1) still needs the real-server
  test of lot 1.3 to settle; not touched here.
- WordPress `Link: rel="https://api.w.org/"` detection (roadmap
  lot 7) — separate lot.
- `__version__` — unchanged.

## Tests

- Existing `tests/test_source_djangoplicity.py::TestInventory` and
  `::TestToElement` still cover the happy paths.
- Two new focused test classes cover the new branches with a
  fake session and `_source()` helper already present in the module.

Verification:

- `pytest -q` → still passes; 509 + new tests.
- `python tools/check_coverage.py` → floors held.
- `ruff check` on `Glaneur/sources/djangoplicity.py` and
  `tests/test_source_djangoplicity.py`: no new warnings.

## Invariants

- `__version__` unchanged.
- No persisted-format touched.
- No dispatch-value literal touched.
- The `Original` variant is still never picked as an automatic
  fallback (this lot only *makes visible* the existing behaviour).
- Same-origin follows the (scheme, netloc) pair; a relative
  `Next` (empty netloc) is treated as same-origin — this matches
  `urljoin` semantics used implicitly today when `requests` resolves
  a relative URL.

## Validation

Level `local` — same-file changes, targeted tests, no boundary or
persisted format touched. `invariant-reviewer` not required per the
roadmap's lot 0 footprint.

- `pytest -q` green.
- `ruff check` clean on touched files.
