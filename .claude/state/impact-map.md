# Impact Map

<!--
Gabarit temporaire, propre à la tâche courante. Remets-le à cet état vide
entre deux lots. N'y stocke ni copie de fichiers, ni logs, ni résultats de
tests volumineux, ni informations déjà présentes dans CLAUDE.md. Voir
CLAUDE.md section « Impact Map » et « Politique de contexte minimal ».
-->

## Task

Lot 3 du sprint « Coupe-circuit réseau et report différé ». Câble
`Resultat.reporte`/`Resultat.retenter_apres` (lot 2) dans le
planificateur via un nouveau champ persistant `Config.retenter_apres`
et un `Config.backoff_niveau` (0/1/2 → 1h/2h/4h). Le planificateur
gagne une méthode `differer(res)` que l'UI/le CLI appelleront au
lot 4 en lieu et place de `marquer_execution()` quand `res.reporte`
est vrai.

## Directly modified

- Glaneur/config.py                          (ajout de
                                              `retenter_apres: str`,
                                              `backoff_niveau: int`,
                                              validation et migration
                                              douce)
- Glaneur/scheduler.py                       (`differer(res)`,
                                              `prochaine()` respecte
                                              `retenter_apres`,
                                              `marquer_execution()`
                                              remet backoff à zéro,
                                              libellé dédié dans
                                              `texte_prochaine`)
- tests/test_scheduler.py                    (nouvelle classe pour
                                              `differer`, `prochaine`
                                              avec report,
                                              `texte_prochaine`
                                              libellé de report)
- tests/test_config.py                       (round-trip des deux
                                              nouveaux champs +
                                              validation des bornes
                                              de `backoff_niveau`)

## Direct dependencies

- `Glaneur.engine.resultat.Resultat` : consommé par
  `Planificateur.differer(res)`. Import direct depuis `scheduler.py`.
  Pas de cycle (resultat.py n'importe rien de scheduler).

## Tests

- Suite ciblée : `tests/test_scheduler.py` + `tests/test_config.py`.
- Ruff ciblé sur `Glaneur/config.py`, `Glaneur/scheduler.py`,
  `tests/test_scheduler.py`, `tests/test_config.py`.
- Suite complète + couverture + Sphinx en validation finale de fin de
  lot (format persistant `config.json` modifié — cf. tableau CLAUDE.md).
- `invariant-reviewer` requis (frontière `Config` + format persisté).

## Potentially affected

- `app.py` : lit `Config` mais ne consomme pas encore les nouveaux
  champs — câblage au lot 4.
- `cli.py` : idem.

## Explicitly out of scope

- Câblage UI dans `app.py::_terminer` et exit code CLI (lot 4).
- Traductions `.ts` (lot 4).
- Docs Sphinx (lot 5).

## Invariants

- Frontière 1 : `scheduler.py` reste dépendant de Qt (déjà écarté
  dans CLAUDE.md), mais on n'ajoute aucune nouvelle dépendance Qt.
- Compatibilité ascendante : un `config.json` existant sans les deux
  nouveaux champs charge sans erreur (défauts `""` et `0`).
- `Config.derniere_execution` reste naïf local (statu quo). Le
  planificateur reçoit `res.retenter_apres` en ISO 8601 aware UTC
  (lot 2) et le convertit en naïf local avant persistance dans
  `Config.retenter_apres`, pour rester comparable à
  `derniere_execution` (règle notée par la review du lot 2 :
  éviter le mélange aware/naïf dans `prochaine()`).
- `backoff_niveau` borné à `[0, 2]` par `Config.valider`, table
  interne `[3600, 7200, 14400]` s. Réinitialisé à 0 par
  `marquer_execution()`.
- `marquer_execution()` remet aussi `retenter_apres = ""` : un run
  qui réussit après un report clôt le report.
