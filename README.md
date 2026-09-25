# Glaneur — Multi-source image downloader

> 🇫🇷 [Version française en bas de ce document](#glaneur--téléchargeur-dimages-multi-sources).

> **Disclaimer**
>
> This project is personal and independent. It is not an official product,
> service or partnership of any targeted site. Names and trademarks that may
> be mentioned are used only for descriptive purposes.

> **Former name.** The application was called `WpImageDownloader`
> (`WpImagerDownloader` on the installer side) until version 1.0.42 — a
> leftover from an initial WordPress-only scope. The new name **Glaneur**
> reflects the move to multi-source. Existing installations have their
> config (`%APPDATA%\WpImageDownloader\`) migrated automatically to
> `%APPDATA%\Glaneur\` on first launch.

A Windows application that syncs images published on a remote site to the
local disk. Two kinds of sources are supported:
`WordPress` (through the REST API `/wp-json/wp/v2`) and
`Djangoplicity` (`d2d/` feed used by the ESO, ESA/Hubble… sites). It runs
in the background, updates at the chosen interval and never redownloads
an image that is already present.

---

## 1. Architecture

The layout strictly separates the engine from the interface: `Glaneur/engine.py`
imports nothing from Tkinter and communicates through callbacks. It can
therefore be driven from the UI, from `cli.py`, or from a future Windows
service without rewriting anything.

```
glaneur/
├── app.py                  PySide6 graphical interface
├── cli.py                  Command-line interface (same features)
├── requirements.txt
├── build.bat               Full build in a single command
├── Glaneur/
│   ├── config.py           Persisted preferences (JSON in %APPDATA%)
│   ├── engine.py           Engine: orchestration, manifest, downloads, resumes
│   ├── scheduler.py        Due-date computation (pure logic, no thread)
│   ├── systeme.py          Windows registry, folder opening
│   ├── logsetup.py         Rotating file logger (%APPDATA%\Glaneur\app.log)
│   ├── bug_report.py       Builds the GitHub issues/new URL used by Help → Report a bug
│   ├── i18n.py             Loads QTranslator on startup (see §4 Internationalisation)
│   ├── sources/            Per-site adapters (shared `Source` contract)
│   │   ├── base.py         Abstract `Source` class + shared HTTP `Transport`
│   │   ├── wordpress.py    REST API `/wp-json/wp/v2`
│   │   └── djangoplicity.py `d2d/` feed (ESO, ESA/Hubble…)
│   └── updater/            In-app updates from GitHub Releases
│       ├── github_release.py  Queries the Releases API
│       ├── downloader.py      Download + SHA-256 verification
│       ├── qt_threads.py      Qt threads (check / download) and handoff
│       ├── models.py, version.py
└── build/
    ├── Glaneur.spec        PyInstaller recipe
    └── installer.iss       Inno Setup script
```

**Engine contract.** `Moteur(options, journal, progression, arret).executer()`
returns a `Resultat`. The engine imports neither Qt nor any widget: callbacks
are wired to Qt signals emitted from a `QThread`, and Qt marshals them
automatically back to the main thread through its queued connections. That is
what makes the rule « no widget touched outside the main thread » automatic
rather than something to watch.

The scheduler is reduced to pure logic — it answers « is it time yet? » and
nothing else. Two `QTimer` drive it: a due-date check every 30 s and a
countdown refresh every second. No extra thread; triggering stays entirely on
the main thread.

Cancellation goes through a `threading.Event` checked between each request
and each 64 KB block. An interrupted download leaves a `.part` file, resumed
via a `Range` header on the next pass.

---

## 2. Development

```bash
python -m venv .venv
.venv\Scripts\activate          # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt

python app.py                   # graphical interface
python cli.py --dossier ./photos --verifier
```

Python 3.11 or later. `PySide6-Essentials` is enough: it is the variant
without QtWebEngine or the 3D modules, roughly 90 MB installed instead of
300, and nothing the application uses is missing from it.

On Linux, Qt requires the X11 libraries (`libxcb-cursor0`,
`libxkbcommon-x11-0`). For a headless run:
`QT_QPA_PLATFORM=offscreen python app.py`.

**Tests.** `pip install -r requirements-dev.txt` then
`QT_QPA_PLATFORM=offscreen python -m pytest -q`. `pytest-qt` is required for
the `qtbot` fixture used by the updater QThread tests; the other tests
(engine, scheduler, config, unit updater) run without it.

---

## 3. How it works

**Sources.** The engine delegates to a `Source` adapter (in
`Glaneur/sources/`) exposing two methods: `inventaire()` lists the available
images, and `titre_parent()` resolves a gallery id to a readable label. Two
implementations are shipped:

- `wordpress` — REST API `GET /wp-json/wp/v2/media?per_page=100`, paginated
  through the `X-WP-TotalPages` header. The `source_url` field points
  directly to the full-resolution original.
- `djangoplicity` — `d2d/` feed used by ESO/ESA/Hubble-style sites; the
  image format is configurable (default `Large`, automatic fallback to
  `Small` when `Large` is missing for a given entry).

The choice is made in **Preferences → « Site type »**, or through
`cli.py --type {wordpress,djangoplicity}`. Adding a source amounts to
implementing `Source` and registering it in `sources/SOURCES`.

**Inventory (WordPress).** One request per page, paginated with
`X-WP-TotalPages`. The `source_url` field returns the original.

**Filtering.** Entries below the minimum width (800 px by default) are
discarded: those are sponsor logos, favicons and thumbnails.

**Sorting.** In « by gallery » mode, parent content ids are resolved to
slugs through the endpoints discovered on `/wp-json/wp/v2/types`. In « by
date » mode, folders follow the `YYYY-MM` upload structure. In « everything
in one folder » mode no subfolder is created; since WordPress only
guarantees name uniqueness within a single upload month, a duplicate gets
the media id appended (`match-1234.jpg`). Changing the sort mode does not
move anything: only new images follow the new mode.

**Manifest.** `.etat.json` at the root of the destination folder maps each
image id to its local path, size, ETag and `Last-Modified`. An image that is
already complete triggers no request — on a routine update, only the
inventory travels over the network. A file whose size no longer matches
(interruption, corruption) is queued again.

**API cache.** `.cache.json` sits next to the manifest and remembers the
highest date of the media already seen (`derniere_date_media`) and the
resolved gallery titles (`titres_parents`), keyed by the site URL. On later
runs the inventory only asks the API for media newer than that date (`after=…`
parameter) and gallery resolution avoids any round-trip for ids already
known. If the site URL changes the cache is ignored; `--force` (CLI) and
`--pas-cache` bypass it too. An interruption does not write the cache: only
a clean exit is memorised.

**Deleted images.** A complete image whose file has disappeared from disk
must have been erased by the user: the manifest marks it
(`"supprime": <timestamp>`) and it is no longer redownloaded. The
« Deleted images… » button in the interface, or `cli.py --restaurer [ID…]`,
lifts the mark to put it back in queue. `--force`, which ignores the
manifest, also clears those marks.

**« Verify integrity » option.** Sends a conditional `If-None-Match`
request for each known file. The server answers `304` with no bytes
transferred if its copy is identical. Useful occasionally, unnecessary on a
daily basis.

**Scheduling.** `scheduler.py` compares the current time to
`derniere_execution` stored in the configuration. The due date therefore
survives the application being closed: if the interval elapsed while it was
closed, the update starts on the next launch. An interrupted run does not
update the timestamp.

---

## 4. Configuration

File: `%APPDATA%\Glaneur\config.json`
(`~/.config/glaneur/` elsewhere).

The main window exposes the actions (update, stop, remove the wallpaper,
deleted images) and the log; the settings — site type, URL, destination,
interval, sort mode, minimum width, system integration — live in
**Configuration → Preferences…** (shortcut `Ctrl+,`). The menu
**Help → About…** shows the version and repository, and **Help → Report a
bug…** opens a prefilled GitHub issue (version, platform and the compacted
last 50 lines of log).

| Key | Purpose | Default |
|---|---|---|
| `type_source` | `wordpress` or `djangoplicity` | `wordpress` |
| `site` | URL of the target site | set from the application |
| `dossier` | image destination | user's Pictures folder |
| `intervalle_heures` | 0, 6, 12, 24 or 168 | `24` |
| `largeur_min` | width threshold in pixels | `800` |
| `classement` | `galerie`, `date` or `plat` | `galerie` |
| `format_image` | Djangoplicity: `Large` / `Small` / `Original` | `Large` |
| `verifier_integrite` | conditional revalidation | `false` |
| `verifier_maj_demarrage` | queries GitHub Releases at launch | `true` |
| `lancer_au_demarrage` | `HKCU\...\Run` entry with `--reduit` | `false` |
| `langue` | ISO code (`fr`, `en`); empty = system locale | `""` |
| `fermer_dans_barre` | the close button minimises instead of quitting | `true` |
| `notifications` | balloon after an automatic update | `true` |
| `delai_requetes` | delay between requests, in seconds | `0.5` |
| `diaporama_dossier` | registers the folder as the Windows slideshow source | `false` |
| `derniere_execution` | ISO timestamp, managed by the app | — |

Settings are saved when the Preferences window is validated (OK button).
Values out of bounds are brought back to sane values at load time;
`delai_requetes` has a hard floor of 0.2 s to avoid hammering the target
server.

### Internationalisation

All UI strings go through `self.tr(...)` (widgets) or
`QCoreApplication.translate("BugReport", ...)` (module `bug_report.py`).
Sources are in French; other languages live in
`translations/glaneur_<code>.ts`, compiled to `.qm` which
`Glaneur/i18n.py` installs on startup according to the `langue`
preference (or the system locale when empty). Language changes take effect
on **next launch** — no hot retranslation.

Translator workflow:

```bash
# 1. After editing code: (re)extract strings into the .ts files
python translations/build_translations.py update

# 2. Open and translate with Qt Linguist
pyside6-linguist translations/glaneur_en.ts

# 3. Compile the .ts into .qm consumed by the app
python translations/build_translations.py release
```

`build.bat` calls step 3 automatically before PyInstaller. The `.qm` files
are not versioned (generated at build time); the `.ts` files are.

### Licence and downloaded content

The source code of this project is distributed under the GNU GPL version 3
or any later version. See the [LICENSE](LICENSE) file.

This licence only covers the project's code. It does not cover the images,
videos, texts, logos or other content fetched from the targeted sites.
That content remains subject to its own copyright, trademarks and terms
of use.

---

## 5. Build

### In a single command

```bat
build.bat
```

Creates the virtual environment, compiles with PyInstaller, then calls
Inno Setup if `iscc.exe` is on `PATH`.

### Step by step

```bat
pip install pyinstaller
pyinstaller build\Glaneur.spec --noconfirm --clean
iscc build\installer.iss
```

Outputs: `dist\Glaneur\` then
`build\Output\Glaneur-1.1.0-setup.exe`.

**Icon.** No third-party logo or heraldry is distributed in the repository.
Without an ICO file supplied separately at build time, the application
draws a solid burgundy disc marked « S » on the fly: the tray icon and the
window stay correct, only the executable keeps the default Python icon.

**Windows signing.** Unsigned PyInstaller executables can be misclassified
as suspicious by Microsoft Defender, especially on first publications.
To obtain a recognised installer, the Windows workflow signs both the
executable and the installer when an Authenticode certificate is provided
through the GitHub secrets `WINDOWS_PFX_BASE64` and `WINDOWS_PFX_PASSWORD`.
Without those secrets the build still works but Defender/SmartScreen
warnings cannot be reliably avoided.

### Automatic Windows update

On startup, Windows checks the latest stable GitHub Release in the
background. The `Glaneur-<version>-setup.exe` installer and its `.sha256`
file are picked from the official Release. After integrity verification, a
small separate updater closes the application, launches Inno Setup, then
relaunches the application. Network errors or a « Later » choice let the
application keep running normally.

Installation is **user-scope**: `PrivilegesRequired=lowest` combined with
`DefaultDirName={autopf}` resolves to `%LOCALAPPDATA%\Programs\Glaneur`, so
no UAC elevation is required on install or on updates.

**Size.** Qt is large. The `QT_INUTILES` list in the `.spec` file drops
QtWebEngine, Qt3D, QtQuick, QtMultimedia and about twenty other modules the
application does not use: the distribution shrinks from around 180 MB to
60 MB, and the compressed installer to about 25 MB. If you add a Qt
feature and it fails with an `ImportError` when the executable launches —
but not in development — it is almost always a module removed by that list.

**Packaging choice.** Folder mode (`COLLECT`) is preferred over `--onefile`:
faster startup and no re-extraction into `%TEMP%` on every launch, which
matters even more with Qt and reduces antivirus false positives. UPX is
disabled for the same reason — it also regularly corrupts Qt DLLs. The
installer is set to `PrivilegesRequired=lowest`: per-user install under
`%LOCALAPPDATA%`, without a UAC prompt.

**Autostart.** Two deliberately separate paths: the checkbox during
installation creates a shortcut in the Startup folder; the one in the
application writes an entry into
`HKCU\Software\Microsoft\Windows\CurrentVersion\Run`. Both pass the
`--reduit` argument, which starts the application minimised.

### Linux packages

The released versions also build a Debian package (`.deb`) and a Flatpak
bundle (`.flatpak`). They ship the same PyInstaller executable as the
Windows distribution and are produced automatically by GitHub Actions
when a version tag is created.

In short, the build installs Python dependencies, compiles the application
with PyInstaller, then packages it for the target system: Inno Setup
installer on Windows, Debian package and Flatpak on Linux, `.zip` archive
and `.dmg` image on macOS. Tests are run before versions are published.

The same workflow produces a macOS application (`.app`) distributed as a
`.zip` archive and a `.dmg` disk image.

---

## 6. Troubleshooting

| Symptom | Likely cause |
|---|---|
| « The API is not responding » | site unreachable, or `/wp-json/` disabled by a site update |
| Folders named `contenu-12345` | the « galleries » content type is not exposed by the API; switch to sort-by-date |
| Very few images found | `largeur_min` is set too high |
| « no Qt platform plugin could be initialized » | on Linux, X11 libraries missing; on Windows, the `platforms\qwindows.dll` plugin is missing from the `dist` folder |
| `ImportError` on a Qt module only in the exe | module removed by `QT_INUTILES` in the `.spec` |
| Windows SmartScreen blocks the installer | unsigned executable — « More info » then « Run anyway », or sign with a certificate |
| The antivirus quarantines the exe | classic PyInstaller false positive; make sure UPX stays disabled |

For diagnosis, `cli.py` prints the same messages without going through the
UI. The full log lives in `%APPDATA%\Glaneur\app.log` (rotation handled by
`logsetup.py`); **Help → Report a bug…** attaches the last 50 lines to a
prefilled GitHub issue.

---

## 7. Future work

- **Windows scheduled task** through `schtasks`, for updates with no
  application running. The engine is already usable from the command line;
  a `cli.py --silencieux` flag would be enough.
- **Browsing gallery** inside the application: a `QListView` in icon mode
  over a `QFileSystemModel`, thirty lines or so to browse the photos
  without opening Explorer.
- **Team filtering** by tapping into the API taxonomies
  (`categorie-galeries`) to follow only the first team or the women's team.
- **Catalogue export** to CSV or HTML from the manifest.

---

## 8. Usage rights

Downloaded content belongs to its authors or rights holders and may be
subject to terms of use specific to the targeted site. This application
grants no right of republication or commercial use.

The minimum delay between requests is not a cosmetic setting: it is what
tells a discreet synchronisation apart from a useless load on a server
that did not ask for anything.

---
---

<a id="glaneur--téléchargeur-dimages-multi-sources"></a>

# Glaneur — Téléchargeur d'images multi-sources

> 🇬🇧 [English version at the top of this document](#glaneur--multi-source-image-downloader).

> **Disclaimer**
>
> Ce projet est personnel et indépendant. Il ne constitue pas un produit,
> service ou partenariat officiel d'un site ciblé. Les noms et marques
> éventuellement mentionnés sont utilisés uniquement à titre descriptif.

> **Ancien nom.** L'application s'appelait `WpImageDownloader`
> (`WpImagerDownloader` côté installer) jusqu'à la version 1.0.42 —
> vestige d'un scope initial WordPress-only. Le nouveau nom **Glaneur**
> reflète le passage au multi-source. Les installations existantes
> voient leur config (`%APPDATA%\WpImageDownloader\`) migrée
> automatiquement vers `%APPDATA%\Glaneur\` au premier lancement.

Application Windows qui synchronise en local les images publiées sur un site
distant. Deux types de source sont supportés :
`WordPress` (via l'API REST `/wp-json/wp/v2`) et
`Djangoplicity` (flux `d2d/` des sites ESO, ESA/Hubble…). Elle tourne en
arrière-plan, se met à jour à l'intervalle choisi et ne retélécharge jamais
une image déjà présente.

---

## 1. Architecture

Le découpage sépare strictement le moteur de l'interface :
`Glaneur/engine.py`
n'importe rien de Tkinter et communique par callbacks. On peut donc le piloter
depuis l'UI, depuis `cli.py`, ou depuis un futur service Windows sans rien
réécrire.

```
glaneur/
├── app.py                  Interface graphique PySide6
├── cli.py                  Interface ligne de commande (mêmes fonctions)
├── requirements.txt
├── build.bat               Construction complète en une commande
├── Glaneur/
│   ├── config.py           Préférences persistées (JSON dans %APPDATA%)
│   ├── engine.py           Moteur : orchestration, manifeste, téléchargement, reprise
│   ├── scheduler.py        Calcul d'échéance (logique pure, sans thread)
│   ├── systeme.py          Registre Windows, ouverture de dossier
│   ├── logsetup.py         Logger fichier rotatif (%APPDATA%\Glaneur\app.log)
│   ├── bug_report.py       Compose l'URL GitHub issues/new du menu Aide → Signaler un bug
│   ├── i18n.py             Charge QTranslator au démarrage (voir §4 Internationalisation)
│   ├── sources/            Adaptateurs par type de site (contrat commun `Source`)
│   │   ├── base.py         Classe abstraite `Source` + `Transport` HTTP partagé
│   │   ├── wordpress.py    API REST `/wp-json/wp/v2`
│   │   └── djangoplicity.py Flux `d2d/` (ESO, ESA/Hubble…)
│   └── updater/            Mise à jour in-app depuis GitHub Release
│       ├── github_release.py  Interrogation de l'API Releases
│       ├── downloader.py      Téléchargement + vérification SHA-256
│       ├── qt_threads.py      Threads Qt (check / download) et handoff
│       ├── models.py, version.py
└── build/
    ├── Glaneur.spec Recette PyInstaller
    └── installer.iss       Script Inno Setup
```

**Contrat du moteur.** `Moteur(options, journal, progression, arret).executer()`
renvoie un `Resultat`. Le moteur n'importe ni Qt ni aucun widget : les
callbacks sont branchés sur des signaux Qt émis depuis un `QThread`, et Qt les
marshale automatiquement vers le thread principal via ses connexions en file.
C'est ce qui rend la règle « aucun widget touché hors du thread principal »
automatique plutôt qu'à surveiller.

Le planificateur est réduit à de la logique pure — il répond à « est-ce
l'heure ? » et rien d'autre. Deux `QTimer` le pilotent : un contrôle d'échéance
toutes les 30 s et un rafraîchissement du compte à rebours toutes les secondes.
Pas de thread supplémentaire, tout le déclenchement reste sur le thread
principal.

L'arrêt passe par un `threading.Event` vérifié entre chaque requête et chaque
bloc de 64 Ko. Un téléchargement coupé laisse un fichier `.part` qui sera repris
par un en-tête `Range` au passage suivant.

---

## 2. Développement

```bash
python -m venv .venv
.venv\Scripts\activate          # Linux/macOS : source .venv/bin/activate
pip install -r requirements.txt

python app.py                   # interface
python cli.py --dossier ./photos --verifier
```

Python 3.11 ou plus. `PySide6-Essentials` suffit : c'est la variante sans
QtWebEngine ni les modules 3D, soit environ 90 Mo au lieu de 300 à
l'installation, et rien de ce que l'application utilise n'y manque.

Sous Linux, Qt réclame les bibliothèques X11 (`libxcb-cursor0`,
`libxkbcommon-x11-0`). Pour un test sans affichage :
`QT_QPA_PLATFORM=offscreen python app.py`.

**Tests.** `pip install -r requirements-dev.txt` puis
`QT_QPA_PLATFORM=offscreen python -m pytest -q`. `pytest-qt` est nécessaire
pour la fixture `qtbot` utilisée par les tests des QThread updater ; les
autres tests (moteur, scheduler, config, updater unitaire) tournent sans lui.

---

## 3. Fonctionnement

**Sources.** Le moteur délègue à un adaptateur `Source` (dans
`Glaneur/sources/`) qui expose deux méthodes : `inventaire()` liste
les images disponibles, `titre_parent()` résout un ID de galerie en libellé
lisible. Deux implémentations sont fournies :

- `wordpress` — API REST `GET /wp-json/wp/v2/media?per_page=100`, paginée
  d'après l'en-tête `X-WP-TotalPages`. Le champ `source_url` donne
  directement l'original en pleine résolution.
- `djangoplicity` — flux `d2d/` des sites style ESO/ESA/Hubble ; le format
  d'image est réglable (défaut `Large`, repli automatique sur `Small` si
  le `Large` manque pour une entrée).

Le choix se fait dans **Préférences → « Type de site »**, ou via
`cli.py --type {wordpress,djangoplicity}`. Ajouter une source revient à
implémenter `Source` et à l'enregistrer dans `sources/SOURCES`.

**Inventaire (WordPress).** Une requête par page, paginée via
`X-WP-TotalPages`. Le champ `source_url` donne l'original.

**Filtrage.** Les entrées sous la largeur minimale (800 px par défaut) sont
écartées : ce sont les logos sponsors, favicons et vignettes.

**Classement.** En mode « Par galerie », les IDs de contenus parents sont
résolus en slugs via les endpoints découverts sur `/wp-json/wp/v2/types`. En
mode « Par date », les dossiers suivent l'arborescence `AAAA-MM` des uploads.
En mode « Tout dans un dossier », aucun sous-dossier n'est créé ; comme
WordPress ne garantit l'unicité des noms qu'au sein d'un même mois d'upload,
un doublon reçoit l'ID du média en suffixe (`match-1234.jpg`). Changer de
classement ne déplace rien : seules les nouvelles images suivent le nouveau
mode.

**Manifeste.** `.etat.json` à la racine du dossier de destination associe
chaque ID d'image à son chemin local, sa taille, son ETag et son
`Last-Modified`. Une image déjà complète ne génère aucune requête — sur une
mise à jour de routine, seul l'inventaire circule sur le réseau. Un fichier dont
la taille ne correspond plus (interruption, corruption) repasse dans la file.

**Cache API.** `.cache.json` mémorise, à côté du manifeste, la date maximale
des médias déjà vus (`derniere_date_media`) et les titres de galeries résolus
(`titres_parents`), avec l'URL du site pour empreinte. Aux runs suivants,
l'inventaire ne demande à l'API que les médias postérieurs à cette date
(paramètre `after=…`) et la résolution des galeries évite tout aller-retour
pour les IDs déjà connus. Si l'URL du site change, le cache est ignoré ; le
mode `--force` (CLI) et `--pas-cache` le contournent aussi. Une interruption
n'écrit pas le cache : on ne mémorise qu'un état de sortie propre.

**Images supprimées.** Une image complète dont le fichier a disparu du disque
a forcément été effacée par l'utilisateur : le manifeste la marque
(`"supprime": <horodatage>`) et elle n'est plus retéléchargée. Le bouton
« Images supprimées… » de l'interface, ou `cli.py --restaurer [ID…]`, lève la
marque pour la remettre en file. `--force`, qui ignore le manifeste, efface
aussi ces marques.

**Option « vérifier l'intégrité ».** Envoie une requête conditionnelle
`If-None-Match` sur chaque fichier connu. Le serveur répond `304` sans
transférer d'octets si sa copie est identique. Utile ponctuellement, inutile au
quotidien.

**Planification.** `scheduler.py` compare l'heure courante à
`derniere_execution` enregistré dans la configuration. L'échéance survit donc à
la fermeture de l'application : si l'intervalle s'est écoulé pendant qu'elle
était fermée, la mise à jour part au lancement suivant. Une exécution
interrompue ne met pas à jour l'horodatage.

---

## 4. Configuration

Fichier : `%APPDATA%\Glaneur\config.json`
(`~/.config/glaneur/` ailleurs).

La fenêtre principale expose les actions (mise à jour, arrêter, supprimer le
fond, images supprimées) et le journal ; les paramètres — type de site, URL,
destination, intervalle, classement, largeur minimale, intégration système —
vivent dans **Configuration → Préférences…** (raccourci `Ctrl+,`). Le menu
**Aide → À propos…** rappelle la version et le dépôt, et **Aide → Signaler un
bug…** ouvre une issue GitHub préremplie (version, plateforme et 50 dernières
lignes de log compactées).

| Clé | Rôle | Défaut |
|---|---|---|
| `type_source` | `wordpress` ou `djangoplicity` | `wordpress` |
| `site` | URL du site cible | configurée dans l'application |
| `dossier` | destination des images | dossier Images de l'utilisateur |
| `intervalle_heures` | 0, 6, 12, 24 ou 168 | `24` |
| `largeur_min` | seuil en pixels | `800` |
| `classement` | `galerie`, `date` ou `plat` | `galerie` |
| `format_image` | Djangoplicity : `Large` / `Small` / `Original` | `Large` |
| `verifier_integrite` | revalidation conditionnelle | `false` |
| `verifier_maj_demarrage` | interroge GitHub Releases au lancement | `true` |
| `lancer_au_demarrage` | entrée `HKCU\...\Run` avec `--reduit` | `false` |
| `langue` | code ISO (`fr`, `en`) ; vide = locale système | `""` |
| `fermer_dans_barre` | la croix réduit au lieu de quitter | `true` |
| `notifications` | bulle après une mise à jour automatique | `true` |
| `delai_requetes` | pause entre requêtes, en secondes | `0.5` |
| `diaporama_dossier` | déclare le dossier comme source du diaporama Windows | `false` |
| `derniere_execution` | horodatage ISO, géré par l'app | — |

Les paramètres sont sauvegardés à la validation de la fenêtre Préférences
(bouton OK). Les valeurs hors bornes sont ramenées à des valeurs saines au
chargement ; `delai_requetes` est plafonné à un minimum de 0,2 s pour ne pas
marteler le serveur cible.

### Internationalisation

Toutes les chaînes d'interface passent par `self.tr(...)` (widgets) ou
`QCoreApplication.translate("BugReport", ...)` (module `bug_report.py`).
Les sources sont en français ; les autres langues vivent dans
`translations/glaneur_<code>.ts`, compilées en `.qm` que
`Glaneur/i18n.py` installe au démarrage selon la préférence
`langue` (ou la locale système si vide). Le changement de langue prend
effet au **prochain lancement** — pas de retranslation à chaud.

Workflow traducteur :

```bash
# 1. Après avoir modifié du code : (ré)extraire les strings vers les .ts
python translations/build_translations.py update

# 2. Ouvrir et traduire dans Qt Linguist
pyside6-linguist translations/glaneur_en.ts

# 3. Compiler les .ts en .qm consommés par l'app
python translations/build_translations.py release
```

`build.bat` appelle automatiquement l'étape 3 avant PyInstaller. Les `.qm`
ne sont pas versionnés (générés au build) ; les `.ts` le sont.

### Licence et contenus téléchargés

Le code source de ce projet est distribué sous licence GNU GPL version 3 ou
ultérieure. Voir le fichier [LICENSE](LICENSE).

Cette licence couvre uniquement le code du projet. Elle ne couvre pas les
images, vidéos, textes, logos ou autres contenus récupérés depuis les sites
ciblés. Ces contenus restent soumis à leurs propres droits d'auteur, marques
et conditions d'utilisation.

---

## 5. Construction

### En une commande

```bat
build.bat
```

Crée l'environnement virtuel, compile avec PyInstaller, puis appelle Inno Setup
si `iscc.exe` est dans le PATH.

### Étape par étape

```bat
pip install pyinstaller
pyinstaller build\Glaneur.spec --noconfirm --clean
iscc build\installer.iss
```

Résultats : `dist\Glaneur\` puis
`build\Output\Glaneur-1.1.0-setup.exe`.

**Icône.** Aucun logo ou blason tiers n'est distribué dans le dépôt. Sans fichier
ICO fourni séparément au moment du build, l'application dessine à la volée un
disque grenat marqué « S » : la zone de notification et la fenêtre restent
correctes, seul l'exécutable garde l'icône Python par défaut.

**Signature Windows.** Les exécutables PyInstaller non signés peuvent être
classés à tort comme suspects par Microsoft Defender, notamment lors des
premières publications. Pour obtenir un installateur reconnu, le workflow
Windows signe l'exécutable et l'installateur lorsqu'un certificat Authenticode
est fourni dans les secrets GitHub `WINDOWS_PFX_BASE64` et
`WINDOWS_PFX_PASSWORD`. Sans ces secrets, la construction reste possible mais
les avertissements Defender/SmartScreen ne peuvent pas être évités de manière
fiable.

### Mise à jour automatique Windows

Au démarrage, Windows vérifie en arrière-plan la dernière GitHub Release stable.
L'installateur `Glaneur-<version>-setup.exe` et son fichier
`.sha256` sont sélectionnés dans la Release officielle. Après vérification de
l'intégrité, un petit updater séparé ferme l'application, lance Inno Setup puis
relance l'application. Les erreurs réseau ou un choix « Plus tard » laissent
l'application fonctionner normalement.

L'installation est **user-scope** : `PrivilegesRequired=lowest` combiné à
`DefaultDirName={autopf}` résout vers `%LOCALAPPDATA%\Programs\Glaneur`,
donc aucune élévation UAC n'est demandée à l'installation ni aux mises à jour.

**Taille.** Qt est volumineux. La liste `QT_INUTILES` du fichier `.spec`
écarte QtWebEngine, Qt3D, QtQuick, QtMultimedia et une vingtaine d'autres
modules dont l'application n'a que faire : la distribution passe d'environ
180 Mo à 60 Mo, et l'installateur compressé tourne autour de 25 Mo. Si tu
ajoutes une fonctionnalité Qt et qu'elle échoue avec un `ImportError` au
lancement de l'exécutable — mais pas en développement — c'est presque toujours
un module retiré par cette liste.

**Choix de packaging.** Le mode dossier (`COLLECT`) est préféré à `--onefile` :
démarrage plus rapide et pas de réextraction dans `%TEMP%` à chaque lancement,
ce qui compte d'autant plus avec Qt et limite les faux positifs antivirus. UPX
est désactivé pour la même raison — il corrompt d'ailleurs régulièrement les
DLL Qt. L'installateur est en `PrivilegesRequired=lowest` : installation par
utilisateur dans `%LOCALAPPDATA%`, sans invite UAC.

**Démarrage automatique.** Deux chemins possibles, volontairement séparés : la
case à cocher pendant l'installation crée un raccourci dans le dossier Démarrage,
celle de l'application écrit une entrée dans
`HKCU\Software\Microsoft\Windows\CurrentVersion\Run`. Les deux passent
l'argument `--reduit`, qui lance l'application en fenêtre réduite.

### Paquets Linux

Les versions publiées construisent également un paquet Debian (`.deb`) et un
bundle Flatpak (`.flatpak`). Ils contiennent le même exécutable PyInstaller que
la distribution Windows et sont générés automatiquement par GitHub Actions
lorsqu'un tag de version est créé.

En résumé, la construction installe les dépendances Python, compile l'application
avec PyInstaller, puis l'empaquette selon le système cible : installateur Inno
Setup sous Windows, paquet Debian et Flatpak sous Linux, archive `.zip` et image
`.dmg` sous macOS. Les tests sont exécutés avant la publication des versions.

Le même workflow produit une application macOS (`.app`) distribuée en archive
`.zip` et en image disque `.dmg`.

---

## 6. Dépannage

| Symptôme | Cause probable |
|---|---|
| « L'API ne répond pas » | site injoignable, ou `/wp-json/` désactivé par une mise à jour du site |
| Dossiers nommés `contenu-12345` | le type de contenu « galeries » n'est pas exposé dans l'API ; bascule sur le classement par date |
| Très peu d'images trouvées | `largeur_min` trop élevée |
| « no Qt platform plugin could be initialized » | sous Linux, bibliothèques X11 manquantes ; sous Windows, plugin `platforms\qwindows.dll` absent du dossier `dist` |
| `ImportError` sur un module Qt dans l'exe seulement | module retiré par `QT_INUTILES` dans le `.spec` |
| Windows SmartScreen bloque l'installateur | exécutable non signé — « Informations complémentaires » puis « Exécuter quand même », ou signer avec un certificat |
| L'antivirus met l'exe en quarantaine | faux positif classique sur PyInstaller ; vérifier que UPX reste désactivé |

Pour diagnostiquer, `cli.py` affiche les mêmes messages sans passer par l'UI.
Le fichier log complet vit dans `%APPDATA%\Glaneur\app.log`
(rotation gérée par `logsetup.py`) ; **Aide → Signaler un bug…** en attache
les 50 dernières lignes à une issue GitHub préremplie.

---

## 7. Pistes d'évolution

- **Tâche planifiée Windows** via `schtasks`, pour des mises à jour sans aucune
  application lancée. Le moteur est déjà utilisable en ligne de commande, il
  suffirait d'un `cli.py --silencieux`.
- **Galerie de consultation** dans l'application : `QListView` en mode icônes
  sur un `QFileSystemModel`, une trentaine de lignes pour parcourir les photos
  sans ouvrir l'explorateur.
- **Filtrage par équipe** en exploitant les taxonomies de l'API
  (`categorie-galeries`) pour ne suivre que l'équipe première ou les féminines.
- **Export d'un catalogue** CSV ou HTML à partir du manifeste.

---

## 8. Droits d'usage

Les contenus téléchargés appartiennent à leurs auteurs ou ayants droit et
peuvent être soumis à des conditions d'utilisation propres au site ciblé.
Cette application ne confère aucun droit de republication ou d'usage
commercial.

Le délai minimal entre requêtes n'est pas une option cosmétique : c'est ce qui
distingue une synchronisation discrète d'une charge inutile sur un serveur qui
n'a rien demandé.
