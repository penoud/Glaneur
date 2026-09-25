# Évolution : support de plusieurs types de sites

> Étude d'architecture. Objectif : pouvoir ajouter d'autres types de sites que
> WordPress (premier cas : le site public de l'ESO) sans casser le moteur actuel,
> ses invariants ni ses frontières. Rien n'est implémenté ici.

---

## 0. En bref

- Le moteur actuel mélange deux choses : une **mécanique de synchronisation
  générique** (manifeste, reprise `.part`, revalidation 304, suppressions,
  sauvegardes atomiques) et une **connaissance de WordPress** (URL de l'API,
  pagination `X-WP-TotalPages`, `media_details`, résolution des parents,
  arborescence `/uploads/AAAA/MM/`).
- Proposition : garder la première dans `engine.py` et déplacer la seconde dans
  un **adaptateur de source**. Chaque type de site fournit un adaptateur qui
  produit une liste d'éléments normalisés ; le moteur ne connaît plus que ces
  éléments.
- L'ESO tourne sur **Djangoplicity** (CMS Django open source, aussi utilisé par
  ESA/Hubble et ESA/Webb). Djangoplicity expose un flux JSON paginé
  (`images/d2d/`) qui ressemble beaucoup à ce que l'API WordPress nous donne :
  un adaptateur propre est réaliste **sans parsing HTML**. Le flux est actif
  chez l'ESO : 15 741 images annoncées (§3.1, mesures sur la première page).
- Migration en 4 étapes, dont la première ne change aucun comportement.

---

## 1. Ce qui a été vérifié, et ce qui ne l'a pas été

**Vérifié :**

| Fait | Source |
|---|---|
| Djangoplicity définit une vue `images/d2d/` (Django REST Framework) : pagination `page`, taille `count` (100 par défaut), tri `order_by` ∈ `priority`, `-priority`, `release_date`, `-release_date` (défaut `-release_date`), filtres `after` / `before` au format `AAAAMMJJhhmmss`, filtre `after` **inclusif** (`>=`) | Code source `djangoplicity/media/d2d/views.py`, `utils/d2d.py` (dépôt GitHub, commit du 22/09/2026) |
| La réponse a la forme `{Count, Next, Previous, Collections: [...]}` ; `Previous`/`Next` absents quand ils valent `None` | idem (`D2dDict` supprime les clés nulles) |
| Le flux peut être désactivé par l'exploitant (`ENABLE_D2D_FEEDS`) | `media/urls_images.py` |
| Le flux fonctionne en réel sur `esahubble.org/images/d2d/` : `Count` = 5518, `Next` en URL absolue, chaque entrée a `ID` (chaîne), `PublicationDate`, `Credit`, `Rights`, `Assets[0].Resources[]` | Requête du 24/09/2026 |
| Chaque ressource donne `ResourceType` (`Original`, `Large`, `Small`, `Thumbnail`, `Icon`), `URL`, `FileSize`, `Dimensions`, parfois `Checksum` (64 caractères hexadécimaux) | idem, et `eso.org/public/images/archive/top100/json/` |
| Côté ESO, les originaux sont des TIFF, parfois énormes : 1,56 Go pour `eso1740a`, 1,22 Go pour `eso1625a` ; même le JPEG `Large` atteint 155 Mo | `eso.org/public/images/archive/top100/json/` |
| Licence des images ESO : CC BY 4.0, avec un champ `Credit` par image | idem |
| Un bug connu de certaines installations Djangoplicity renvoie des textes sous la forme `"b'...'"` (repr Python de bytes) dans l'endpoint par image `…/api/json/` | Issue djangoplicity #147, et correctif dans `toasty` (WorldWideTelescope) |

**Non vérifié** (le bac à sable n'a pas accès à `eso.org` en direct) :

- que `cdn.eso.org` réponde `304` à une requête conditionnelle (`If-None-Match`) ;
- le comportement de `www.eso.org/public/archives/…`, qui sert 2 % des fichiers ;
- le comportement des gros `Original` (plusieurs centaines de Mo), dont l'`ETag`
  pourrait avoir une autre forme ;
- l'algorithme du champ `Checksum` (la longueur suggère SHA-256, sans preuve) ;
- le nombre total d'images de l'ESO.

À noter : l'endpoint `archive/top100/json/` de l'ESO n'a **pas** la même forme
que `d2d/` (ressources à plat, champ `Date`, alors que `d2d` a `Assets` et
`PublicationDate`). L'adaptateur doit viser un seul format, `d2d`.

---

## 2. État des lieux : où WordPress est câblé dans le code

Lecture de `engine.py` et `config.py` de la base de connaissances :

| Élément | Générique | Spécifique WordPress |
|---|---|---|
| `Options`, `Resultat` | oui (sauf libellés) | — |
| `nettoyer`, `format_octets`, manifeste, cache (lecture/écriture atomique) | oui | — |
| `supprimer_image`, `restaurer`, `lister_supprimees` | oui | — |
| `Moteur.__init__` | session, callbacks, `arret` | `self.api = …/wp-json/wp/v2` |
| `_api` | rejeux, pause, arrêt | « 400 = fin de pagination » |
| `lister_medias` | déduplication, progression | paramètres WP, `X-WP-TotalPages`, `after`/`before` ISO |
| `_bases_rest`, `resoudre_parents` | — | entièrement |
| `dossier_pour` | le choix plat/date/galerie | regex `/uploads/AAAA/MM/`, champ `post` |
| `chemin_libre` | oui | `media_id: int` (typage seulement) |
| `telecharger` | oui (Range/206, 304, 416, `.part`) | — |
| `executer` | orchestration, compteurs, sauvegardes | lit `m["id"]`, `m["source_url"]`, `m["post"]`, `media_details.width/filesize` ; filtre `isdigit()` sur les clés de `titres_parents` |

Deux constats :

1. Le couplage est **localisé** : les dictionnaires WordPress bruts traversent
   `executer`, mais toutes les écritures disque et tout le HTTP de fichiers sont
   déjà génériques. L'extraction est un déplacement de code, pas une réécriture.
2. Le filtre `str(k).isdigit()` sur le cache des titres et le typage `int` des
   identifiants supposent des IDs numériques. Les IDs Djangoplicity sont des
   chaînes (`eso1907a`). C'est le seul vrai piège de modèle de données.

---

## 3. Le cas ESO / Djangoplicity

Ce que la source apporte, mis en regard de WordPress :

| Besoin du moteur | WordPress | Djangoplicity `d2d` |
|---|---|---|
| Inventaire paginé | `/wp-json/wp/v2/media?page=N` | `/public/images/d2d/?page=N` |
| Signal de fin | `X-WP-TotalPages` | absence de `Next` (et `Count`) |
| Delta incrémental | `after=` ISO, exclusif | `after=AAAAMMJJhhmmss`, **inclusif** |
| Identifiant | entier | chaîne |
| URL du fichier | `source_url` (original) | une ressource à choisir parmi `Original` / `Large` / `Small`… |
| Largeur pour le filtre | `media_details.width` | `Dimensions[0]` (parfois flottant : `1280.0`) |
| Taille attendue | `media_details.filesize` | `FileSize` |
| Regroupement « galerie » | parent (`post`) à résoudre par requêtes | pas d'album ; mais `Subject.Category` (hiérarchie AVM, ex. `Unspecified : Technology : Observatory : Instrument`) est présent en ligne, sans requête supplémentaire |
| Crédit / licence | — | `Credit`, `Rights` |

### 3.1 Mesures sur la première page réelle de l'ESO (`d2d/`, 24/09/2026)

| Mesure | Valeur |
|---|---|
| `Count` | 15 741 images, soit environ 158 pages de 100 |
| `Next` | URL absolue `https://www.eso.org/public/images/d2d/?page=2` ; pas de `Previous` en page 1 |
| Ordre | `PublicationDate` strictement décroissante (du 21/09/2026 au 03/06/2026) |
| Structure | 100 entrées, chacune avec exactement un `Asset` de type `Image` et les cinq ressources `Original`, `Large`, `Small`, `Thumbnail`, `Icon` |
| Extensions | `Original` toujours `.tif`, les autres `.jpg` |
| Taille `Original` | médiane 36,5 Mo, max 1 564 Mo, total de la page 10,7 Go |
| Taille `Large` | médiane 3,7 Mo, max 277 Mo, total de la page 1,08 Go |
| Taille `Small` | total de la page 25 Mo |
| `Checksum` | sur 30 `Original` et 3 `Large` seulement |
| `Dimensions` | entiers pour `Original`/`Large`, flottants pour `Small`/`Thumbnail`/`Icon` |
| Hôtes | `cdn.eso.org` pour 98 %, `www.eso.org/public/archives/…` pour 2 entrées |
| `Subject.Category` | présent sur les 100 ; `Subject.Name` sur 69 |
| Licence | CC BY 4.0 partout |
| Textes `b'…'` | aucun sur cette page |
| Largeur `Large` < 800 px | 1 image (602 px) |

### 3.2 Comportement du CDN (`cdn.eso.org`, mesuré le 24/09/2026)

Sur `images/large/potw2638a.jpg` :

| Requête | Résultat |
|---|---|
| `HEAD` | `200`, `content-length: 5294315` — identique au `FileSize` du flux `d2d` |
| En-têtes de validation | `ETag` présent (32 caractères hexadécimaux entre guillemets), `Last-Modified` présent |
| `Range: bytes=0-99` | `206`, `content-range: bytes 0-99/5294315` |
| Divers | `accept-ranges: bytes`, CDN77 devant un stockage de type S3 (`x-amz-meta-*`, `x-rgw-object-type`), réponse servie depuis le cache (`x-77-cache: HIT`) |

Conséquences : `telecharger` fonctionne tel quel. La reprise `.part` sur 206
est possible, `fichier_complet` peut comparer à `FileSize`, et `--verifier`
dispose d'un `ETag` à envoyer. Il ne faut **pas** traiter l'`ETag` comme une
somme MD5 du fichier : sur un stockage S3 cela n'est vrai que pour les objets
envoyés en une fois, et rien ne garantit la forme sur les gros TIFF.

Extrapolation grossière (la page 1 ne contient que des images récentes, donc
probablement plus grandes que la moyenne) : de l'ordre de 60 à 170 Go en
`Large`, de l'ordre du téraoctet en `Original`.

**Piège repéré : l'`ID` n'est pas toujours le nom du fichier.** Sept entrées
ont un `ID` suffixé par la langue (`annlang26007b-es-cl-en`) alors que le fichier
s'appelle `annlang26007b-es-cl.jpg`. Il est probable qu'une autre entrée (la
version dans la langue d'origine) pointe vers le même fichier ou un homonyme :
l'adaptateur doit prendre le nom de fichier dans l'URL, et `chemin_libre`
suffixera un éventuel doublon. À vérifier sur les pages suivantes avant de
décider s'il faut dédupliquer par URL.

Conséquences de conception :

- **Choix du format obligatoire.** Télécharger `Original` par défaut sur l'ESO
  reviendrait à rapatrier des TIFF de plusieurs centaines de Mo, voire plus d'un
  Go. Il faut un réglage « format » propre à ce type de source.
- **Le classement « par galerie » n'a pas d'équivalent direct.** Chaque source
  déclare les classements qu'elle sait faire ; l'interface grise les autres.
- **Le crédit mérite d'être conservé** dans le manifeste : c'est la seule
  obligation de la licence, et cela nourrit directement l'item 4 du backlog
  (export de catalogue).

Plan B si `d2d` est désactivé chez l'ESO : `toasty` liste les images en lisant
une variable JavaScript `var images = [...]` embarquée dans les pages
`archive/search/…/N/`, puis interroge `…/<id>/api/json/` image par image. C'est
exactement le parsing HTML que le projet a choisi d'éviter, et c'est une requête
par image en plus : à ne faire que si le plan A est fermé.

---

## 4. Proposition d'architecture

### 4.1 Principe

```
                 ┌──────────────────────────── engine.py ─────────────────────────────┐
app.py / cli.py ─┤ Moteur : manifeste, filtre largeur, classement, chemins, telecharger │
   (Options)     │           ▲ Element (normalisé)                                      │
                 │           │                                                          │
                 │   Source (adaptateur)  ◄── Transport (session, délai, arrêt, rejeux)│
                 └───────────┼──────────────────────────────────────────────────────────┘
                             ├── sources/wordpress.py
                             └── sources/djangoplicity.py
```

- Le **moteur** ne voit que des `Element`. Il ne sait plus ce qu'est un `post`
  ni un `ResourceType`.
- La **source** traduit un site en `Element`, et elle seule interprète les
  signaux de son serveur (codes d'erreur, en-têtes, liens `Next`).
- Le **transport** est fourni par le moteur à la source. Il porte le délai entre
  requêtes, l'arrêt coopératif et les rejeux ; une source ne crée jamais sa
  propre session. C'est ce qui garantit que le plancher de 0,2 s s'applique à
  tous les types de sites sans qu'un adaptateur puisse l'oublier.

Pas de dépendance nouvelle, pas de Qt : tout reste du côté moteur de la
frontière 1.

### 4.2 Le contrat

```python
# sources/base.py
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, ClassVar, Iterator


@dataclass(frozen=True)
class Element:
    """Une image à synchroniser, telle que le moteur la comprend."""
    ident: str               # unique au sein de la source ; clé du manifeste
    url: str
    nom_fichier: str
    date: str | None         # ISO 8601 ; sert au delta et au classement par date
    mois: str | None         # "AAAA-MM" pour le classement par date
    largeur: int | None
    taille: int | None       # taille annoncée, pour détecter un fichier tronqué
    groupe: str | None       # clé de regroupement « galerie », résolue plus tard
    extra: dict = field(default_factory=dict)   # crédit, titre, somme de contrôle…


class Source(ABC):
    type: ClassVar[str]
    classements: ClassVar[frozenset[str]]       # sous-ensemble de config.CLASSEMENTS

    def __init__(self, base: str, transport: "Transport", reglages: dict,
                 progression: Callable[[int, int, str], None]) -> None: ...

    @abstractmethod
    def inventaire(self, depuis: str | None, jusqua: str | None) -> Iterator[Element]:
        """Parcourt le catalogue dans l'ordre chronologique si possible."""

    def resoudre_groupes(self, cles: set[str], connus: dict[str, str]) -> dict[str, str]:
        """Clé de groupe → nom de dossier. Par défaut : aucun regroupement."""
        return dict(connus)
```

Correspondance pour les deux sources :

| Champ | WordPress | Djangoplicity |
|---|---|---|
| `ident` | `str(m["id"])` | `f"{ID}:{format}"` |
| `url` | `source_url` | `URL` de la ressource du format choisi |
| `nom_fichier` | nom du chemin de l'URL | idem (`eso1907a.jpg`) |
| `date` | `date` | `PublicationDate` |
| `mois` | extrait de `/uploads/AAAA/MM/` (comportement actuel conservé) | extrait de `PublicationDate` |
| `largeur` / `taille` | `media_details.width` / `filesize` | `int(Dimensions[0])` / `FileSize` |
| `groupe` | `str(post)` ou `None` | `None` (voir question 5) |
| `extra` | — | `credit`, `titre`, `checksum` |

Deux choix à signaler :

- **`ident` WordPress reste `str(id)`**, exactement la clé actuelle du
  manifeste : les dossiers existants sont repris tels quels, sans migration.
- **`ident` Djangoplicity inclut le format.** Si l'utilisateur passe de `Large`
  à `Original`, les nouvelles versions se téléchargent et les anciennes restent
  en place — même logique que « changer de classement ne déplace rien ». Sans
  cela, le manifeste considérerait l'image comme déjà faite dans l'autre format.

### 4.3 Le transport

```python
class Transport:
    """Plomberie HTTP partagée : une session, un délai, un arrêt."""

    def __init__(self, delai: float, arret: threading.Event) -> None: ...
    def verifier_arret(self) -> None: ...
    def pause(self, secondes: float | None = None) -> None: ...        # défaut : délai
    def get_json(self, url: str, params: dict | None = None,
                 fin_si: frozenset[int] = frozenset()) -> tuple[object | None, Mapping]:
        """Rejeux et pause inclus. Un code de `fin_si` renvoie (None, en-têtes)."""
```

`_verifier_arret`, `_pause` et le cœur de `_api` actuels y migrent. La règle
« 400 = page au-delà de la dernière » devient `fin_si={400}` passé par
l'adaptateur WordPress : elle n'est plus imposée aux autres sources.
`telecharger` reste dans le moteur et emprunte la session du transport.

### 4.4 Arborescence

```
Glaneur/
  engine.py              Moteur générique, manifeste, cache, telecharger
  sources/
    __init__.py          SOURCES = {"wordpress": WordPress, "djangoplicity": Djangoplicity}
    base.py              Element, Source, Transport
    wordpress.py         lister_medias, _bases_rest, resoudre_parents actuels
    djangoplicity.py     nouveau
```

Registre **statique** : un dictionnaire importé explicitement. Pas de découverte
par `entry_points` ni d'import dynamique — PyInstaller ne verrait pas les modules
et on retomberait sur un `ImportError` qui n'existe que dans l'exécutable.

### 4.5 Les invariants, un par un

| Invariant | Devenir |
|---|---|
| Pagination par `X-WP-TotalPages` | Reste dans `wordpress.py`, avec ses tests. Djangoplicity applique la même règle à sa façon : on suit `Next` tel que renvoyé, jamais le nombre d'entrées reçues. |
| Mode d'ouverture du `.part` selon le 206 | Inchangé, `telecharger` ne bouge pas. Encore plus critique avec des fichiers de 1 Go. |
| `__init__.py` présent | S'applique aussi à `sources/`. |
| Plancher de 0,2 s | Garanti par construction : seul le transport fait des requêtes d'inventaire. |
| Écritures atomiques | Inchangé. |
| Interruption ⇒ pas de `derniere_execution` | Inchangé (géré hors moteur). |
| Manifeste mémorise le chemin | Inchangé ; une reprise ne sollicite pas la source pour les éléments connus. |
| Second passage sans résolution de parent | Conservé : `resoudre_groupes` n'est appelé que pour les éléments nouveaux, avec le cache. |

Nouveau point de vigilance : le filtre `after` de Djangoplicity est inclusif,
donc l'élément le plus récent du cache revient à chaque passage. Le manifeste
l'écarte déjà, mais le compteur « déjà à jour » en tiendra compte ; les tests
doivent l'attendre.

### 4.6 Cache

On garde les clés actuelles (`derniere_date_media`, `titres_parents`) pour ne
pas invalider les caches existants, avec trois ajustements :

- l'empreinte devient `site` **et** `type` ;
- les clés de `titres_parents` sont des chaînes quelconques (suppression du
  filtre `isdigit`) ;
- la conversion de `derniere_date_media` vers le format de `after` est l'affaire
  de l'adaptateur, pas du moteur.

### 4.7 Configuration

Dans `config.py`, source unique de vérité, sur le modèle de `CLASSEMENTS` :

```python
TYPES_SOURCE: dict[str, str] = {
    "WordPress (API REST)": "wordpress",
    "Djangoplicity (ESO, ESA/Hubble…)": "djangoplicity",
}

FORMATS_DJANGOPLICITY: dict[str, str] = {
    "Grand JPEG": "Large",
    "Original (TIFF, très lourd)": "Original",
    "Écran (1280 px)": "Small",
}
```

et deux champs dans `Config` : `type_source = "wordpress"` et
`format_image = "Large"` (valeur par défaut à confirmer, question 3).
`valider()` ramène un type inconnu à `wordpress`, un format inconnu au défaut,
et un classement non supporté par la source à `date`. Une configuration
existante sans ces champs se charge donc à l'identique.

`Options` gagne `type_source` et `format_image` ; `Moteur` choisit l'adaptateur
dans `SOURCES`. L'UI ne connaît que les libellés.

### 4.8 Interface

Dans le dialogue des préférences : le groupe « Site WordPress » devient « Site »,
avec une liste déroulante de type au-dessus du champ URL, et un champ « Format »
visible seulement pour Djangoplicity. Les classements non supportés sont grisés
(l'info vient de `Source.classements`, exposée par une fonction du moteur pour
que `app.py` n'importe pas les adaptateurs). Rien d'autre ne change dans
`app.py` : il construit toujours un `Options` et lance un `QThread`.

---

## 5. Décisions et alternatives écartées

- **Adaptateurs plutôt qu'un moteur par site.** Dupliquer `executer` par site
  doublerait le code le plus délicat (reprise, suppressions) et donc les
  endroits où un invariant peut se perdre.
- **Type explicite plutôt que détection automatique.** La détection coûte des
  requêtes à chaque lancement et peut se tromper sur un site derrière un proxy.
  On peut proposer un bouton « Détecter » dans les préférences, qui sonde
  `/wp-json/` puis `…/images/d2d/` une seule fois et remplit le champ.
- **Une source par dossier de destination.** Le manifeste et le cache sont par
  dossier ; mélanger deux sources dans un même dossier mélangerait deux espaces
  d'identifiants. Si plusieurs sources simultanées sont voulues (question 2),
  la bonne forme est une liste de « profils » site + dossier, pas un dossier
  partagé.
- **Pas de framework de plugins.** Deux ou trois adaptateurs connus ne
  justifient pas plus qu'un dictionnaire.

---

## 6. Plan de migration

Chaque étape est livrable seule et passe les tests.

1. **Extraction sans changement de comportement.** Créer `sources/base.py`
   (`Element`, `Source`, `Transport`) et `sources/wordpress.py` avec le code
   déplacé ; `executer` consomme des `Element`. Coût réel : les tests actuels
   patchent `Moteur.lister_medias`, `_api`, `_bases_rest` et `resoudre_parents` ;
   il faudra les recibler sur l'adaptateur ou sur un faux transport. C'est
   l'essentiel du travail de l'étape.
2. **Configuration.** `type_source`, `format_image`, `TYPES_SOURCE`, validation,
   empreinte de cache. Toujours aucun changement visible.
3. **Adaptateur Djangoplicity** et ses tests contre un faux serveur `d2d`.
4. **Interface et CLI** (`--type`, `--format`), bouton « Détecter » optionnel.

---

## 7. Tests

Les cinq scénarios du projet deviennent des **tests de contrat** paramétrés par
type de source : un faux serveur WordPress et un faux serveur `d2d`, les mêmes
assertions.

1. premier passage complet ;
2. second passage : zéro requête fichier, zéro résolution de groupe ;
3. fichier tronqué et fichier supprimé : seuls ceux-là repassent ;
4. `--verifier` : 304 partout, aucun octet ;
5. interruption puis reprise : total exact.

Spécifiques à Djangoplicity :

- fin de pagination sur absence de `Next`, y compris si une page renvoie moins
  de `count` entrées avant la dernière ;
- `after` inclusif : l'élément frontière n'est pas retéléchargé ;
- `Dimensions` flottantes ; ressource du format demandé absente pour une image
  (compter un échec ou l'ignorer ? question 3) ;
- textes `"b'...'"` nettoyés avant d'en faire un nom de dossier.

---

## 8. Risques

- **Volume.** Plusieurs milliers d'images côté ESA/Hubble ; l'ESO est
  probablement du même ordre. En `Original`, on parle de téraoctets. Le format
  par défaut et un avertissement dans l'UI ne sont pas optionnels.
- **Reprise et revalidation.** Le CDN honore `Range` et fournit `ETag` et
  `Last-Modified` (§3.2) : le risque principal est levé pour `cdn.eso.org`. Il
  reste le `304` à confirmer, et l'hôte `www.eso.org`, qui n'a pas été mesuré.
  L'invariant 206 continue de protéger ce second hôte s'il ignorait `Range`.
- **Lien `Next` absolu.** On le suit tel quel ; s'il pointait un jour vers un
  autre hôte ou schéma que la base configurée, mieux vaut s'arrêter en erreur
  que suivre aveuglément.
- **Nom du produit.** « WP Image Downloader » décrit mal un outil multi-sources.
  Sans impact technique, mais le nom est dans `NOM_APP`, le dossier de config et
  l'installeur : le changer plus tard coûte une migration de `%APPDATA%`.

---

## 9. Questions ouvertes

1. ~~Le flux `d2d` de l'ESO répond-il ?~~ Oui (§3.1). ~~Le CDN gère-t-il `Range`
   et les validateurs ?~~ Oui (§3.2). Reste le `304` sur `If-None-Match`.
2. Une source à la fois (on ajoute juste un type), ou plusieurs sources
   synchronisées en parallèle (profils site + dossier) ? La seconde option
   touche `Config`, le planificateur et l'UI bien plus largement.
3. Quel format par défaut pour l'ESO, et que faire d'une image dont ce format
   manque : l'ignorer, ou se rabattre sur le format inférieur ?
4. Tout le catalogue ESO, ou un sous-ensemble ? `d2d` ne filtre que par date ;
   un filtrage par catégorie demanderait autre chose.
5. Faut-il un regroupement pour l'ESO ? Candidat naturel : le premier niveau
   significatif de `Subject.Category`, disponible sans requête. Ou le classement
   par date suffit-il ?
6. As-tu d'autres types de sites en tête ? Si c'est seulement WordPress et
   Djangoplicity, le contrat ci-dessus suffit ; s'il y a des sites sans API, il
   faudra prévoir une source « HTML » et le contrat restera valable, mais
   l'adaptateur sera d'une autre nature.

---

## Annexe : écarts relevés entre les instructions du projet et le code

À corriger d'un côté ou de l'autre, sinon je raisonnerai sur une mauvaise carte :

- Les instructions parlent du paquet `servette/` ; le code importé est dans
  `Glaneur/` (et c'est ce que `app.py` et `cli.py` importent).
- Les instructions disent « pas de framework de tests » ; le dépôt utilise
  `pytest` et `pytest-qt` (README et `tests/`).
- La docstring d'`engine.py` mentionne encore l'UI Tkinter.
- Le cache API (`.cache.json`) et le mode `--pas-cache` existent dans le code
  mais pas dans les invariants des instructions ; « une interruption n'écrit pas
  le cache » mériterait d'y figurer.
