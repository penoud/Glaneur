# Impact Map

<!--
Gabarit temporaire, propre à la tâche courante. Remets-le à cet état vide
entre deux lots. N'y stocke ni copie de fichiers, ni logs, ni résultats de
tests volumineux, ni informations déjà présentes dans CLAUDE.md. Voir
CLAUDE.md section « Impact Map » et « Politique de contexte minimal ».
-->

## Task

**US-VERIF-04 — Événements structurés du moteur (lot 2, fin, frontière 1).**

Quatrième et dernière US du sprint
`docs/sprints/2026-09-verifier-lots-1-4-avant-lot-5.md`.

Aujourd'hui, `Glaneur/engine/core.py` importe `QCoreApplication` et fait
17 appels `translate("Moteur", …)`. Conséquences :

- Frontière 1 violée (CLAUDE.md, section « Écarts connus »), matérialisée
  par le `xfail(strict=True)` sur cet import dans `tests/test_boundaries.py`.
- La liste de profils prévue au lot 5.0 E2 (« colonne statut ») n'a rien
  à consommer : elle lit une chaîne déjà traduite, pas un couple
  code+params sur lequel construire un état visuel.

Objectif : le moteur émet des `EngineEvent(code, params)` via son
callback `journal`. L'UI est le seul endroit qui les rend en français
(via `QCoreApplication.translate("UiJournal", …)`). Le CLI et la CLI-log
les rendent en anglais via une fonction pure `render_en(event)`.
L'import `QCoreApplication` disparaît de `engine/core.py`. Le
`xfail(strict=True)` de la frontière 1 saute.

## Directly modified

- **`Glaneur/engine/events.py`** (**nouveau**) : classe frozen
  `EngineEvent(code: str, params: Mapping[str, object])` et fonction
  pure `render_en(event) -> str` qui applique les gabarits anglais des
  17 codes.
- **`Glaneur/engine/result.py`** : ajout du champ
  `message_event: EngineEvent | None = None`. Le champ existant
  `message: str = ""` reste : le moteur y écrit `render_en(event)` pour
  que la CLI puisse continuer à printer directement.
- **`Glaneur/engine/core.py`** :
  - retirer `from PySide6.QtCore import QCoreApplication` ;
  - callback `journal` typé `Callable[[EngineEvent], None]` ;
  - chaque `QCoreApplication.translate("Moteur", …)` → `EngineEvent(...)`
    passé à `self._journal(...)` ou fixé sur `res.message_event` ;
  - `res.message` toujours mis à jour, avec `render_en(res.message_event)`,
    afin que le CLI et les tests hérités puissent s'appuyer dessus ;
  - `Engine.download` renvoie désormais `(status, infos, classification,
    error_text)` — quatre éléments, `error_text: str | None` fourni sur
    le chemin d'erreur ; la conversion en chaîne traduite n'est plus dans
    `download` ;
  - le libellé de progression pour « Identification des galeries… » et
    pour le defer utilise `render_en(event)` : en anglais côté engine,
    l'UI conserve le droit de reconstruire un rendu FR à partir de
    `message_event` sur son écran principal.
- **`Glaneur/engine/__init__.py`** : ré-export de `EngineEvent` et
  `render_en` (surface publique du sous-paquet).
- **`app.py`** :
  - `Travailleur.journal = Signal(str)` → `Signal(object)` (portant un
    `EngineEvent`) ;
  - un slot rend l'événement en français via
    `QCoreApplication.translate("UiJournal", <template FR>).format(**params)` ;
  - la fenêtre principale lit `res.message_event` pour recomposer le
    statut et le journal en français ; à défaut d'un `message_event`
    (défer, cas historique inchangé), elle retombe sur `res.message`.
- **`cli.py`** :
  - callback `journal` qui imprime `render_en(event)` ;
  - `res.message` reste utilisé tel quel pour le résumé final.
- **`tests/test_core.py`** : chaque assertion qui matchait une chaîne
  française particulière compare désormais `event.code` (et éventuellement
  un champ de `event.params`). Rédaction déléguée à `test-author`.
- **`tests/test_boundaries.py`** : `KNOWN_QT_IMPORTS` vidé de
  `Glaneur/engine/core.py`. Le test devient garant de la frontière 1
  côté moteur.
- **`translations/glaneur_fr.ts` et `translations/glaneur_en.ts`** :
  régénérés via `pyside6-lupdate` après les modifications de code. La
  compilation `.qm` est produite par `translations/build_translations.py
  release`.
- **`docs/sprints/2026-09-verifier-lots-1-4-avant-lot-5.md`** :
  section US-VERIF-04 non modifiée ; c'est la source de la présente
  US.

## Direct dependencies

- `Glaneur/engine/options.py`, `Glaneur/engine/_folder_lock.py`,
  `Glaneur/engine/_locks.py`, `Glaneur/scheduler.py`, `Glaneur/config.py`,
  `Glaneur/sources/*` : **inchangés**. Le refactor est strictement local
  à la couche journal/message du moteur.
- `Glaneur/logsetup.py` : non modifié. Le logging fichier n'est pas
  connecté au callback `journal` aujourd'hui ; le brancher relève d'un
  lot ultérieur.
- `tests/test_cli.py` : lecture ; ses stubs `_FauxEngine` acceptent
  `journal=None` — le contrat de l'argument reste, seul le type de ce
  qu'on lui passe change. Adaptation seulement si des assertions
  matchent une chaîne journal historique.
- `tests/test_folder_lock.py` (US-VERIF-03) : `_FauxBusyEngine.run`
  renvoie un `RunResult(busy=True)` sans passer par `journal` ni
  `message_event`. **Non impacté**.
- `.claude/state/impact-map.md` : cet artéfact de session.

## Explicitly out of scope

- **Renommage de `journal` en `on_event`** : sprint doc parle de
  « changement de signature du callback `journal` » — on garde le nom
  pour ne pas casser tous les appelants et tests. Renommage possible
  dans un lot ultérieur si utile.
- **Migration du manifeste ou du cache vers un format v2** : lot 6.
- **Écarts CLAUDE.md restants** : clés FR du manifeste, champs FR
  d'`Element`, flags CLI FR, valeurs de dispatch FR (`transitoire`,
  `coupure`, `definitif`, `galerie`, `date`, `plat`, `wordpress`,
  `djangoplicity`, statuts moteur `ok`/`repris`/`inchangé`/`introuvable`,
  marques `supprime`/`restaure`) — laissés tels quels, ces chaînes
  restent des codes de dispatch, pas des messages utilisateur.
- **Contextes Qt autres que `Moteur`** (`Planificateur`, `Updater`,
  `BugReport`) : intacts. Les nouveaux libellés UI arrivent dans le
  contexte `UiJournal`, séparé.
- **File log en anglais** (roadmap 2) : partie facultative, non branchée
  au callback aujourd'hui ; laissée à un lot dédié.
- **`__version__`** : inchangé.

## Tests

Cible principale : `tests/test_core.py` (~129 tests), où de nombreuses
assertions matchent aujourd'hui les chaînes françaises journal /
`res.message`. Rédaction déléguée à `test-author`, qui doit :

- remplacer les match de chaîne « déjà connues », « Aucune image ne
  correspond aux critères. », « Tout est déjà à jour. »,
  « nouvelle(s) image(s) », « Interrompu — la reprise repartira d'ici. »,
  « Erreur : », « Problème d'écriture », etc. par des vérifications
  `event.code == "..."` sur ce que le callback `journal` a reçu ;
- vérifier aussi `res.message_event.code` là où la chaîne `res.message`
  était comparée ;
- ne pas retester la traduction FR — la traduction vit dans l'UI,
  couverte par un unique test de rendu ajouté dans
  `tests/test_ui_journal_render.py` (voir plus bas).

Nouveau fichier `tests/test_ui_journal_render.py` (couvert par
`test-author` ou par la conversation principale, à décider) :
- pour chacun des 17 codes, `_render(EngineEvent(code, {…}))` renvoie
  une chaîne non vide et déterministe (deux appels au même code donnent
  le même rendu). Ne teste pas le contenu FR — trop fragile — juste
  la présence et la stabilité.

`tests/test_boundaries.py::test_no_qt_outside_ui` : doit passer sur
`Glaneur/engine/core.py` sans `xfail`.

Suite complète (`pytest -q`) verte. Couverture : `engine/*` reste
≥ 98.0 %, `sources/*` reste ≥ 98.0 %.

## Invariants

- `__version__` inchangé.
- `EngineEvent` est un dataclass gelé — impossibilité de muter `params`
  après création.
- La signature publique de `Engine.__init__` conserve les mêmes
  paramètres (`options`, `journal`, `progression`, `arret`), seul le
  type de `journal` change de `Callable[[str], None]` à
  `Callable[[EngineEvent], None]`.
- `RunResult` reste additif : `message_event` a un défaut `None`, tous
  les consommateurs existants qui lisent `message` continuent de le
  faire.
- **Frontière 1 résolue** : `Glaneur/engine/core.py` n'importe plus
  aucun module Qt. `tests/test_boundaries.py::test_no_qt_outside_ui`
  le garantit désormais.
- Aucun format persisté ne change (manifeste, cache, `config.json`).
- Aucune chaîne de dispatch persistée ne change (statuts moteur, marques
  `supprime`/`restaure`, `sort_mode`, etc.).
- Les plafonds de couverture (US-VERIF-01) tiennent : `sources/*` 98.0,
  `scheduler.py` 95.0, `config.py` 97.0, `engine/*` 98.0.

## Validation

Niveau `subsystem` — nouveau module dans le moteur, changement de
signature d'un callback, mais aucun format persisté, aucune API
externe.

- Rédaction des tests par `test-author` (sous-agent).
- Rédaction du code de production par la conversation principale.
- `pytest -q --cov=Glaneur --cov-branch` vert.
- `python tools/check_coverage.py` vert.
- `ruff check` propre sur les fichiers touchés (les avertissements
  `DTZ005` et `EXE001` préexistants, hors périmètre US-VERIF-03,
  restent — non introduits par cette US).
- `sphinx-build -W -n -b html docs/sphinx docs/sphinx/_build/html` vert.
- Relecture `invariant-reviewer` (frontière 1 est le cœur de l'US).
- Regénération des `.ts` puis compilation des `.qm` — vérifier que
  `translations/glaneur_fr.qm` charge dans l'UI.
