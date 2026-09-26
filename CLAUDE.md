# CLAUDE.md — Glaneur

Ce fichier est volontairement minimal pour l'instant : seules les sections
nécessaires au fonctionnement multi-agent sont posées. Les frontières, le
tableau d'invariants et les conventions seront rédigés dans un lot dédié.

## Écarts connus entre ce document et le code

Ce document décrit l'état visé. Tant qu'un écart figure ici, il n'est ni corrigé
hors de son lot, ni signalé comme régression, sauf s'il s'aggrave.

- `Glaneur/engine/core.py` importe `QCoreApplication` (PySide6) pour traduire
  ses messages. La frontière 1 sera tenue quand le moteur émettra des événements
  structurés. Suivi par `xfail(strict=True)` dans `tests/test_boundaries.py`.
  Les autres submodules de `Glaneur/engine/` sont indépendants de Qt.
- `Glaneur/scheduler.py` importe `PySide6.QtCore`. Même frontière 1 à tenir,
  probablement par extraction de la partie « planification » hors Qt. Suivi
  par `xfail(strict=True)` dans `tests/test_boundaries.py` (entrée
  `Glaneur/scheduler.py` dans `KNOWN_QT_IMPORTS`) ; à retirer dès que le
  prochain lot qui touche le scheduler extrait la partie planification hors
  Qt.
- Les identifiants Python (noms de fonctions, classes, variables locales) et
  les chaînes source de l'interface (`.ts` en `sourcelanguage="fr"`, libellés
  français en clés dans `config.py`) restent en français : futur lot. Les
  docstrings et les noms de fichiers Python sont désormais en anglais depuis
  le lot « nettoyage et docstrings-en » (2026-09-26).
- Le README décrit encore la signature par `WINDOWS_PFX_BASE64`, obsolète (lot 9).
- Les métadonnées AppStream de `packaging/linux/` décrivent encore une
  application WordPress seule : en attente avec Linux.

Mets cette liste à jour quand un lot résorbe un écart ou que tu en découvres un.

## Travail multi-agent

- La conversation principale cadre, implémente et décide. Elle ne délègue pas
  l'écriture du code de production.
- Sous-agents : `test-author` (tests seulement), `test-runner` (exécution et
  résumé), `invariant-reviewer` (relecture, lecture seule), `server-prober`
  (serveurs réels, sur demande). La suite complète et la couverture passent par
  `test-runner` ; un test isolé peut se lancer directement.
- Un seul rédacteur à la fois sur le code de production. Deux lots indépendants
  en parallèle se font dans deux sessions distinctes, chacune dans son worktree
  et sa branche.
- Jamais de push, de tag ni de modification de `__version__` : `main` publie.
  Des hooks le bloquent. Ne les contourne pas (autre shell, autre syntaxe) :
  signale le blocage.
- Un sous-agent ne voit pas cette conversation. Le message de délégation donne
  le périmètre, les fichiers et les invariants en jeu.

## Politique de contexte minimal

Chaque agent travaille avec le plus petit périmètre de fichiers permettant de
répondre correctement à la tâche.

- Ne jamais analyser tout le dépôt par défaut.
- Commencer par le diff et les fichiers explicitement concernés.
- Ne rechercher des dépendances supplémentaires que lorsqu'une dépendance
  réelle est découverte.
- Ne pas relire un fichier déjà analysé dans la même tâche sans raison.
- Les recherches `Glob` et `Grep` doivent être ciblées.
- Ne pas explorer les répertoires hors périmètre simplement pour comprendre
  « tout le projet ».
- Une modification locale ne déclenche pas une analyse globale.
- Une modification de documentation ne déclenche pas une analyse du code.
- Une modification d'un test ne déclenche pas automatiquement une analyse
  de toute la production.
- Les tests sont ciblés avant d'envisager la suite complète.
- Une vérification coûteuse doit être justifiée par l'impact du changement.
- Lorsqu'un fichier supplémentaire est nécessaire, identifier brièvement le
  lien entre ce fichier et le changement avant de poursuivre.
- Une exploration terminée ne doit pas être recommencée par un autre agent :
  son résultat doit être transmis via l'Impact Map ou le message de délégation.

## Impact Map

Chaque lot comportant une modification de code doit disposer d'une Impact Map.
Le fichier `.claude/state/impact-map.md` en fournit le gabarit ; il est
temporaire, remis à zéro entre deux lots, et ne contient que ce qui est
nécessaire à la tâche courante.

L'Impact Map :

- définit le périmètre de travail ;
- distingue les fichiers directement modifiés des dépendances ;
- identifie les tests concernés ;
- indique explicitement ce qui est hors périmètre ;
- identifie les invariants réellement concernés ;
- détermine le niveau de validation nécessaire.

Les sous-agents reçoivent cette information dans leur délégation.

Un sous-agent ne doit pas reconstruire une Impact Map déjà disponible.

Si un agent découvre une nouvelle dépendance réelle, il peut proposer son ajout
à l'Impact Map et expliquer pourquoi elle est nécessaire.

Une simple possibilité théorique ne suffit pas à élargir le périmètre.

## Validation conditionnelle

La présence d'un outil dans le workflow ne signifie pas qu'il doit être lancé
à chaque changement.

Le niveau de validation est déterminé par l'Impact Map (`local`, `module`,
`subsystem`, `full`).

| Type de changement                       | Vérifications                                                                    |
| ---------------------------------------- | -------------------------------------------------------------------------------- |
| Test seul                                | tests concernés + ruff ciblé                                                     |
| Python local                             | tests concernés + ruff ciblé                                                     |
| Une source (`Glaneur/sources/…`)         | tests de la source + tests de contrat concernés + ruff ciblé + `invariant-reviewer` si frontière/invariant touché |
| Moteur, scheduler, `config.py`           | tests concernés + ruff ciblé + `invariant-reviewer`                              |
| API publique ou format persistant        | tests concernés + suite complète + couverture + `invariant-reviewer`             |
| Packaging                                | tests concernés + validation packaging + `invariant-reviewer`                    |
| Documentation Sphinx (`docs/sphinx/**`)  | `sphinx-build -W -n -b html docs/sphinx docs/sphinx/_build/html` (installer d'abord `requirements-doc.txt`) |
| Docstrings d'un module Python            | `sphinx-build -W` en plus des vérifications habituelles du type de changement    |
| Transversal                              | pytest complet + couverture + ruff complet + Sphinx + `invariant-reviewer`       |

Une validation complète est réservée aux changements transversaux, aux
changements d'API/format persistant et aux étapes explicitement prévues par
le lot.

Après une modification locale, ne pas lancer automatiquement la suite complète,
la couverture complète ou Sphinx.

## Docstrings et documentation API

La documentation API vit dans `docs/sphinx/`. Elle est générée par Sphinx
avec `autodoc` + `napoleon` à partir des docstrings du code — la source
de vérité est le code, pas des fichiers `.rst` maintenus à la main.

- Style de docstring : **Napoleon (Google-style)**. Sections `Args:`,
  `Returns:`, `Yields:`, `Raises:`, `Attributes:` quand elles s'appliquent.
  Détail, exemple canonique et raison du choix dans
  `docs/sphinx/README.md`.
- Champs de dataclass : documentés par commentaires `#:` inline, jamais
  par une section `Attributes:` — sinon autodoc et Napoleon créent deux
  entrées d'index pour le même champ et cassent `sphinx-build -W`.
- Références internes qui ne résolvent pas via autodoc (constantes de
  module, attributs d'instance, membres d'un autre paquet non documenté)
  s'écrivent en double-backtick (```` ``foo`` ````), pas avec un rôle
  Sphinx comme `:data:` ou `:attr:`.
- Régénérer `docs/sphinx/api/*.rst` après un ajout, rename ou suppression
  de module : `make -C docs/sphinx apidoc` (ou `make.bat` sous Windows).
  Le post-traitement du Makefile retire les blocs « Module contents »
  paquet qui produiraient des doublons.
- `sphinx-build -W -n -b html docs/sphinx docs/sphinx/_build/html` doit
  rester vert. Un warning se traite avant le commit, pas après.

## Politique de délégation

Un agent est lancé uniquement lorsqu'il apporte une capacité distincte de
celle de la conversation principale ou d'un autre agent.

- Ne pas lancer plusieurs agents pour analyser le même problème.
- Ne pas lancer un reviewer pour une modification triviale qui ne touche aucun
  invariant.
- Ne pas lancer `server-prober` si un test local suffit.
- Ne pas lancer `test-runner` pour exécuter une commande unique triviale qui
  peut être exécutée directement.
- Ne pas lancer un agent uniquement pour déplacer du travail vers un autre
  contexte.
- Le parallélisme est réservé aux tâches réellement indépendantes.

### Politique de modèle

| Rôle                            | Modèle par défaut                              |
| ------------------------------- | ---------------------------------------------- |
| Exploration ciblée              | modèle économique (par défaut de la session)   |
| Exécution de tests              | Haiku (`test-runner`)                          |
| Écriture de tests               | modèle hérité (`test-author`)                  |
| Probe serveur                   | Sonnet (`server-prober`)                       |
| Review standard                 | Sonnet (`invariant-reviewer`)                  |
| Review d'architecture           | Opus, uniquement si l'Impact Map le justifie   |

Opus est réservé aux changements d'architecture, de persistance, de sécurité,
de concurrence, de packaging complexe, ou explicitement désignés comme tels
dans l'Impact Map. Il se demande à `invariant-reviewer` via le message de
délégation (« review Opus »), sans créer un second reviewer.
