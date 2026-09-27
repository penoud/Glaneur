# Impact Map

<!--
Gabarit temporaire, propre à la tâche courante. Remets-le à cet état vide
entre deux lots. N'y stocke ni copie de fichiers, ni logs, ni résultats de
tests volumineux, ni informations déjà présentes dans CLAUDE.md. Voir
CLAUDE.md section « Impact Map » et « Politique de contexte minimal ».
-->

## Task

Frontière 1 sur le scheduler : rendre `Glaneur/scheduler.py` Qt-free en
extrayant le formatage traduit `texte_prochaine()` vers un helper UI
séparé. Retirer l'entrée correspondante de `KNOWN_QT_IMPORTS` dans
`tests/test_boundaries.py` (le xfail strict échoue dès que la dette est
soldée). Mettre à jour CLAUDE.md et régénérer les `.ts`.

`Glaneur/engine/core.py` reste **hors périmètre** (chantier séparé :
émission d'événements structurés).

## Directly modified

- Glaneur/scheduler.py                       (retirer `QCoreApplication`,
                                              retirer `texte_prochaine()`,
                                              exposer `report_actif()`
                                              publique pour que le helper
                                              n'ait pas à toucher aux
                                              méthodes `_` )
- Glaneur/scheduler_labels.py                (nouveau : fonction
                                              `texte_prochaine(planificateur)`
                                              avec les 7 chaînes
                                              « Planificateur » traduites ;
                                              hors périmètre du test de
                                              boundary, qui ne scanne que
                                              scheduler.py, detect.py,
                                              engine/*.py et sources/*.py)
- app.py                                     (dans `_rafraichir_echeance` :
                                              `texte_prochaine(self.planificateur)`
                                              au lieu de la méthode)
- cli.py                                     (idem : `texte_prochaine(planificateur)`)
- tests/test_boundaries.py                   (retirer
                                              `"Glaneur/scheduler.py"`
                                              de `KNOWN_QT_IMPORTS`)
- tests/test_scheduler.py                    (les tests `TestTextePresentable*`
                                              importent et exercent la
                                              fonction du helper, pas la
                                              méthode)
- CLAUDE.md                                  (retirer l'écart connu
                                              scheduler ; l'écart moteur
                                              reste)
- translations/glaneur_fr.ts                 (régénérer via
                                              `build_translations.py update`
                                              — les libellés
                                              « Planificateur » ne
                                              changent pas, seul le
                                              `filename=` bascule sur
                                              `scheduler_labels.py`)
- translations/glaneur_en.ts                 (idem)

## Direct dependencies

- `build_translations.py` scanne déjà `*(RACINE / "Glaneur").glob("*.py")`,
  donc le nouveau fichier est capté sans modification du build.

## Tests

- `tests/test_scheduler.py` : classes `TestTextePresentable` et
  `TestTextePresentableAvecReport` (7 tests) — mêmes assertions, appel
  changé.
- `tests/test_boundaries.py::test_no_qt_outside_ui[Glaneur/scheduler.py]`
  doit passer de XFAIL à PASSED.
- `tests/test_cli.py::test_deux_si_run_reporte` couvre déjà le chemin
  d'appel dans le CLI.
- Ruff ciblé sur les fichiers modifiés.
- Pas de suite complète nécessaire : validation `local` selon la table
  de CLAUDE.md (« Une source » → tests concernés + ruff), le scheduler
  n'étant ni API publique ni format persistant.

## Explicitly out of scope

- `Glaneur/engine/core.py` (chantier séparé, événements structurés).
- Réécriture de la logique de planification (dates, backoff) — inchangée.
- Ajout de traductions anglaises (les entrées restent `unfinished`,
  comme aujourd'hui).
- Docs Sphinx : pas de docstrings publiques changées dans le sens des
  signatures ; `texte_prochaine()` disparaît mais il n'est pas
  documenté en `autoclass` séparément.

## Invariants

- Le scheduler n'importe plus Qt (frontière 1 satisfaite).
- Les 7 chaînes source « Planificateur » restent **identiques
  caractère pour caractère** — sinon les `.ts` existants perdraient
  leurs entrées et il faudrait retraduire.
- L'API du CLI et de l'UI reste inchangée du point de vue de
  l'utilisateur (mêmes libellés affichés).
- `Planificateur.report_actif()` (nouveau) renvoie exactement le même
  booléen que le calcul inline précédent dans `texte_prochaine`.
