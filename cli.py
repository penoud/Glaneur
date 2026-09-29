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


def _build_parser(c: Config, profile=None) -> argparse.ArgumentParser:
    """Build the argparse parser, exposing English flags and hidden FR aliases.

    Every French flag from the pre-US-EN-06 CLI is preserved as a
    second ``add_argument`` call sharing the same ``dest`` and marked
    ``help=argparse.SUPPRESS`` so it stays out of ``--help`` while
    keeping existing scripts working.

    Args:
        c: Persisted config; per-profile defaults come from ``profile``
            (see below), application-level ones (``request_delay``)
            stay on ``c``.
        profile: The profile whose settings seed the per-profile
            defaults. When ``None``, the config's default profile
            (``c.default_profile()``) is used — the behaviour every
            pre-multi-profile script keeps depending on.

    Returns:
        A configured ``argparse.ArgumentParser``.
    """
    p = argparse.ArgumentParser(
        description="Download images from a site (WordPress or Djangoplicity).")
    # Per-profile defaults come through the profile passed in (or the
    # default one if `--profile` was not on the command line). Same
    # None-inheritance rule as the runtime: `min_width` /
    # `verify_integrity` resolve against `c.defaults()`.
    if profile is None:
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

    # Multi-profile picker (lot 5.1 E3 part B step 6). Without
    # ``--profile``, the default profile (index 0) runs — every
    # pre-multi-profile script keeps working verbatim.
    p.add_argument("--profile", dest="profile", metavar="NAME|ID",
                   help="run against a specific profile"
                        " (name or full id; default: the first profile)")
    p.add_argument("--list-profiles", dest="list_profiles",
                   action="store_true",
                   help="print the configured profiles and exit")
    return p


def _pick_profile(c: Config, wanted: str | None):
    """Resolve ``wanted`` to one of the configured profiles.

    Match order is name-first, then id-prefix (so a user can type a
    short prefix of the uuid). Ambiguity — multiple profiles matching
    the same name or id-prefix — raises ``SystemExit`` with exit code 2.

    Args:
        c: The persisted config.
        wanted: The ``--profile`` argument value, or ``None`` (return
            the default profile).

    Returns:
        The chosen :class:`Glaneur.config.Profile`.
    """
    profiles = c.profiles()
    if wanted is None:
        return profiles[0]
    # Name match first (exact).
    par_nom = [p for p in profiles if p.name == wanted]
    if len(par_nom) == 1:
        return par_nom[0]
    if len(par_nom) > 1:
        print(f"Ambiguous profile name {wanted!r}: {len(par_nom)} profiles"
              " share this name; use the full id instead.", file=sys.stderr)
        raise SystemExit(2)
    # Id-prefix match next.
    par_id = [p for p in profiles if p.id.startswith(wanted)]
    if len(par_id) == 1:
        return par_id[0]
    if len(par_id) > 1:
        print(f"Ambiguous profile id-prefix {wanted!r}: {len(par_id)}"
              " profiles match; use a longer prefix.", file=sys.stderr)
        raise SystemExit(2)
    print(f"No profile named or starting with {wanted!r}.", file=sys.stderr)
    raise SystemExit(2)


def _print_profiles(c: Config) -> None:
    """Print one line per profile (name — id — site) on stdout."""
    for p in c.profiles():
        print(f"{p.name}\t{p.id}\t{p.site or '—'}")


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

    # Two-pass parsing so `--profile` can steer the defaults of every
    # per-profile flag: pass 1 uses a minimal parser to pick out
    # `--profile` / `--list-profiles`; pass 2 rebuilds the real parser
    # seeded with the picked profile's fields.
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--profile", dest="profile")
    pre.add_argument("--list-profiles", dest="list_profiles",
                     action="store_true")
    pre_args, _ = pre.parse_known_args()

    if pre_args.list_profiles:
        _print_profiles(c)
        return 0

    profile = _pick_profile(c, pre_args.profile)
    args = _build_parser(c, profile).parse_args()

    if args.restore is not None:
        dossier = Path(args.target_dir).expanduser()
        ids = args.restore or [e["id"] for e in list_deleted(dossier)]
        print(f"{restore(dossier, ids)} image(s) re-queued.")

    options = Options(
        target_dir=Path(args.target_dir).expanduser(),
        site=profile.site,
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
