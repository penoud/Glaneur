# Makefile Sphinx minimal — voir `docs/sphinx/README.md` pour les
# conventions. La cible `html` est la seule tenue verte à chaque commit.

SPHINXOPTS    ?= -W -n
SPHINXBUILD   ?= sphinx-build
SOURCEDIR     = .
BUILDDIR      = _build

.PHONY: help html clean apidoc

help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS)

html:
	@$(SPHINXBUILD) -b html $(SPHINXOPTS) "$(SOURCEDIR)" "$(BUILDDIR)/html"

clean:
	@rm -rf "$(BUILDDIR)"

# Régénère `api/*.rst` à partir du paquet Glaneur. À relancer quand un
# module Python est ajouté, renommé ou supprimé. Le post-traitement
# supprime les blocs « Module contents » des rst de paquet : ils ne font
# que ré-inclure les re-exports d'`__init__.py`, ce qui déclenche des
# doublons d'index (warnings `ref.python` en `-W`).
apidoc:
	@sphinx-apidoc -f -e -o api ../../Glaneur
	@for f in api/Glaneur.rst api/Glaneur.engine.rst api/Glaneur.sources.rst api/Glaneur.updater.rst; do \
	    python3 -c "import sys,re,pathlib;p=pathlib.Path(sys.argv[1]);t=p.read_text(encoding='utf-8');p.write_text(re.sub(r'\nModule contents\n-+\n\n\.\. automodule::[^\n]*\n(?:   :[^\n]*\n)+','\n',t),encoding='utf-8')" $$f; \
	done

%:
	@$(SPHINXBUILD) -M $@ "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS)
