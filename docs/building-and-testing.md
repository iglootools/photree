# Building and Testing

Run automated tests and checks:
```bash
# mise tasks
mise run check              # Run all checks: format + lint + type-check + compat-check + clidocs-check + depgraph-check
mise run check-all          # Run all checks: regular checks + all tests

mise run test-all           # All tests
mise run test-unit          # Unit tests

mise run format             # ruff format
mise run lint               # ruff check
mise run type-check         # pyright
mise run compat-check       # vermin (enforce Python >=3.12 compatibility)

mise run clidocs            # Regenerate CLI reference in docs/cli-reference.md
mise run clidocs-check      # Check that CLI reference is up to date
mise run depgraph           # Regenerate Module Overview in docs/architecture.md
mise run depgraph-check     # Check that Module Overview is up to date

# Using Poetry syntax directly
poetry run pytest tests/ -v                         # All tests
poetry run ruff format .                            # formatting
poetry run ruff check photree/ tests/               # linting
poetry run pyright photree/                          # type-checking
poetry run vermin --target=3.12- --no-tips --no-parse-comments photree/ tests/  # compat check
poetry run pytest tests/test_cli.py::TestVersionCommand::test_version_flag -v   # run a single test
```

The `check-links` workflow runs a link checker against the documentation to catch broken links.
It is scheduled to run weekly, but can also be triggered manually using `gh workflow run check-links.yml`.

## Release Process
- Trigger the `release` workflow: `gh workflow run release.yml`
- Let github workflows take care of the rest
    - `release` workflow: will bump version according to conventional commit conventions, push tag, and create a Github release
    - `publish` workflow: will publish the new version to PyPI

## Github Config
- The `main` branch is protected against force pushes.
- Settings > Advanced Security > Enable Dependency graph

## Renovate
- Added the [iglootools](https://github.com/iglootools) org to [developer.mend.io](https://developer.mend.io/)
