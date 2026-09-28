# Sprint CI — Valider l'exe avant de tagger

Emplacement cible dans le dépôt : `docs/sprints/sprint-ci-validation-avant-tag.md`.

## Objectif

Sur `main`, construire et contrôler l'installateur Windows **avant** de créer
le tag, faire valider manuellement l'installateur par le mainteneur, puis
publier **exactement les octets testés**.

Chaîne actuelle :

```
tests → tag → gh workflow run build.yml --ref v<version> → build → publish
```

Chaîne cible, dans **une seule exécution** de `release.yml` :

```
tests → version → build (+ smoke test) → [approbation manuelle] → tag + publish
```

## Contraintes du sprint

- Seuls `.github/workflows/` et la documentation changent. Aucun code
  applicatif ne change : `--controle-bundle` existe déjà dans `app.py`.
- **`__version__` ne change pas.** Toute PR de ce sprint ne publie rien.
- Aucune nouvelle dépendance.
- Commentaires YAML en **anglais**, en expliquant le *pourquoi*.
- La fusion sur `main` et le réglage de l'environnement GitHub reviennent au
  **mainteneur**. Claude Code ouvre la PR en brouillon et s'arrête là.
- Vérification locale avec `actionlint` sur `.github/workflows/`, si
  l'outil est disponible sur le poste. Ce n'est pas une dépendance du projet.

## Décisions et leur raison

| Décision | Raison |
|---|---|
| `build.yml` devient réutilisable (`workflow_call`) et perd `push: tags` | Le dispatch sur le tag n'existait que parce qu'un tag poussé avec `GITHUB_TOKEN` ne déclenche aucun workflow. Il n'est plus nécessaire. |
| Le job `publish` est déplacé de `build.yml` vers `release.yml` | La release reçoit les artifacts du build qui a été testé, dans la même exécution. |
| Le tag est posé explicitement sur `$GITHUB_SHA` | Le tag désigne le commit construit, jamais un commit plus récent. |
| `publish` porte l'environnement `release`, avec relecteur requis | L'exécution s'arrête après le build : le mainteneur télécharge l'installateur, le teste, puis approuve ou rejette. C'est l'approbation prévue au lot 9, mise en place dès maintenant. |
| Un rejet ne crée ni tag ni release | Le numéro de version n'est pas consommé : on corrige, on repousse avec la même `__version__`, et l'exécution suivante reconstruit. |
| Smoke test placé avant la signature | Inutile de signer un bundle cassé. |

**Impasse à ne pas prendre** : valider un exe dans un job, puis laisser
`build.yml` reconstruire sur le tag. On publierait alors un binaire différent
de celui qui a été validé, avec une autre signature.

---

## US-CI-07 — Build, validation puis tag dans `release.yml`

### Modification 1 — `.github/workflows/release.yml` (remplacement complet)

Voir le fichier livré dans cette PR. Points essentiels :

- `permissions: contents: read` au niveau top-level ; plus de
  `actions: write` puisqu'il n'y a plus de `gh workflow run`.
- Concurrence `group: release`, `cancel-in-progress: false` : ne
  jamais couper une exécution en attente d'approbation ou de
  publication.
- Job `tests` : appelle `tests.yml` par `workflow_call`.
- Job `version` : lit et valide `__version__`, décide si un build est
  nécessaire (`release=true` si le tag n'existe pas encore).
- Job `build` : appelle `build.yml` par `workflow_call` avec
  `secrets: inherit` (nécessaire pour `WINDOWS_PFX_*`).
- Job `publish` : sous `environment: release`, télécharge les
  artifacts, pose le tag sur `$GITHUB_SHA`, publie la release. Le
  `--clobber` est sans danger ici : il ne sert qu'à relancer le même
  build (mêmes octets), ce qui ne réintroduit pas le bug corrigé par
  US-CI-01. La logique préversion d'US-CI-02 est conservée : elle lit
  désormais `$TAG` au lieu de `GITHUB_REF_NAME`, qui vaudrait `main`.

L'étape de tag est idempotente : l'attente d'approbation peut durer
des jours, donc elle re-vérifie l'existence du tag au moment de la
publication et n'accepte un tag existant que s'il pointe déjà sur
`$GITHUB_SHA` (reprise après un `Re-run failed jobs`).

### Modification 2 — `.github/workflows/build.yml`

**a. Déclencheurs** : `workflow_call` et `workflow_dispatch`
uniquement. `push: tags` disparaît. Un `workflow_dispatch` seul produit
un installateur en artifact, sans rien publier, depuis n'importe
quelle branche.

**b. Smoke test** dans le job `windows`, juste après l'étape
`pyinstaller` et avant « Sign application when certificate is
configured » :

```yaml
      - name: Smoke test the bundle
        # Windowed exe: launched directly it returns at once and its exit
        # code is lost; Start-Process -Wait -PassThru exposes it.
        shell: pwsh
        run: |
          $p = Start-Process "dist\Glaneur\Glaneur.exe" `
                 -ArgumentList "--controle-bundle" -Wait -PassThru
          if ($p.ExitCode -ne 0) { throw "Bundle check failed: exit code $($p.ExitCode)" }
```

**c. Suppression du job `publish`**, déplacé dans `release.yml`.

**d. Commentaires des blocs Linux et macOS** : ils pointent désormais
vers le job `publish` de `release.yml`. Un rappel est ajouté : à la
réactivation, lire la version dans `__version__`, car `GITHUB_REF_NAME`
vaudra `main`. Le code de ces blocs reste commenté et inchangé.

Le job `windows` reste identique pour le reste, y compris le nom
d'artifact `Glaneur-setup`.

### Modification 3 — documentation

- `docs/sprints/sprint-ci-workflows.md`, section « Procédure de
  reprise », mise à jour :
  - **Installateur rejeté à l'approbation** : corriger, puis repousser
    sur `main` avec la même `__version__`. Aucun tag n'existe.
  - **Échec après approbation** (tag ou upload) : lancer *Re-run failed
    jobs* sur `publish`. L'étape de tag accepte un tag déjà posé sur le
    même commit.
  - L'incrément de *patch* ne sert plus qu'en dernier recours, si un
    tag existe sur un autre commit.
- `README.md` : les passages qui décrivent la publication par `push` de
  tag sont corrigés et mentionnent l'étape d'approbation. Les passages
  sur la signature `WINDOWS_PFX_*` restent tels quels, car ils relèvent
  du lot 9.

### Réglage du dépôt — à faire par le mainteneur, pas par Claude Code

Dans *Settings → Environments → New environment* :

1. Créer l'environnement `release`.
2. Cocher *Required reviewers* et ajouter le mainteneur.
3. **Laisser *Prevent self-review* décoché.** Sinon, un mainteneur seul
   ne peut jamais approuver.
4. Optionnel : restreindre *Deployment branches* à `main`.

Sans ce réglage, `environment: release` est créé automatiquement **sans
protection**, et la publication part sans pause. La PR ne doit pas être
fusionnée avant que le réglage soit fait.

### Vérifié ou supposé

- **Documenté par GitHub** :
  - les environnements avec relecteurs requis sont disponibles sur les
    dépôts publics, quel que soit le plan ;
  - `secrets: inherit` est nécessaire pour que `build.yml` voie
    `WINDOWS_PFX_*`.
- **Supposé, à confirmer au premier essai** :
  - les artifacts produits par un workflow appelé sont téléchargeables
    par un job du workflow appelant ;
  - ils sont visibles sur la page de l'exécution pendant l'attente
    d'approbation (comportement annoncé depuis `upload-artifact` v4).
- **Concurrence** : pendant l'attente, l'exécution occupe le groupe
  `release`. Un deuxième push attend. Un troisième remplace le deuxième
  en file, car GitHub n'en garde qu'un en attente. Le dernier commit
  gagne, ce qui est acceptable.
- **Limites du smoke test** : il couvre les imports de `app.py` au
  niveau module, ainsi que `engine`, `sources` et `updater`. Il ne
  couvre ni l'ouverture de la fenêtre, ni les `.qm`, ni les imports Qt
  paresseux. L'essai manuel avant approbation couvre ces points.

### Critères d'acceptation

Ils s'observent après fusion. Chaque critère coché renvoie à l'URL de
l'exécution qui le prouve.

- [ ] `actionlint` ne signale rien sur `.github/workflows/`.
- [ ] Push sur `main` sans changement de version : `build` et `publish`
      sont *skipped*, et aucune approbation n'est demandée.
- [ ] `workflow_dispatch` de `builds` sur une branche : l'artifact
      `Glaneur-setup` est produit, sans tag ni release.
- [ ] Sur un fork, ou sur une branche avec la garde temporairement
      levée, jamais sur `main`, avec une version `0.0.0-ci.1` :
      - l'exécution s'arrête en *Waiting* et l'installateur est
        téléchargeable ;
      - un rejet ne crée ni tag ni release ;
      - une approbation crée le tag sur le commit construit et une
        release *Pre-release* ;
      - le SHA-256 de l'asset publié est identique à celui de
        l'artifact testé.
- [ ] *Re-run failed jobs* sur `publish` après un échec simulé de
      l'upload : l'étape de tag reprend sans erreur.
- [ ] Contre-épreuve : un module importé par l'application, ajouté à
      `QT_INUTILES` sur une branche jetable, fait échouer le smoke
      test, et aucune approbation n'est demandée.
- [ ] Nettoyage : supprimer les tags et releases de test.

---

## US-CI-08 (optionnelle, PR séparée) — `build-check` réutilise `build.yml`

**Problème.** `build-check.yml` ne compile pas les traductions. Il ne
contrôle donc pas le même bundle que celui qui est publié.

**Modification.**

- Ajouter à `build.yml` une entrée
  `workflow_call.inputs.sign` (booléen, défaut `false`).
- Conditionner les deux étapes de signature à `inputs.sign`. Pour le
  `workflow_dispatch` direct, une entrée équivalente vaut `false` par
  défaut.
- Dans `release.yml`, appeler le build avec `with: { sign: true }`.
- Réduire `build-check.yml` à un seul job qui appelle `build.yml` avec
  `sign: false`, en gardant son filtre `paths` et sa concurrence.

**Raison.** On obtient une seule définition du build, et chaque PR
fournit son installateur en artifact. Un build de PR n'est jamais
signé.

**Critères d'acceptation**

- [ ] Une PR qui touche `Glaneur/` produit l'artifact `Glaneur-setup`,
      non signé, avec des `.qm` présents dans le bundle.
- [ ] La publication sur `main` reste signée quand le certificat est
      configuré.

---

## Definition of Done

- [ ] PR(s) ouvertes en brouillon, avec les critères d'US-CI-07 listés.
- [ ] `__version__` inchangé.
- [ ] Environnement `release` configuré par le mainteneur avant la
      fusion.
- [ ] Procédure de reprise et README à jour.
