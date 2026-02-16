# Building Documentation

## Install Documentation Dependencies

```bash
pip install -e ".[dev]"
```

This installs:
- `sphinx` - Documentation generator
- `sphinx-rtd-theme` - ReadTheDocs theme for professional appearance
- `myst-parser` - Support for Markdown in Sphinx

## Build HTML Documentation

```bash
cd docs
make html
```

The HTML documentation will be generated in `docs/_build/html/`. Open `docs/_build/html/index.html` in your browser.

## Build Other Formats

**PDF documentation:**
```bash
cd docs
make pdf
```

**Single HTML file:**
```bash
cd docs
make singlehtml
```

**Clean the build directory:**
```bash
cd docs
make clean
```

## View Documentation Locally

After building:
```bash
cd docs/_build/html
python -m http.server 8000
```

Then visit `http://localhost:8000` in your browser.

## Key Documentation Features

- **API Reference**: Auto-generated documentation from source code docstrings
- **Architecture Guide**: [docs/ARCHITECTURE.md](ARCHITECTURE.md)
- **Benchmarking**: [docs/BENCHMARKING.md](BENCHMARKING.md)
- **Philosophy**: [docs/PHILOSOPHY.md](PHILOSOPHY.md)
- **Workflow Guide**: [docs/WORKFLOW.md](WORKFLOW.md)
- **Expert Guide**: [docs/EXPERT_GUIDE.md](EXPERT_GUIDE.md)

## Adding New Documentation

1. **Module Documentation**: Add `.rst` files to `docs/api/` with `automodule` directives
2. **Markdown Files**: Place `.md` files in `docs/` and reference in `index.rst`
3. **Update Index**: Add new documents to the table of contents in `docs/index.rst`

## Documentation Configuration

The Sphinx configuration is defined in [conf.py](conf.py):
- **Theme**: Read the Docs (sphinx-rtd-theme)
- **Extensions**: autodoc, napoleon, intersphinx, linkcode, myst_parser
- **Source Format**: Supports both `.rst` and `.md` files
