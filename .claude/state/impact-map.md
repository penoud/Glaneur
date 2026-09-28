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

- `.github/workflows/tests.yml` : « Run tests » remplacé par trois étapes
  conditionnelles — mesure de couverture sur Linux, exécution simple sur
  Windows, contrôle des plafonds par module sur Linux uniquement.
- `tools/check_coverage.py` : `FLOORS` **abaissés à la baseline mesurée**
  (`sources/*` 98.0 %, `scheduler.py` 95.0 %, `config.py` 97.0 %,
  `engine/*` 98.5 %) — les valeurs aspirationnelles 100/100/100 n'avaient
  jamais été gardées en CI. Commentaire ajouté pour expliquer que ce
  sont les valeurs d'entrée du cliquet, à ne monter qu'à mesure que la
  couverture progresse.

## Direct dependencies

- `pyproject.toml` : `[tool.coverage.run] branch = true` et
  `source = ["Glaneur"]` déjà en place — **lu, non modifié**.
- `tools/check_coverage.py` `main()` : logique inchangée, seul le
  dictionnaire `FLOORS` bouge.
- `requirements-dev.txt` : `pytest-cov>=7.1.0` déjà présent — **lu, non
  modifié**.
- `.github/workflows/tests.yml` étapes existantes (checkout, setup-python,
  install Qt libs, install deps, compile translations) : **inchangées**.

## Explicitly out of scope

- **Toute autre étape CI** : ruff, pip-audit, sphinx-build,
  actionlint — traitées par leur propre lot (roadmap 1.4 et 1.5). Ne
  pas les ajouter ici, même si tentant : cela élargirait le périmètre
  au-delà d'US-VERIF-01.
- **Ajouter des tests pour combler les écarts** (`sources/base.py:83`,
  `sources/djangoplicity.py:42-43`, `scheduler.py:166-167`,
  `config.py:305-306`, branches partielles) : reporté à un futur US
  (« raise ratchet »), après US-VERIF-04. La règle « le cliquet ne
  descend jamais » démarre à partir des valeurs branchées ici.
- **Code applicatif** (`Glaneur/`) : aucune modification.
- **Tests** : aucun ajout ni suppression. La CI se contente de mesurer la
  suite existante.
- **Couverture sur Windows** : la mesure branchée reste Linux uniquement,
  parce que `config_dir()` a des embranchements dépendants de l'OS. La
  suite tourne toujours en entier sur Windows.
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
- Les plafonds `FLOORS` posés ici sont la baseline mesurée localement le
  2026-09-28 (`sources/*` 98.11 %, `scheduler.py` 95.12 %, `config.py`
  97.24 %, `engine/*` 98.69 %), arrondie vers le bas pour laisser un
  minuscule matelas numérique (98.0 / 95.0 / 97.0 / 98.5). À partir de
  ce point, le cliquet ne descend jamais : chaque futur PR qui monte la
  couverture doit monter le plafond dans le même diff.
- La mesure et le contrôle des plafonds tournent sur `ubuntu-latest`
  uniquement ; la suite complète tourne sur `windows-latest` sans
  mesure de couverture. La matrice reste identique par ailleurs.
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
