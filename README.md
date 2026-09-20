# Servette FC — Téléchargeur d'images

Application Windows qui synchronise en local les photos publiées sur
`servettefc.ch`, via l'API REST WordPress du site. Elle tourne en arrière-plan,
se met à jour à l'intervalle choisi et ne retélécharge jamais une image déjà
présente.

---

## 1. Architecture

Le découpage sépare strictement le moteur de l'interface : `servette/engine.py`
n'importe rien de Tkinter et communique par callbacks. On peut donc le piloter
depuis l'UI, depuis `cli.py`, ou depuis un futur service Windows sans rien
réécrire.

```
servette-downloader/
├── app.py                  Interface graphique PySide6
├── cli.py                  Interface ligne de commande (mêmes fonctions)
├── requirements.txt
├── build.bat               Construction complète en une commande
├── servette/
│   ├── config.py           Préférences persistées (JSON dans %APPDATA%)
│   ├── engine.py           Moteur : API, manifeste, téléchargement, reprise
│   ├── scheduler.py        Calcul d'échéance (logique pure, sans thread)
│   └── systeme.py          Registre Windows, ouverture de dossier
└── build/
    ├── servette.spec       Recette PyInstaller
    ├── installer.iss       Script Inno Setup
    └── servette.ico        Icône (optionnelle, voir §5)
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

**Manifeste.** `.etat.json` à la racine du dossier de destination associe
chaque ID d'image à son chemin local, sa taille, son ETag et son
`Last-Modified`. Une image déjà complète ne génère aucune requête — sur une
mise à jour de routine, seul l'inventaire circule sur le réseau. Un fichier dont
la taille ne correspond plus (interruption, corruption) repasse dans la file.

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

Fichier : `%APPDATA%\ServetteDownloader\config.json`
(`~/.config/servette-downloader/` ailleurs).

| Clé | Rôle | Défaut |
|---|---|---|
| `dossier` | destination des images | `Mes images\Servette FC` |
| `intervalle_heures` | 0, 6, 12, 24 ou 168 | `24` |
| `largeur_min` | seuil en pixels | `800` |
| `classement` | `galerie` ou `date` | `galerie` |
| `verifier_integrite` | revalidation conditionnelle | `false` |
| `fermer_dans_barre` | la croix réduit au lieu de quitter | `true` |
| `notifications` | bulle après une mise à jour automatique | `true` |
| `delai_requetes` | pause entre requêtes, en secondes | `0.5` |
| `derniere_execution` | horodatage ISO, géré par l'app | — |

Toute modification dans l'interface est sauvegardée immédiatement. Les valeurs
hors bornes sont ramenées à des valeurs saines au chargement ; `delai_requetes`
est plafonné à un minimum de 0,2 s pour ne pas marteler le serveur du club.

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
pyinstaller build\servette.spec --noconfirm --clean
iscc build\installer.iss
```

Résultats : `dist\ServetteDownloader\` puis
`build\Output\ServetteDownloader-1.0.0-setup.exe`.

**Icône.** Place un `servette.ico` dans `build\` (256×256, ICO
multi-résolutions) et décommente `SetupIconFile` dans `installer.iss`. Sans ce
fichier, l'application dessine à la volée un disque grenat marqué « S » : la
zone de notification et la fenêtre restent correctes, seul l'exécutable garde
l'icône Python par défaut.

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

Les photographies appartiennent au Servette FC et à ses photographes ; le site
porte la mention « tous droits réservés ». Cette application est prévue pour un
usage personnel d'archivage. Toute republication ou usage commercial nécessite
l'accord du club, qui dispose d'un formulaire de contact sur son site.

Le délai minimal entre requêtes n'est pas une option cosmétique : c'est ce qui
distingue une synchronisation discrète d'une charge inutile sur un serveur qui
n'a rien demandé.
