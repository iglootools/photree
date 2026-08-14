# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Architecture

Detailed overview of the architecture, design patterns, and execution flow: @docs/architecture.md

Internals (Image Capture file structure, album on-disk layout): @docs/internals.md

## Guidelines and Workflow

Before writing any code, apply the guidelines at write time, not as a post-hoc review. Walk the implementation checklist item by item before considering a task done.

Common guidelines (shared across iglootools projects):

@../common-guidelines/coding.md
@../common-guidelines/python.md

The two above govern every edit, so they are imported. The rest of the shared set is triggered by a
specific file — read the whole file before touching one of these, not just the section that looks
relevant:

| Read | Before touching |
|---|---|
| `../common-guidelines/python-tooling.md` | `pyproject.toml`, `mise.toml`, `uv.lock` — or adding a dependency, a mise task, or anything about building and publishing |
| `../common-guidelines/ide.md` | `.vscode/`, `.claude/settings.json`, `*.code-workspace`, `[tool.pyright]` |
| `../common-guidelines/project-setup.md` | `.github/workflows/`, `renovate.json`, `dependabot.yml`, `.gitignore` |

Project-specific guidelines: @docs/guidelines.md

Implementation checklists: @docs/implementation-checklists.md

## Code Navigation

Answer symbol questions with the Pyright LSP, not with text search: where something is defined, what
references or calls it, what type it returns, what a module contains. The `pyright-lsp` plugin is
enabled at project scope in `.claude/settings.json`. The same name appears in several modules here
(`check`, `refresh`, `ops`, `cmd_handler`), so a symbol answer must come from the import graph rather
than from text matches.

Reach for `grep`/`Glob` when the target is not a resolvable Python symbol — string literals, config
keys, YAML/TOML, comments, filenames, or a name that may not resolve. The LSP does not jump into
`site-packages` either, so third-party definitions still need the file read directly.

## Build & Test Commands

Instructions on how to run unit tests, as well as formatting and linting checks: @docs/building-and-testing.md

## Releasing and Publishing

Instructions on how to create new releases and publish the package to PyPI: @docs/releasing-and-publishing.md
