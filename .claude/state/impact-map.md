# Impact Map

<!--
Gabarit temporaire, propre à la tâche courante. Remets-le à cet état vide
entre deux lots. N'y stocke ni copie de fichiers, ni logs, ni résultats de
tests volumineux, ni informations déjà présentes dans CLAUDE.md. Voir
CLAUDE.md section « Impact Map » et « Politique de contexte minimal ».
-->

## Task

Découpage de `Glaneur/engine.py` en paquet `Glaneur/engine/` avec un
fichier par fonction/dataclass et un fichier pour la classe `Moteur`.
But : simplifier la maintenance future en localisant chaque unité de
comportement dans son propre fichier. Aucun changement de comportement,
aucun changement de la surface publique — `from Glaneur.engine import …`
continue de fonctionner à l'identique via un `__init__.py` qui
ré-exporte l'API.

## Directly modified

- Glaneur/engine.py                          (supprimé)
- Glaneur/engine/__init__.py                 (ré-exports)
- Glaneur/engine/_verrous.py                 (`_MANIFESTE_LOCK` partagé)
- Glaneur/engine/_constantes.py              (`UA`, `SIZE_SUFFIX`)
- Glaneur/engine/_fusion.py                  (`_fusionner_marques_ui`)
- Glaneur/engine/options.py                  (`Options`)
- Glaneur/engine/resultat.py                 (`Resultat`)
- Glaneur/engine/nettoyer.py                 (`nettoyer`)
- Glaneur/engine/format_octets.py            (`format_octets`)
- Glaneur/engine/chemin_manifeste.py         (`chemin_manifeste`)
- Glaneur/engine/lire_manifeste.py           (`lire_manifeste`)
- Glaneur/engine/ecrire_manifeste.py         (`ecrire_manifeste`)
- Glaneur/engine/chemin_cache.py             (`chemin_cache`)
- Glaneur/engine/lire_cache.py               (`lire_cache`)
- Glaneur/engine/ecrire_cache.py             (`ecrire_cache`)
- Glaneur/engine/lister_supprimees.py        (`lister_supprimees`)
- Glaneur/engine/restaurer.py                (`restaurer`)
- Glaneur/engine/supprimer_image.py          (`supprimer_image`)
- Glaneur/engine/moteur.py                   (classe `Moteur`)
- tests/test_boundaries.py                   (KNOWN_QT_IMPORTS et
                                              _qt_cases pointent
                                              maintenant sur les
                                              submodules du paquet)
- CLAUDE.md                                  (section « Écarts connus » :
                                              l'entrée `Glaneur/engine.py`
                                              devient `Glaneur/engine/moteur.py`)
- docs/sphinx/api/*.rst                      (régénéré par `apidoc`)

## Direct dependencies

- `cli.py`, `app.py`, `tests/test_moteur.py`,
  `tests/test_source_djangoplicity.py` importent depuis
  `Glaneur.engine` : imports inchangés (le paquet expose la même API que
  l'ancien module).
- `Glaneur/config.py` et `Glaneur/sources/base.py` référencent
  `Glaneur.engine.*` dans les docstrings : chemins mis à jour vers le
  chemin canonique du submodule (`Glaneur.engine.options.Options`,
  `Glaneur.engine.resultat.Resultat`, `Glaneur.engine.moteur.Moteur`).
  Nécessaire parce que Sphinx documente maintenant ces symboles à
  l'endroit où ils vivent, pas au ré-export du paquet.

## Tests

- Suite complète (changement structurel touchant l'API publique).
- `tests/test_boundaries.py::test_no_qt_outside_ui` doit continuer à
  passer, `xfail(strict=True)` uniquement sur `Glaneur/engine/moteur.py`
  (les autres submodules du paquet n'importent pas Qt).

## Potentially affected

- `docs/sphinx/api/Glaneur.engine.rst` : remplacé par la structure de
  paquet (page paquet + page par submodule) via `make apidoc`.
- `packaging/**` : pas d'entrée explicite pour `engine.py`. PyInstaller
  collecte automatiquement le paquet via `Glaneur/__init__.py`. Point
  de contrôle `--controle-bundle` dans `app.py` importe déjà le paquet.

## Explicitly out of scope

- Frontière 1 (Qt hors moteur) : `QCoreApplication` reste importé dans
  `Glaneur/engine/moteur.py`. La dette est déplacée, pas résorbée.
- Refactor du corps des fonctions : contenu identique, seule la
  répartition en fichiers change.
- Traduction (`.ts`) : le contexte `"Moteur"` des `translate(...)` reste
  littéral dans `moteur.py`, donc `lupdate` continue à les extraire.
- Suppression de `UA` / `SIZE_SUFFIX` qui semblent inutilisés : hors
  périmètre.

## Invariants

- Surface publique de `Glaneur.engine` inchangée : mêmes symboles
  importables au même chemin de qualification.
- Atomicité de `ecrire_manifeste` / `ecrire_cache` inchangée.
- `_MANIFESTE_LOCK` reste un unique `threading.Lock` partagé entre
  `restaurer`, `supprimer_image` et `Moteur.sauver_manifeste`.
- Frontière 1 : la seule frontière Qt violée reste celle du moteur ;
  le paquet n'introduit pas de nouvelle violation ailleurs.
