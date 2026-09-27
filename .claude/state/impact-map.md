# Impact Map

<!--
Gabarit temporaire, propre à la tâche courante. Remets-le à cet état vide
entre deux lots. N'y stocke ni copie de fichiers, ni logs, ni résultats de
tests volumineux, ni informations déjà présentes dans CLAUDE.md. Voir
CLAUDE.md section « Impact Map » et « Politique de contexte minimal ».
-->

## Task

**Sprint « Identifiants FR → EN ». Batch 2 — moteur.**

Renommer la surface publique de `Glaneur/engine/` :

- classes : `Moteur → Engine`, `Resultat → RunResult`, exception
  `Interrompu → Interrupted` (définie dans `Glaneur/sources/base.py`
  mais raise/catch et export depuis l'engine → tirée par la conversation
  principale du lot 2 pour rester cohérent).
- fonctions module engine (leaf files) : `chemin_cache → cache_path`,
  `chemin_manifeste → manifest_path`, `nettoyer → clean`,
  `format_octets → format_bytes`, `_fusionner_marques_ui →
  _merge_ui_marks`, `lire_cache → read_cache`, `ecrire_cache →
  write_cache`, `lire_manifeste → read_manifest`, `ecrire_manifeste →
  write_manifest`, `supprimer_image → delete_image`,
  `restaurer → restore`, `lister_supprimees → list_deleted`.
- méthodes `Engine` : `charger_manifeste → load_manifest`,
  `sauver_manifeste → save_manifest`, `charger_cache → load_cache`,
  `sauver_cache → save_cache`, `nettoyer` (helper) → `_clean_group`
  (méthode interne différente du helper module), `chemin_libre →
  free_path`, `_verifier_arret → _check_stop`,
  `_declencher_report → _trigger_defer`, `executer → run`.
- fonction `classer_erreur → classify_error` dans
  `Glaneur/sources/base.py` (importée par le moteur ; la dataclass
  `Classification` et son champ `categorie` restent FR — lot 6).
- champs `Options` (mémoire uniquement) : `dossier → target_dir`,
  `classement → sort_mode`, `largeur_min → min_width`, `delai → delay`,
  `verifier → verify`, `depuis → since`, `jusqua → until`,
  `utiliser_cache → use_cache`, `type_source → source_type`,
  `format_image → image_format`.
- champs `RunResult` (mémoire, jamais sérialisé) : `telechargees →
  downloaded`, `reprises → resumed`, `inchangees → unchanged`,
  `deja_presentes → already_present`, `supprimees → deleted`,
  `ignorees → skipped`, `echecs → failures`, `octets → bytes`,
  `interrompu → interrupted`, `reporte → deferred`, `retenter_apres →
  retry_after`.

**Hors périmètre strict :** les champs FR de `Config` (lot 4b, format
persistant, mêmes noms mais **champs différents** — attention aux
sites `options = Options(target_dir=cfg.dossier, sort_mode=cfg.classement,
…)` qui traduisent d'un vocabulaire à l'autre), les dataclass `Element`
et `Classification` (persistance + lot 6), le scheduler (`Planificateur`,
lot 3), les libellés Qt (`.translate("Moteur", …)`), les valeurs de
chaînes (`"transitoire"`, `"coupure"`, `"definitif"`, `"galerie"`,
`"date"`, `"plat"`, `"introuvable"`, `"inchangé"`, `"repris"`,
`"supprime"`, `"restaure"`, …).

## Directly modified

Engine (rewrite):
- Glaneur/engine/__init__.py                (imports + `__all__`)
- Glaneur/engine/core.py                    (Moteur, Options.*, Resultat.*)
- Glaneur/engine/result.py                  (classe + champs)
- Glaneur/engine/options.py                 (champs)
- Glaneur/engine/cache_path.py              (fonction)
- Glaneur/engine/manifest_path.py           (fonction)
- Glaneur/engine/sanitize.py                (fonction)
- Glaneur/engine/format_bytes.py            (fonction)
- Glaneur/engine/_merge.py                  (fonction)
- Glaneur/engine/read_cache.py              (fonction)
- Glaneur/engine/write_cache.py             (fonction)
- Glaneur/engine/read_manifest.py           (fonction)
- Glaneur/engine/write_manifest.py          (fonction)
- Glaneur/engine/delete_image.py            (fonction)
- Glaneur/engine/restore.py                 (fonction)
- Glaneur/engine/list_deleted.py            (fonction)

Sources (nécessaire pour la cohérence engine) :
- Glaneur/sources/base.py                   (`Interrompu → Interrupted`,
                                             `classer_erreur → classify_error`)
- Glaneur/sources/__init__.py               (`__all__`)
- Glaneur/sources/wordpress.py              (usages de `Interrompu` /
                                             `classer_erreur`)
- Glaneur/sources/djangoplicity.py          (usages)

Consommateurs :
- Glaneur/scheduler.py                      (import `Resultat` → `RunResult`
                                             + éventuels champs)
- app.py                                    (construction `Options`,
                                             `Moteur`, lecture `Resultat`)
- cli.py                                    (idem)

Tests :
- tests/test_core.py                        (majeur)
- tests/test_scheduler.py                   (import `Resultat`)
- tests/test_cli.py                         (options / résultats)
- tests/test_source_base.py                 (`classer_erreur`, `Interrompu`)
- tests/test_source_wordpress.py            (`Interrompu`, options)
- tests/test_source_djangoplicity.py        (idem)
- tests/test_sources_edges.py               (idem)
- tests/test_boundaries.py                  (potentiel : liste des imports Qt)

## Direct dependencies

- Documentation Sphinx : rôles `:class:\`Resultat\``, `:meth:\`Moteur.…\``,
  ``\`\`Moteur\`\``, `:func:\`ecrire_cache\``, `:mod:\`Glaneur.engine.core\``
  etc. dans les docstrings de `engine/`, `scheduler.py`, `config.py`.
  Régénérer `docs/sphinx/api/*.rst` après renommage (`make -C docs/sphinx
  apidoc`) et vérifier `sphinx-build -W`.
- CLAUDE.md « Écarts connus » : le premier écart parle de
  `Glaneur/engine/core.py` qui importe `QCoreApplication`. Lot 2 ne
  résout pas cet écart (frontière 1), il ne l'aggrave pas non plus →
  aucune modif de CLAUDE.md.
- `translations/*.ts` : `Glaneur/engine/core.py` appelle
  `.translate("Moteur", …)` avec `"Moteur"` comme contexte
  d'internationalisation. Ce **contexte** est un identifiant de
  traduction : le changer ferait perdre les traductions actuelles. **On
  garde `"Moteur"` littéral** au lieu de le calquer sur `Engine`.
- `packaging/**` : non concerné (pas de référence à ces identifiants).

## Tests

- Suite complète : `pytest` avec couverture (la rupture touche l'API
  publique `Glaneur.engine.*`).
- `ruff check` global.
- `sphinx-build -W -n -b html docs/sphinx docs/sphinx/_build/html`
  après régénération des `.rst`.
- Boundaries : `test_boundaries.py` scanne les imports Qt de
  `scheduler.py`, `detect.py`, `engine/*.py`, `sources/*.py`. Le
  renommage `Moteur → Engine` ne change pas la liste des imports Qt du
  moteur (`QCoreApplication` reste importé → l'entrée `xfail(strict=True)`
  du moteur reste **xfail**). Ne pas la retirer.

## Explicitly out of scope

- Frontière 1 (Qt hors moteur) — chantier séparé (voir écart connu
  CLAUDE.md, événements structurés).
- Champs `Config` (lot 4b). Attention : `Config.dossier`,
  `Config.classement`, `Config.type_source`, `Config.format_image`,
  `Config.largeur_min`, `Config.retenter_apres` restent nommés FR ce
  lot-ci. Les sites `Options(target_dir=cfg.dossier, …)` traduisent.
- `Element`, `Classification` (lot 4b et lot 6).
- `Planificateur` (lot 3) — mais l'attribut `.telechargees`, `.reporte`,
  `.retenter_apres` sur `RunResult` que le scheduler lit doit être
  renommé côté scheduler dans **ce** lot (impossible autrement, sinon
  le scheduler casse). Renommer *seulement* la lecture des champs,
  pas la classe `Planificateur` ni ses méthodes.
- Chaînes littérales dispatch (`"transitoire"`, `"coupure"`,
  `"definitif"`, `"galerie"`, `"date"`, `"plat"`, `"introuvable"`,
  `"inchangé"`, `"repris"`, `"supprime"`, `"restaure"`, `"divers"`).
- Contexte Qt `.translate("Moteur", …)` : reste `"Moteur"` littéral.

## Invariants

- **`.qm`/`.ts` inchangés.** Le contexte de traduction `"Moteur"` et
  toutes les chaînes source FR restent bit-à-bit identiques.
- **Format persistant inchangé.** Ni le manifeste (`Element` FR), ni le
  cache (structure `{"date_max": …, "titres": {…}}` peu impactée), ni
  `config.json` (champs `Config` FR) ne changent. Un manifeste écrit
  avant ce lot reste lisible après.
- **Aucune modification de comportement.** Ce lot est un rename pur.
  Les tests fonctionnels existants doivent passer sans changement
  d'assertion, seuls les noms qu'ils invoquent changent.
- **Docs Sphinx `-W` vertes.** Toute référence `:meth:`, `:class:`,
  `:func:`, `:attr:`, `\`\`X\`\`` visant un identifiant renommé est mise
  à jour dans le même commit.

## Validation

Niveau **`full`** selon la table CLAUDE.md :

- `pytest` complet + couverture.
- `ruff check` global.
- `sphinx-build -W -n -b html docs/sphinx docs/sphinx/_build/html`
  après `make -C docs/sphinx apidoc`.
- Relecture par `invariant-reviewer` (Sonnet) — surface `Glaneur.engine`
  et frontière 1 potentiellement affectée si un import est ajouté.
  **Pas de `review Opus`** : pas de rupture de format persistant, pas
  d'architecture nouvelle.
