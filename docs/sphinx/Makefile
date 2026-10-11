# Minimal Sphinx Makefile — see `docs/sphinx/README.md` for the
# conventions. The `html` target is the only one kept green at every
# commit.

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

# Regenerate `api/*.rst` from the Glaneur package. Rerun whenever a
# Python module is added, renamed or removed. The post-processing step
# strips the "Module contents" blocks from the package rst files: they
# merely re-include the `__init__.py` re-exports, which triggers index
# duplicates (`ref.python` warnings under `-W`).
apidoc:
	@sphinx-apidoc -f -e -o api ../../Glaneur
	@for f in api/Glaneur.rst api/Glaneur.engine.rst api/Glaneur.sources.rst api/Glaneur.updater.rst; do \
	    python3 -c "import sys,re,pathlib;p=pathlib.Path(sys.argv[1]);t=p.read_text(encoding='utf-8');p.write_text(re.sub(r'\nModule contents\n-+\n\n\.\. automodule::[^\n]*\n(?:   :[^\n]*\n)+','\n',t),encoding='utf-8')" $$f; \
	done

%:
	@$(SPHINXBUILD) -M $@ "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS)
