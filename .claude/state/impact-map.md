# Impact Map

<!--
Gabarit temporaire, propre à la tâche courante. Remets-le à cet état vide
entre deux lots. N'y stocke ni copie de fichiers, ni logs, ni résultats de
tests volumineux, ni informations déjà présentes dans CLAUDE.md. Voir
CLAUDE.md section « Impact Map » et « Politique de contexte minimal ».
-->

## Task

**US-VERIF-01 — Cliquet de couverture branché en CI.**

Première US du sprint
`docs/sprints/2026-09-verifier-lots-1-4-avant-lot-5.md`.

`tools/check_coverage.py` et les plafonds par module (`sources/*` 100 %,
`scheduler.py` 100 %, `config.py` 100 %, `engine/*` 95 %) existent déjà,
ainsi que `branch = true` dans `pyproject.toml`. Mais
`.github/workflows/tests.yml` ne lance que `python -m pytest -q` : ni
`--cov`, ni `check_coverage.py`. Le cliquet n'est pas gardé et le lot 5
touchera des formats persistés sans filet.

Objectif : `tests.yml` mesure la couverture branches puis compare aux
plafonds. Aucun code applicatif ne change.

## Directly modified

- `.github/workflows/tests.yml` (deux étapes remplacées : suppression de
  « Run tests », ajout de « Run tests with coverage » puis « Check
  per-module coverage floors »).

## Direct dependencies

- `pyproject.toml` : `[tool.coverage.run] branch = true` et
  `source = ["Glaneur"]` déjà en place — **lu, non modifié**.
- `tools/check_coverage.py` : `FLOORS` et `main()` déjà en place — **lu,
  non modifié**.
- `requirements-dev.txt` : `pytest-cov>=7.1.0` déjà présent — **lu, non
  modifié**.
- `.github/workflows/tests.yml` étapes existantes (checkout, setup-python,
  install Qt libs, install deps, compile translations) : **inchangées**.

## Explicitly out of scope

- **Toute autre étape CI** : ruff, pip-audit, sphinx-build,
  actionlint — traitées par leur propre lot (roadmap 1.4 et 1.5). Ne
  pas les ajouter ici, même si tentant : cela élargirait le périmètre
  au-delà d'US-VERIF-01.
- **Réhausser les plafonds** : ce n'est pas un cliquet qui monte ici,
  c'est un cliquet qu'on branche. Les plafonds actuels reflètent la
  couverture actuelle ; on les monte lors des lots suivants selon la
  règle « le cliquet ne descend jamais ».
- **Code applicatif** (`Glaneur/`) : aucune modification.
- **Tests** : aucun ajout ni suppression. La CI se contente de mesurer la
  suite existante.
- **`__version__`** : inchangé.
- **`.github/workflows/build.yml`, `release.yml`, `build-check.yml`** :
  hors périmètre.

## Tests

Aucun test unitaire à ajouter — la modification est un workflow YAML, pas
du code Python.

Vérifications avant PR :

- Localement, `pytest --cov=Glaneur --cov-branch` puis
  `python tools/check_coverage.py` doivent sortir en code 0. C'est la
  garantie que la PR passera au vert du premier coup en CI.
- Contrôle syntaxique YAML par relecture manuelle, plus `actionlint` si
  disponible sur le poste (non installé par défaut — la relecture manuelle
  suffit pour ce diff minuscule).

## Invariants

- `__version__` inchangé.
- Aucun fichier `Glaneur/` modifié.
- Aucun test ajouté, retiré ou modifié.
- Les plafonds `FLOORS` de `tools/check_coverage.py` sont **exactement**
  ceux mesurés sur `main` à ce jour : le cliquet ne descend jamais et
  ne monte pas non plus dans cette US.
- La matrice de la CI (`ubuntu-latest`, `windows-latest`, Python 3.11)
  reste identique.
- L'étape « Compile translations » reste avant la mesure : sinon le test
  end-to-end de `Glaneur.i18n.installer_traducteur` ne charge pas les
  `.qm` et fausse la couverture.

## Validation

Niveau `local`. Édition d'un unique fichier de workflow, aucun code
applicatif, aucune persistance touchée.

- Pas de `pytest` en supplément côté rédacteur — la CI est le juge.
- Pas d'`invariant-reviewer` — aucun invariant du moteur, aucune
  frontière du package `Glaneur/` n'est concernée.
- Pas de sous-agent `test-author` — aucun test n'est écrit.
- Pas de sous-agent `test-runner` — l'exécution de vérification est
  soit locale (une seule commande), soit la CI de la PR elle-même.
