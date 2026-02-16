# Makefile for Sphinx documentation
# 
# For more information, see: http://www.sphinx-doc.org/

SPHINXOPTS    ?=
SPHINXBUILD   ?= sphinx-build
PAPER         ?=
BUILDDIR      ?= _build

ifeq ($(OS),Windows_NT)
	RMDIR = rmdir /s /q
	SEP = \\
else
	RMDIR = rm -rf
	SEP = /
endif

.PHONY: help Makefile

# Put it first so that "make" without argument is like "make help"
help:
	@$(SPHINXBUILD) -M help "$(CURDIR)" "$(BUILDDIR)" $(SPHINXOPTS)

.PHONY: clean
clean:
	$(RMDIR) "$(BUILDDIR)"

.PHONY: html
html:
	$(SPHINXBUILD) -b html "$(CURDIR)" "$(BUILDDIR)/html" $(SPHINXOPTS)
	@echo "Build finished. The HTML pages are in $(BUILDDIR)/html."

.PHONY: dirhtml
dirhtml:
	$(SPHINXBUILD) -b dirhtml "$(CURDIR)" "$(BUILDDIR)/dirhtml" $(SPHINXOPTS)
	@echo "Build finished. The HTML pages are in $(BUILDDIR)/dirhtml."

.PHONY: singlehtml
singlehtml:
	$(SPHINXBUILD) -b singlehtml "$(CURDIR)" "$(BUILDDIR)/singlehtml" $(SPHINXOPTS)
	@echo "Build finished. The single HTML page is in $(BUILDDIR)/singlehtml."

.PHONY: json
json:
	$(SPHINXBUILD) -b json "$(CURDIR)" "$(BUILDDIR)/json" $(SPHINXOPTS)
	@echo "Build finished. The JSON file is in $(BUILDDIR)/json."

.PHONY: htmlhelp
htmlhelp:
	$(SPHINXBUILD) -b htmlhelp "$(CURDIR)" "$(BUILDDIR)/htmlhelp" $(SPHINXOPTS)
	@echo "Build finished. The HTML help pages are in $(BUILDDIR)/htmlhelp."

.PHONY: qthelp
qthelp:
	$(SPHINXBUILD) -b qthelp "$(CURDIR)" "$(BUILDDIR)/qthelp" $(SPHINXOPTS)
	@echo "Build finished. The Qt help pages are in $(BUILDDIR)/qthelp."

.PHONY: epub
epub:
	$(SPHINXBUILD) -b epub "$(CURDIR)" "$(BUILDDIR)/epub" $(SPHINXOPTS)
	@echo "Build finished. The epub file is in $(BUILDDIR)/epub."

.PHONY: latex
latex:
	$(SPHINXBUILD) -b latex "$(CURDIR)" "$(BUILDDIR)/latex" $(SPHINXOPTS)
	@echo "Build finished. The LaTeX files are in $(BUILDDIR)/latex."

.PHONY: latexpdf
latexpdf:
	$(SPHINXBUILD) -b latex "$(CURDIR)" "$(BUILDDIR)/latex" $(SPHINXOPTS)
	@echo "The LaTeX files are in $(BUILDDIR)/latex."
	@echo "Run \`make' in that directory to run the command \`pdflatex' here and create PDF files."

.PHONY: text
text:
	$(SPHINXBUILD) -b text "$(CURDIR)" "$(BUILDDIR)/text" $(SPHINXOPTS)
	@echo "Build finished. The text files are in $(BUILDDIR)/text."

.PHONY: man
man:
	$(SPHINXBUILD) -b man "$(CURDIR)" "$(BUILDDIR)/man" $(SPHINXOPTS)
	@echo "Build finished. The man pages are in $(BUILDDIR)/man."

.PHONY: texinfo
texinfo:
	$(SPHINXBUILD) -b texinfo "$(CURDIR)" "$(BUILDDIR)/texinfo" $(SPHINXOPTS)
	@echo "Build finished. The texinfo files are in $(BUILDDIR)/texinfo."

.PHONY: pdf
pdf:
	$(SPHINXBUILD) -b pdf "$(CURDIR)" "$(BUILDDIR)/pdf" $(SPHINXOPTS)
	@echo "Build finished. The PDF files are in $(BUILDDIR)/pdf."

.PHONY: linkcheck
linkcheck:
	$(SPHINXBUILD) -b linkcheck "$(CURDIR)" "$(BUILDDIR)/linkcheck" $(SPHINXOPTS)
	@echo "Link check complete; look for any errors in the above output or in $(BUILDDIR)/linkcheck/index.html."

.PHONY: spelling
spelling:
	$(SPHINXBUILD) -b spelling "$(CURDIR)" "$(BUILDDIR)/spelling" $(SPHINXOPTS)
	@echo "Spell check complete; look for any errors in the above output or in $(BUILDDIR)/spelling/output.txt."

.PHONY: doctest
doctest:
	$(SPHINXBUILD) -b doctest "$(CURDIR)" "$(BUILDDIR)/doctest" $(SPHINXOPTS)
	@echo "Testing of doctests in the sources finished, look at the results in $(BUILDDIR)/doctest/index.html."

.PHONY: coverage
coverage:
	$(SPHINXBUILD) -b coverage "$(CURDIR)" "$(BUILDDIR)/coverage" $(SPHINXOPTS)
	@echo "Testing of coverage in the sources finished, look at the results in $(BUILDDIR)/coverage/index.html."

.PHONY: dummy
dummy:
	$(SPHINXBUILD) -b dummy "$(CURDIR)" "$(BUILDDIR)/dummy" $(SPHINXOPTS)
	@echo "Build finished. No output generated."

%: Makefile
	@$(SPHINXBUILD) -M $@ "$(CURDIR)" "$(BUILDDIR)" $(SPHINXOPTS)
