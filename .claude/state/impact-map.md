# Impact Map

<!--
Gabarit temporaire, propre à la tâche courante. Remets-le à cet état vide
entre deux lots. N'y stocke ni copie de fichiers, ni logs, ni résultats de
tests volumineux, ni informations déjà présentes dans CLAUDE.md. Voir
CLAUDE.md section « Impact Map » et « Politique de contexte minimal ».
-->

## Task

**Sprint « Identifiants FR → EN ». Batch 4b — champs `Config` (format
persistant).**

Renommer les champs FR de la dataclass `Config` en anglais. Les clés
JSON de `config.json` deviennent EN à l'écriture ; à la lecture, le
`load()` accepte les deux orthographes via un **shim de compat** pour
qu'un utilisateur existant ne perde pas sa config.

### Renommages `Config`

| FR                        | EN                        |
| ------------------------- | ------------------------- |
| `dossier`                 | `target_dir`              |
| `intervalle_heures`       | `interval_hours`          |
| `largeur_min`             | `min_width`               |
| `classement`              | `sort_mode`               |
| `type_source`             | `source_type`             |
| `format_image`            | `image_format`            |
| `verifier_integrite`      | `verify_integrity`        |
| `diaporama_dossier`       | `slideshow_dir`           |
| `delai_requetes`          | `request_delay`           |
| `derniere_execution`      | `last_run`                |
| `retenter_apres`          | `retry_after`             |
| `backoff_niveau`          | `backoff_level`           |
| `lancer_au_demarrage`     | `run_at_startup`          |
| `fermer_dans_barre`       | `close_to_tray`           |
| `verifier_maj_demarrage`  | `check_updates_on_start`  |
| `langue`                  | `language`                |

`site` et `notifications` sont déjà EN et restent.

### Shim de compat

Dans `Config.load`, avant `setattr`, on traduit chaque clé FR trouvée
dans le JSON vers son nom EN via une table `_LEGACY_FIELD_ALIASES`.
Le shim :

- accepte tout ancien fichier `config.json` sans changement de format,
- accepte un JSON hybride (mix EN/FR) — le EN gagne s'il est présent,
- écrit systématiquement les clés EN via `Config.save`
  (`dataclasses.asdict` sur les champs renommés produit du EN
  directement).

Après un cycle load→save, un vieux `config.json` est réécrit en EN.

### Nouveaux tests requis

- **Round-trip legacy** : écrire un `config.json` avec toutes les clés
  FR, faire `Config.load(chemin)` puis `Config.save()`, relire brut,
  vérifier que le disque contient les clés EN et les mêmes valeurs.
- **Hybride** : JSON avec une clé FR (`dossier`) et une clé EN
  (`sort_mode`) → les deux sont chargées correctement.
- **Cœur inchangé** : la validation (`validate()`) tolère les valeurs
  hors-liste comme avant.

## Directly modified

- Glaneur/config.py                    (dataclass, `_LEGACY_FIELD_ALIASES`,
                                        `load`, `validate`, properties)
- Glaneur/scheduler.py                 (accès aux champs `derniere_execution`,
                                        `retenter_apres`, `intervalle_heures`,
                                        `backoff_niveau`)
- app.py                               (nombreux sites : lecture de
                                        `cfg.classement`, `cfg.dossier`,
                                        etc. + écriture)
- cli.py                               (lecture de `c.dossier`,
                                        `c.delai_requetes`)
- tests/test_config.py                 (tests existants + 2/3 nouveaux
                                        pour le shim et le round-trip)
- tests/test_scheduler.py              (helper `_cfg(...)`)
- tests/test_cli.py                    (patch de Config.load)

## Direct dependencies

- CLAUDE.md « Écarts connus » : l'écart identifiants va être partiellement
  résorbé (Config fields → EN). Note à mettre à jour dans un commit
  ultérieur, pas ici, pour ne pas mélanger deux préoccupations.
- Sphinx : les rôles `:attr:\`Config.dossier\`` etc. dans les docstrings
  d'`engine/options.py`, `sources/base.py`, `scheduler.py`, `config.py`
  changent au fil des renommages.
- `translations/*.ts` : aucun contexte de traduction ni chaîne source
  n'est touché.

## Explicitly out of scope

- **`Element` et ses champs** (`nom_fichier`, `mois`, `largeur`,
  `taille`, `groupe`) : à la relecture des tests, `Element` n'est
  **jamais** sérialisé (le manifeste stocke un `infos` dict à clés
  hardcodées, pas `dataclasses.asdict(Element)`). Le renommage
  d'`Element` n'est donc pas bloqué par la persistance et peut se
  faire dans un lot cleanup séparé sans shim. Reste FR ici.
- **Clés du manifeste** (`taille`, `fichier`, `etag`, `modifie`, `url`,
  `extra`, `supprime`, `restaure`) : elles **sont** persistées et un
  renommage exigerait un shim de manifest-read distinct. Hors périmètre
  de ce lot ; à faire dans un lot 4c éventuel.
- **Valeurs de dispatch** (`"galerie"`, `"date"`, `"plat"`, `"wordpress"`,
  `"djangoplicity"`, `"Large"`, `"Small"`, `"Original"`) : restent
  bit-à-bit identiques.
- CLI flags FR (`--dossier`, `--classement`, `--delai`, `--verifier`,
  `--depuis`, `--jusqua`, `--restaurer`, etc.) : user-facing, restent
  FR jusqu'à un lot UI dédié.
- Attributs argparse `args.dossier`, `args.classement`, etc. : dérivés
  des flags, restent FR pour rester alignés.

## Invariants

- **Rétro-compatibilité de `config.json`** : tout fichier écrit par une
  version antérieure doit se charger sans exception avec les mêmes
  valeurs de champs.
- Après un cycle `load → save`, le fichier disque contient les clés EN
  (migration silencieuse à l'écriture suivante).
- Les valeurs de dispatch et les libellés UI restent inchangés.
- Le contexte Qt et les strings `.ts` restent inchangés.
- Suite complète green, y compris les tests existants qui construisent
  un `Config` via kwargs FR — ceux-là seront migrés vers kwargs EN.

## Validation

Niveau **`full` + reviewer Opus** — rupture de format persistant, cœur
de sprint.

- `pytest` complet + couverture.
- `ruff check` global.
- Nouveaux tests round-trip pour le shim.
- Sphinx : différé, cf. lots précédents.
