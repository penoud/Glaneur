# Sprint — Vérifier lots 1→4 avant d'ouvrir lot 5

Emplacement cible dans le dépôt :
`docs/sprints/2026-09-verifier-lots-1-4-avant-lot-5.md`.

## Objectif

Rendre les lots 1 à 4 de `docs/design/roadmap.md` suffisamment solides pour
que le lot 5 (profils) puisse s'ouvrir sans dette cachée. Le sprint **vérifie**
l'existant et **ne corrige que ce qui bloque le lot 5**. Tout le reste des
lots 1 à 4 reste à sa place, dans son propre lot.

Ce sprint ne publie rien : `__version__` ne change pas.

## État observé le 2026-09-28 (état de départ)

Constaté à la lecture du code sur la branche `update-docs`. « Fait » signifie
observé, « partiel » signifie présent mais incomplet par rapport à
`docs/design/roadmap.md`, « manquant » signifie absent.

| Élément | État | Preuve |
|---|---|---|
| 1.1 Couverture branches + cliquet | partiel | `pyproject.toml` (`branch = true`) et `tools/check_coverage.py` (plafonds par module) existent, mais **`.github/workflows/tests.yml` ne lance ni `--cov` ni `check_coverage.py`**. Le cliquet n'est pas gardé. |
| 1.2 Faux serveur HTTP local | manquant | Aucun `ThreadingHTTPServer` dans `tests/`. |
| 1.3 Tests réseau `@pytest.mark.network` | manquant | Marker non enregistré ; pas de workflow dédié. |
| 1.4 Ruff, pip-audit, Dependabot | partiel | `ruff.toml` n'active que `ARG, RUF` au-dessus du défaut Ruff. Ruff pas exécuté en CI. `pip-audit` pas exécuté. **Dependabot fait** (`.github/dependabot.yml`). |
| 1.5 Sphinx + docstrings Google | partiel | `docs/sphinx/conf.py` complet et `requirements-doc.txt` en place, mais **Sphinx pas exécuté en CI** et pas de règles pydocstyle `D` dans Ruff. |
| 2 Identifiants et docstrings en anglais | fait | Vérifié dans `engine/core.py`, `sources/base.py`, `config.py`. |
| 2 Sources de `tr()` en français | connu | 17 occurrences `QCoreApplication.translate("Moteur", <FR>)` dans `engine/core.py`. |
| 2 `QCoreApplication` dans le moteur (frontière 1) | connu | `Glaneur/engine/core.py:20`. |
| 2 Événements structurés du moteur | manquant | Le moteur passe des chaînes déjà traduites au callback `journal(str)`. |
| 3.1 Politique de reprise de `Transport.get_json` | bug | `sources/base.py:264-275` : réessaie tout `RequestException` (donc **les 4xx**), attend `2×(tentative+1)` s (2/4/6 au lieu de 2/4), **`Retry-After` extrait mais jamais utilisé** dans la boucle. Arrêt coopératif OK. |
| 3.1 Reprise partagée avec `Engine.download` | manquant | `engine/core.py:302-339` : une seule tentative, l'échec remonte au circuit-breaker de la boucle `run`. |
| 3.2 Erreur fatale explicite sur API racine | partiel | Classifié `definitif` par `classify_error`, mais `get_json` remonte un `RuntimeError` générique. |
| 3.3 Validation avant renommage du `.part` | manquant | `engine/core.py:321` `tmp.replace(dest)` sans magic-bytes, ni taille, ni Checksum. |
| 3.4 Manifeste par lots | partiel | Sauvegarde toutes les 25 images + `finally:` sur interruption. Pas de flush temporel (30 s). |
| 4 Verrou OS par dossier | manquant | `engine/_locks.py` = un `threading.Lock` de processus, pour la fusion du manifeste. Aucun `fcntl.flock` ni `msvcrt.locking`. |

## Ce qui bloque réellement le lot 5

Trois blocages fonctionnels, un blocage de filet de sécurité.

- **Lot 5.0 E2** — la colonne « statut » de la liste des profils lit des
  **événements structurés** du moteur (`docs/design/evolution-multi-sources.md`
  §4). Sans lot 2, on ne peut pas la construire.
- **Lot 5.2** — file d'un seul worker traitant un profil à la fois, plus le
  rattrapage après extinction du PC. Requiert un **verrou OS par dossier cible**
  (roadmap lot 4). Un `threading.Lock` ne protège pas contre l'application UI
  ouverte + tâche planifiée + ancienne installation résiduelle.
- **Lot 5.2** — le calcul de créneau utilise `retry_after`. Si
  `Transport.get_json` retente les 4xx et ignore `Retry-After`, on empoisonne
  la règle I/2 (roadmap §5.2). Correction ciblée du lot 3.1 requise.
- **Lot 5.1** — v2 du `config.json` = **changement de format persisté**. Le
  cliquet de couverture doit tourner en CI comme filet de sécurité (lot 1.1
  fin).

Le reste (1.2, 1.3, 1.4 ruff/pip-audit, 1.5 pydocstyle, 3.1 download, 3.2, 3.3,
3.4 timer) améliore le projet mais n'empêche pas d'ouvrir le lot 5. Chacun
reste à sa place dans son propre lot.

## Contraintes du sprint

- **`__version__` ne change pas.** Aucune PR de ce sprint ne publie.
- Aucune nouvelle dépendance d'exécution. `pytest-cov` et `ruff` sont déjà
  dans `requirements-dev.txt`.
- Commentaires de code, docstrings et messages de log **en anglais**. Les
  chaînes UI restent traduites, mais **la source est l'anglais** (base de
  départ de la conversion `.ts` prévue au lot 2 complet).
- Un seul rédacteur à la fois sur le code de production. Les US-VERIF-01
  et US-VERIF-03 sont indépendantes et peuvent tourner en parallèle dans
  deux worktrees séparés ; US-VERIF-02 puis US-VERIF-04 se font en série
  car elles touchent respectivement `sources/base.py` et `engine/core.py`.
- Chaque US ouvre sa propre PR en brouillon, avec un `.claude/state/impact-map.md`
  remis à zéro à son démarrage, comme prévu par `CLAUDE.md` section « Impact Map ».
- Jamais de push, de tag, ni de modification de `__version__`. Les hooks
  bloquent ; on ne les contourne pas.

## Décisions et leur raison

| Décision | Raison |
|---|---|
| Ne pas couvrir tout le lot 1 dans ce sprint | 1.2 (faux serveur local) et 1.3 (tests réseau) apportent de la qualité de test, pas un déblocage du lot 5. Les traiter ici les entraîne dans des questions de matrice CI qui doublent la durée du sprint. |
| Corriger `Transport.get_json` seulement, pas `Engine.download` | La roadmap 3.1 les veut unifiés, mais aujourd'hui le circuit-breaker de la boucle `run` (5 échecs consécutifs → `defer`) absorbe déjà l'absence de reprise dans `download`. Le lot 5.2 n'en dépend pas. |
| US-VERIF-04 en dernier | C'est la modification la plus large (tous les `translate()` du moteur, plus la couche UI qui les rendra). Elle bénéficie du filet de sécurité (US-VERIF-01) et du verrou (US-VERIF-03) déjà verts. |
| Ne pas toucher aux clés FR du manifeste ni aux champs FR d'`Element` | CLAUDE.md liste explicitement ces écarts comme reportés à leur propre lot. Les rouvrir ici cascade sur trop de fichiers. |
| Cliquet de couverture branché uniquement sur les modules déjà à leur plafond | Les plafonds actuels (`sources/*` 100 %, `scheduler.py` 100 %, `config.py` 100 %, `engine/*` 95 %) sont ceux mesurés à ce jour. On les grave dans le CI ; on les monte lors des lots suivants selon la règle « le cliquet ne descend jamais ». |

---

## US-VERIF-01 — Cliquet de couverture branché en CI (lot 1.1, fin)

### Modification 1 — `.github/workflows/tests.yml`

Une seule étape ajoutée après « Run tests ». La couverture est mesurée par
`--cov=Glaneur --cov-branch`, puis `tools/check_coverage.py` compare le
résultat aux plafonds par module.

```yaml
      - name: Run tests with coverage
        env:
          QT_QPA_PLATFORM: offscreen
        run: python -m pytest -q --cov=Glaneur --cov-branch

      - name: Check per-module coverage floors
        run: python tools/check_coverage.py
```

L'ancienne étape « Run tests » disparaît. La matrice reste inchangée
(`ubuntu-latest`, `windows-latest`, Python 3.11), la mesure marche
identiquement sur les deux OS.

### Modification 2 — `pyproject.toml`

`fail_under` global reste à `0` (les plafonds par module font foi). On ne
touche pas à ce fichier dans cette US.

### Vérifié ou supposé

- **Vérifié** : les plafonds actuels sont ceux mesurés. Une exécution locale
  de `pytest --cov=Glaneur --cov-branch` puis `python tools/check_coverage.py`
  doit sortir en 0 avant de fusionner la PR.
- **Supposé** : sur Windows, `coverage.Coverage.load()` lit correctement le
  `.coverage` produit par pytest-cov. À confirmer en CI dès le premier run.

### Critères d'acceptation

- [ ] `tests.yml` lance `pytest --cov=Glaneur --cov-branch` puis
      `tools/check_coverage.py`, sur `ubuntu-latest` et `windows-latest`.
- [ ] Une PR de contrôle qui casse volontairement un test (couverture au
      passage) échoue au job `tests`.
- [ ] Une PR de contrôle qui retire une branche testée dans `sources/`
      (couverture passe de 100 % à 99 %) échoue au job « Check per-module
      coverage floors ».
- [ ] La PR de cette US passe au vert du premier coup après merge — c'est-à-dire
      que les plafonds inscrits dans `check_coverage.py` sont respectés par
      la suite actuelle.

---

## US-VERIF-02 — Politique de reprise de `Transport.get_json` (lot 3.1, cœur)

### Contexte

Aujourd'hui, `Glaneur/sources/base.py:264-275` (`Transport.get_json`) réessaie
tout `requests.RequestException` — donc 401, 403, 404 comme un timeout. La
pause est `2 × (tentative + 1)` secondes (2, 4, 6). `Retry-After` est bien
extrait par `_retry_after` mais uniquement consommé dans le chemin
`Engine.download`, jamais dans la boucle de `get_json`.

### Modification 1 — `Glaneur/sources/base.py`

`get_json` s'appuie sur `classify_error` :

- 3 tentatives au total. Pause entre tentatives = 2 s puis 4 s (roadmap 3.1).
- Sur `classify_error` = `"definitif"` (400 hors `fin_si`, 401, 403, 404, 405,
  410, `MissingSchema`, `InvalidURL`…), on relance immédiatement l'exception
  d'origine sans réessayer.
- Sur `"transitoire"` ou `"coupure"`, on réessaie. Si `retry_after` est fourni
  par le serveur (`Retry-After` en secondes ou HTTP-date), on l'utilise, mais
  **plafonné à 120 s**. Au-delà, on relance sans attendre indéfiniment.
- Chaque attente reste `Event`-interruptible (déjà géré par
  `Transport.sleep`).

`fin_si` est appliqué **avant** classification comme aujourd'hui : un 400 avec
`fin_si={400}` (pagination WordPress) reste une fin normale, jamais un échec.

### Modification 2 — tests

Le rédacteur est le sous-agent `test-author`. Cibles dans
`tests/test_source_base.py` :

- 401, 403, 404 (hors `fin_si`) : levée immédiate, **une seule** tentative,
  aucun `sleep`.
- 429 avec `Retry-After: 3` : `Transport.sleep` appelé avec 3 s, deuxième
  tentative en succès.
- 429 avec `Retry-After: 300` : `Transport.sleep` appelé avec **120 s**, pas
  300 s.
- Trois échecs 500 consécutifs : pauses observées 2 s puis 4 s (deux pauses
  pour trois tentatives). L'ancienne troisième pause de 6 s ne doit plus
  apparaître.
- Arrêt coopératif : `Transport.arret.set()` pendant la pause fait remonter
  `Interrupted` sans nouvelle requête.
- `fin_si={400}` avec réponse 400 : retour `(None, headers)`, aucune reprise.

Les tests existants qui reposaient sur la boucle 2/4/6 doivent être mis à
jour au même commit.

### Vérifié ou supposé

- **Vérifié** : `classify_error` existe déjà (`sources/base.py:90`) et couvre
  les cas nécessaires ; les tables `_CUT_STATUSES` et `_DEFINITIVE_STATUSES`
  sont exhaustives.
- **Vérifié** : `Transport.sleep` fragmente l'attente et coopère à l'arrêt.
- **Supposé** : aucun test existant ne vérifie la troisième pause à 6 s
  comme comportement voulu. À contrôler avant de basculer.

### Critères d'acceptation

- [ ] La suite existante reste verte.
- [ ] Les nouveaux tests listés ci-dessus passent.
- [ ] Aucun `sleep(6)` observé dans les traces de `test_source_base.py`.
- [ ] Le plafond de couverture de `Glaneur/sources/*` reste à 100 %.
- [ ] Relecture `invariant-reviewer` (frontière `Transport`).

---

## US-VERIF-03 — Verrou OS par dossier cible (lot 4)

### Contexte

Aujourd'hui, `Glaneur/engine/_locks.py` = `threading.Lock` de processus, pour
la fusion du manifeste UI ↔ moteur. Le lot 5.2 introduit une file de profils
puis (lot 8) une tâche planifiée horaire. À ce moment-là, deux triggers
peuvent atterrir en même temps sur le même dossier : application UI ouverte
et tâche planifiée, ou installation résiduelle de l'ancien binaire. Un
`threading.Lock` ne protège pas entre processus.

Choix : un verrou OS par dossier cible, portable, sans dépendance.

### Modification 1 — `Glaneur/engine/_folder_lock.py` (nouveau)

Module isolé avec un context manager :

```python
from contextlib import contextmanager
from pathlib import Path

@contextmanager
def folder_lock(target_dir: Path) -> Iterator[None]:
    """Hold an exclusive OS lock on ``target_dir/.glaneur.lock``.

    Uses ``fcntl.flock`` on POSIX and ``msvcrt.locking`` on Windows. The
    file body carries PID/host/UTC time for diagnostics only — the OS
    lock is the real gate, not the file's content. Raises
    :class:`FolderBusy` if the lock is already held.
    """
```

- POSIX : `fcntl.flock(fd, LOCK_EX | LOCK_NB)`. Sur `BlockingIOError`, lever
  `FolderBusy`. Libéré par le `close()` du descripteur, sûr même si le
  processus meurt.
- Windows : `msvcrt.locking(fd, LK_NBLCK, 1)` sur le premier octet du fichier.
  Même comportement : si `OSError`, lever `FolderBusy`. Le verrou est libéré
  à la fermeture du handle.
- Le fichier `.glaneur.lock` reste sur disque après release — c'est un
  détail d'implémentation, pas un verrou-fichier au sens historique. Sur
  la prochaine acquisition on réutilise le même fichier. Un utilisateur qui
  supprime le fichier « à la main » ne casse rien : la prochaine acquisition
  le recrée.

### Modification 2 — `Glaneur/engine/core.py`

Encapsuler la logique de `Engine.run()` dans le context manager :

```python
def run(self) -> RunResult:
    try:
        with folder_lock(Path(self.o.target_dir)):
            return self._run_locked()
    except FolderBusy:
        return RunResult(
            message=<code busy>,   # via structured event, cf US-VERIF-04
            busy=True,
        )
```

`RunResult` gagne un booléen `busy: bool = False`. Aucune autre transformation
du moteur dans cette US.

### Modification 3 — `cli.py`

Sur `busy=True`, sortir avec **exit code 3** (roadmap lot 4). Message court
sur `stderr`.

### Modification 4 — tests

Cibles dans un nouveau `tests/test_folder_lock.py` :

- Deux acquisitions successives d'un même dossier dans le même processus :
  la deuxième lève `FolderBusy`.
- Deux acquisitions successives séparées par la libération de la première :
  la deuxième acquisition réussit.
- Deux processus (`multiprocessing.Process`) courant en parallèle : le
  premier obtient le verrou, le second lève `FolderBusy`.
- Suppression manuelle du fichier `.glaneur.lock` entre deux runs : la
  reprise fonctionne.
- Intégration : `Engine.run()` sur un dossier déjà verrouillé renvoie
  `RunResult(busy=True)`, sans effet de bord (pas de manifeste écrit, pas
  de fichier téléchargé).

### Vérifié ou supposé

- **Vérifié** : `fcntl` disponible sur macOS et Linux. `msvcrt` disponible
  dans tout CPython Windows.
- **Supposé** : `msvcrt.locking(fd, LK_NBLCK, 1)` sur un fichier créé en
  `r+b` place bien un verrou obligatoire, non un verrou consultatif. À
  confirmer sur `windows-latest` en CI.
- **Supposé** : sur un partage SMB monté, le verrou fonctionne. Non testé
  ici. La roadmap n'exige pas ce cas ; laisser en note.

### Critères d'acceptation

- [ ] La suite existante reste verte.
- [ ] Les nouveaux tests ci-dessus passent sur `ubuntu-latest` et
      `windows-latest`.
- [ ] `Engine.run()` sur un dossier verrouillé renvoie `RunResult(busy=True)`,
      manifeste non modifié.
- [ ] `python -m cli` sur un dossier verrouillé sort avec exit code 3.
- [ ] Le plafond de couverture de `Glaneur/engine/*` (95 %) reste tenu.
- [ ] Relecture `invariant-reviewer` (nouveau module dans le moteur ;
      frontière moteur/OS).

---

## US-VERIF-04 — Événements structurés du moteur (lot 2, fin, frontière 1)

### Contexte

`Glaneur/engine/core.py` importe `QCoreApplication` et fait 17 appels
`translate("Moteur", <FR>)`. La conséquence : le moteur dépend de Qt (violation
de la frontière 1 documentée dans CLAUDE.md) et la « colonne statut » de la
liste des profils du lot 5.0 E2 n'a rien à consommer.

Cible : le moteur émet un couple `(code, params)` — une clé stable en anglais
et un dictionnaire de valeurs — que l'UI traduit dans son propre code.

### Modification 1 — Registre d'événements

Nouveau module `Glaneur/engine/events.py` :

```python
from dataclasses import dataclass
from typing import Mapping

@dataclass(frozen=True)
class EngineEvent:
    """A structured message emitted by the engine.

    ``code`` is a stable identifier (kebab-case) known to the UI mapper
    and to the file logger. ``params`` carries the values needed to
    render the message; the engine never formats a user-facing string.
    """
    code: str
    params: Mapping[str, object]
```

Codes à définir (dérivés des 17 `translate("Moteur", …)` recensés) — sujets
à ajustement lors du câblage :

| Code | Params | Occurrence actuelle |
|---|---|---|
| `manifest-unreadable` | — | `core.py:113` |
| `download-error` | `{error}` | `core.py:336, 572` |
| `defer-with-time` | `{until}` | `core.py:362` |
| `defer-no-time` | — | `core.py:367` |
| `already-known` | `{count}` | `core.py:404` |
| `nothing-matches` | — | `core.py:437` |
| `known-and-todo` | `{known, todo}` | `core.py:468` |
| `all-up-to-date` | — | `core.py:476` |
| `identifying-galleries` | — | `core.py:488` |
| `n-new-images` | `{count, size}` | `core.py:551` |
| `interrupted` | — | `core.py:569` |
| `write-problem` | `{error}` | `core.py:574` |
| `not-found` | — | `core.py:531` |

La liste est indicative : le rédacteur de l'US énumère chaque `translate()`
au commit et lui donne un code au moment du câblage.

### Modification 2 — `Glaneur/engine/core.py`

- Retirer l'import `PySide6.QtCore.QCoreApplication`.
- Le callback `journal` change de signature : `Callable[[EngineEvent], None]`.
- Chaque `self._journal(QCoreApplication.translate("Moteur", …))` devient
  `self._journal(EngineEvent(code, params))`.
- Le fichier de log écrit le code + les paramètres en anglais (roadmap lot 2).

### Modification 3 — `app.py` (UI)

- Un mapper `_render(event: EngineEvent) -> str` reprend les 17 chaînes
  françaises actuelles et les rebranche sur les nouveaux codes. C'est là
  et **seulement là** que vit `QCoreApplication.translate`, avec le
  contexte `"UiJournal"` (nouveau contexte, séparé de `"Moteur"` qui
  n'existe plus).
- Le callback passé à `Engine` devient
  `lambda ev: self.journal_widget.appendPlainText(self._render(ev))`.

### Modification 4 — `translations/`

- Retirer les entrées `context="Moteur"` du `.ts`.
- Ajouter les nouvelles sources anglaises sous `context="UiJournal"`.
- Regénérer `translations/glaneur_fr.ts` avec `lupdate`, en conservant les
  autres contextes littéraux comme aujourd'hui.
- Recompiler les `.qm` par le script existant `translations/build_translations.py`.

### Modification 5 — `Glaneur/logsetup.py` et logs fichier

Le log fichier écrit `event.code` + `json.dumps(event.params, ensure_ascii=False)`.
Pas de traduction côté fichier — roadmap lot 2 : « Le fichier de log les écrit
en anglais. »

### Modification 6 — tests

- `tests/test_core.py` : chaque assertion qui attendait une chaîne française
  particulière compare maintenant `event.code` et éventuellement un champ de
  `event.params`. C'est là que se cache la plus grande partie du travail de
  l'US.
- `tests/test_boundaries.py` : le `xfail(strict=True)` sur l'import
  `QCoreApplication` dans le moteur bascule en `pass`. Retirer le marqueur.
- Nouveau `tests/test_ui_journal_render.py` : chaque code d'événement rend
  une chaîne non vide en français, et deux appels au même code donnent le
  même rendu (déterminisme).

### Vérifié ou supposé

- **Vérifié** : `test_boundaries.py` marque déjà l'import `QCoreApplication`
  comme frontière à respecter (CLAUDE.md).
- **Vérifié** : `Glaneur/i18n.py` installe déjà le traducteur avec le contexte
  attendu ; ajouter un contexte `"UiJournal"` ne demande pas de nouvelle
  plomberie.
- **Supposé** : `lupdate` conserve les autres contextes (`"Planificateur"`,
  `"Updater"`, `"BugReport"`) intacts lors de la regénération. À vérifier
  sur le diff du `.ts` avant commit.
- **Supposé** : aucun autre module que `engine/core.py` n'importe
  `QCoreApplication` en dehors de la couche UI. À contrôler par un grep au
  commit.

### Critères d'acceptation

- [ ] `Glaneur/engine/core.py` n'importe plus `PySide6`.
- [ ] `test_boundaries.py` : l'import interdit devient un `pass` sans
      `xfail`.
- [ ] La suite complète reste verte, y compris les nouveaux tests de rendu.
- [ ] Le fichier de log contient des codes anglais + params JSON, pas de
      chaîne française.
- [ ] Le compilé `.qm` produit par `translations/build_translations.py` est
      lisible et couvre chacun des codes.
- [ ] `sphinx-build -W -n -b html docs/sphinx docs/sphinx/_build/html`
      reste vert (docstrings mises à jour).
- [ ] Relecture `invariant-reviewer` **Opus** (frontière 1 + événements
      structurés + traductions).

---

## Ordre et parallélisme

```
US-VERIF-01  ─┐
              ├─►  US-VERIF-02  ──►  US-VERIF-04  ──►  ouverture du lot 5
US-VERIF-03  ─┘
```

- US-VERIF-01 et US-VERIF-03 sont indépendantes (CI vs moteur) et peuvent
  courir en parallèle dans deux worktrees séparés.
- US-VERIF-02 attend US-VERIF-01 fusionnée (le cliquet CI protège le
  changement de politique de reprise).
- US-VERIF-04 clôt le sprint. Elle attend US-VERIF-02 fusionnée (pour ne
  pas mélanger la refonte des tests moteur et un changement de reprise dans
  le même diff), et bénéficie du verrou US-VERIF-03 pour ses tests
  d'intégration.

## Hors périmètre — explicitement

- Lot 1.2 (faux serveur local), lot 1.3 (tests réseau), lot 1.4 ruleset
  Ruff complet + `pip-audit`, lot 1.5 pydocstyle en Ruff.
- Lot 3.1 côté `Engine.download` (unification de la reprise).
- Lot 3.2 message fatal typé sur la racine API.
- Lot 3.3 validation `.part` (magic bytes, taille, checksum).
- Lot 3.4 flush temporel du manifeste.
- Écarts CLAUDE.md restants : clés FR du manifeste, champs FR d'`Element`,
  flags CLI FR, valeurs de dispatch FR, `sourcelanguage="fr"` des `.ts`.

Chacun reste à sa place dans son propre lot.

## Definition of Done

- [ ] Les quatre US ont chacune leur PR fusionnée sur `main`.
- [ ] `__version__` inchangé.
- [ ] La suite complète et `python tools/check_coverage.py` passent sur
      `main` en fin de sprint.
- [ ] `sphinx-build -W -n -b html docs/sphinx docs/sphinx/_build/html`
      reste vert.
- [ ] Le `xfail(strict=True)` sur l'import `QCoreApplication` a été retiré
      de `tests/test_boundaries.py`.
- [ ] `CLAUDE.md` section « Écarts connus » est mise à jour : les deux
      écarts « `engine/core.py` importe `QCoreApplication` » et
      « `_locks.py` = `threading.Lock` » disparaissent.
- [ ] Le lot 5.0 E1 peut démarrer sans dette technique traînante des
      lots 1 à 4.
