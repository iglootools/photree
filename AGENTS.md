# AGENTS.md

photree is a CLI that imports, organizes, verifies and exports iOS photo albums as plain
directories, keeping originals, edits and sidecars without a proprietary database. Python, uv,
Typer; tasks run through mise.

## Commands

- `mise run check-all`: every check and test CI runs. `mise run check` is the static checks
  alone, `mise run test-unit` the fast tests; `mise tasks` lists the rest.
- Run a mise task when one does the job, and `uv run --no-sync <tool>` otherwise, never a bare
  tool: another project's virtualenv on `PATH` could stand in for this one.
- Generated documents are regenerated, never edited by hand: `mise run reference-doc` rewrites
  the CLI reference and the Module Overview, and `mise run toc` the tables of contents. `check`
  fails when one is stale.

## Guidelines

The shared iglootools guidelines govern every change. Claude Code gets them from the `iglootools`
plugin; other agents read them at https://github.com/iglootools/common/tree/main/guidelines,
starting from its README. Read [docs/guidelines.md](docs/guidelines.md) before any change: it
records where photree deviates from them, its own rules, and the checklists for specific changes.

## Where things are

Read a document when the task reaches it, not up front.
[CONTRIBUTING.md](CONTRIBUTING.md) indexes all of them.

- [docs/domain.md](docs/domain.md): galleries, albums, media sources, collections, naming
  conventions, IDs and Image Capture variants. Read before changing behaviour.
- [docs/architecture.md](docs/architecture.md): the modules, layering and execution flow. Read
  before moving code or adding a module.
- [docs/cli-conventions.md](docs/cli-conventions.md): how the command-line layer is built. Read
  before adding or changing a command.
- [docs/internals.md](docs/internals.md): the on-disk layout, metadata formats, and the refresh
  and import algorithms.
- [docs/building-and-testing.md](docs/building-and-testing.md): the test suites and the checks CI
  runs.
- [docs/config-reference.md](docs/config-reference.md) and
  [docs/cli-reference.md](docs/cli-reference.md): every config field, and every command
  (generated).
- [docs/releasing-and-publishing.md](docs/releasing-and-publishing.md): cutting a release.
