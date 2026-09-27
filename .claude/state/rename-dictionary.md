# Dictionnaire de renommage FR → EN

<!--
Source de vérité pour le sprint « Identifiants FR → EN ». Chaque lot
suivant s'y réfère pour choisir un nom. Toute divergence se corrige ici
d'abord, dans le code ensuite.

Une entrée = un identifiant Python (classe, méthode, fonction, attribut,
constante). Les valeurs de chaînes stockées (JSON, Qt) sont hors table.

Statut :
- `pending`     : décidé mais pas encore appliqué (état de départ).
- `in-progress` : lot en cours modifie cet identifiant.
- `done`        : appliqué, tests + docs à jour.
- `skipped`     : identifiant qui reste FR (raison en note).
-->

## Rappels et contraintes

Ces règles limitent le libre choix des noms. Un renommage qui les enfreint
est bloqué en review.

- **Persistance**. Les clés JSON écrites par `Config.sauver` sont un
  contrat externe. Renommer un champ dataclass renomme la clé JSON :
  interdit hors lot 4b. Le lot 4b introduit le shim FR → EN en lecture.
- **`Element.mois`** est écrit dans le manifeste JSON par
  `Moteur.sauver_manifeste` (via `dataclasses.asdict`). Cette clé
  entre aussi sous le lot 4b, pas dans le lot 6.
- **Valeurs de `Config.classement`** (`"galerie"`, `"date"`, `"plat"`)
  et de `Classification.categorie` (`"transitoire"`, `"coupure"`,
  `"definitif"`) sont **des chaînes**, pas des identifiants. Hors sprint.
- **Chaînes de l'UI Qt** (arguments de `QCoreApplication.translate` et
  équivalents dans les modules UI) restent FR jusqu'au lot 7 optionnel.
- **Docstrings Sphinx** contiennent des rôles `:class:`, `:meth:`,
  `:func:`, `:attr:`, ``\`\`X\`\`\`\`\``. Renommer un identifiant impose
  de mettre à jour ces références dans le même commit, sous peine
  d'échec `sphinx-build -W`.
- **Compat rétro dans le code**. Pas d'alias FR public (`Moteur =
  Engine`) ni de re-exports temporaires : le sprint casse net, sauf
  au lot 4b pour les clés JSON persistées.

## Classes (`Glaneur/`)

Colonne « Lot » = lot cible.

| FR                          | EN                     | Fichier                             | Lot | Notes |
| --------------------------- | ---------------------- | ----------------------------------- | --- | ----- |
| Moteur                      | Engine                 | Glaneur/engine/core.py              | 2   | Réexporté par `engine/__init__.py`. |
| Resultat                    | RunResult              | Glaneur/engine/result.py            | 2   | Éviter la collision avec le nom de module `result.py` : garder le module, renommer la classe seulement. `RunResult` plutôt que `Result` pour rester chercheble. |
| Element                     | Item                   | Glaneur/sources/base.py             | 6   | `Item` sans qualification : contexte source évident. Alternative envisagée `SourceItem`, écartée pour la brièveté aux sites d'appel. |
| Classification              | ErrorClassification    | Glaneur/sources/base.py             | 6   | Décrit une erreur, pas une catégorie générique. |
| Interrompu                  | Interrupted            | Glaneur/engine/core.py              | 2   | Exception. Reste réexportée depuis `engine/__init__.py`. |
| Planificateur               | Scheduler              | Glaneur/scheduler.py                | 3   |  |
| VerificationMiseAJour       | UpdateCheck            | Glaneur/updater/qt_threads.py       | 5   |  |
| TelechargementMiseAJour     | UpdateDownload         | Glaneur/updater/qt_threads.py       | 5   |  |

`Config`, `Options`, `Source`, `WordPress`, `Djangoplicity`, `Transport`,
`Version`, `Release`, `ReleaseAsset`, `UpdateInfo`, `GitHubReleaseProvider`,
`DownloadError`, `GUID` : conservés (déjà EN ou noms propres).

## Fonctions et méthodes

### Moteur / engine (lot 2)

| FR                    | EN                         | Fichier                             | Notes |
| --------------------- | -------------------------- | ----------------------------------- | ----- |
| charger_manifeste     | load_manifest              | engine/core.py, engine/read_manifest.py |  |
| sauver_manifeste      | save_manifest              | engine/core.py, engine/write_manifest.py | La méthode et l'helper module. |
| lire_manifeste        | read_manifest              | engine/read_manifest.py             | Helper bas-niveau. |
| charger_cache         | load_cache                 | engine/core.py, engine/read_cache.py |  |
| sauver_cache          | save_cache                 | engine/core.py, engine/write_cache.py |  |
| lire_cache            | read_cache                 | engine/read_cache.py                |  |
| ecrire_cache          | write_cache                | engine/write_cache.py               |  |
| ecrire_manifeste      | write_manifest             | engine/write_manifest.py            |  |
| chemin_cache          | cache_path                 | engine/cache_path.py                | Le module s'appelle déjà `cache_path.py` : renommage aligné. |
| chemin_manifeste      | manifest_path              | engine/manifest_path.py             | Idem. |
| chemin_libre          | free_path                  | engine/sanitize.py                  | Trouve un chemin non collidant. |
| nettoyer              | clean                      | engine/core.py, engine/delete_image.py | `.nettoyer` sur `Moteur` → `.clean`. |
| _nettoyer             | _clean                     | engine/_merge.py                    |  |
| restaurer             | restore                    | engine/core.py, engine/restore.py   |  |
| inventaire            | inventory                  | engine/core.py                      |  |
| lister_supprimees     | list_deleted               | engine/list_deleted.py              |  |
| supprimer_image       | delete_image               | engine/delete_image.py              |  |
| _fusionner_marques_ui | _merge_ui_marks            | engine/_merge.py                    |  |
| classer_erreur        | classify_error             | sources/base.py                     | Renvoie une `ErrorClassification`. |
| executer              | run                        | engine/core.py                      | Nom d'action principal du moteur. Attention conflit avec `Moteur.run` existant s'il y en a. |
| _verifier_arret       | _check_stop                | engine/core.py                      |  |
| verifier_arret        | check_stop                 | engine/core.py                      |  |

### Scheduler (lot 3)

| FR                    | EN                         | Fichier                             | Notes |
| --------------------- | -------------------------- | ----------------------------------- | ----- |
| differer              | defer                      | scheduler.py                        |  |
| marquer_execution     | mark_run                   | scheduler.py                        |  |
| echeance_atteinte     | is_due                     | scheduler.py                        |  |
| prochaine             | next_run                   | scheduler.py                        |  |
| derniere              | last_run                   | scheduler.py                        |  |
| report_actif          | defer_active               | scheduler.py                        | Attention : renommé récemment en public (voir historique frontière 1). |
| est_gele              | is_frozen                  | scheduler.py                        |  |
| _retenter_apres       | _retry_after               | scheduler.py                        |  |
| texte_prochaine       | next_run_text              | scheduler_labels.py                 | Le module reste `scheduler_labels.py` : c'est l'helper UI post-frontière 1. |

### Config (lot 4a — méthodes seulement)

| FR                    | EN                         | Fichier      | Notes |
| --------------------- | -------------------------- | ------------ | ----- |
| charger               | load                       | config.py    | Méthode de classe. Extension au lot 4b : accepter clés JSON FR. |
| sauver                | save                       | config.py    |  |
| resoudre_groupes      | resolve_groups             | config.py    |  |
| classements_pour      | sort_modes_for             | config.py    | `classement` = mode de tri de la galerie. Voir aussi lot 4b si la valeur `"galerie"` change (non prévu). |
| libelle_classement    | sort_mode_label            | config.py    |  |
| libelle_intervalle    | interval_label             | config.py    |  |
| dossier_config        | config_dir                 | config.py    |  |
| dossier_images_defaut | default_images_dir         | config.py    |  |
| dossier_traductions   | translations_dir           | config.py    |  |
| dossier_pour          | dir_for                    | config.py    |  |
| _anciens_dossiers_config | _legacy_config_dirs     | config.py    |  |
| migrer_depuis_ancien_nom | migrate_from_legacy_name | config.py    | Cite « WpImageDownloader → Glaneur » : commentaire à revoir dans le même commit. |
| installer_traducteur  | install_translator         | i18n.py      |  |
| resoudre_langue       | resolve_language           | i18n.py      |  |
| convertir_depuis      | from_env                   | version.py   | Sur `Version`. `from_env` est le pattern usuel Python. |

### Config (lot 4b — champs dataclass, format persistant)

Ces renommages traversent la persistance. Le lot 4b lit les deux
orthographes et écrit la nouvelle.

| FR                    | EN                         | Fichier      | Clé JSON | Notes |
| --------------------- | -------------------------- | ------------ | -------- | ----- |
| dossier               | target_dir                 | config.py    | oui      | Dataclass `Config`. |
| intervalle_heures     | interval_hours             | config.py    | oui      |  |
| largeur_min           | min_width                  | config.py    | oui      |  |
| classement            | sort_mode                  | config.py    | oui      | Valeurs (`galerie`, `date`, `plat`) inchangées : hors sprint. |
| type_source           | source_type                | config.py    | oui      | Idem pour les valeurs (`wordpress`, `djangoplicity`). |
| format_image          | image_format               | config.py    | oui      | Valeurs (`Large`, …) inchangées. |
| verifier_integrite    | verify_integrity           | config.py    | oui      |  |
| diaporama_dossier     | slideshow_dir              | config.py    | oui      |  |
| delai_requetes        | request_delay              | config.py    | oui      |  |
| derniere_execution    | last_run                   | config.py    | oui      | Attention à ne pas collisionner avec `Scheduler.last_run` (méthode, pas champ). |
| retenter_apres        | retry_after                | config.py    | oui      |  |
| backoff_niveau        | backoff_level              | config.py    | oui      |  |
| lancer_au_demarrage   | run_at_startup             | config.py    | oui      |  |
| fermer_dans_barre     | close_to_tray              | config.py    | oui      |  |
| verifier_maj_demarrage| check_updates_on_start     | config.py    | oui      |  |
| langue                | language                   | config.py    | oui      |  |
| _chemin               | _path                      | config.py    | non (repr=False, compare=False) | Interne. |

`notifications` et `site` restent inchangés (déjà EN).

### Updater (lot 5)

| FR                    | EN                         | Fichier                       | Notes |
| --------------------- | -------------------------- | ----------------------------- | ----- |
| telecharger           | download                   | updater/downloader.py         | Conflit potentiel avec la fonction module `download` : garder `download` comme méthode et supprimer la fonction si redondante. À trancher dans le lot 5. |
| valider               | verify                     | updater/downloader.py         | Vérifie le sha256 après téléchargement. |
| _appel_com            | _com_call                  | updater/qt_threads.py         |  |
| _compact_line         | _compact_line              | updater/downloader.py         | Déjà EN. |
| _is_stable            | _is_stable                 | updater/version.py            | Déjà EN. |

### Sources et base (lot 6)

| FR                    | EN                         | Fichier                       | Notes |
| --------------------- | -------------------------- | ----------------------------- | ----- |
| _bases_rest           | _rest_bases                | sources/wordpress.py          |  |
| _choisir_ressource    | _select_resource           | sources/djangoplicity.py      |  |
| _creer_tableau_images | _build_images_table        | sources/wordpress.py          |  |
| _nominale             | _nominal                   | sources/base.py               | Nom de méthode privée. |
| _sain                 | _sanitized                 | sources/base.py               |  |
| _pause                | _sleep                     | sources/base.py               | `_pause` chevauche le mot-clé abstrait Python `pass` visuellement ; `_sleep` explicite l'attente. |
| pause                 | sleep                      | sources/base.py               | Méthode publique. Idem justification. |
| _to_element           | _to_item                   | sources/wordpress.py, sources/djangoplicity.py | Suit le renommage `Element → Item` (lot 6, même lot). |

### System / bug report / logsetup (lot 6)

| FR                    | EN                         | Fichier               | Notes |
| --------------------- | -------------------------- | --------------------- | ----- |
| avancer_diaporama     | advance_slideshow          | system.py             |  |
| commande_lancement    | launch_command             | system.py             |  |
| fond_ecran_actuel     | current_wallpaper          | system.py             |  |
| _declencher_report    | _trigger_defer             | system.py             | Vérifier le lien avec le scheduler (lot 3) avant le lot 6. |
| _instancier_bureau    | _instantiate_desktop       | system.py             |  |
| _liberer_bureau       | _release_desktop           | system.py             |  |
| definir_dossier_diaporama | set_slideshow_dir      | system.py             |  |
| demarrage_automatique | autostart                  | system.py             |  |
| demarrage_automatique_actif | autostart_active     | system.py             |  |
| ouvrir_dossier        | open_dir                   | system.py             |  |
| format_octets         | format_bytes               | engine/format_bytes.py| Le module s'appelle déjà `format_bytes.py`. |
| _tail_log             | _tail_log                  | bug_report.py         | Déjà EN. |

## Champs de dataclass hors `Config`

Ces renommages n'affectent pas la persistance : `Options` est passé en
mémoire, `Resultat` n'est pas sérialisé côté disque (utilisé pour le
retour d'exécution et l'affichage), `Element` est écrit au manifeste
via `dataclasses.asdict` et ses clés sont donc persistées → **traité
au lot 4b, pas au lot 6**.

### `Options` (lot 2, en même temps que le moteur)

| FR              | EN               | Notes |
| --------------- | ---------------- | ----- |
| dossier         | target_dir       |  |
| classement      | sort_mode        |  |
| largeur_min     | min_width        |  |
| delai           | delay            |  |
| verifier        | verify           |  |
| depuis          | since            |  |
| jusqua          | until            |  |
| utiliser_cache  | use_cache        |  |
| type_source     | source_type      |  |
| format_image    | image_format     |  |

### `Resultat` → `RunResult` (lot 2)

| FR              | EN                 | Notes |
| --------------- | ------------------ | ----- |
| telechargees    | downloaded         |  |
| reprises        | resumed            |  |
| inchangees      | unchanged          |  |
| deja_presentes  | already_present    |  |
| supprimees      | deleted            |  |
| ignorees        | skipped            |  |
| echecs          | failures           |  |
| octets          | bytes              | ok en Python (pas de collision avec le builtin `bytes` sur un attribut). |
| interrompu      | interrupted        |  |
| reporte         | deferred           |  |
| retenter_apres  | retry_after        |  |
| message         | message            | Déjà EN. |
| details         | details            | Déjà EN. |

### `Element` → `Item` (lot 4b, format persistant)

Alignés ici pour la traçabilité, appliqués **au même lot que les clés
`Config`** puisqu'ils partagent la contrainte de shim de compat.

| FR              | EN                 | Notes |
| --------------- | ------------------ | ----- |
| ident           | ident              | Reste (identifiant chaîne, préexistant EN). |
| nom_fichier     | filename           |  |
| date            | date               | Déjà EN. |
| mois            | month              | Clé de manifeste. |
| largeur         | width              | Clé de manifeste. |
| taille          | size               | Clé de manifeste. |
| groupe          | group              | Clé de manifeste. |
| extra           | extra              | Déjà EN. |

### `Classification` → `ErrorClassification` (lot 6)

| FR              | EN                 | Notes |
| --------------- | ------------------ | ----- |
| categorie       | category           | Valeurs de chaîne inchangées. |
| retry_after     | retry_after        | Déjà EN. |

## Constantes

| FR                    | EN                            | Fichier      | Notes |
| --------------------- | ----------------------------- | ------------ | ----- |
| NOM_APP               | APP_NAME                      | config.py    |  |
| NOM_ENTREE            | REGISTRY_ENTRY                | config.py    | Nom d'entrée dans le registre Windows. |
| CLE_RUN               | RUN_KEY                       | config.py    | Clé Registry Windows. |
| INTERVALLES           | INTERVALS                     | config.py    |  |
| CLASSEMENTS           | SORT_MODES                    | config.py    |  |
| TYPES_SOURCE          | SOURCE_TYPES                  | config.py    |  |
| FORMATS_DJANGOPLICITY | DJANGOPLICITY_FORMATS         | config.py    |  |
| LANGUES_DISPONIBLES   | AVAILABLE_LANGUAGES           | i18n.py      |  |
| BACKOFFS_S            | BACKOFFS_S                    | scheduler.py | Déjà EN au sens du sprint. |

`API`, `APPDATA`, `ESA`, `ESO`, `GNOME`, `HKCU`, `HKEY_CURRENT_USER`,
`JSON`, `MTA`, `PYZ`, `REST`, `UTC`, `XDG_CONFIG_HOME`, `README`, `ISO`,
`JPEG`, `TIFF`, `WINFUNCTYPE`, `POINTER`, `REG_SZ`, `KEY_QUERY_VALUE`,
`KEY_SET_VALUE`, `SPI_GETDESKWALLPAPER`, `S_OK`, `S_FALSE`,
`RPC_E_CHANGED_MODE`, `TYPE_CHECKING`, `GUID`, GitHub-related :
inchangés (acronymes, API externes, constantes système).

## Chaînes littérales déjà en français : hors sprint

- Valeurs de `Config.classement` / `Options.classement` :
  `"galerie"`, `"date"`, `"plat"`.
- Valeurs de `Config.type_source` : `"wordpress"`, `"djangoplicity"`
  (déjà EN).
- Valeurs de `Classification.categorie` : `"transitoire"`, `"coupure"`,
  `"definitif"`.
- Libellés d'UI (`QCoreApplication.translate`) dans `scheduler_labels.py`
  et modules UI.
- Clés `INTERVALLES` (`"Manuel"`, `"1 heure"`, …), `CLASSEMENTS`,
  `TYPES_SOURCE`, `FORMATS_DJANGOPLICITY` : ce sont des libellés d'UI
  utilisés comme clés de dict. Voir lot 7 pour le passage à des IDs
  stables + libellés traduits.

Ces éléments sont **volontairement laissés FR par ce sprint**. Un lot
suivant (7, hors code) devra les traiter avec l'i18n owner.

## Fichiers hors périmètre de tout renommage identifiant

- `packaging/**` : ne référence pas d'identifiants Python à renommer.
- `docs/sphinx/api/*.rst` : régénéré par `make apidoc` après chaque
  lot ; jamais édité à la main.
- `translations/*.qm` : régénéré depuis `.ts`, jamais édité.
- `translations/*.ts` : hors sprint (lot 7 optionnel).

## Suivi statut (à jour à la clôture de Batch 0)

Tous les identifiants ci-dessus sont au statut `pending`. Chaque lot met
à jour la ligne de statut de ses entrées lors de son commit d'ouverture.
