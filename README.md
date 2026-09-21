# Téléchargeur d'images WordPress

> **Disclaimer**
>
> Ce projet est personnel et indépendant. Il ne constitue pas un produit,
> service ou partenariat officiel d'un site ciblé. Les noms et marques
> éventuellement mentionnés sont utilisés uniquement à titre descriptif.

Application Windows qui synchronise en local les images publiées sur un site
WordPress compatible avec l'API REST utilisée. Elle tourne en arrière-plan,
se met à jour à l'intervalle choisi et ne retélécharge jamais une image déjà
présente.

---

## 1. Architecture

Le découpage sépare strictement le moteur de l'interface :
`WpImageDownloader/engine.py`
n'importe rien de Tkinter et communique par callbacks. On peut donc le piloter
depuis l'UI, depuis `cli.py`, ou depuis un futur service Windows sans rien
réécrire.

```
wp-image-downloader/
├── app.py                  Interface graphique PySide6
├── cli.py                  Interface ligne de commande (mêmes fonctions)
├── requirements.txt
├── build.bat               Construction complète en une commande
├── WpImageDownloader/
│   ├── config.py           Préférences persistées (JSON dans %APPDATA%)
│   ├── engine.py           Moteur : API, manifeste, téléchargement, reprise
│   ├── scheduler.py        Calcul d'échéance (logique pure, sans thread)
│   └── systeme.py          Registre Windows, ouverture de dossier
└── build/
    ├── WpImageDownloader.spec Recette PyInstaller
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

**Tests.** `pip install pytest pytest-qt` puis
`QT_QPA_PLATFORM=offscreen python -m pytest -q`. `pytest-qt` est nécessaire
pour la fixture `qtbot` utilisée par les tests des QThread updater ; les
autres tests (moteur, scheduler, config, updater unitaire) tournent sans lui.

---

## 3. Fonctionnement

**Inventaire.** Une requête `GET /wp-json/wp/v2/media?per_page=100` par page,
paginée d'après l'en-tête `X-WP-TotalPages`. Le champ `source_url` donne
directement l'original en pleine résolution.

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

Fichier : `%APPDATA%\WpImageDownloader\config.json`
(`~/.config/wp-image-downloader/` ailleurs).

La fenêtre principale expose les actions (mise à jour, arrêter, supprimer le
fond, images supprimées) et le journal ; les paramètres — URL du site,
destination, intervalle, classement, largeur minimale, intégration système —
vivent dans **Configuration → Préférences…** (raccourci `Ctrl+,`). Le moteur
utilise l'URL du site comme préfixe de l'endpoint `/wp-json/wp/v2`. Le menu
**Aide → À propos…** rappelle la version et le dépôt.

| Clé | Rôle | Défaut |
|---|---|---|
| `site` | URL du site WordPress cible | configurée dans l'application |
| `dossier` | destination des images | dossier Images de l'utilisateur |
| `intervalle_heures` | 0, 6, 12, 24 ou 168 | `24` |
| `largeur_min` | seuil en pixels | `800` |
| `classement` | `galerie`, `date` ou `plat` | `galerie` |
| `verifier_integrite` | revalidation conditionnelle | `false` |
| `fermer_dans_barre` | la croix réduit au lieu de quitter | `true` |
| `notifications` | bulle après une mise à jour automatique | `true` |
| `delai_requetes` | pause entre requêtes, en secondes | `0.5` |
| `diaporama_dossier` | déclare le dossier comme source du diaporama Windows | `false` |
| `derniere_execution` | horodatage ISO, géré par l'app | — |

Les paramètres sont sauvegardés à la validation de la fenêtre Préférences
(bouton OK). Les valeurs hors bornes sont ramenées à des valeurs saines au
chargement ; `delai_requetes` est plafonné à un minimum de 0,2 s pour ne pas
marteler le serveur cible.

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
pyinstaller build\WpImageDownloader.spec --noconfirm --clean
iscc build\installer.iss
```

Résultats : `dist\WpImagerDownloader\` puis
`build\Output\WpImagerDownloader-1.0.18-setup.exe`.

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
L'installateur `WpImagerDownloader-<version>-setup.exe` et son fichier
`.sha256` sont sélectionnés dans la Release officielle. Après vérification de
l'intégrité, un petit updater séparé ferme l'application, lance Inno Setup puis
relance l'application. Les erreurs réseau ou un choix « Plus tard » laissent
l'application fonctionner normalement.

L'installation est **user-scope** : `PrivilegesRequired=lowest` combiné à
`DefaultDirName={autopf}` résout vers `%LOCALAPPDATA%\Programs\WpImagerDownloader`,
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
