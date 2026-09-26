# Impact Map

<!--
Gabarit temporaire, propre à la tâche courante. Remets-le à cet état vide
entre deux lots. N'y stocke ni copie de fichiers, ni logs, ni résultats de
tests volumineux, ni informations déjà présentes dans CLAUDE.md. Voir
CLAUDE.md section « Impact Map » et « Politique de contexte minimal ».
-->

## Task

Lot 4 du sprint « Coupe-circuit réseau et report différé ». Câble
`Resultat.reporte` dans l'UI (`app.py`) et le CLI (`cli.py`), et met à
jour les fichiers `.ts` avec les nouvelles chaînes traduites introduites
par les lots 2 et 3.

## Directly modified

- app.py                                     (dans `_terminer` : si
                                              `res.reporte`, appeler
                                              `planificateur.differer(res)`
                                              au lieu de
                                              `marquer_execution()`,
                                              adapter le message des
                                              échecs pour éviter le
                                              double libellé)
- cli.py                                     (après `moteur.executer()` :
                                              si `res.reporte`, appeler
                                              `differer(res)` sur un
                                              `Planificateur(c)`, imprimer
                                              un résumé et sortir avec
                                              exit code 2)
- translations/glaneur_fr.ts                 (mise à jour via
                                              `build_translations.py update`)
- translations/glaneur_en.ts                 (idem, traductions à
                                              compléter manuellement pour
                                              les nouvelles chaînes)

## Direct dependencies

- `Glaneur.scheduler.Planificateur.differer` (lot 3), consommé par
  `app.py` et `cli.py`.
- Nouvelles chaînes traduisibles introduites aux lots 2/3 :
  - `Moteur` : « Serveur indisponible ou quota atteint — reprise après {heure}. »
    et sa variante sans heure.
  - `Planificateur` : « Reprise reportée dans {delai} ({date}) ».
  - `Glaneur.cli` : nouvelles impressions (pas traduites, cohérent
    avec le reste du CLI qui est en français hard-coded).

## Tests

- Pas de nouveaux tests unitaires : `app.py` est peu testé et le
  cheminement est trivial (assignation conditionnelle). Le CLI n'a
  pas de tests dédiés dans le dépôt.
- La régression est couverte par la suite existante — aucun test ne
  doit se casser.
- Ruff ciblé sur `app.py` et `cli.py`.

## Potentially affected

- `_verifier_echeance` : quand un report est actif, `prochaine()`
  renvoie une date future, donc `echeance_atteinte()` reste `False` —
  pas d'auto-run intempestif. Comportement voulu, testé au lot 3
  côté planificateur.

## Explicitly out of scope

- Docs Sphinx (lot 5).
- Refactor de `_terminer` au-delà du câblage du report.
- Tests unitaires de l'UI (le dépôt n'en a pas pour `app.py`).

## Invariants

- Un run avec `res.reporte = True` :
  - ne doit PAS appeler `marquer_execution()` (sinon le report est
    immédiatement effacé au lot 3) ;
  - doit appeler `planificateur.differer(res)` exactement une fois.
- Un run avec `res.interrompu = True` conserve le comportement existant
  (ni `marquer_execution` ni `differer`).
- Un run normal (`not res.reporte and not res.interrompu`) reste
  inchangé : `marquer_execution()`.
- Le CLI ne quitte plus toujours 0/1 : 2 est réservé aux reports.
