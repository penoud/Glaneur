# Impact Map

<!--
Gabarit temporaire, propre à la tâche courante. Remets-le à cet état vide
entre deux lots. N'y stocke ni copie de fichiers, ni logs, ni résultats de
tests volumineux, ni informations déjà présentes dans CLAUDE.md. Voir
CLAUDE.md section « Impact Map » et « Politique de contexte minimal ».
-->

## Task

**US-VERIF-03 — Verrou OS par dossier cible (lot 4).**

Troisième US du sprint
`docs/sprints/2026-09-verifier-lots-1-4-avant-lot-5.md`.

Aujourd'hui, `Glaneur/engine/_locks.py` = un `threading.Lock` de
processus, dédié à la fusion UI ↔ moteur du manifeste (voir
`Engine.save_manifest`). Il ne protège **pas** contre deux processus
Glaneur qui viseraient le même dossier — cas concret dès l'ouverture du
lot 5.2 : file de profils + tâche planifiée horaire (lot 8) + ancienne
installation résiduelle.

Objectif : ajouter un verrou OS par dossier cible, portable (`fcntl.flock`
sur POSIX, `msvcrt.locking` sur Windows), acquis à l'entrée de
`Engine.run()` et libéré à la sortie du context manager. Sur verrou
déjà tenu, `run()` renvoie un `RunResult(busy=True)` sans effet de bord
sur le manifeste. La CLI convertit ce cas en exit code 3.

## Directly modified

- `Glaneur/engine/_folder_lock.py` (**nouveau**) : module isolé avec la
  classe d'exception `FolderBusy` et le context manager
  `folder_lock(target_dir: Path)`. Fichier `.glaneur.lock` posé dans le
  dossier cible, contenu = PID/host/UTC pour diagnostic (le verrou OS
  est le vrai garde-fou, pas le contenu du fichier).
- `Glaneur/engine/result.py` : ajouter le champ `busy: bool = False` à
  `RunResult`.
- `Glaneur/engine/core.py::Engine.run` : encapsuler le corps existant
  dans un `with folder_lock(self.o.target_dir):`. Sur `FolderBusy`,
  renvoyer un `RunResult(busy=True)` immédiat, sans toucher au manifeste
  ni ouvrir la session. Le message du result reste vide dans cette US
  (US-VERIF-04 branchera un événement structuré).
- `cli.py` : sortir avec exit code **3** lorsque `res.busy` est vrai, un
  court message sur `stderr`. Positionner ce test avant le calcul de
  l'exit code habituel (`0/1/2`).
- `tests/test_folder_lock.py` (**nouveau**) : voir la section « Tests ».

## Direct dependencies

- `Glaneur/engine/_locks.py` : **inchangé**. Le `threading.Lock` reste
  dédié à la fusion du manifeste — c'est une autre couche, intra-processus.
- `Glaneur/engine/__init__.py` : **inchangé**. `FolderBusy` et
  `folder_lock` restent des symboles privés du sous-paquet ; l'entrée
  publique reste `Engine.run` renvoyant un `RunResult`.
- `Glaneur/engine/options.py::Options.target_dir` (type `Path`,
  ligne 18) : **lu, non modifié** — le context manager attend un `Path`.
- `Glaneur/engine/core.py::Engine.load_manifest`, `save_manifest`,
  `save_cache` : appelés uniquement dans la partie protégée du `with`,
  jamais avant. **Non modifiés.**
- `cli.py::main` retourne aujourd'hui `0/1/2/130` (`--restaurer` et
  déferred inclus) ; ajout du chemin `3` sans en retirer.

## Explicitly out of scope

- **Toute file d'attente ou logique de scheduler** liée au lot 5.2 : le
  verrou est un pré-requis, pas la file. Le lot 5.2 s'en servira dans
  une future US.
- **Intégration côté UI Qt** (`app.py`, `Engine` lancé depuis un
  `QThread`) : la CLI seule couvre le pré-requis du lot 5. Si l'UI
  lance `Engine.run()` sur un dossier occupé, elle recevra un
  `RunResult(busy=True)` — le rendu utilisateur côté UI est traité dans
  US-VERIF-04 ou plus tard.
- **Suppression du fichier `.glaneur.lock`** après release : le fichier
  peut rester en place, le verrou OS est libéré à la fermeture du
  descripteur. L'utilisateur peut le supprimer à la main sans casser la
  prochaine acquisition (nouveau fichier recréé).
- **Verrou sur partage SMB** : la roadmap ne l'exige pas ; laisser en
  note dans la docstring du module.
- **`Glaneur/engine/_locks.py`** : sa raison d'être (fusion manifeste
  intra-processus) reste valide et distincte du verrou inter-processus
  ajouté ici.
- **`__version__`** : inchangé.

## Tests

Nouveau fichier `tests/test_folder_lock.py`. Aucun test existant
modifié.

Cas :

- **Double acquisition intra-processus** : `with folder_lock(dir):`
  imbriqué → le second bloc lève `FolderBusy`. Fonctionne sur POSIX
  parce que deux `open()` donnent deux descripteurs indépendants ; à
  reproduire tel quel sur Windows.
- **Acquisition séquentielle** : premier `with folder_lock(dir):` puis
  release, deuxième `with folder_lock(dir):` sur le même dossier → OK.
- **Multi-processus** : `multiprocessing.get_context("spawn").Process`
  (spawn explicite pour ne pas hériter du descripteur ouvert). Parent
  tient le verrou, le fils tente et voit `FolderBusy` ; le parent
  vérifie via un `multiprocessing.Queue`.
- **Suppression manuelle** du fichier `.glaneur.lock` entre deux runs :
  la prochaine acquisition doit fonctionner (recréation du fichier).
- **Intégration** : `Engine.run()` sur un dossier déjà verrouillé
  renvoie `RunResult(busy=True)` ; aucun manifeste n'est écrit, aucun
  appel à la source. Utilise `tmp_path` et une source no-op montée via
  `SOURCES` ou par patch — cf. le pattern existant dans
  `tests/test_core.py`.
- **CLI busy = exit 3** : appel `main()` en patchant `Engine.run` pour
  renvoyer un `RunResult(busy=True)` ; capturer `sys.exit`.

Sleep réel évité. Aucun appel réseau.

## Invariants

- `__version__` inchangé.
- Le contrat de `Engine.run` reste : renvoyer un `RunResult`, ne pas
  lever d'exception autre que `Interrupted` (qui reste convertie en
  `RunResult.interrupted=True` dans le corps existant).
- Le champ `RunResult.busy` est `False` sur tout run non conflictuel :
  les 26 sites qui construisent un `RunResult` (tous dans
  `engine/core.py` et les tests) n'ont pas besoin de changer.
- Sur `busy=True` : ni écriture de manifeste, ni écriture de cache, ni
  appel à `self.source.inventory`, ni acquisition de session HTTP.
- Le verrou est libéré même si `Engine.run` lève une exception :
  garantie par le `with` context manager, indépendamment du corps.
- Frontière 1 (Qt) : `_folder_lock.py` n'importe ni PySide6 ni Qt.
- Plafond de couverture `Glaneur/engine/*` (98.0 %) tient.

## Validation

Niveau `subsystem`. Un nouveau module dans le moteur, un champ ajouté
à un dataclass persisté-adjacent, une nouvelle branche dans `Engine.run`,
un nouvel exit code CLI.

- Rédaction des tests par `test-author` (sous-agent).
- Rédaction du code de production par la conversation principale.
- `pytest tests/test_folder_lock.py tests/test_core.py tests/test_cli.py -q`
  vert.
- `pytest -q --cov=Glaneur --cov-branch && python tools/check_coverage.py`
  vert.
- `ruff check Glaneur/engine/_folder_lock.py Glaneur/engine/result.py Glaneur/engine/core.py cli.py tests/test_folder_lock.py`
  vert.
- Relecture `invariant-reviewer` (nouveau module dans le moteur ;
  frontière moteur ↔ OS ; changement de contrat `Engine.run`).
