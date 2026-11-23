# CLI Conventions

How photree's command-line layer is built: the command hierarchy, option and
output conventions, progress and error reporting, and where CLI code ends and
the domain begins. [guidelines.md](../guidelines.md#area-conventions) lists the
paths these conventions govern; read this before changing any of them, or adding
a command anywhere.

<!-- toc -->
**On this page**

- [Framework](#framework)
- [Command Hierarchy](#command-hierarchy)
- [Standard Operations](#standard-operations)
- [Option Conventions](#option-conventions)
- [Progress Indicators](#progress-indicators)
- [Icons and Result Formatting](#icons-and-result-formatting)
- [Error Handling and Exit Codes](#error-handling-and-exit-codes)
- [Declare system dependencies in `sysdeps`, and check them before any change](#declare-system-dependencies-in-sysdeps-and-check-them-before-any-change)
- [Suggest the next command in single quotes, with its flags](#suggest-the-next-command-in-single-quotes-with-its-flags)
- [CSV Output](#csv-output)
- [Resolve the gallery in the CLI layer, and pass the value in](#resolve-the-gallery-in-the-cli-layer-and-pass-the-value-in)
- [Batch Operation Architecture](#batch-operation-architecture)
- [Validation Levels](#validation-levels)
<!-- tocstop -->

## Framework

The CLI is built on Typer and prints through Rich, as
[python.md › Print through Rich](https://github.com/iglootools/common/blob/main/guidelines/coding/python.md#print-through-rich-escaping-interpolated-text-exactly-once)
describes. photree's consoles:

- `console` (`clihelpers/console.py`) — standard output
- `err_console` — stderr for errors and troubleshooting
- `typer.echo()` — simple unformatted text (section headers, plain messages)

## Command Hierarchy

Commands are organized in three scopes (see `docs/usage.md`):

| Scope | Pattern | Resolution | Example |
|-------|---------|------------|---------|
| **Single item** | `album <op>`, `collection <op>` | `--album-dir`/`--collection-dir` (default: `.`) | `album check` |
| **Batch** | `albums <op>`, `collections <op>` | `--dir` (scan) or `--album-dir`/`--collection-dir` (repeatable) | `albums check` |
| **Gallery** | `gallery <op>` | `--gallery-dir` or resolved from cwd via `.photree/gallery.yaml` | `gallery check` |

Gallery commands are the recommended entry point. Batch commands don't
require a gallery. Single-item commands operate on one directory.

**Nested sub-commands**: Use `typer.Typer` sub-apps for grouping
(e.g., `gallery metadata set`, `collection metadata set`).

## Standard Operations

Most entity types support the same set of operations:

| Operation | Purpose | Available at |
|-----------|---------|-------------|
| `init` | Create metadata | album, collection, gallery |
| `show` | Display metadata | album, collection, gallery |
| `check` | Validate integrity | album, albums, collection, collections, gallery |
| `refresh` | Update derived metadata | album, albums, gallery |
| `import` | Import content | album, albums, collection, collections, gallery |
| `fix` | Repair issues | album, albums, gallery |
| `list` / `list-*` | List items with optional CSV | albums, gallery |
| `stats` | Aggregated disk usage and content statistics | album, albums, gallery |
| `metadata set` | Update settings after init | collection, gallery |

## Option Conventions

- **Directory options**: `--album-dir -a`, `--collection-dir -c`,
  `--gallery-dir -g`, `--dir -d` (scan base)
- **Mutually exclusive options**: Check in the command body and
  `raise usage_error(...)` (`clihelpers/usage.py`), which prints to stderr and
  exits 2, like any other [usage error](#error-handling-and-exit-codes)
- **Shared options**: the `<NAME>_OPTION` constants
  [python.md](https://github.com/iglootools/common/blob/main/guidelines/coding/python.md#start-a-functions-name-with-the-verb-that-says-what-the-caller-gets)
  asks for live in `clihelpers/options.py` (e.g., `DRY_RUN_OPTION`,
  `CHECKSUM_OPTION`, `LINK_MODE_OPTION`)
- **Dry run**: every command that changes data or runs long takes
  `--dry-run -n` (`DRY_RUN_OPTION`), and skips every filesystem mutation. Its
  output carries the label `[dry-run]`, spelled exactly so, from
  `common.formatting.format_dry_run`:
  - a line describing one action starts with it, and keeps its "Would …"
    phrasing: `[dry-run] Would generate album ID.`
  - a block (a section header, a batch tally, a result summary) carries it
    once, at the start of its header or summary line, never on every row:
    `[dry-run] 3 album(s) would be refreshed, 0 failed.`
  - a labelled line says what would happen, never what was done ("Done.",
    "Removed"): the formatter takes `dry_run` and words it as hypothetical
  - the label is a Rich tag: pass `markup=True` when the line is printed
    with `console.print`, so Rich does not drop it

## Progress Indicators

All progress bars are in `clihelpers/progress.py` and support context
managers (`with` syntax). Choose based on the operation:

| Class | When to use | Output |
|-------|------------|--------|
| `SilentProgressBar` | Per-file operations where individual results are not needed | Spinner + count |
| `FileProgressBar` | Per-file operations where each file gets a result line | `✓`/`✗` per file |
| `StageProgressBar` | Multi-stage sequential operations (import, refresh) | `✓` per stage |
| `BatchProgressBar` | Per-item batch operations (albums, collections) | `✓`/`✗`/`⚠` per item |

Usage pattern:

```python
with BatchProgressBar(
    total=len(items), description="Checking", done_description="check"
) as progress:
    for item in items:
        progress.on_start(item.name)
        progress.on_end(item.name, success=True)
```

For gallery-scoped scanning (resolving album list), use a transient Rich spinner
via `resolve_check_batch_albums` in `albums/batchcli/resolution.py`.

## Icons and Result Formatting

Defined in `common/formatting.py`:

- `✓` (green) — `CHECK` — success
- `✗` (red) — `CROSS` — failure
- `✓` (orange) — `WARNING` — success with warnings

Progress bar labels during operation:

- "Checking..." during the operation
- "✓ check" for a successfully completed step
- "✗ check" for a failed step

## Error Handling and Exit Codes

photree follows
[general.md › Exit with 0, 1 or 2](https://github.com/iglootools/common/blob/main/guidelines/coding/general.md#exit-with-0-1-or-2):

| Exit code | Meaning | When |
|-----------|---------|------|
| 0 | Success | Normal completion, or "nothing to do" (no albums found) |
| 1 | The operation or a check failed | Validation failures, check failures, missing metadata, resolution errors, missing system tools |
| 2 | Usage or configuration error | Invalid config file; mutually exclusive options, a command given nothing to do (no fields, no files, no fix selected), an option value photree validates itself |

A usage error is about the invocation alone: the same command line fails
whatever is on disk. An error that depends on the gallery, an album or a file
exits 1, even when it names an option.

**Error output pattern**, photree's form of
[general.md › Provide preflight checks and troubleshooting commands](https://github.com/iglootools/common/blob/main/guidelines/coding/general.md#provide-preflight-checks-and-troubleshooting-commands):

1. Describe the problem via `err_console.print()`
2. Suggest a fix: `"Run 'photree <command>' to <fix>."`
3. `raise typer.Exit(code=1)`

A usage error takes steps 1 and 3 in one call,
`raise usage_error("<problem>\n<fix>")` from `clihelpers/usage.py`, which exits
2 instead of 1.

**A batch reports every failure**, as
[general.md › Report every failure in a batch, apart from the skips](https://github.com/iglootools/common/blob/main/guidelines/coding/general.md#report-every-failure-in-a-batch-apart-from-the-skips)
describes, and exits 1 when any item failed.

## Declare system dependencies in `sysdeps`, and check them before any change

photree's form of
[general.md › Provide preflight checks and troubleshooting commands](https://github.com/iglootools/common/blob/main/guidelines/coding/general.md#provide-preflight-checks-and-troubleshooting-commands):
anything that shells out to `sips` or `exiftool` resolves its requirement
through `clihelpers/sysdeps.py` (`import_deps()`, `refresh_deps()`,
`EXIF_DEPS`, `FACE_DETECTION_DEPS`) and checks it **before** any filesystem
mutation.

**Why:** with every requirement declared in that one module, never inline at
the call site, adding a binary cannot leave a caller behind.

- Add the binary itself to `common/sysdeps.py`, with its purpose and install
  hint, never as a bare `shutil.which`.
- Keep the command/requirement table in
  [internals.md](../internals.md#system-dependencies) in sync.

Two call styles, matching what the command does:

- **Gate** — `require_system_deps(...)` prints the check lines and exits on a
  miss. The default.
- **Fold into a wider report** — the import family probes with
  `check_system_dependencies(...)` and passes the statuses into
  `run_preflight`, so a broken setup reports the missing binary *and* the
  staging/Image Capture problems in one pass. `import-check` is a pure
  diagnostic and depends on this.

Probing PATH is the CLI layer's job, as ambient state is under
[general.md › Testability](https://github.com/iglootools/common/blob/main/guidelines/coding/general.md#testability).
Library functions take the resolved statuses as a parameter; output layers
render them with `common/sysdeps_output.py`, never by importing `clihelpers`
(only CLI modules — `*/cli/`, `albums/batchcli/`, `clihelpers/` — may import
`clihelpers`; an import-linter contract enforces this).

## Suggest the next command in single quotes, with its flags

Commands reference each other in error messages, as
[general.md › Make the CLI navigable from its own output](https://github.com/iglootools/common/blob/main/guidelines/coding/general.md#make-the-cli-navigable-from-its-own-output)
asks:

```text
Albums with missing IDs found:
  2024-07-14 - Trip
Run 'photree gallery fix --id' to generate missing album IDs.
```

Put single quotes around the command, include the flags it needs, and print
paths with `display_path`.

**Why:** the user copies the suggestion as-is.

## CSV Output

Commands with `--format csv` follow this pattern:

- `--format` option: `text` (default) or `csv`, declared with the shared
  `OUTPUT_FORMAT_OPTION` (an `OutputFormat` enum, so an unknown value is
  rejected rather than silently rendered as text)
- `--output -o` option (`OUTPUT_FILE_OPTION`): write to file instead of
  stdout, for every format
- CSV always includes a header row
- Write to stdout or file, close file in `finally`
- When `--format csv`, suppress non-CSV output (e.g., "No albums found"
  goes to stderr)

## Resolve the gallery in the CLI layer, and pass the value in

Finding the gallery (walking up to `.photree/gallery.yaml`) is ambient state,
like probing PATH, so it is the CLI layer's job too. Core functions take the
resolved value — e.g. `link_mode: LinkMode` on `refresh_album_derived_data`
and `run_album_check` — and the CLI (or `albums/batchcli/`) calls
`foundation.gallery_metadata.resolve_link_mode`. A batch handler whose albums
may live in different galleries takes a resolver instead
(`link_mode_for=...` on `batch_refresh`, `batch_check` and the album batch
import), still supplied by the CLI.

## Batch Operation Architecture

Batch operations follow a three-layer pattern:

1. **CLI command** (`albums/cli/*_cmd.py`, `gallery/cli/*_cmd.py`) — argument
   parsing, delegates to the shared wrapper
2. **Batch wrapper** (`albums/batchcli/<operation>.py`) — progress bars,
   output formatting, `typer.Exit`. Shared between `albums` and `gallery`
   commands, so it is a sibling of `albums/cli/` rather than part of it: the
   `gallery` CLI never imports the `albums` command group
3. **Command handler** (`albums/cmd_handler/*.py`) — pure business logic with
   callbacks, no `typer`/`rich`/`clihelpers`. It stays in `albums/` because
   it is the domain of "a set of albums" (alongside `albums/index.py` and
   `albums/renamer.py`); the batch wrappers and `gallery` depend on it, not
   the other way round

Album resolution helpers live in `albums/batchcli/resolution.py`:

- `resolve_check_batch_albums` — for check/list/refresh commands
- `resolve_batch_albums` — for archive-based commands (fix-ios)
- `resolve_init_batch_albums` — for init commands
- `resolve_gallery_albums` — for every `gallery` command that processes the
  gallery's albums: it scans `<gallery>/albums` only, through
  `discover_gallery_albums`, which the domain code also uses

## Validation Levels

Two levels of album validation, used in different contexts:

- **Light check** (naming + cross-album collisions): fast, no media I/O.
  Used as a gate before `gallery refresh` and `gallery import`.
- **Full check** (structure, integrity, EXIF, cross-album): used by
  `check` commands. Supports `--no-checksum` and
  `--no-check-exif-date-match` to skip expensive operations.

See
[internals.md — Album Validation Levels](../internals.md#album-validation-levels).
