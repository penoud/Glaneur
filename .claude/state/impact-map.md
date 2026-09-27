# Impact Map

<!--
Gabarit temporaire, propre à la tâche courante. Remets-le à cet état vide
entre deux lots. N'y stocke ni copie de fichiers, ni logs, ni résultats de
tests volumineux, ni informations déjà présentes dans CLAUDE.md. Voir
CLAUDE.md section « Impact Map » et « Politique de contexte minimal ».
-->

## Task

**Sprint « Identifiants FR → EN ». Batch 6 — sources + system.**

Renommer la surface de `Glaneur/sources/` (base, wordpress, djangoplicity,
package) et de `Glaneur/system.py`.

### `Glaneur/sources/base.py`

Constantes module :
- `_MOTS_COUPURE → _CUT_KEYWORDS`
- `_STATUTS_COUPURE → _CUT_STATUSES`
- `_STATUTS_DEFINITIFS → _DEFINITIVE_STATUSES`

Classe `Classification → ErrorClassification` + champ `categorie → category`.
Les VALEURS de `category` (`"transitoire"`, `"coupure"`, `"definitif"`)
restent FR (chaînes de dispatch persistables via l'engine `res.message`).

Classe `Transport` :
- constructeur : `delai → delay` (paramètre + attribut)
- méthode : `verifier_arret → check_stop`
- méthode : `pause → sleep`

Classe `Source` :
- constructeur : `reglages → settings` (paramètre + attribut)
- class var : `classements → sort_modes`
- méthode abstraite : `inventaire → inventory`
- méthode : `resoudre_groupes → resolve_groups`
- méthode : `convertir_depuis → convert_from`

### `Glaneur/sources/wordpress.py`

- Fonction module : `_nettoyer → _clean`
- Méthodes de `WordPress` : `inventaire → inventory`,
  `resoudre_groupes → resolve_groups`, `_bases_rest → _rest_bases`

### `Glaneur/sources/djangoplicity.py`

- Fonction module : `_sain → _sanitized`
- Constante module : `REPLIS → FALLBACKS`
- Méthodes de `Djangoplicity` : `convertir_depuis → convert_from`,
  `inventaire → inventory`, `_choisir_ressource → _select_resource`

### `Glaneur/sources/__init__.py`

- Fonction : `classements_pour → sort_modes_for`

### `Glaneur/system.py`

Constantes module :
- `NOM_ENTREE → REGISTRY_ENTRY`
- `CLE_RUN → RUN_KEY`

Fonctions publiques :
- `est_gele → is_frozen`
- `commande_lancement → launch_command`
- `demarrage_automatique → autostart` (paramètre `actif → enabled`)
- `demarrage_automatique_actif → autostart_active`
- `ouvrir_dossier → open_dir`
- `definir_dossier_diaporama → set_slideshow_dir`
- `fond_ecran_actuel → current_wallpaper`
- `avancer_diaporama → advance_slideshow`

Fonctions privées :
- `_appel_com → _com_call`
- `_instancier_bureau → _instantiate_desktop`
- `_liberer_bureau → _release_desktop`
- `_creer_tableau_images → _build_images_array`

## Explicitly out of scope

- **`Element`** et ses champs (`ident`, `url`, `nom_fichier`, `date`,
  `mois`, `largeur`, `taille`, `groupe`, `extra`) — lot 4b (persistés
  au manifeste via `dataclasses.asdict`).
- **`Transport.arret`** (param + attribut) et le paramètre `arret` de
  `Engine.__init__` — grosse cascade sur toute l'API des callbacks
  d'interruption ; garder FR ce lot pour rester tractable, à faire dans
  un lot cleanup ultérieur si souhaité.
- **`Engine.dossier_pour`** (méthode de `Engine`, garde FR par cohérence
  avec `Element.groupe`/`.mois` qui restent FR jusqu'au lot 4b).
- **`Engine._pause`** (méthode privée, gardée FR en lot 2 par cohérence
  avec le nom local et le fait qu'elle enveloppe `transport.sleep`).
- **`WordPress._to_element` / `Djangoplicity._to_element`** — restent FR
  parce qu'elles retournent `Element` (renommage `→ Item` au lot 4b) ;
  les deux renommages iront ensemble.
- Valeurs de dispatch FR (chaînes `"transitoire"`, `"coupure"`,
  `"definitif"`, `"galerie"`, `"date"`, `"plat"`, `"wordpress"`,
  `"djangoplicity"`, `"Large"`, `"Small"`, `"Original"`, statuts
  d'engine, marques `"supprime"`, `"restaure"`, etc.).
- Constantes CO/COM identifiées par des UUID Microsoft
  (`_CLSID_DESKTOP_WALLPAPER`, `_IID_IDESKTOP_WALLPAPER`, `_VT_*`, etc.) :
  gardent leur nom actuel (déjà EN-ish + collisions avec spec Windows).
- Contexte Qt `"Updater"` etc. et strings sources FR : inchangés.

## Directly modified

- Glaneur/sources/base.py
- Glaneur/sources/wordpress.py
- Glaneur/sources/djangoplicity.py
- Glaneur/sources/__init__.py
- Glaneur/system.py
- Glaneur/engine/core.py            (Transport(...) call, `self.source.*`
                                      chains, imports d'`ErrorClassification`
                                      / `classify_error`)
- Glaneur/config.py                 (`from .sources import
                                      sort_modes_for` + usage)
- app.py                            (imports depuis `Glaneur.system`)
- tests/test_source_base.py         (Classification/categorie)
- tests/test_source_wordpress.py    (méthodes)
- tests/test_source_djangoplicity.py
- tests/test_sources_edges.py       (_sain, _nettoyer)
- tests/test_system.py              (fonctions)
- tests/test_core.py                (patchs sur `source.inventaire`,
                                      `source.resoudre_groupes`)
- tests/test_boundaries.py          (potentiel : liste des imports Qt)

## Direct dependencies

- Sphinx docstrings : rôles `:class:`, `:meth:`, `:func:`, ``\`\`X\`\```
  sur `Classification`, `Source.inventaire`, `Transport.pause`,
  `resoudre_groupes`, etc. Le lot met à jour les rôles au fil des
  edits.
- CLAUDE.md « Écarts connus » : le premier écart parle du moteur/Qt,
  le second des identifiants Python restants. Ce lot fait avancer le
  deuxième mais ne le solde pas (Config fields lot 4b, Element lot 4b,
  arret & Engine._pause différés). Aucune modif de CLAUDE.md ce lot.
- Frontière 1 : les sources et `system.py` restent Qt-free (déjà).

## Invariants

- **Format JSON du manifeste et du config inchangés** : rien de persisté
  touché (Element FR ; Config fields FR).
- **`.ts` / `.qm` inchangés** : aucune string source ou contexte de
  traduction touché.
- **Valeurs de `Classification.category`** (`"transitoire"`, `"coupure"`,
  `"definitif"`) restent bit-à-bit identiques : ce sont des chaînes
  de dispatch consommées par `Engine.run`.
- **Suite complète green** après renommage.
- `test_boundaries.py` : les imports Qt de `system.py` restent limités
  aux appels ctypes/COM (aucun Qt). Les sources restent Qt-free.

## Validation

Niveau **`full`** — le lot traverse `sources/`, `system.py`, `engine/core.py`
et les couches d'app/tests.

- `pytest` complet + couverture.
- `ruff check` global.
- Sphinx : différé, cf. lots précédents.
