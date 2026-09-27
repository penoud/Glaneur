# Impact Map

<!--
Gabarit temporaire, propre à la tâche courante. Remets-le à cet état vide
entre deux lots. N'y stocke ni copie de fichiers, ni logs, ni résultats de
tests volumineux, ni informations déjà présentes dans CLAUDE.md. Voir
CLAUDE.md section « Impact Map » et « Politique de contexte minimal ».
-->

## Task

**Sprint « Identifiants FR → EN ». Batch 0 — préparation.**

Ce lot ne touche pas au code de production. Il produit :

1. La présente Impact Map, remise au format « lot en cours » — elle sera
   réécrite au début de chaque lot suivant du sprint.
2. Le **dictionnaire de renommage** consolidé (`rename-dictionary.md`)
   qui sert de source de vérité aux lots 2 à 6 : toute décision d'un
   lot suivant sur un identifiant renvoie à ce fichier plutôt qu'à une
   discussion locale.

Les décisions ouvertes de fin de plan de sprint (voir chat) sont
figées ici, dans « Décisions figées ».

## Directly modified

- .claude/state/impact-map.md          (ce fichier — réécrit)
- .claude/state/rename-dictionary.md   (nouveau — dictionnaire FR → EN)

## Direct dependencies

Aucune. Batch 0 n'a pas de dépendance de code.

## Tests

Aucun test à jouer. Le contenu produit sera exercé par les lots suivants.

## Explicitly out of scope

- Toute modification de `Glaneur/**/*.py`, `tests/**`, `translations/**`,
  `docs/sphinx/**`, `packaging/**`, `README.md`, `CLAUDE.md`.
- La sweep résiduelle de commentaires FR (lot 1).
- Les renommages eux-mêmes (lots 2 à 6).
- Le changement de clés JSON persistées de `Config` (lot 4b, décision
  figée ci-dessous mais implémentation reportée).
- Les `.ts`/`.qm` Qt (lot 7, différé).

## Invariants

Ce lot ne modifie aucune frontière ni invariant du code. Les invariants
qui **contraignent** les lots suivants sont recensés dans le dictionnaire
sous « Contraintes », pas ici, pour rester au bon endroit lorsque les
lots 2 à 6 recopieront ce champ.

## Validation

Niveau `local` (rédaction). Pas de pytest, pas de ruff, pas de Sphinx.
La cohérence est vérifiée à la lecture par la conversation principale.

## Décisions figées pour le sprint (arbitrages des points ouverts)

Ces choix sont pris à Batch 0 pour que les lots suivants n'aient pas à
les rejouer. Ils sont recopiés en tête du dictionnaire.

- **Clés JSON persistées de `Config` (lot 4b) : shim de compatibilité.**
  Le lot 4b renomme les champs de `Config` en anglais et ajoute dans
  `Config.load` (ex `Config.charger`) une traduction FR → EN des clés
  lues. Les écritures sortent en anglais. Le shim reste au moins une
  release. Justification : sinon rupture silencieuse pour tout
  utilisateur existant, hors politique de l'écart connu actuel.
- **Sources Qt (`.ts` `sourcelanguage="fr"`) : différé.** Ce sprint est
  code-only côté identifiants. Le lot 7 reste optionnel et sera
  déclenché par l'owner i18n dans un sprint séparé — la manipulation
  demande une passe de retraduction du côté `glaneur_fr.ts` qui devient
  cible et non plus source.
- **`review Opus`.** Réservé au lot 4b (rupture de format persistant).
  Les lots 2 (moteur) et 3 (scheduler) restent en Sonnet — ils changent
  l'API interne exportée par `Glaneur.engine.__init__` et
  `Glaneur.scheduler`, mais pas la persistance. Un `review Opus` sur
  Batch 2 se demande à `invariant-reviewer` uniquement si le diff
  découvre une frontière non prévue.
- **Ordre d'exécution retenu.** 0 → 1 → 2 → 3 → 4a → 5 → 6 → 4b → 8.
  Le lot 4b passe en dernier des lots de renommage : il consomme le
  vocabulaire EN adopté par les lots 2/3/5/6, et son shim de compat
  bénéficie des `test_boundaries` mis à jour.
- **Parallélisme.** Autorisé uniquement entre lots 2 (moteur) et 3
  (scheduler), dans deux worktrees. Non recommandé par défaut : les
  tests partagent `conftest.py`, `test_boundaries.py` et le tableau
  d'imports.
