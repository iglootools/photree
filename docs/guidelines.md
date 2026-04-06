# Project-Specific Guidelines

A set of [implementation checklists](./implementation-checklists.md) serve as a reminder for things to check when implementing new features or making changes to the codebase.

For general coding, Python, and tooling guidelines, see the [common guidelines](https://github.com/iglootools/common-guidelines).

## Coding
- **Naming Conventions**
  - `kebab-case` for CLI commands
- **Printing/Logging**
  - Print/Log relative paths when paths relative to the current working directory, using `display_path`

## CLI UX

### Framework

Use `typer` for CLI implementation. Rich console instances for formatted
output:
- `console` (`clihelpers/console.py`) — standard output
- `err_console` — stderr for errors and troubleshooting
- `typer.echo()` — simple unformatted text (section headers, plain messages)

### Command Hierarchy

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

### Standard Operations

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
| `metadata set` | Update settings after init | collection, gallery |

### Option Conventions

- **Directory options**: `--album-dir -a`, `--collection-dir -c`,
  `--gallery-dir -g`, `--dir -d` (scan base)
- **Mutually exclusive options**: Check in the command body, print error
  to stderr, exit with code 1
- **Shared options**: Define as `Annotated` types in `clihelpers/options.py`
  (e.g., `DRY_RUN_OPTION`, `CHECKSUM_OPTION`, `LINK_MODE_OPTION`)
- **Dry run**: `--dry-run -n`. Operations skip filesystem mutations.
  Output includes `[dry-run]` or `[dry run]` prefix. Summary shows
  "would be" phrasing

### Progress Indicators

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
with BatchProgressBar(total=len(items), description="Checking", done_description="check") as progress:
    for item in items:
        progress.on_start(item.name)
        progress.on_end(item.name, success=True)
```

For gallery-scoped scanning (resolving album list), use a transient
Rich spinner via `resolve_check_batch_albums` in `albums/cli/ops.py`.

### Icons and Result Formatting

Defined in `common/formatting.py`:
- `✓` (green) — `CHECK` — success
- `✗` (red) — `CROSS` — failure
- `✓` (orange) — `WARNING` — success with warnings

Progress bar labels during operation:
- "Checking..." during the operation
- "✓ check" for a successfully completed step
- "✗ check" for a failed step

### Error Handling and Exit Codes

| Exit code | Meaning | When |
|-----------|---------|------|
| 0 | Success | Normal completion, or "nothing to do" (no albums found) |
| 1 | Error | Validation failures, check failures, missing metadata, resolution errors |
| 2 | Configuration error | Invalid config file |

**Error output pattern**:
1. Describe the problem via `err_console.print()`
2. Suggest a fix: `"Run 'photree <command>' to <fix>."`
3. `raise typer.Exit(code=1)`

### Discoverability

Commands reference each other in error messages so the user can navigate
the tool by following its output:

```
Albums with missing IDs found:
  2024-07-14 - Trip
Run 'photree gallery fix --id' to generate missing album IDs.
```

Use single quotes around commands, include necessary flags, and use
`display_path` for paths so they can be copy-pasted.

### CSV Output

Commands with `--format csv` follow this pattern:
- `--format` option: `text` (default) or `csv`
- `--output -o` option: write to file instead of stdout
- CSV always includes a header row
- Write to stdout or file, close file in `finally`
- When `--format csv`, suppress non-CSV output (e.g., "No albums found"
  goes to stderr)

### Batch Operation Architecture

Batch operations follow a three-layer pattern:

1. **CLI command** (`*_cmd.py`) — argument parsing, delegates to shared wrapper
2. **Batch wrapper** (`batch_ops.py`) — progress bars, output formatting,
   `typer.Exit`. Shared between `albums` and `gallery` commands
3. **Command handler** (`cmd_handler/*.py`) — pure business logic with callbacks

Album resolution helpers live in `albums/cli/ops.py` (mirroring
`gallery/cli/ops.py`):
- `resolve_check_batch_albums` — for check/list/refresh commands
- `resolve_batch_albums` — for archive-based commands (optimize, fix-ios)
- `resolve_init_batch_albums` — for init commands

### Validation Levels

Two levels of album validation, used in different contexts:

- **Light check** (naming + cross-album collisions): fast, no media I/O.
  Used as a gate before `gallery refresh` and `gallery import`.
- **Full check** (structure, integrity, EXIF, cross-album): used by
  `check` commands. Supports `--no-checksum` and
  `--no-check-exif-date-match` to skip expensive operations.

See [internals.md — Album Validation Levels](./internals.md#album-validation-levels).