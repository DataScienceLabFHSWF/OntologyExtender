# Contributing to OntologyExtender

Thank you for your interest in contributing! This document outlines the development workflow and CI/CD setup.

## Development Setup

### 1. Clone and Install

```bash
git clone https://github.com/DataScienceLabFHSWF/OntologyExtender.git
cd OntologyExtender
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### 2. Set Up Pre-Commit Hooks (Recommended)

Pre-commit hooks automatically validate code before committing:

```bash
pip install pre-commit
pre-commit install
```

Now any `git commit` will automatically:
- Format code with `ruff`
- Type-check with `mypy`
- Validate YAML/JSON/TOML files
- Check for trailing whitespace and debug statements
- **Build and validate Sphinx documentation**

To manually run all hooks:
```bash
pre-commit run --all-files
```

## Code Quality

### Linting & Formatting

```bash
make lint          # Check code style
make format        # Auto-format code
make check         # Lint + test
```

### Type Checking

```bash
mypy src/
```

### Tests

```bash
pytest tests/ -v
```

## Documentation

### Building Docs Locally

```bash
make docs
open docs/_build/html/index.html
```

Or with the docs-check target (for CI):
```bash
make docs-check
```

### Adding Documentation

1. **Module docstrings**: Add/update docstrings in source code
   ```python
   def my_function(arg: str) -> int:
       """One-line summary.
       
       Longer description if needed.
       
       Parameters
       ----------
       arg : str
           Parameter description
       
       Returns
       -------
       int
           Return value description
       """
   ```

2. **Narrative docs**: Add `.md` or `.rst` files to `docs/`

3. **Update TOC**: Add to `docs/index.rst`

## Commit Workflow

### Before Committing

```bash
make check      # Lint, type-check, and test
make docs-check # Validate docs build
```

### Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
type(scope): subject

body (optional)
footer (optional)
```

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `ci`

Examples:
- `feat(agents): Add new debate strategy`
- `fix(benchmark): Handle None values in answer field`
- `docs: Update architecture documentation`
- `ci: Configure GitHub Actions workflows`

## CI/CD Pipelines

### Automated Checks (GitHub Actions)

Two workflows run on every PR and push:

#### 1. **lint-test.yml** — Code Quality & Tests
Runs on: `push` to any branch, `pull_request` to main/develop

- Python 3.10, 3.11, 3.12 (matrix)
- Ruff linting + formatting check
- MyPy type checking
- Pytest + coverage upload (Python 3.10 only)

**Status badge**: Check in PR for pass/fail

#### 2. **docs.yml** — Documentation Build
Runs on: `push`/`pull_request` if docs or source code changed

- Clean build of Sphinx documentation
- Upload artifacts (available in PR for review)
- **Auto-deploy to GitHub Pages** on `main` branch pushes

**To view built docs in a PR**: Go to "Artifacts" tab

### Local Pre-Commit Hook

The `.pre-commit-config.yaml` includes a `sphinx-docs-build` hook that:
- Runs before commits
- Rebuilds docs if `docs/` or `src/` files changed
- Prevents commits if docs fail to build

## Pull Request Process

1. **Create a feature branch**
   ```bash
   git checkout -b feature/my-feature
   ```

2. **Make changes** and commit regularly
   ```bash
   git add .
   git commit -m "feat(module): Description"
   ```

3. **Run pre-commit locally** before final push
   ```bash
   pre-commit run --all-files
   ```

4. **Push and create PR**
   ```bash
   git push --set-upstream origin feature/my-feature
   ```

5. **Respond to CI feedback** (comments, required status checks)

6. **Request review** from maintainers

7. **Merge** once approved and all checks pass

## Documentation CI/CD

The docs build is integrated into CI/CD:

- **On PR**: Docs are built and uploaded as artifacts; check "Artifacts" tab
- **On push to main**: Docs are auto-deployed to GitHub Pages at `https://ontologyextender.readthedocs.io/`

### Debugging Docs Failures

If `docs.yml` fails:

1. Download the artifact from the failed workflow
2. Check for Sphinx warnings/errors in the build log
3. Run locally: `make clean && make html`
4. Fix issues and re-commit

## Common Issues

### Pre-commit hook too slow?

The Sphinx build hook can be slow. Skip it for WIP commits:
```bash
git commit --no-verify -m "WIP: testing something"
```

But re-enable before final push.

### Mypy strict mode?

Use type: ignore sparingly:
```python
x = some_untyped_function()  # type: ignore
```

### Coverage requirements?

Current target: ≥ 70% for new code. See `.github/workflows/lint-test.yml` for details.

## Questions?

Open an issue or ask in discussions. Thank you for contributing!
