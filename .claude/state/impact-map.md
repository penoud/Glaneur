# Impact Map

<!--
Gabarit temporaire, propre à la tâche courante. Remets-le à cet état vide
entre deux lots. N'y stocke ni copie de fichiers, ni logs, ni résultats de
tests volumineux, ni informations déjà présentes dans CLAUDE.md. Voir
CLAUDE.md section « Impact Map » et « Politique de contexte minimal ».
-->

## Task

**Sprint « Identifiants FR → EN ». Batch 3 — scheduler.**

Renommer la classe `Planificateur` et sa surface :

- `Planificateur → Scheduler`.
- Méthodes publiques : `differer → defer`, `marquer_execution → mark_run`,
  `echeance_atteinte → is_due`, `prochaine → next_run`,
  `derniere → last_run`, `report_actif → defer_active`,
  `est_gele → is_frozen`.
- Méthodes internes : `_retenter_apres → _retry_after` (nom déjà utilisé
  par `Classification.retry_after` dans `sources/base.py`, mais pas de
  conflit — classes distinctes), `_nominale → _nominal`.
- Helper UI : `texte_prochaine → next_run_text` dans
  `Glaneur/scheduler_labels.py`.
- Contexte de traduction Qt `"Planificateur"` : **inchangé** (les entrées
  `.ts` existantes le référencent, comme pour `"Moteur"` au lot 2).

## Directly modified

- Glaneur/scheduler.py               (classe + méthodes)
- Glaneur/scheduler_labels.py        (helper + appels sur Scheduler)
- Glaneur/config.py                  (2 rôles `:meth:` dans les
                                      docstrings de champs, pointant
                                      vers Scheduler.defer / mark_run)
- app.py                             (import + attribut
                                      `self.planificateur` + méthodes)
- cli.py                             (import + `Planificateur(c)` +
                                      `.differer` + `texte_prochaine`)
- tests/test_scheduler.py            (majeur : classes, méthodes,
                                      noms de méthodes de test qui
                                      contiennent `prochaine`, `differer`,
                                      `marquer_execution` etc.)
- tests/test_cli.py                  (import de `texte_prochaine` si
                                      présent)

## Direct dependencies

- CLAUDE.md « Écarts connus » : l'écart moteur reste — pas d'ajout ni
  de retrait par ce lot.
- `translations/*.ts` : le contexte `"Planificateur"` reste littéral,
  les chaînes sources FR (« Mise à jour automatique désactivée », etc.)
  restent bit-à-bit identiques.
- Docs Sphinx : rôles `:class:\`Planificateur\``,
  `:meth:\`Planificateur.…\``, ``\`\`Planificateur\`\``` dans les
  docstrings de `config.py`, `scheduler.py`, `scheduler_labels.py`.
- Frontière 1 (`tests/test_boundaries.py`) : le scheduler reste Qt-free
  (frontière 1 déjà tenue au lot précédent) — le renommage
  n'introduit pas d'import Qt, la ligne du scheduler dans
  `KNOWN_QT_IMPORTS` reste absente.
- `packaging/**` : inchangé.

## Tests

- `pytest tests/test_scheduler.py tests/test_cli.py tests/test_boundaries.py
  tests/test_core.py` — plus un run complet pour non-régression.
- `ruff check` sur les fichiers modifiés.
- Sphinx : même remarque qu'au lot 2 (sphinx-build non installé dans
  l'environnement de travail ; la mise à jour des rôles Sphinx est
  faite en même temps que le renommage).

## Explicitly out of scope

- Champs `Config` — `derniere_execution`, `retenter_apres`,
  `intervalle_heures`, `backoff_niveau` — restent FR (lot 4b).
- Chaînes de traduction Qt (contexte `"Planificateur"` et strings
  sources), CLI flags et messages FR de sortie utilisateur.
- `Glaneur/system.py::est_gele()` — homonyme non-scheduler, appartient
  à un autre module et sera traité au lot 6.
- Renommage éventuel de la variable d'instance `self.planificateur`
  dans `app.py` (attribut de `FenetrePrincipale`) : reste en FR ce lot,
  passera avec un lot UI / app.py dédié plus tard.

## Invariants

- `.qm`/`.ts` inchangés (contexte `"Planificateur"` + sources FR
  identiques).
- Persistence inchangée (aucun champ `Config` renommé).
- Tests passent (surtout `TestPlanificateur*`, `TestTextePresentable*`,
  `TestTextePresentableAvecReport`).

## Validation

Niveau **`full`** selon la table CLAUDE.md (« Moteur, scheduler,
`config.py` » — la ligne du scheduler dans la table demande tests
concernés + ruff + `invariant-reviewer`, mais le renommage traverse
`app.py` et `cli.py` donc on passe la suite complète).

- `pytest` complet + couverture.
- `ruff check` global.
- Sphinx : différé, comme au lot 2.
