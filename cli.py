#!/usr/bin/env python3
"""Command-line interface, useful for testing the engine without the UI.

    python cli.py --folder ./photos --verify
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from Glaneur.config import (
    DJANGOPLICITY_FORMATS,
    SORT_MODES,
    SOURCE_TYPES,
    Config,
)
from Glaneur.engine import (
    Engine,
    EngineEvent,
    Options,
    format_bytes,
    list_deleted,
    render_en,
    restore,
)
from Glaneur.scheduler import Scheduler
from Glaneur.scheduler_labels import next_run_text


def _build_parser(c: Config) -> argparse.ArgumentParser:
    """Build the argparse parser, exposing English flags and hidden FR aliases.

    Every French flag from the pre-US-EN-06 CLI is preserved as a
    second ``add_argument`` call sharing the same ``dest`` and marked
    ``help=argparse.SUPPRESS`` so it stays out of ``--help`` while
    keeping existing scripts working.

    Args:
        c: Persisted config, used only to seed the flag defaults.

    Returns:
        A configured ``argparse.ArgumentParser``.
    """
    p = argparse.ArgumentParser(
        description="Download images from a site (WordPress or Djangoplicity).")
    # Per-profile defaults come through the forward-compat builder so
    # this call site keeps working verbatim when E3 part B step 2
    # flips Config storage to a real list[Profile] (roadmap §5.1).
    # `request_delay` is application-level and stays on `c`.
    profile = c.default_profile()
    defaults = c.defaults()

    p.add_argument("-d", "--folder", dest="target_dir",
                   default=profile.target_dir, help="destination folder")
    p.add_argument("--dossier", dest="target_dir", help=argparse.SUPPRESS)

    # Choices come from the single-source-of-truth registries in
    # `Glaneur.config`; hard-coded copies drift as soon as a profile
    # (lot 5) or filter (lot 11.2) adds a value (roadmap lot 0.8,
    # boundary 3).
    source_types = list(SOURCE_TYPES.values())
    image_formats = list(DJANGOPLICITY_FORMATS.values())
    sort_modes = list(SORT_MODES.values())

    p.add_argument("--type", dest="source_type",
                   choices=source_types,
                   default=profile.source_type, help="site type to query")
    p.add_argument("--format", dest="image_format",
                   choices=image_formats,
                   default=profile.image_format,
                   help="Djangoplicity resolution (ignored for WordPress)")

    p.add_argument("--sort", dest="sort_mode",
                   choices=sort_modes,
                   default=profile.sort_mode,
                   help="folder layout of downloaded files")
    p.add_argument("--classement", dest="sort_mode",
                   choices=sort_modes, help=argparse.SUPPRESS)

    p.add_argument("--min-width", dest="min_width", type=int,
                   default=profile.effective_min_width(defaults),
                   help="skip images narrower than this (pixels)")
    p.add_argument("--largeur-min", dest="min_width", type=int,
                   help=argparse.SUPPRESS)

    p.add_argument("--delay", dest="delay", type=float,
                   default=c.request_delay,
                   help="floor of the pause between two requests (seconds)")
    p.add_argument("--delai", dest="delay", type=float,
                   help=argparse.SUPPRESS)

    p.add_argument("--verify", dest="verify", action="store_true",
                   help="revalidate files already present")
    p.add_argument("--verifier", dest="verify", action="store_true",
                   help=argparse.SUPPRESS)

    p.add_argument("--force", action="store_true", help="ignore the manifest")

    p.add_argument("--no-cache", dest="no_cache", action="store_true",
                   help="ignore the API cache (max date, gallery titles)"
                        " and re-fetch everything")
    p.add_argument("--pas-cache", dest="no_cache", action="store_true",
                   help=argparse.SUPPRESS)

    p.add_argument("--since", dest="since", help="YYYY-MM-DD lower bound")
    p.add_argument("--depuis", dest="since", help=argparse.SUPPRESS)

    p.add_argument("--until", dest="until", help="YYYY-MM-DD upper bound")
    p.add_argument("--jusqua", dest="until", help=argparse.SUPPRESS)

    p.add_argument("--restore", dest="restore", nargs="*", metavar="ID",
                   help="re-queue previously deleted images"
                        " (all of them if no ID is given)")
    p.add_argument("--restaurer", dest="restore", nargs="*", metavar="ID",
                   help=argparse.SUPPRESS)
    return p


def main() -> int:
    """CLI entry point.

    Parses the command line, applies the arguments on top of the
    persisted configuration, runs the :class:`Glaneur.engine.Engine`
    once and prints a readable summary on stdout. A keyboard interrupt
    (``Ctrl+C``) propagates a cooperative ``stop_event`` to the engine before
    exiting.

    Returns:
        ``0`` if the run finished cleanly, ``1`` if every download
        failed without any new file being fetched, ``2`` if the run was
        deferred by the network circuit-breaker (server unavailable,
        quota, ...), ``3`` if the target folder is already in use by
        another Glaneur process (per-folder OS lock held), ``130`` on
        keyboard interrupt (shell convention).
    """
    c = Config.load()
    args = _build_parser(c).parse_args()

    if args.restore is not None:
        dossier = Path(args.target_dir).expanduser()
        ids = args.restore or [e["id"] for e in list_deleted(dossier)]
        print(f"{restore(dossier, ids)} image(s) re-queued.")

    options = Options(
        target_dir=Path(args.target_dir).expanduser(),
        site=c.default_profile().site,
        sort_mode=args.sort_mode,
        min_width=args.min_width,
        delay=args.delay,
        verify=args.verify,
        force=args.force,
        since=args.since,
        until=args.until,
        use_cache=not args.no_cache,
        source_type=args.source_type,
        image_format=args.image_format,
    )

    dernier = [""]

    def progression(fait: int, total: int, etiquette: str) -> None:
        """Progression callback: rewrites a single line on stdout.

        Args:
            fait: Number of items processed.
            total: Number of items to process.
            etiquette: Short label to display (truncated to 60
                characters).
        """
        ligne = f"\r  {fait}/{total} — {etiquette[:60]:<60}"
        if ligne != dernier[0]:
            sys.stdout.write(ligne)
            sys.stdout.flush()
            dernier[0] = ligne

    def journal(event: EngineEvent) -> None:
        """Render an engine event in English and print it on stdout."""
        print(f"\n{render_en(event)}")

    moteur = Engine(options, journal=journal, progression=progression)
    try:
        res = moteur.run()
    except KeyboardInterrupt:
        moteur.stop_event.set()
        print("\nInterrupted.")
        return 130

    if res.busy:
        # Another Glaneur process holds the per-folder OS lock (open UI,
        # scheduled task, legacy install). Nothing was written; retry later.
        print(
            f"Folder already in use: {options.target_dir}",
            file=sys.stderr,
        )
        return 3

    print(f"\n\n{res.message}")
    print(f"  downloaded    : {res.downloaded}   resumed : {res.resumed}")
    print(f"  up-to-date    : {res.already_present}   unchanged : {res.unchanged}")
    print(f"  deleted       : {res.deleted}   skipped : {res.skipped}")
    print(f"  failures      : {res.failures}   volume : {format_bytes(res.bytes)}")

    if res.deferred:
        # Persist the defer so the next invocation (UI or CLI) honours
        # the backoff. We do NOT call `mark_run` — the run was
        # truncated.
        planificateur = Scheduler(c)
        planificateur.defer(res)
        print(f"  {next_run_text(planificateur)}", file=sys.stderr)
        return 2
    return 1 if res.failures and not res.downloaded else 0


if __name__ == "__main__":
    raise SystemExit(main())
