# Impact Map

<!--
Gabarit temporaire, propre à la tâche courante. Remets-le à cet état vide
entre deux lots. N'y stocke ni copie de fichiers, ni logs, ni résultats de
tests volumineux, ni informations déjà présentes dans CLAUDE.md. Voir
CLAUDE.md section « Impact Map » et « Politique de contexte minimal ».
-->

## Task

Lot 1 du sprint « Coupe-circuit réseau et report différé ». Introduire
dans la couche source une fonction utilitaire `classer_erreur(exc, reponse=None)`
qui classe une exception `requests` ou un code HTTP en trois catégories :

- `"transitoire"` : timeout ponctuel, un 5xx isolé.
- `"coupure"` : le serveur nous a coupés (429, 503, `NameResolutionError`,
  `ConnectionError` avec « Max retries exceeded »).
- `"definitif"` : autre erreur non retryable.

Extrait aussi un `Retry-After` (secondes) si l'en-tête est présent.
Aucune modification du moteur ni du scheduler à ce lot — juste
l'utilitaire et ses tests unitaires. Les lots suivants consommeront cette
API.

## Directly modified

- Glaneur/sources/base.py                      (nouvelle fonction publique
                                                `classer_erreur` + une
                                                dataclass `Classification`
                                                si besoin)
- tests/test_source_base.py                    (nouveaux tests unitaires
                                                pour `classer_erreur`)

## Direct dependencies

- Aucun. Le module reste autonome ; ni `Transport` ni `Source` ne
  consomment encore la nouvelle fonction à ce lot (lot 2 s'en chargera
  dans le moteur).

## Tests

- Suite ciblée : `tests/test_source_base.py` uniquement.
- `ruff` ciblé sur `Glaneur/sources/base.py` et `tests/test_source_base.py`.

## Potentially affected

- `tests/test_source_djangoplicity.py`, `tests/test_source_wordpress.py` :
  aucun impact tant que le comportement de `Transport.get_json` n'est pas
  modifié.

## Explicitly out of scope

- Modification de `Transport.get_json`, `Moteur.telecharger`, du
  planificateur ou de la config : lots 2 et 3.
- Câblage UI / CLI : lot 4.
- Frontière 1 (Qt hors moteur) : inchangée, `base.py` n'a jamais
  dépendu de Qt.

## Invariants

- Le module `Glaneur/sources/base.py` ne dépend pas de Qt.
- Les symboles existants (`Element`, `Source`, `Transport`, `Interrompu`,
  `UA`) restent exportés au même chemin.
- La fonction ne fait aucun I/O : elle reçoit exception + réponse et
  renvoie une classification pure — testable sans réseau.
