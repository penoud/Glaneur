# Impact Map

<!--
Gabarit temporaire, propre à la tâche courante. Remets-le à cet état vide
entre deux lots. N'y stocke ni copie de fichiers, ni logs, ni résultats de
tests volumineux, ni informations déjà présentes dans CLAUDE.md. Voir
CLAUDE.md section « Impact Map » et « Politique de contexte minimal ».
-->

## Task

Lot 2 du sprint « Coupe-circuit réseau et report différé ». Ajoute au
moteur un compteur d'échecs consécutifs et une sortie propre quand
`classer_erreur` (lot 1) classe une erreur en `coupure`. Trigger :
1 seule erreur `coupure` OU 5 erreurs `transitoire` consécutives.

Résultat exposé via deux nouveaux champs sur `Resultat` :
`reporte: bool` et `retenter_apres: str` (ISO 8601, hint depuis un
`Retry-After` serveur si disponible ; vide sinon → le planificateur
appliquera son propre backoff au lot 3).

## Directly modified

- Glaneur/engine/resultat.py                 (ajout de `reporte`
                                              et `retenter_apres`)
- Glaneur/engine/moteur.py                   (import de
                                              `classer_erreur` +
                                              coupe-circuit dans la
                                              boucle de `executer` ;
                                              `telecharger` renvoie
                                              désormais un tuple à 3
                                              éléments avec la
                                              `Classification`)
- tests/test_moteur.py                       (mise à jour des tests
                                              existants pour le nouvel
                                              unpacking ; nouveaux
                                              tests de coupe-circuit)

## Direct dependencies

- `Glaneur/sources/base.py::classer_erreur` (introduit au lot 1),
  consommé par `Moteur.telecharger`.
- Aucun autre appelant de `Moteur.telecharger` en dehors de `executer`.

## Tests

- `tests/test_moteur.py` : suite ciblée (TestTelecharger et
  TestExecuter mis à jour + nouvelle classe TestCoupeCircuit).
- `ruff check` sur les deux fichiers modifiés.
- Suite complète non nécessaire à ce lot (frontière non touchée,
  format persistant inchangé — les nouveaux champs de `Resultat`
  sont transients, pas sérialisés sur disque).
- `invariant-reviewer` requis : le moteur est un module « moteur »
  au sens du tableau de validation conditionnelle de CLAUDE.md.

## Potentially affected

- `app.py::_terminer` lit `Resultat` : les nouveaux champs ont des
  valeurs par défaut (`False`, `""`), donc pas de casse. Le câblage
  UI attend le lot 4.
- `cli.py` idem.

## Explicitly out of scope

- `Config.retenter_apres` et `Config.backoff_niveau` (lot 3).
- `Planificateur.differer()` (lot 3).
- Câblage UI et CLI (lot 4).
- Traductions `.ts` (lot 4).
- Docs Sphinx (lot 5).

## Invariants

- Frontière 1 (Qt hors moteur) inchangée : le moteur importe déjà
  `QCoreApplication`, on n'ajoute pas de nouvelle dépendance Qt.
- Le manifeste et les `.part` restent sauvegardés en fin de run
  même en cas de report (le `finally` sur `sauver_manifeste` est
  conservé). Les `.part` sont préservés pour la reprise.
- Le cache moteur n'est PAS sauvegardé en cas de report (analogue
  au traitement d'`Interrompu`) : on ne mémorise pas
  `derniere_date_media` à partir d'un run tronqué.
- La surface publique de `Resultat` s'enrichit mais reste
  rétrocompatible : les champs existants gardent leur type et
  valeur par défaut.
