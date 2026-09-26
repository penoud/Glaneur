# Impact Map

<!--
Gabarit temporaire, propre à la tâche courante. Remets-le à cet état vide
entre deux lots. N'y stocke ni copie de fichiers, ni logs, ni résultats de
tests volumineux, ni informations déjà présentes dans CLAUDE.md. Voir
CLAUDE.md section « Impact Map » et « Politique de contexte minimal ».
-->

## Task

Sprint « Suppression pendant un run » : rendre `bouton_supprimer_fond`,
`action_supprimer_fond`, `action_supprimer_fond_tray` et
`bouton_supprimees` utilisables pendant une synchronisation. La cause
racine est une race last-writer-wins sur le manifeste entre
`Moteur.executer()` (charge à l'entrée, réécrit tout dans le `finally`)
et `supprimer_image()`/`restaurer()` (lire-muter-écrire côté UI). Le
correctif est une fusion en écriture côté moteur : la marque `supprime`
ou `restaure` posée par l'UI l'emporte sur la version mémoire du moteur ;
les entrées uniquement présentes sur disque sont préservées.

## Directly modified

- Glaneur/engine.py                 (verrou + read-merge-write ;
                                     `sauver_manifeste` devient fusionnant ;
                                     `supprimer_image` et `restaurer`
                                     passent par le même chemin)
- app.py                            (retrait des `setEnabled(False)` en
                                     début de run et de leur miroir en
                                     fin de run ; commentaire obsolète
                                     à supprimer)
- tests/test_moteur.py              (tests de régression race UI/moteur)

## Direct dependencies

- `chemin_manifeste`, `lire_manifeste`, `ecrire_manifeste` :
  contrat inchangé (I/O atomique tmp+rename), le verrou l'englobe.
- `Moteur.executer()` : la sauvegarde périodique (tick 25) et le
  `finally` passent par la nouvelle fusion, aucun autre changement
  d'orchestration.
- `app.py::_lancer`/`_terminer` : suppression des lignes 1110-1113 et
  1167-1170 qui gèrent l'état des 4 contrôles pendant le run.

## Tests

- tests/test_moteur.py — TestSauverManifeste (nouveau) :
  * marque `supprime` posée pendant que le moteur détient un manifeste
    en mémoire survit à sa réécriture ;
  * marque `restaure` posée pendant un run survit ;
  * entrée uniquement sur disque (ident non vu ce run) préservée ;
  * nouvelle entrée écrite par le moteur reste écrite ;
  * suppression + re-téléchargement dans la même passe : `supprime`
    l'emporte (choix éditorial : dernier geste utilisateur gagne) ;
  * pas de régression sur le tick des 25.

## Potentially affected

- CLAUDE.md — section « Écarts connus » : rien à retirer (l'écart
  n'y figurait pas).
- docs/sphinx/api/engine.rst — regénéré automatiquement par
  `make -C docs/sphinx apidoc` uniquement si la surface publique du
  module change ; ici seuls des docstrings évoluent, pas de nouveau
  symbole → pas de régénération requise.

## Explicitly out of scope

- Frontière 1 (Qt hors moteur) : `QCoreApplication` reste importé dans
  engine.py, `xfail(strict=True)` dans test_boundaries.py conservé.
- Glaneur/scheduler.py : hors sujet.
- Portage multi-plateforme de « Supprimer ce fond d'écran »
  (encore Windows-only par nature — dépend de l'API du diaporama).
- Format persistant du manifeste : inchangé, aucune migration.
- Packaging, updater, sources, i18n.

## Invariants

- Atomicité de `ecrire_manifeste` (tmp + os.replace) : préservée.
- Le manifeste est la source de vérité de l'état « déjà téléchargé /
  supprimé / restauré » : préservé, la fusion ne change pas la
  sémantique de ces marques.
- Frontière 1 : non aggravée (aucun nouvel import Qt dans le moteur).

## Validation level

subsystem

## Agents

- test-author  : écrit les tests de fusion (avant l'implémentation).
- test-runner  : lance tests/test_moteur.py + ruff ciblé après le fix.
- invariant-reviewer : review Sonnet (pas Opus — pas de changement
  d'architecture, ni de format persistant, ni de sécurité) après le
  passage des tests.
- pas de server-prober, pas d'exploration complémentaire.
