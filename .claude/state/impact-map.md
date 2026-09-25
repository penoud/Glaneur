# Impact Map

<!--
Gabarit temporaire, propre à la tâche courante. Remets-le à cet état vide
entre deux lots. N'y stocke ni copie de fichiers, ni logs, ni résultats de
tests volumineux, ni informations déjà présentes dans CLAUDE.md. Voir
CLAUDE.md section « Impact Map » et « Politique de contexte minimal ».
-->

## Task

US-02 du sprint courant : mise en place d'une doc Sphinx minimale dans
`docs/sphinx/`. US-01 est terminée (voir `docs/sphinx/README.md`).

## Directly modified

- docs/sphinx/conf.py               (à créer)
- docs/sphinx/index.rst             (à créer)
- docs/sphinx/Makefile              (à créer)
- docs/sphinx/make.bat              (à créer)
- docs/sphinx/api/                  (généré par sphinx-apidoc, à commiter)
- requirements-doc.txt              (à créer : sphinx, furo)
- .gitignore                        (ajouter docs/sphinx/_build/)

## Direct dependencies

- Glaneur/ — cible d'autodoc, lu par sphinx-apidoc. Pas modifié en US-02.
- docs/sphinx/README.md — décision Napoleon, existe (US-01).

## Tests

- aucun (nouveau outillage, pas de test unitaire pour Sphinx)
- vérification : `sphinx-build -W -n -b html docs/sphinx docs/sphinx/_build/html`

## Potentially affected

- CLAUDE.md — la matrice de validation référence Sphinx sans donner le
  chemin ; à préciser en US-06 (pas en US-02).

## Explicitly out of scope

- Glaneur/**/*.py            (conversion des docstrings = US-03)
- docs/design/, docs/sprints/ (restructuration = US-05)
- .github/workflows/         (intégration CI Sphinx à évaluer après US-02)
- servette/                  (résidu de rename, à traiter séparément)

## Invariants

- aucun invariant du code de production n'est touché
- l'unique invariant nouveau : `sphinx-build -W` doit rester vert dès US-02

## Validation level

subsystem

## Agents

- (aucun) — l'outillage Sphinx se met en place à la main dans la
  conversation principale, sans écriture de test ni exploration coûteuse.
