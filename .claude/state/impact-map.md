# Impact Map

<!--
Gabarit temporaire, propre à la tâche courante. Remets-le à cet état vide
entre deux lots. N'y stocke ni copie de fichiers, ni logs, ni résultats de
tests volumineux, ni informations déjà présentes dans CLAUDE.md. Voir
CLAUDE.md section « Impact Map » et « Politique de contexte minimal ».
-->

## Task

**Sprint « Identifiants FR → EN ». Batch 8 — housekeeping.**

Le sprint a renommé la surface Python à travers les lots 2 à 6 + 4b.
Deux artefacts documentaires portent encore les anciens noms et
doivent être alignés :

1. **`CLAUDE.md` « Écarts connus »** : la ligne « identifiants Python
   restent en français » n'est plus vraie. La récrire pour lister
   précisément ce qui reste FR après le sprint (persistance non
   déplacée + user-facing).
2. **`README.md`** : sections EN et FR, arbre du projet et description
   du contrat du moteur, référencent encore `Moteur`, `Resultat`,
   `lire_cache`, `ecrire_cache`, `nettoyer`, `restaurer`,
   `supprimer_image`, `lister_supprimees`, `format_octets`,
   `inventaire`, `derniere_execution`, `retenter_apres`,
   `intervalle_heures`, `verifier_integrite`, `verifier_maj_demarrage`,
   `lancer_au_demarrage`, `fermer_dans_barre`, `delai_requetes`,
   `langue`. Les mettre à jour avec les noms EN adoptés.

## Directly modified

- CLAUDE.md
- README.md

## Direct dependencies

Aucune. Édition documentaire pure.

## Explicitly out of scope

- `WINDOWS_PFX_BASE64` dans README — CLAUDE.md le désigne « lot 9 »,
  concerne le mécanisme de signature Windows, pas le renommage FR→EN.
- Métadonnées AppStream `packaging/linux/` — CLAUDE.md dit « en attente
  avec Linux ».
- Frontière 1 (`QCoreApplication` dans `engine/core.py`) — reste
  l'écart connu principal ; distinct du sprint.
- Traductions `.ts` (contextes `"Moteur"`, `"Planificateur"`,
  `"Updater"` et strings sources FR) — inchangés.
- Éléments Python restés FR de manière volontaire : voir la liste
  détaillée que ce lot ajoute à CLAUDE.md.

## Tests

Aucun. Docs pures. Vérification qu'aucun rôle Sphinx cassé n'est
introduit (les identifiants nommés dans le README sont en prose et
non `:class:` / `:meth:`).

## Invariants

- Comportement inchangé.
- Aucun code Python modifié.
- CLAUDE.md « Écarts connus » reste une liste courte et fidèle à ce
  qui reste divergent entre le code et l'état visé.

## Validation

Niveau `local`. Relecture, pas de pytest ni ruff.
