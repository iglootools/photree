# Building and Testing

Run automated tests and checks:
```bash
# mise tasks
mise run check              # Run all checks: format + lint + type-check + compat-check + lock-check + lock-check-uv + clidocs-check + depgraph-check
mise run check-all          # Run all checks: regular checks + all tests

mise run test-all           # All tests (unit + integration)
mise run test-unit          # Unit tests
mise run test-integration-fs # Filesystem integration tests (full workflow)

mise run format             # ruff format
mise run lint               # ruff check
mise run type-check         # pyright
mise run compat-check       # vermin (enforce Python >=3.12 compatibility — see Python versions below)

mise run clidocs            # Regenerate CLI reference in docs/cli-reference.md
mise run clidocs-check      # Check that CLI reference is up to date
mise run depgraph           # Regenerate Module Overview in docs/architecture.md
mise run depgraph-check     # Check that Module Overview is up to date

mise run install            # Sync .venv with uv.lock (rarely needed by hand — see below)
mise run reinstall          # Delete .venv and sync from scratch
mise run lock-check-uv      # Check uv.lock is consistent with pyproject.toml

# Running tools directly
uv run pytest tests/ -v                         # All tests
uv run ruff format .                            # formatting
uv run ruff check photree/ tests/               # linting
uv run pyright photree/                         # type-checking
uv run vermin --target=3.12- --no-tips --no-parse-comments photree/ tests/  # compat check
uv run pytest tests/test_cli.py::TestVersionCommand::test_version_flag -v   # run a single test
```

`uv run` is the prefix to use rather than a bare `pytest`/`ruff`. It resolves the
environment from the project root, so it is correct regardless of what is on `PATH` — a bare
command in a shell that has *another* project's `.venv` active silently runs that project's
copy of the tool. The mise tasks above use `uv run --no-sync` for the same reason.

Dependencies install themselves: `[deps.uv]` in `mise.toml` runs `uv sync` before any
`mise run` whenever `uv.lock` or `pyproject.toml` has changed, or `.venv` has gone missing.
So `mise run install` is seldom needed explicitly, and `mise run reinstall` is for the case
that automatic check cannot see — a `.venv` that is *dirty* rather than *stale*, e.g. after
a manual `uv pip install`. Add or remove dependencies with `uv add` / `uv remove`.

## Python versions

Local development runs Python 3.14 (pinned in `mise.toml`), while the supported floor
is 3.12 — the system `python3` on Ubuntu 24.04 LTS. Code must therefore not use any
feature newer than 3.12, even though you are running 3.14. `mise run compat-check`
(vermin) is what catches violations; ruff's and pyright's 3.12 targets catch some but
not all of them.

photree itself is macOS-only today (see [Installation](installation.md)), so the Ubuntu
floor is about keeping the codebase portable rather than a platform we ship to — it
matters if Linux support is added later, and it keeps the policy consistent across
iglootools projects.

CI currently tests only the 3.12 floor — the 3.14 matrix entry in
`.github/workflows/test.yml` is commented out to save CI minutes.

Raising the floor to 3.14 (Ubuntu 26.04 LTS) is under consideration; see the
[Python Version Policy](https://github.com/iglootools/common-guidelines/blob/main/python.md#python-version-policy)
for the full rationale and the list of knobs that must move together.

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
- Set up the following Github secrets:
    - `ASCIINEMA_INSTALL_ID`:
        1. Execute `asciinema auth` in your terminal
        2. Click the suggested link
        3. store the content of `~/.local/state/asciinema/install-id` in the `ASCIINEMA_INSTALL_ID` secret

## Renovate
- Added the [iglootools](https://github.com/iglootools) org to [developer.mend.io](https://developer.mend.io/)
