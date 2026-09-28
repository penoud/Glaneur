# Impact Map

<!--
Gabarit temporaire, propre à la tâche courante. Remets-le à cet état vide
entre deux lots. N'y stocke ni copie de fichiers, ni logs, ni résultats de
tests volumineux, ni informations déjà présentes dans CLAUDE.md. Voir
CLAUDE.md section « Impact Map » et « Politique de contexte minimal ».
-->

## Task

**US-VERIF-02 — Politique de reprise de `Transport.get_json`.**

Deuxième US du sprint
`docs/sprints/2026-09-verifier-lots-1-4-avant-lot-5.md`.

Aujourd'hui, `Transport.get_json` (`Glaneur/sources/base.py:234-275`)
attrape toute `requests.RequestException` puis attend
`2 × (tentative + 1)` secondes — soit 2, 4, 6 s sur trois tentatives —
avant de réessayer. Donc :

- un 401 ou un 404 hors `fin_si` est réessayé trois fois, gaspillage
  et bruit vers le serveur ;
- l'entête `Retry-After` est bien extrait par `_retry_after` mais n'est
  jamais consommé dans la boucle de `get_json` ;
- la pause après la dernière tentative (6 s) est du gaspillage : on ne
  va plus réessayer, on va lever `RuntimeError`.

Objectif : brancher `get_json` sur `classify_error` — arrêt immédiat sur
`definitif`, `Retry-After` respecté (plafonné à 120 s), trois tentatives
au total avec attentes de 2 s puis 4 s (pas de troisième attente).

## Directly modified

- `Glaneur/sources/base.py` : la méthode `Transport.get_json` seule.
  La classe `Transport`, `ErrorClassification`, `classify_error`,
  `_retry_after` et les constantes de dispatch ne changent pas.
- `tests/test_source_base.py` : nouveau bloc `TestTransportGetJson`
  couvrant les 6 cas listés plus bas. Le docstring de module est
  élargi pour inclure `Transport` (aujourd'hui « strictement
  `classify_error` »).

## Direct dependencies

- `ErrorClassification`, `classify_error` (`Glaneur/sources/base.py`) :
  déjà en place — **lues, non modifiées**. Le nouveau `get_json` les
  utilise.
- `tests/test_source_wordpress.py::TestTransportGetJson` (5 tests) :
  lecture pour s'assurer qu'ils passent sans modification sous la
  nouvelle politique (le `sleep` est déjà mocké, les compteurs de
  tentatives restent à 3, l'issue reste `RuntimeError` ou succès). **Ne
  pas modifier**.
- `Glaneur/sources/wordpress.py` et `Glaneur/sources/djangoplicity.py` :
  appellent `get_json` avec `fin_si={400}` (WordPress) et sans `fin_si`
  (Djangoplicity). Le contrat `fin_si` ne change pas. **Non modifiés**.

## Explicitly out of scope

- **`Engine.download`** (`Glaneur/engine/core.py:252-339`) : la roadmap
  3.1 veut à terme la même politique de reprise, mais le circuit-breaker
  de la boucle `run` (5 échecs consécutifs → `defer`) absorbe déjà
  l'absence de reprise. Le lot 5.2 n'en dépend pas. **Non touché.**
- **Docstrings du module `base.py`** : mise à jour de la docstring de
  `get_json` pour refléter la nouvelle politique ; les autres restent.
- **Sources WordPress / Djangoplicity** : aucune modification.
- **Autres tests** existant dans `tests/test_source_wordpress.py`,
  `tests/test_source_djangoplicity.py`, `tests/test_sources_edges.py` :
  vérifiés verts, **pas modifiés**.
- **`__version__`** : inchangé.

## Tests

Six cas nouveaux dans `tests/test_source_base.py`, classe
`TestTransportGetJson`. Le `sleep` de `Transport` est mocké dans chaque
test (comme les tests existants) pour ne pas ajouter de secondes réelles
à la suite. Le `session.get` est un `MagicMock`.

- **401 non réessayé** : `session.get` renvoie une réponse 401 (levant
  `HTTPError` sur `raise_for_status`). `get_json` lève sans réessayer,
  `session.get.call_count == 1`, `sleep` jamais appelé.
- **403 non réessayé** : idem avec 403.
- **404 non réessayé** : idem avec 404.
- **429 avec `Retry-After: 3`** : premier appel = 429 (`coupure`),
  deuxième = 200 succès. `sleep` appelé une fois avec 3.0 s, pas 2 s.
- **429 avec `Retry-After: 300`** : premier appel = 429, deuxième = 200.
  `sleep` appelé une fois avec **120.0 s** (plafond), pas 300.
- **Trois échecs 500 consécutifs** : `session.get` lève trois fois.
  `sleep` appelé exactement deux fois, avec 2.0 puis 4.0. Aucun
  troisième `sleep(6)`. `RuntimeError` finale.
- **Arrêt coopératif** : `Transport.arret.set()` puis `get_json` doit
  lever `Interrupted` sans nouvel appel réseau. Facultatif si couvert
  déjà par `test_sources_edges.py::TestTransport::test_sleep_est_annule_par_l_arret`
  — à confirmer à la lecture.

Les cinq tests existants dans
`tests/test_source_wordpress.py::TestTransportGetJson` doivent rester
verts sans modification.

## Invariants

- `__version__` inchangé.
- `ErrorClassification` reste un dataclass gelé, aucune signature ne
  bouge dans `sources/base.py` hors de `get_json`.
- Le contrat de `classify_error` (trois catégories, `retry_after`) reste
  identique.
- Le contrat de `fin_si` reste identique : un code dans `fin_si` est
  une fin normale, même après le patch (le `if r.status_code in fin_si`
  reste avant `raise_for_status`).
- L'arrêt coopératif reste effectif pendant l'attente : `Transport.sleep`
  n'est pas modifié.
- Le plafond `Glaneur/sources/*` du cliquet (98.0 %, US-VERIF-01) tient.

## Validation

Niveau `module` (roadmap 5.1 tableau : « une source touchée + frontière
`Transport` »). Étapes :

- Rédaction des tests par `test-author` (sous-agent, cf. CLAUDE.md).
- Rédaction du code de production par la conversation principale.
- `pytest tests/test_source_base.py tests/test_source_wordpress.py tests/test_source_djangoplicity.py tests/test_sources_edges.py -q`
  vert.
- `pytest -q --cov=Glaneur --cov-branch && python tools/check_coverage.py`
  vert (le plafond `sources/*` = 98.0 tient).
- `ruff check Glaneur/sources/base.py tests/test_source_base.py`.
- Relecture `invariant-reviewer` (frontière `Transport`, changement de
  politique de reprise).
