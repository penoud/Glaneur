# Documentation Sphinx — Glaneur

Ce dossier accueille la doc API générée par Sphinx (US-02 du sprint courant).
Il contiendra `conf.py`, `index.rst`, l'arborescence `api/` produite par
`sphinx-apidoc`, et `_build/` (ignoré par git).

## Style de docstring

**Décision : Napoleon (Google-style).**

- Extension activée dans `conf.py` : `sphinx.ext.napoleon`.
- Sections attendues, dans cet ordre quand elles s'appliquent :

  ```python
  def resoudre(url: str, timeout: float = 30) -> Resultat:
      """Résout une URL vers un `Resultat`.

      La résolution suit les redirections HTTP puis vérifie l'ETag.
      Voir `Glaneur.engine.Resultat` pour la sémantique du champ `message`.

      Args:
          url: URL absolue à résoudre.
          timeout: Délai maximum en secondes.

      Returns:
          Le `Resultat` construit à partir de la réponse.

      Raises:
          Interrompu: Si l'utilisateur a demandé l'arrêt pendant l'appel.
          requests.RequestException: En cas d'échec réseau irrémédiable.
      """
  ```

- Une ligne résumé, ligne vide, description longue si utile, ligne vide,
  sections `Args:` / `Returns:` / `Yields:` / `Raises:` / `Attributes:`.
- Types dans les annotations Python, **pas** dans les sections
  (`Args: url: URL...`, pas `Args: url (str): URL...`).

Pourquoi Napoleon et pas rST natif ? Les docstrings existants sont tous en
prose française lisible ; Napoleon permet de les enrichir progressivement
sans les démolir. Le rendu final HTML est équivalent.

## État de départ (mesure US-01, 2026-09-25)

| Module                             | Doc / total | Style   |
|-----------------------------------|:-----------:|---------|
| `Glaneur/__init__.py`             | 1 / 1       | prose   |
| `Glaneur/bug_report.py`           | 4 / 4       | prose   |
| `Glaneur/config.py`               | 3 / 10      | prose   |
| `Glaneur/engine.py`               | 8 / 25      | prose   |
| `Glaneur/i18n.py`                 | 4 / 4       | prose   |
| `Glaneur/logsetup.py`             | 2 / 2       | prose   |
| `Glaneur/scheduler.py`            | 2 / 8       | prose   |
| `Glaneur/sources/__init__.py`     | 2 / 2       | prose   |
| `Glaneur/sources/base.py`         | 10 / 13     | prose   |
| `Glaneur/sources/djangoplicity.py`| 2 / 5       | prose   |
| `Glaneur/sources/wordpress.py`    | 2 / 5       | prose   |
| `Glaneur/systeme.py`              | 8 / 9       | prose   |
| `Glaneur/updater/__init__.py`     | 1 / 1       | prose   |
| `Glaneur/updater/downloader.py`   | 1 / 5       | prose   |
| `Glaneur/updater/github_release.py`| 1 / 4      | prose   |
| `Glaneur/updater/models.py`       | 1 / 7       | prose   |
| `Glaneur/updater/qt_threads.py`   | 3 / 7       | prose   |
| `Glaneur/updater/version.py`      | 1 / 3       | prose   |
| `app.py`                          | 8 / 19      | prose   |
| `cli.py`                          | 1 / 3       | prose   |
| **Total**                         | **65 / 137**| **prose** |

- 100 % des docstrings existants sont en prose libre. Aucun n'utilise déjà
  `:param:` ou `Args:` — la conversion est purement additive.
- `servette/` ne contient que du `.pyc` (résidu du rename `WpImageDownloader
  → Glaneur`) et sort du périmètre du sprint. À supprimer dans un lot séparé
  ou pris en compte par le prochain nettoyage.

## Ordre de conversion pour US-03

Le sprint propose un ordre par « visibilité et invariants ». Combiné à la
dette mesurée ci-dessus, l'ordre reste :

1. `Glaneur/engine.py` — 17 symboles à documenter, module central.
2. `Glaneur/sources/base.py` puis `wordpress.py`, `djangoplicity.py`,
   `__init__.py` — contrats d'adaptateur, 8 symboles nus au total.
3. `Glaneur/config.py` — 7 symboles nus, format persistant.
4. `Glaneur/scheduler.py` — 6 symboles nus, frontière Qt à trancher plus tard.
5. `Glaneur/systeme.py` — 1 seul manquant, rapide.
6. `Glaneur/i18n.py`, `Glaneur/logsetup.py`, `Glaneur/bug_report.py` — déjà
   couverts, une passe d'enrichissement Napoleon.
7. `Glaneur/updater/` — 20 symboles nus répartis sur 6 fichiers,
   traiter le sous-paquet en un seul lot.
8. `app.py` — 11 manquants, gros fichier (54 kB), possiblement en deux
   commits par sections d'UI.
9. `cli.py` — 2 manquants, trivial.

Un commit par fichier (ou par groupe cohérent quand un fichier tient en
moins de ~100 lignes de docstring modifiées). Après chaque commit,
`sphinx-build -W` doit rester vert (US-02 doit être en place).
