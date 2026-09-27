# Impact Map

<!--
Gabarit temporaire, propre à la tâche courante. Remets-le à cet état vide
entre deux lots. N'y stocke ni copie de fichiers, ni logs, ni résultats de
tests volumineux, ni informations déjà présentes dans CLAUDE.md. Voir
CLAUDE.md section « Impact Map » et « Politique de contexte minimal ».
-->

## Task

**Sprint « Identifiants FR → EN ». Batch 4a — config methods + i18n.**

Renommer la surface non persistée de `Glaneur/config.py` et de
`Glaneur/i18n.py`. **Les champs dataclass de `Config` restent FR** —
c'est le lot 4b qui les traite avec le shim de compatibilité.

### `Glaneur/config.py`

Constantes module :
- `NOM_APP → APP_NAME`
- `INTERVALLES → INTERVALS`
- `CLASSEMENTS → SORT_MODES`
- `TYPES_SOURCE → SOURCE_TYPES`
- `FORMATS_DJANGOPLICITY → DJANGOPLICITY_FORMATS`
- `_ANCIENS_NOMS_APP → _LEGACY_APP_NAMES`
- `_ANCIENS_NOMS_XDG → _LEGACY_XDG_NAMES`

Fonctions module :
- `dossier_config → config_dir`
- `_anciens_dossiers_config → _legacy_config_dirs`
- `migrer_depuis_ancien_nom → migrate_from_legacy_name`
- `dossier_images_defaut → default_images_dir`

Méthodes/properties de `Config` :
- `charger → load`
- `sauver → save`
- `valider → validate`
- `libelle_intervalle → interval_label` (property)
- `libelle_classement → sort_mode_label` (property)

Attribut privé :
- `_chemin → _path` (interne, `repr=False, compare=False`, non persisté)

### `Glaneur/i18n.py`

Constantes module :
- `LANGUES_DISPONIBLES → AVAILABLE_LANGUAGES`

Fonctions module :
- `dossier_traductions → translations_dir`
- `resoudre_langue → resolve_language`
- `installer_traducteur → install_translator`

## Directly modified

- Glaneur/config.py                (constantes, fonctions, méthodes)
- Glaneur/i18n.py                  (constantes, fonctions)
- Glaneur/scheduler.py             (`self.config.sauver()` — 3 sites)
- app.py                           (imports, appels)
- cli.py                           (imports, appels)
- Glaneur/bug_report.py            (si NOM_APP importé ; vérifier)
- Glaneur/updater/qt_threads.py    (idem, à vérifier)
- Glaneur/updater/version.py       (idem)
- tests/test_config.py             (majeur)
- tests/test_i18n.py               (majeur)
- tests/test_cli.py                (Config.charger monkeypatch)
- tests/test_scheduler.py          (helper `_cfg` qui utilise Config.sauver ?)
- tests/test_bug_report.py         (NOM_APP ?)

## Direct dependencies

- **Sphinx docstrings** : rôles `:meth:\`Config.charger\``, `:meth:\`Config.sauver\``,
  `:func:\`dossier_config\``, `:func:\`dossier_images_defaut\``,
  `:func:\`installer_traducteur\``, `:func:\`resoudre_langue\``,
  `:attr:\`INTERVALLES\`` etc. dans les docstrings de `config.py`,
  `i18n.py`, `scheduler.py`, `engine/*.py`, `sources/*.py`.
- CLAUDE.md « Écarts connus » : le renommage `WpImageDownloader → Glaneur`
  est déjà mentionné dans le commentaire de `_ANCIENS_NOMS_*` — le message
  du commit devra pointer que le renommage passe côté fonction/constante
  mais que les **chaînes** `"WpImageDownloader"` et `"wp-image-downloader"`
  restent inchangées (elles pointent sur des chemins de config existants
  chez l'utilisateur, changer les strings casserait la migration).
- `translations/*.ts` : aucun contexte de traduction dans ces modules
  (i18n.py ne fait qu'installer un translator, config.py n'a pas de
  string `.translate()`), donc rien à préserver côté `.ts`.
- `packaging/**` : inchangé.

## Tests

- `pytest` complet + couverture (Config.charger / Config.sauver =
  API publique + touche persistence lecture).
- `ruff check` global.
- Sphinx : différé, comme aux lots 2 et 3.

## Explicitly out of scope

- **Champs dataclass de `Config`** — `site`, `dossier`, `intervalle_heures`,
  `largeur_min`, `classement`, `type_source`, `format_image`,
  `verifier_integrite`, `diaporama_dossier`, `delai_requetes`,
  `derniere_execution`, `retenter_apres`, `backoff_niveau`,
  `lancer_au_demarrage`, `fermer_dans_barre`, `notifications`,
  `verifier_maj_demarrage`, `langue`. Lot 4b avec compat shim.
- Valeurs de dict FR utilisées comme clés dans les tables `INTERVALS`,
  `SORT_MODES`, `SOURCE_TYPES`, `FORMATS_DJANGOPLICITY` (« Manuel
  uniquement », « Par galerie », etc.). Ces clés sont affichées dans l'UI
  et l'inverse des tables sert d'ID stable côté persistance : lot UI
  séparé si jamais.
- Valeurs `"galerie"`, `"date"`, `"plat"`, `"wordpress"`,
  `"djangoplicity"`, `"Large"`, `"Small"`, `"Original"` : valeurs
  persistées / IDs de dispatch — restent.
- Chaînes `"WpImageDownloader"`, `"wp-image-downloader"` dans
  `_LEGACY_APP_NAMES` / `_LEGACY_XDG_NAMES` : chemins réels de l'utilisateur.
- `Source.resoudre_groupes`, `Source.convertir_depuis`,
  `classements_pour` (dans `Glaneur/sources/`) : lot 6.
- `Engine.dossier_pour` (dans `Glaneur/engine/core.py`) : gardé FR
  au lot 2 par cohérence avec `Element` non renommé.
- `Glaneur/system.py::est_gele` : lot 6.

## Invariants

- **Format JSON `config.json` inchangé** : aucun champ dataclass n'est
  renommé, donc les clés persistées sont bit-à-bit identiques.
- **`.qm` / `.ts` inchangés** : pas de string source ou contexte de
  traduction modifié.
- **Chemins legacy inchangés** : les strings `"WpImageDownloader"` /
  `"wp-image-downloader"` restent, sinon la migration `Config.load`
  casse pour un utilisateur qui a l'ancien dossier.
- **`Config.charger` (maintenant `load`) accepte les mêmes clés qu'avant**
  — c'est le lot 4b qui étend la lecture (pas ici).

## Validation

Niveau **`full`** selon la table CLAUDE.md (« Moteur, scheduler,
`config.py` » — pytest + ruff + `invariant-reviewer`).

- `pytest` complet + couverture.
- `ruff check` global.
- Sphinx : différé.
