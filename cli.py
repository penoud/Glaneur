#!/usr/bin/env python3
"""Interface en ligne de commande, utile pour tester le moteur sans UI.

    python cli.py --dossier ./photos --dry-run
    python cli.py --dossier ./photos --verifier
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from WpImageDownloader.config import Config
from WpImageDownloader.engine import (
    Moteur,
    Options,
    format_octets,
    lister_supprimees,
    restaurer,
)


def main() -> int:
    c = Config.charger()
    p = argparse.ArgumentParser(description="Télécharge les images du Servette FC.")
    p.add_argument("-d", "--dossier", default=c.dossier, help="dossier de destination")
    p.add_argument("--classement", choices=["galerie", "date", "plat"],
                   default=c.classement)
    p.add_argument("--largeur-min", type=int, default=c.largeur_min)
    p.add_argument("--delai", type=float, default=c.delai_requetes)
    p.add_argument("--verifier", action="store_true", help="revalider les fichiers existants")
    p.add_argument("--force", action="store_true", help="ignorer le manifeste")
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
    )

    dernier = [""]

    def progression(fait: int, total: int, etiquette: str) -> None:
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
    return 1 if res.echecs and not res.telechargees else 0


if __name__ == "__main__":
    raise SystemExit(main())
