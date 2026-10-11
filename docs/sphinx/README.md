# Sphinx documentation — Glaneur

This folder holds the Sphinx-generated API docs (US-02 of the current
sprint). It contains `conf.py`, `index.rst`, `architecture.rst`, the
`api/` tree produced by `sphinx-apidoc`, and `_build/` (git-ignored).

## Docstring style

**Decision: Napoleon (Google-style).**

- Extension enabled in `conf.py`: `sphinx.ext.napoleon`.
- Sections, in this order when they apply:

  ```python
  def resolve(url: str, timeout: float = 30) -> RunResult:
      """Resolve a URL into a ``RunResult``.

      Resolution follows HTTP redirects then checks the ETag. See
      ``Glaneur.engine.RunResult`` for the semantics of the ``message``
      field.

      Args:
          url: Absolute URL to resolve.
          timeout: Maximum delay in seconds.

      Returns:
          The ``RunResult`` built from the response.

      Raises:
          Interrupted: If the user requested a stop during the call.
          requests.RequestException: On an unrecoverable network failure.
      """
  ```

- One summary line, blank line, long description if useful, blank line,
  sections `Args:` / `Returns:` / `Yields:` / `Raises:` / `Attributes:`.
- Types belong in the Python annotations, **not** in the sections
  (`Args: url: URL...`, not `Args: url (str): URL...`).

Why Napoleon rather than native rST? The existing docstrings are all
readable prose; Napoleon lets us enrich them incrementally without
rewriting them. The rendered HTML is equivalent.

## Starting point (US-01 measurement, 2026-09-25)

| Module                             | Doc / total | Style   |
|-----------------------------------|:-----------:|---------|
| `Glaneur/__init__.py`             | 1 / 1       | prose   |
| `Glaneur/bug_report.py`           | 4 / 4       | prose   |
| `Glaneur/config.py`               | 3 / 10      | prose   |
| `Glaneur/engine.py`               | 8 / 25      | prose   |
| `Glaneur/i18n.py`                 | 4 / 4       | prose   |
| `Glaneur/logsetup.py`             | 2 / 2       | prose   |
| `Glaneur/scheduler.py`            | 2 / 8       | prose   |
| `Glaneur/sources/__init__.py`     | 2 / 2       | prose   |
| `Glaneur/sources/base.py`         | 10 / 13     | prose   |
| `Glaneur/sources/djangoplicity.py`| 2 / 5       | prose   |
| `Glaneur/sources/wordpress.py`    | 2 / 5       | prose   |
| `Glaneur/systeme.py`              | 8 / 9       | prose   |
| `Glaneur/updater/__init__.py`     | 1 / 1       | prose   |
| `Glaneur/updater/downloader.py`   | 1 / 5       | prose   |
| `Glaneur/updater/github_release.py`| 1 / 4      | prose   |
| `Glaneur/updater/models.py`       | 1 / 7       | prose   |
| `Glaneur/updater/qt_threads.py`   | 3 / 7       | prose   |
| `Glaneur/updater/version.py`      | 1 / 3       | prose   |
| `app.py`                          | 8 / 19      | prose   |
| `cli.py`                          | 1 / 3       | prose   |
| **Total**                         | **65 / 137**| **prose** |

- 100 % of the existing docstrings are free-form prose. None already
  uses `:param:` or `Args:` — the conversion is purely additive.
- `servette/` contains only `.pyc` leftovers from the
  `WpImageDownloader → Glaneur` rename and sits outside the sprint
  scope. To be removed in a separate lot or caught by the next cleanup.

## Conversion order for US-03

The sprint proposes an order driven by "visibility and invariants".
Combined with the debt measured above, the order stays:

1. `Glaneur/engine.py` — 17 symbols to document, central module.
2. `Glaneur/sources/base.py`, then `wordpress.py`, `djangoplicity.py`,
   `__init__.py` — adapter contracts, 8 bare symbols in total.
3. `Glaneur/config.py` — 7 bare symbols, persisted format.
4. `Glaneur/scheduler.py` — 6 bare symbols, Qt boundary to settle
   later.
5. `Glaneur/systeme.py` — 1 missing, quick.
6. `Glaneur/i18n.py`, `Glaneur/logsetup.py`, `Glaneur/bug_report.py` —
   already covered, one Napoleon enrichment pass.
7. `Glaneur/updater/` — 20 bare symbols across 6 files, handled as a
   single lot.
8. `app.py` — 11 missing, large file (54 kB), possibly split into two
   commits by UI section.
9. `cli.py` — 2 missing, trivial.

One commit per file (or per coherent group when a file holds less than
~100 lines of modified docstrings). After each commit,
`sphinx-build -W` must stay green (US-02 must be in place).
