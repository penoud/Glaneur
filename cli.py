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
    Moteur,
    Options,
    format_octets,
    lister_supprimees,
    restaurer,
)
from Glaneur.scheduler import Planificateur


def main() -> int:
    """CLI entry point.

    Parses the command line, applies the arguments on top of the
    persisted configuration, runs the :class:`Glaneur.engine.Moteur`
    once and prints a readable summary on stdout. A keyboard interrupt
    (``Ctrl+C``) propagates a cooperative ``arret`` to the engine before
    exiting.

    Returns:
        ``0`` if the run finished cleanly, ``1`` if every download
        failed without any new file being fetched, ``2`` if the run was
        deferred by the network circuit-breaker (server unavailable,
        quota, ...), ``130`` on keyboard interrupt (shell convention).
    """
    c = Config.charger()
    p = argparse.ArgumentParser(
        description="Télécharge les images d'un site (WordPress ou Djangoplicity).")
    p.add_argument("-d", "--dossier", default=c.dossier, help="dossier de destination")
    p.add_argument("--type", dest="type_source",
                   choices=["wordpress", "djangoplicity"],
                   default=c.type_source, help="type de site à interroger")
    p.add_argument("--format", dest="format_image",
                   choices=["Large", "Original", "Small"],
                   default=c.format_image,
                   help="résolution Djangoplicity (ignoré pour WordPress)")
    p.add_argument("--classement", choices=["galerie", "date", "plat"],
                   default=c.classement)
    p.add_argument("--largeur-min", type=int, default=c.largeur_min)
    p.add_argument("--delai", type=float, default=c.delai_requetes)
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
        ids = args.restaurer or [e["id"] for e in lister_supprimees(dossier)]
        print(f"{restaurer(dossier, ids)} image(s) remise(s) en file.")

    options = Options(
        dossier=Path(args.dossier).expanduser(),
        site=c.site,
        classement=args.classement,
        largeur_min=args.largeur_min,
        delai=args.delai,
        verifier=args.verifier,
        force=args.force,
        depuis=args.depuis,
        jusqua=args.jusqua,
        utiliser_cache=not args.pas_cache,
        type_source=args.type_source,
        format_image=args.format_image,
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

    moteur = Moteur(options, journal=lambda m: print(f"\n{m}"), progression=progression)
    try:
        res = moteur.executer()
    except KeyboardInterrupt:
        moteur.arret.set()
        print("\nInterrompu.")
        return 130

    print(f"\n\n{res.message}")
    print(f"  téléchargées : {res.telechargees}   reprises : {res.reprises}")
    print(f"  déjà à jour  : {res.deja_presentes}   inchangées : {res.inchangees}")
    print(f"  supprimées   : {res.supprimees}   ignorées : {res.ignorees}")
    print(f"  échecs       : {res.echecs}   volume : {format_octets(res.octets)}")

    if res.reporte:
        # Persist the defer so the next invocation (UI or CLI) honours
        # the backoff. We do NOT call `marquer_execution` — the run was
        # truncated.
        planificateur = Planificateur(c)
        planificateur.differer(res)
        print(f"  {planificateur.texte_prochaine()}", file=sys.stderr)
        return 2
    return 1 if res.echecs and not res.telechargees else 0


if __name__ == "__main__":
    raise SystemExit(main())
