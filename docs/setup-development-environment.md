# Setup Development Environment

## System Setup

1. Clone the [common-guidelines](https://github.com/iglootools/common-guidelines) repo as a sibling directory:
   ```bash
   # From the parent directory of photree (e.g. iglootools/)
   git clone git@github.com:iglootools/common-guidelines.git
   ```
   This is required for Claude Code to load shared coding guidelines via `@` imports in `CLAUDE.md`.

2. [Install and activate mise](https://mise.jdx.dev/installing-mise.html)

3. Configure github CLI with `gh auth login` and ensure you have access to the repository (optional, for convenience).

4. Activate the virtual environment:
   ```bash
   # - Install all the tools defined in mise.toml
   # - Set up the .venv with the correct Python version
   mise install

   # vscode and poetry should automatically detect and use the .venv created by mise
   poetry install

   # To recreate the virtualenv from scratch:
   poetry env remove --all
   ```

## VSCode Setup

Install the following extensions:

- [Ruff](https://marketplace.visualstudio.com/items?itemName=charliermarsh.ruff) — formatting and linting (format-on-save is enabled in `.vscode/settings.json`)
- [Pylance](https://marketplace.visualstudio.com/items?itemName=ms-python.vscode-pylance) — type checking (uses pyright, configured via `[tool.pyright]` in `pyproject.toml`)
- [Tombi](https://marketplace.visualstudio.com/items?itemName=tombi-toml.tombi) — TOML formatting and validation

No interpreter selection is needed: `.vscode/settings.json` and `[tool.pyright]` in `pyproject.toml`
already point the editor at the `.venv` created by Poetry. See
[Pyright environment resolution](https://github.com/iglootools/common-guidelines/blob/main/tooling.md#pyright-environment-resolution)
and [VSCode setup](https://github.com/iglootools/common-guidelines/blob/main/tooling.md#vscode)
in the shared guidelines for what those settings do, how to verify them, and why a window reload is
required after changing them.

## Claude Code Setup

Install the Pyright LSP plugin so Claude resolves symbols instead of grepping for them. Follow
[Claude Code setup in the shared guidelines](https://github.com/iglootools/common-guidelines/blob/main/tooling.md#claude-code)
once the virtualenv step above is done — it covers the install command, why `pyright-langserver` has
to come from this project's `.venv`, and how to verify that it does.
