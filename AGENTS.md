# AGENTS.md

photree is a CLI that imports, organizes, verifies and exports iOS photo albums
as plain directories, keeping originals, edits and sidecars without a
proprietary database. Python, uv, Typer; tasks run through mise.

## Commands

- `mise run preflight-quick`: every lint and the fast tests, before each commit.
- `mise run preflight`: every lint and test CI runs, every few commits and
  before review.
- `mise tasks` lists the rest.
- `mise run fmt` after editing any file.
- Run a mise task when one does the job, and `uv run --no-sync <tool>`
  otherwise, never a bare tool.
- `mise run reference-doc` regenerates the CLI reference, the config field
  tables and the Module Overview; `mise run toc` the tables of contents.

## Guidelines

The shared iglootools guidelines govern every change. Claude Code loads them
through the `iglootools` plugin. Other agents: read `coding/general.md`,
`coding/python.md` and `coding/git.md` before any change, and the guideline
whose trigger matches the files you are changing, using
[iglootools/common's index](https://github.com/iglootools/common/blob/main/guidelines/README.md).
Read [docs/guidelines.md](docs/guidelines.md) before any change too: it holds
this project's deviations and its own rules, and links to the project's other
guidelines files.

## Where things are

[CONTRIBUTING.md](CONTRIBUTING.md) indexes every document, from setup to the
domain and the architecture. Read a document when the task reaches it, not up
front.
