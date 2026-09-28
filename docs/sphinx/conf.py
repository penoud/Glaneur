"""Sphinx configuration for Glaneur's API documentation.

The docs are built with autodoc + napoleon (Google-style docstrings)
and rendered by the furo theme. See ``docs/sphinx/README.md`` for the
docstring conventions the project adopts.
"""

from __future__ import annotations

import sys
from pathlib import Path

# The repository root must be on sys.path so autodoc can find the
# ``Glaneur`` package without an editable install.
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

# Napoleon: Google-style only, the project's norm.
napoleon_google_docstring = True
napoleon_numpy_docstring = False
napoleon_include_init_with_doc = False
napoleon_use_admonition_for_notes = True

# Autodoc: signature in the header, public members by default, source
# order preserved for readable rendering.
autodoc_default_options = {
    "members": True,
    "undoc-members": False,
    "show-inheritance": True,
}
autodoc_member_order = "bysource"
autodoc_typehints = "description"

# The engine imports PySide6.QtCore; the mock lets autodoc load the
# affected modules without requiring Qt on the build environment.
autodoc_mock_imports = ["PySide6"]

# Mocked classes are not resolvable. We explicitly ignore references
# to PySide6 rather than turning off ``-W`` or ``nitpicky``.
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

# ``-W`` turns warnings into errors: the docs must stay clean at every
# commit. False positives are filtered explicitly, never globally.
nitpicky = True
