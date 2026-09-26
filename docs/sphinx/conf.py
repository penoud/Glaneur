"""Configuration Sphinx pour la doc API de Glaneur.

La doc est construite avec autodoc + napoleon (docstrings Google-style)
et rendue par le thème furo. Voir `docs/sphinx/README.md` pour les
conventions de docstring adoptées dans le projet.
"""

from __future__ import annotations

import sys
from pathlib import Path

# La racine du dépôt doit être sur sys.path pour qu'autodoc trouve le
# paquet `Glaneur` sans installation éditable.
_RACINE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_RACINE))

from Glaneur import __version__ as _version

project = "Glaneur"
author = "Glaneur contributors"
copyright = "2026, Glaneur contributors"
release = _version
version = ".".join(_version.split(".")[:2])

language = "fr"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# Napoleon : Google-style uniquement, la norme du projet.
napoleon_google_docstring = True
napoleon_numpy_docstring = False
napoleon_include_init_with_doc = False
napoleon_use_admonition_for_notes = True

# Autodoc : signature dans l'entête, membres publics par défaut, ordre
# préservé du code source pour rester lisible côté rendu.
autodoc_default_options = {
    "members": True,
    "undoc-members": False,
    "show-inheritance": True,
}
autodoc_member_order = "bysource"
autodoc_typehints = "description"

# The engine imports PySide6.QtCore; the mock lets autodoc load
# les modules concernés sans exiger Qt sur l'environnement de build.
autodoc_mock_imports = ["PySide6"]

# Les classes mockées ne sont pas résolvables. On ignore explicitement les
# renvois vers PySide6 plutôt que de désactiver `-W` ou `nitpicky`.
nitpick_ignore = [
    ("py:class", "PySide6.QtCore.QThread"),
]

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "requests": ("https://requests.readthedocs.io/en/latest/", None),
}

html_theme = "furo"
html_title = f"Glaneur {release}"
html_static_path: list[str] = []

# `-W` transforme les avertissements en erreurs : la doc doit rester propre
# à chaque commit. Faux positifs à filtrer explicitement, jamais globalement.
nitpicky = True
