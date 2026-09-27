#!/usr/bin/env python3
"""Command-line interface, useful for testing the engine without the UI.

    python cli.py --dossier ./photos --dry-run
    python cli.py --dossier ./photos --verifier
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from Glaneur.config import Config
from Glaneur.engine import (
    Engine,
    Options,
    format_bytes,
    list_deleted,
    restore,
)
from Glaneur.scheduler import Scheduler
from Glaneur.scheduler_labels import next_run_text


def main() -> int:
    """CLI entry point.

    Parses the command line, applies the arguments on top of the
    persisted configuration, runs the :class:`Glaneur.engine.Engine`
    once and prints a readable summary on stdout. A keyboard interrupt
    (``Ctrl+C``) propagates a cooperative ``arret`` to the engine before
    exiting.

    Returns:
        ``0`` if the run finished cleanly, ``1`` if every download
        failed without any new file being fetched, ``2`` if the run was
        deferred by the network circuit-breaker (server unavailable,
        quota, ...), ``130`` on keyboard interrupt (shell convention).
    """
    c = Config.load()
    p = argparse.ArgumentParser(
        description="Télécharge les images d'un site (WordPress ou Djangoplicity).")
    p.add_argument("-d", "--dossier", default=c.target_dir, help="dossier de destination")
    p.add_argument("--type", dest="source_type",
                   choices=["wordpress", "djangoplicity"],
                   default=c.source_type, help="type de site à interroger")
    p.add_argument("--format", dest="image_format",
                   choices=["Large", "Original", "Small"],
                   default=c.image_format,
                   help="résolution Djangoplicity (ignoré pour WordPress)")
    p.add_argument("--classement", choices=["galerie", "date", "plat"],
                   default=c.sort_mode)
    p.add_argument("--largeur-min", type=int, default=c.min_width)
    p.add_argument("--delai", type=float, default=c.request_delay)
    p.add_argument("--verifier", action="store_true", help="revalider les fichiers existants")
    p.add_argument("--force", action="store_true", help="ignorer le manifeste")
    p.add_argument("--pas-cache", action="store_true",
                   help="ignorer le cache API (date max, titres galeries) et tout redemander")
    p.add_argument("--depuis", help="AAAA-MM-JJ")
    p.add_argument("--jusqua", help="AAAA-MM-JJ")
    p.add_argument("--restaurer", nargs="*", metavar="ID",
                   help="remet en file des images supprimées (toutes si aucun ID)")
    args = p.parse_args()

    if args.restaurer is not None:
        dossier = Path(args.dossier).expanduser()
        ids = args.restaurer or [e["id"] for e in list_deleted(dossier)]
        print(f"{restore(dossier, ids)} image(s) remise(s) en file.")

    options = Options(
        target_dir=Path(args.dossier).expanduser(),
        site=c.site,
        sort_mode=args.classement,
        min_width=args.largeur_min,
        delay=args.delai,
        verify=args.verifier,
        force=args.force,
        since=args.depuis,
        until=args.jusqua,
        use_cache=not args.pas_cache,
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

    moteur = Engine(options, journal=lambda m: print(f"\n{m}"), progression=progression)
    try:
        res = moteur.run()
    except KeyboardInterrupt:
        moteur.arret.set()
        print("\nInterrompu.")
        return 130

    print(f"\n\n{res.message}")
    print(f"  téléchargées : {res.downloaded}   reprises : {res.resumed}")
    print(f"  déjà à jour  : {res.already_present}   inchangées : {res.unchanged}")
    print(f"  supprimées   : {res.deleted}   ignorées : {res.skipped}")
    print(f"  échecs       : {res.failures}   volume : {format_bytes(res.bytes)}")

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
