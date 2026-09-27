# Impact Map

<!--
Gabarit temporaire, propre à la tâche courante. Remets-le à cet état vide
entre deux lots. N'y stocke ni copie de fichiers, ni logs, ni résultats de
tests volumineux, ni informations déjà présentes dans CLAUDE.md. Voir
CLAUDE.md section « Impact Map » et « Politique de contexte minimal ».
-->

## Task

**Sprint « Identifiants FR → EN ». Batch 1 — sweep résiduel des commentaires
et docstrings français.**

Le lot « docstrings-en » (2026-09-26) a passé `Glaneur/` en anglais côté
docstrings. Les tests n'y sont pas passés : plusieurs modules gardent une
docstring de module et des docstrings de méthode en français, plus quelques
commentaires `#`. Un seul commentaire résiduel subsiste dans la prod
(`Glaneur/engine/core.py:530`) — non couvert par la sweep précédente parce
que le mot est dans une prose entre parenthèses, pas dans une docstring.

Ce lot **ne touche à aucun identifiant** : références comme `nettoyer()`,
`télécharger()`, `Moteur.executer`, `cfg.dossier`, `'fichier'` (clé JSON)
restent telles quelles — leur renommage est le travail des lots 2 à 6.

## Directly modified

- Glaneur/engine/core.py                    (1 commentaire, ligne 530)
- tests/test_bug_report.py                  (docstring de module)
- tests/test_config.py                      (docstring de module)
- tests/test_core.py                        (2 séparateurs `#` + docstrings)
- tests/test_scheduler.py                   (docstring de module + comm.)
- tests/test_source_base.py                 (docstrings + 2 séparateurs)
- tests/test_source_djangoplicity.py        (docstring de module)
- tests/test_source_wordpress.py            (docstring de module)
- tests/test_system.py                      (docstring de module)
- tests/test_updater_threads.py             (docstring de module)
- tests/test_logsetup.py                    (docstring de module)

## Direct dependencies

Aucune. Sweep textuelle sans changement d'API ni de comportement.

## Tests

- Ruff ciblé sur chaque fichier modifié (les docstrings changées peuvent
  déclencher les règles `D` si un style Google-Napoleon est enfreint —
  peu probable ici mais à vérifier).
- Pas d'exécution des tests fonctionnels concernés : les docstrings et
  commentaires n'affectent pas l'exécution des tests. Un simple
  `pytest --collect-only` sur le paquet `tests/` suffit à confirmer
  qu'aucun fichier ne casse à la collecte (encoding, syntaxe des
  triple-quotes après édition, etc.). Validation `local` selon la
  table de CLAUDE.md.

## Explicitly out of scope

- Renommage d'identifiants (lots 2 à 6, 4b).
- Traduction des chaînes littérales FR utilisées comme clés/valeurs
  (`'fichier'`, `"transitoire"`, `"coupure"`, `"definitif"`,
  `"introuvable"`, `"illisible"`, `"divers"`, `"galerie"`, `"date"`,
  `"plat"`, `"Manuel"`, `"1 heure"`…). Ces chaînes sont soit persistées,
  soit affichées, soit des clés de dispatch : elles changent seulement
  quand un lot d'identifiants les prend en charge.
- Docstrings production dans `Glaneur/` déjà passées par le lot
  « docstrings-en ». On ne les rejoue pas.
- Commentaires `#` de la prod qui référencent un identifiant FR à
  renommer plus tard (`nettoyer()`, `Moteur.fichier_complet`, `cfg.dossier`,
  `'fichier'`) : ces références suivront leur renommage dans le bon
  lot.
- Frontière 1 et test `test_boundaries.py::test_no_qt_outside_ui[…]` :
  aucun rapport avec la sweep.

## Invariants

- **Aucun identifiant Python n'est renommé.**
- **Aucune chaîne littérale n'est modifiée.** Les libellés utilisés en
  dispatch (`"transitoire"`, `"coupure"`, `"definitif"`, `"introuvable"`,
  `"galerie"`, etc.) restent bit-à-bit identiques.
- Les docstrings restent en style Napoleon (Google) — la sweep ne doit
  pas casser un `Args:` ou `Returns:` en tête de docstring existante.
- Les tests continuent d'être collectés et de passer sans changement
  d'assertions.

## Validation

Niveau `local` selon la table CLAUDE.md (« Python local » — tests
concernés + ruff ciblé). Ce lot ne concerne aucune frontière ni
invariant du code exécutable, ne modifie aucune API publique, ne touche
pas à la persistance, ne modifie ni `docs/sphinx/**` ni `packaging/**`.

- `ruff check` sur les 11 fichiers modifiés.
- `pytest --collect-only tests/test_bug_report.py tests/test_config.py
  tests/test_core.py tests/test_scheduler.py tests/test_source_base.py
  tests/test_source_djangoplicity.py tests/test_source_wordpress.py
  tests/test_system.py tests/test_updater_threads.py tests/test_logsetup.py`
  — les collecter suffit à valider la sweep. Une exécution complète de
  la suite n'est pas justifiée par l'impact.
