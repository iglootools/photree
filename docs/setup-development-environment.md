# Setup Development Environment

## System Setup

1. [Install and activate mise](https://mise.jdx.dev/installing-mise.html)

2. Install the system tools mise does not manage:

   ```bash
   brew install graphviz exiftool
   ```

   - **graphviz**: `lint-depgraph` and `depgraph` draw the Module Overview with
     it, so `mise run lint`, `preflight-quick` and `preflight` fail without it.
   - **exiftool**: the EXIF tests skip without it, so a local run passes having
     tested less than CI, which installs both.

   On Linux, install `graphviz` and `libimage-exiftool-perl` instead, as the
   `preflight` workflow does.

3. Configure github CLI with `gh auth login` and ensure you have access to the
   repository (optional, for convenience).

4. Activate the virtual environment:

   ```bash
   # - Install all the tools defined in mise.toml (python, uv, ...)
   # - Create .venv on the pinned Python and activate it
   mise install

   # Usually unnecessary: [deps.uv] in mise.toml runs `uv sync` automatically before any
   # `mise run` when uv.lock or pyproject.toml changed, or .venv is missing.
   mise run install

   # To recreate the virtualenv from scratch
   mise run reinstall
   ```

   Add and remove dependencies with `uv add` / `uv remove`, which update
   `pyproject.toml` and `uv.lock` together. (`mise deps add` does not support
   uv.)

   Run tools with `uv run --no-sync <tool>` rather than bare — see
   [Building and Testing](building-and-testing.md) for why that matters when
   more than one project's virtualenv is in play.

## Editor and Claude Code Setup

The repository is already configured; what is left is per-machine installation.

- **Extensions** — accept the prompt on first open; the set is committed in
  [.vscode/extensions.json](../.vscode/extensions.json).
  [What each one is for, and which committed settings silently stop working without it][vscode].
- **Interpreter** — nothing to select. `.vscode/settings.json` and
  `[tool.pyright]` already point at `.venv`.
  [What those settings do, and why a reload is needed after changing them][pyright].
- **Plugins** — `.claude/settings.json` enables `iglootools` for the shared
  guidelines and `pyright-lsp` so Claude resolves symbols instead of grepping
  for them. A plugin the project enables still installs once per machine:
  [install per project][install], then [update one][update-one] or
  [all at once][update-all] on each release. For `pyright-lsp` see
  [Claude Code setup][claude-code] — it needs the virtualenv step above done
  first.

[vscode]: https://github.com/iglootools/common/blob/main/guidelines/project-setup/ide.md#vscode
[pyright]: https://github.com/iglootools/common/blob/main/guidelines/project-setup/ide.md#pin-the-venv-for-pyright-in-toolpyright
[claude-code]: https://github.com/iglootools/common/blob/main/guidelines/project-setup/claude-code.md
[install]: https://github.com/iglootools/common/blob/main/docs/installation.md#install-it-per-project-not-per-user
[update-one]: https://github.com/iglootools/common/blob/main/docs/installation.md#updating-one-project
[update-all]: https://github.com/iglootools/common/blob/main/docs/installation.md#updating-every-project
