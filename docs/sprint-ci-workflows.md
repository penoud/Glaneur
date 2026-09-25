# Sprint CI — Fiabiliser la chaîne GitHub Actions

Emplacement proposé dans le dépôt : `docs/sprint-ci-workflows.md`.

## Objectif

Rendre la chaîne `tests → tag → build → release` sûre **avant** l'extraction de
`sources/wordpress.py`. On corrige deux bugs de publication, on supprime les
exécutions redondantes, et on détecte les problèmes de packaging **avant**
qu'un tag soit créé.

Ce sprint ne modifie que `.github/workflows/`. La seule exception est une option
de contrôle ajoutée à l'application (US-CI-06). **`__version__` ne change pas** :
les PR de ce sprint ne publient rien.

## État de départ (vérifié dans les fichiers)

| Workflow | Déclencheurs | Rôle |
|---|---|---|
| `tests.yml` | `push` sur `main`, `pull_request` | pytest sous Ubuntu |
| `release.yml` | `push` sur `main`, `workflow_dispatch` | pytest (doublon), lecture de `__version__`, tag, `gh workflow run build.yml --ref v<version>` |
| `build.yml` | `push` de tags `v*`, `workflow_dispatch` | PyInstaller, signature, Inno Setup, `.sha256`, Release (job `publish` limité aux refs `refs/tags/v*`) |

Le déclenchement explicite de `build.yml` est volontaire : un tag poussé avec
`GITHUB_TOKEN` ne déclenche aucun autre workflow. Il faut le conserver.

## Découpage en PR

| PR | Stories | Risque |
|---|---|---|
| 1 | US-CI-01, US-CI-02 | Faible, corrige la publication |
| 2 | US-CI-03, US-CI-04 | Faible, restructure `release.yml` |
| 3 | US-CI-05 | Moyen, peut révéler des tests qui échouent sous Windows |
| 4 | US-CI-06 | Moyen, touche `app.py` et ajoute un workflow |

Chaque PR est ouverte en brouillon dès le premier commit, pour que les tests
tournent à chaque push.

---

## US-CI-01 — Ne plus reconstruire la release courante

**Problème.** Dans `release.yml`, le `exit 0` de « Create and push version tag »
ne termine que cette étape. « Trigger installer builds » n'a pas de condition :
chaque push sur `main` sans changement de version relance `build.yml` sur le
tag existant, et `--clobber` remplace les assets. On obtient de nouveaux
binaires et une nouvelle signature pour la même version. Entre les deux
téléversements, l'installateur et son `.sha256` ne correspondent plus, et
l'updater rejette la mise à jour.

**Modification** (`release.yml`) :

```yaml
      - name: Create and push version tag
        id: tag
        # … env et shell inchangés
        run: |
          tag="v$VERSION"
          if git ls-remote --exit-code --tags origin "refs/tags/$tag" >/dev/null 2>&1; then
            echo "Tag $tag already exists; nothing to tag."
            echo "created=false" >> "$GITHUB_OUTPUT"
            exit 0
          fi
          # … configuration git, tag et push inchangés
          echo "created=true" >> "$GITHUB_OUTPUT"
      - name: Trigger installer builds
        if: steps.tag.outputs.created == 'true'
        # … inchangé
```

**Contrepartie acceptée.** Si le tag est créé mais que le déclenchement échoue,
relancer `release.yml` ne relancera plus le build. La reprise se fait à la main
(voir §Procédure de reprise).

**Critères d'acceptation**

- [ ] Un push sur `main` sans changement de version : `release.yml` passe au
      vert et aucune exécution de `builds` n'apparaît.
- [ ] Les assets de la dernière release gardent leur date et leur SHA-256.

## US-CI-02 — Publier les préversions comme telles

**Problème.** La validation `[0-9]*.[0-9]*.[0-9]*` accepte `1.0.5-rc.1`, mais
`gh release create` ne reçoit pas `--prerelease`. Or
`GitHubReleaseProvider._is_stable` se fie au drapeau GitHub, pas au nom du tag.
Une rc serait donc proposée comme mise à jour stable.

**Choix.** On marque la release comme préversion plutôt que de refuser le
suffixe. Ça garde la possibilité de publier des rc de test pendant le
multi-sources sans toucher les utilisateurs, et l'updater ignore déjà les
préversions (couvert par `test_github_provider_ignores_prerelease_and_draft`).

**Modification** (`build.yml`, job `publish`) :

```bash
          prerelease=()
          [[ "$GITHUB_REF_NAME" == *-* ]] && prerelease=(--prerelease)
          if ! gh release view "$GITHUB_REF_NAME" --repo "$GITHUB_REPOSITORY" >/dev/null 2>&1; then
            gh release create "$GITHUB_REF_NAME" \
              --repo "$GITHUB_REPOSITORY" \
              --verify-tag "${prerelease[@]}" \
              --title "WpImageDownloader $GITHUB_REF_NAME" \
              --notes "Automated release $GITHUB_REF_NAME"
          fi
```

**Critères d'acceptation**

- [ ] Vérification hors `main` : pousser à la main un tag `v0.0.0-ci.1` sur un
      commit de la branche de la PR. `builds` se déclenche par `push: tags`,
      et la release est créée avec le badge *Pre-release*.
- [ ] Supprimer ensuite la release et le tag de test.

> Supposé, à confirmer au premier essai : `"${prerelease[@]}"` vide ne produit
> aucun argument sous le bash des runners Ubuntu (bash ≥ 4.4).

## US-CI-03 — Garde de branche et concurrence

**Problèmes.**

- `workflow_dispatch` sur `release.yml` lancé depuis une autre branche
  taguerait et publierait le commit de cette branche.
- Deux pushes rapprochés sur `main` lancent deux `release.yml` qui peuvent
  tenter le même tag.

**Modification** (`release.yml`, en tête et sur le job de tag) :

```yaml
concurrency:
  group: release
  cancel-in-progress: false   # ne jamais couper un tag ou un dispatch en cours

jobs:
  tag:
    if: github.ref == 'refs/heads/main'
```

**Critères d'acceptation**

- [ ] `workflow_dispatch` de `release.yml` depuis une branche : job *skipped*.
- [ ] Deux pushes successifs sur `main` : la seconde exécution attend la première.

## US-CI-04 — Une seule définition des tests

**Problème.** Les tests tournent deux fois à chaque push sur `main`, et leur
définition est dupliquée (paquets apt, dépendances, commande).

**Choix.** Un workflow réutilisable (`workflow_call`) plutôt qu'une action
composite. C'est le mécanisme natif pour enchaîner des jobs entre workflows, et
il ne demande aucun fichier supplémentaire.

**Modification** (`tests.yml`) :

```yaml
on:
  pull_request:
  workflow_call:

concurrency:
  # Sur une PR, un nouveau push rend l'exécution précédente sans intérêt.
  group: tests-${{ github.workflow }}-${{ github.head_ref || github.run_id }}
  cancel-in-progress: true
```

Le `push: main` de `tests.yml` disparaît : sur `main`, c'est `release.yml` qui
l'appelle.

**Modification** (`release.yml`) : le job `test-and-tag` est scindé en deux.

```yaml
jobs:
  tests:
    if: github.ref == 'refs/heads/main'
    uses: ./.github/workflows/tests.yml

  tag:
    needs: tests
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      # checkout, setup-python, lecture de version, tag, dispatch
      # (les étapes apt, pip pytest et « Run tests before tagging » sont supprimées)
```

`fetch-depth: 0` peut être retiré : l'existence du tag est testée par
`git ls-remote`, pas dans l'historique local.

> Point d'attention : dans `tests.yml`, `github.head_ref` est vide lors d'un
> appel par `workflow_call` depuis un push. Le repli sur `run_id` isole alors
> chaque exécution, pour qu'un test de release ne soit jamais annulé.

**Critères d'acceptation**

- [ ] Push sur `main` : une seule exécution de pytest, visible comme job
      `tests / tests` dans `tag-release`.
- [ ] Un test volontairement cassé sur une branche de vérification empêche le
      job `tag` de démarrer (à vérifier sur un fork ou sur une branche en
      dispatch avec garde temporairement levée, jamais sur `main`).
- [ ] Deux pushes rapides sur une PR : la première exécution est annulée.

## US-CI-05 — Tests sous Windows

**Pourquoi.** Plusieurs invariants sont plus fragiles sous Windows : le
`replace` atomique sur un fichier ouvert, le verrouillage des `.part`, et
`systeme.py`. Aujourd'hui, rien ne les teste sur la plateforme principale. Pour
un dépôt public, le coût en minutes est nul.

**Modification** (`tests.yml`) :

```yaml
jobs:
  tests:
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, windows-latest]
    runs-on: ${{ matrix.os }}
    steps:
      # … checkout, setup-python inchangés
      - name: Install Qt runtime libs (offscreen)
        if: runner.os == 'Linux'
        # … inchangé
      # … installation des dépendances et pytest inchangés
```

> Supposé : le plugin `offscreen` est livré dans les wheels
> `PySide6-Essentials` pour Windows, et `QT_QPA_PLATFORM=offscreen` y
> fonctionne. À confirmer à la première exécution.

**Risque.** Des tests peuvent échouer sous Windows (séparateurs de chemin,
fichiers restés ouverts dans les fixtures). On limite le temps passé à les
corriger dans ce sprint. Un test qui révèle un vrai bug du moteur sort du sprint
et devient une issue ; il est alors marqué `xfail` sous Windows, avec le numéro
d'issue en raison.

**Critères d'acceptation**

- [ ] La matrice passe sur les deux OS, ou chaque `xfail` Windows renvoie à une
      issue ouverte.

## US-CI-06 — Contrôler le packaging avant le tag

**Problème.** PyInstaller n'est exécuté qu'après création du tag. Un exe
cassé, par exemple un module manquant dans le bundle, laisse un tag sans
release, et ce tag ne peut plus être recréé. L'extraction de `sources/` est
exactement ce type de changement.

**Partie 1 — option de contrôle dans l'application** (`app.py`, tout en haut du
point d'entrée, avant la création de `QApplication`) :

```python
if "--controle-bundle" in sys.argv:
    # Importe ce que PyInstaller pourrait avoir oublié, sans ouvrir de fenêtre.
    # Le résultat passe par le code de sortie : en mode fenêtré,
    # sys.stdout peut valoir None et un print lèverait une exception.
    import WpImageDownloader.engine  # noqa: F401
    # Quand sources/ existera : import WpImageDownloader.sources
    sys.exit(0)
```

> Supposé : le `.spec` construit l'exe en mode fenêtré (`console=False`), d'où
> le choix du code de sortie plutôt que d'une sortie texte. Si l'exe est en mode
> console, rien ne change.

**Partie 2 — nouveau workflow** `.github/workflows/build-check.yml` :

```yaml
name: build-check

on:
  pull_request:
    paths:
      - "WpImageDownloader/**"
      - "app.py"
      - "cli.py"
      - "build/**"
      - "requirements.txt"
      - ".github/workflows/build-check.yml"

concurrency:
  group: build-check-${{ github.head_ref }}
  cancel-in-progress: true

jobs:
  windows:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v5
      - uses: actions/setup-python@v6
        with:
          python-version: "3.11"
      - run: pip install -r requirements.txt pyinstaller
      - run: pyinstaller build\WpImageDownloader.spec --noconfirm --clean
      - name: Smoke test du bundle
        shell: pwsh
        run: |
          $p = Start-Process "dist\WpImagerDownloader\WpImagerDownloader.exe" `
                 -ArgumentList "--controle-bundle" -Wait -PassThru
          if ($p.ExitCode -ne 0) { throw "Bundle KO : code $($p.ExitCode)" }
```

Il n'y a ni signature ni Inno Setup ici : on contrôle le contenu du bundle, pas
la chaîne de publication. `Start-Process -Wait` est nécessaire, car un exe
fenêtré lancé directement rend la main tout de suite et son code de sortie
serait perdu.

**À ne pas faire** : déclarer `build-check` comme *required status check* dans
la protection de branche. À cause du filtre `paths`, une PR qui ne touche pas
ces chemins ne le lance jamais, et la vérification requise resterait en
attente indéfiniment.

**Critères d'acceptation**

- [ ] Une PR qui touche `WpImageDownloader/` lance `build-check`, qui passe.
- [ ] Contre-épreuve sur une branche jetable : ajouter à `QT_INUTILES` un module
      Qt réellement importé par l'application. Le smoke test doit échouer.
- [ ] Une PR qui ne touche que `docs/` ne lance pas `build-check`.

---

## Hors périmètre

- **Réactivation Linux / macOS.** Le bloc macOS vise `macos-13`, une image que
  GitHub a retirée d'après mes informations (non vérifié à ce jour). Il faudra
  passer à `macos-14` ou plus récent, donc Apple Silicon, ce qui change
  l'architecture du `.app`. C'est à traiter après le multi-sources.
- **Factorisation de la signature.** Le bloc `signtool` est dupliqué dans
  `build.yml`. C'est gênant mais sans risque, donc on ne le touche pas.
- **Protection de branche sur `main`.** C'est un réglage du dépôt, pas un
  fichier. À décider à part : l'imposer obligerait à passer par une PR pour
  tout changement.

## Procédure de reprise : tag créé, release absente

À documenter dans le README de contribution une fois US-CI-01 fusionnée.

1. **Le build a échoué pour une cause externe** (runner, Chocolatey,
   horodatage) : relancer les jobs échoués de l'exécution `builds`, ou lancer
   `builds` en `workflow_dispatch` avec la ref `v<version>`.
2. **Le build a échoué à cause du code** : corriger, puis incrémenter le
   *patch* de `__version__`. Ne pas supprimer le tag, pour que l'historique
   reste lisible. Comme aucune release n'a été publiée, aucun utilisateur n'a
   reçu cette version.

## Vérification

Les workflows ne se testent pas contre le faux serveur. On vérifie donc :

- avant chaque push, en local et de façon facultative : `actionlint` sur
  `.github/workflows/`. C'est un outil du poste de développement, pas une
  dépendance du projet ;
- après fusion, par les scénarios observables des critères d'acceptation.
  Chaque critère coché renvoie à l'URL de l'exécution qui le prouve.

## Definition of Done

- [ ] Les quatre PR sont fusionnées, chacune avec ses critères cochés et les
      liens des exécutions correspondantes.
- [ ] Un push sur `main` sans changement de version ne déclenche aucun build.
- [ ] Sur `main`, pytest tourne une seule fois, sous Ubuntu et Windows.
- [ ] Toute PR touchant le code ou le packaging produit un bundle Windows
      contrôlé.
- [ ] `__version__` est inchangé sur l'ensemble du sprint.
- [ ] La procédure de reprise est documentée.
