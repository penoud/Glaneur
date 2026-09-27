# Impact Map

<!--
Gabarit temporaire, propre à la tâche courante. Remets-le à cet état vide
entre deux lots. N'y stocke ni copie de fichiers, ni logs, ni résultats de
tests volumineux, ni informations déjà présentes dans CLAUDE.md. Voir
CLAUDE.md section « Impact Map » et « Politique de contexte minimal ».
-->

## Task

**Sprint « Identifiants FR → EN ». Batch 5 — updater.**

Le sous-package `Glaneur/updater/` est déjà quasi entièrement en
anglais : `download`, `verify_sha256`, `temporary_directory`,
`DownloadError`, `GitHubReleaseProvider`, `check`, `_is_stable`,
`_parse`, `Version`, `parse`, `_compare_key`, `ReleaseAsset`,
`Release`, `windows_installer`, `checksum_for`, `UpdateInfo`,
`is_available` — inchangés.

**À renommer, tous dans `Glaneur/updater/qt_threads.py`** :

Classes :
- `VerificationMiseAJour → UpdateCheck`
- `TelechargementMiseAJour → UpdateDownload`

Signaux Qt (attributs de classe) :
- `disponible → available` (sur `UpdateCheck`)
- `aucune_maj → up_to_date` (sur `UpdateCheck`)
- `erreur → error` (sur `UpdateCheck` et `UpdateDownload`)
- `termine → finished` (sur `UpdateDownload`)

## Directly modified

- Glaneur/updater/qt_threads.py           (classes + signaux)
- app.py                                  (imports + type annotations +
                                           branchements de signaux
                                           `thread.disponible.connect(…)`
                                           etc.)
- tests/test_updater_threads.py           (classes + signaux)
- tests/test_updater_threads_run.py       (idem)

## Direct dependencies

- **Contexte Qt de traduction `"Updater"`** : reste littéral. Les
  chaînes sources FR (« Vérification de mise à jour impossible : … »,
  « Téléchargement de la mise à jour impossible : … », « Installateur
  Windows ou checksum absent de la release », « Vérification SHA-256
  échouée ») restent bit-à-bit identiques.
- Docs Sphinx : le rôle `:mod:\`Glaneur.updater.qt_threads\`` du
  README du sous-package reste ok, les rôles de classe et méthode
  changent avec le renommage. Aucune référence FR n'est laissée dans
  les docstrings.
- Frontière 1 (`tests/test_boundaries.py`) : `qt_threads.py` importe
  Qt légitimement (thread UI), aucun impact.
- `translations/*.ts` : mêmes strings sources → contexte de traduction
  toujours matché.

## Tests

- `pytest` complet + couverture.
- `ruff check` global.
- Sphinx : différé, comme aux lots précédents.

## Explicitly out of scope

- `Glaneur/system.py::_appel_com` (homonyme découvert au lot précédent :
  vit dans `system.py`, pas dans l'updater — lot 6).
- Attributs d'instance dans `app.py::FenetrePrincipale` :
  `self.verification_mise_a_jour`, `self.telechargement_mise_a_jour`,
  `_mise_a_jour_disponible`, `_aucune_mise_a_jour_manuel`,
  `_erreur_verification_manuel`. Restent FR par cohérence avec le lot
  3 (self.planificateur / _rafraichir_echeance sont dans le même
  esprit).
- Contexte Qt `"Updater"` et strings sources FR.

## Invariants

- **`.qm` / `.ts` inchangés** : contexte `"Updater"` et strings sources
  bit-à-bit identiques.
- **Persistence inchangée** : rien de persisté touché.
- **Suite complète green** après renommage, y compris les tests
  pytest-qt qui utilisent `qtbot.waitSignal(thread.available, …)`.
- Frontière 1 inchangée : les imports Qt de `qt_threads.py` sont
  légitimes (module UI-side), rien n'est ajouté à `KNOWN_QT_IMPORTS`.

## Validation

Niveau **`full`** (touche des classes Qt exportées + tests pytest-qt).

- `pytest` complet + couverture.
- `ruff check` global.
- Sphinx : différé.
