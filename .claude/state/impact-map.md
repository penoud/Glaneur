# Impact Map

<!--
Gabarit temporaire, propre à la tâche courante. Remets-le à cet état vide
entre deux lots. N'y stocke ni copie de fichiers, ni logs, ni résultats de
tests volumineux, ni informations déjà présentes dans CLAUDE.md. Voir
CLAUDE.md section « Impact Map » et « Politique de contexte minimal ».
-->

## Task

**Sprint « CI — Valider l'exe avant de tagger ». US-CI-07.**

Actuellement, `release.yml` tag puis lance `build.yml` par
`gh workflow run`. Si le build casse, un tag existe sans release.
US-CI-07 remplace cette chaîne par : `tests → version → build (+ smoke)
→ [approbation manuelle] → tag + publish`, tout dans une seule exécution
de `release.yml`.

- `build.yml` devient réutilisable (`workflow_call`) et perd `push: tags`.
- Le job `publish` est déplacé de `build.yml` vers `release.yml`.
- Le tag est posé sur `$GITHUB_SHA` juste avant la publication.
- Un job `publish` sous environnement `release` (relecteurs requis)
  fait pauser l'exécution après le build ; le mainteneur télécharge
  l'installateur, le teste, puis approuve ou rejette.
- Un smoke test `--controle-bundle` est ajouté à `build.yml` avant la
  signature.

## Directly modified

- `.github/workflows/release.yml` (remplacement complet)
- `.github/workflows/build.yml` (triggers + smoke test + suppression job publish)
- `docs/sprints/sprint-ci-validation-avant-tag.md` (nouveau, sprint doc)
- `docs/sprints/sprint-ci-workflows.md` (procédure de reprise)
- `README.md` (mentions de publication par push de tag)

## Direct dependencies

- `app.py` : `--controle-bundle` (existe déjà, ligne 1312) — non modifié.
- `.github/workflows/tests.yml` : appelé par `release.yml` via
  `workflow_call` (déjà en place depuis US-CI-04).
- `.github/workflows/build-check.yml` : hors périmètre US-CI-07 ;
  couvert par US-CI-08 (PR séparée), non entreprise ici.

## Explicitly out of scope

- **`__version__`** : ne change pas. Les PR de ce sprint ne publient rien.
- **US-CI-08** : PR séparée, non traitée dans ce lot.
- **Réactivation Linux/macOS** : les blocs restent commentés, seul le
  commentaire pointe désormais vers `release.yml`.
- **Réglage GitHub `environment: release`** : responsabilité du
  mainteneur avant la fusion.
- **Signature `WINDOWS_PFX_*`** : inchangée (relève du lot 9).
- **AppStream metainfo** : inchangé (en attente avec Linux).
- **Frontière 1 (`QCoreApplication`)** : distinct du sprint.

## Tests

Aucun test unitaire à ajouter — les workflows ne s'exécutent pas contre
le faux serveur. Vérifications :

- `actionlint` local si disponible (non installé sur ce poste).
- Critères d'acceptation observés après fusion (voir sprint doc).

## Invariants

- `__version__` inchangé.
- Aucun code applicatif Python modifié.
- La release publie **exactement les octets testés** au smoke test et
  à l'essai manuel.
- Le tag désigne le commit qui a été construit (`GITHUB_SHA`), jamais
  un commit plus récent.
- Un rejet ne consomme pas la version : ni tag ni release.

## Validation

Niveau `local`. Édition workflows + docs. Pas de pytest, pas de
`invariant-reviewer` (aucun invariant du moteur ou de la persistance
n'est touché ; le sprint ne modifie ni `Glaneur/`, ni le format des
fichiers persistés). Relecture manuelle des YAML et cohérence avec la
procédure de reprise documentée.
