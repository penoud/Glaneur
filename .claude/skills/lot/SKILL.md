---
name: lot
description: Déroule un lot ou une tâche de docs/feuille-de-route.md de Glaneur avec les sous-agents — cadrage, tests d'abord, implémentation, vérification, relecture.
disable-model-invocation: true
---

Tâche : $ARGUMENTS

Workflow, dans l'ordre :

1. **Cadrage.** Lis la section correspondante de `docs/feuille-de-route.md` et
   uniquement les fichiers directement nécessaires (délègue une exploration
   ciblée si besoin, jamais globale). Identifie :
   - le périmètre et le hors-périmètre ;
   - les invariants de CLAUDE.md réellement touchés ;
   - les hypothèses sur des serveurs tiers, marquées « supposé » ;
   - le plan par fichier ;
   - le niveau de validation attendu (`local`, `module`, `subsystem`, `full`).
2. **Impact Map.** Remplis `.claude/state/impact-map.md` à partir du cadrage.
   C'est ce document — pas ta conversation — qui sera transmis aux sous-agents.
   Ne remplis que les rubriques utiles ; laisse le reste vide.
3. **Accord utilisateur.** Rends-moi le cadrage et l'Impact Map. **Attends mon
   accord** avant d'écrire quoi que ce soit d'autre.
4. **Branche.** `git switch -c lot-<n>-<slug>` depuis un `main` à jour. Jamais
   de travail directement sur `main`.
5. **Tests ciblés.** Délègue les tests du lot à `test-author` en lui passant
   l'Impact Map. Si le plan dépend d'une hypothèse serveur non tranchable en
   local, lance `server-prober` en arrière-plan à ce moment ; n'intègre son
   verdict qu'une fois reçu.
6. **Implémentation ciblée.** Toi, dans cette conversation, par modifications
   limitées aux fichiers listés dans l'Impact Map. Pas de refactor hors lot,
   pas de dette résorbée au passage.
7. **Vérification adaptée à l'impact.** Applique la table « Validation
   conditionnelle » de CLAUDE.md :
   - niveau `local`/`module` : tests concernés + ruff ciblé via `test-runner` ;
   - niveau `subsystem` : ajoute `invariant-reviewer` ;
   - niveau `full` : suite complète, couverture, ruff, Sphinx et
     `invariant-reviewer`.
   Ne lance ces agents que si l'Impact Map les liste.
8. **Review si nécessaire.** N'invoque `invariant-reviewer` que si le
   changement touche une frontière, un invariant, un format persistant ou le
   packaging. Passe-lui l'Impact Map et le diff. Traite tous les « Bloquant »
   avant de continuer.
9. **Validation finale.** Relance uniquement les vérifications réellement
   affectées par les corrections. Ne relance pas la suite complète pour un
   correctif de test local.
10. **Rapport final (en français).**
    - Changements par fichier, avec leur emplacement.
    - Ce qui est vérifié (quels tests, quel niveau) et ce qui reste supposé.
    - Risques restants et message de commit proposé.
    - Mets à jour « Écarts connus » dans CLAUDE.md si le lot en résorbe un.
    - Vide `.claude/state/impact-map.md` en le remettant au gabarit.
    Ne commite qu'avec mon accord ; ne pousse jamais.
