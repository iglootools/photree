# Usage

## Installation

See [Installation instructions](./installation.md)

## Configuration

photree uses a TOML config file for default settings. The config file is optional — all values
can be overridden via CLI flags.

### Config file location

photree searches for `config.toml` in these directories, in order:

1. `$XDG_CONFIG_HOME/photree/config.toml` (typically `~/.config/photree/config.toml`)
2. Platform user config dir (macOS: `~/Library/Application Support/photree/config.toml`)
3. Platform site config dir (macOS: `/Library/Application Support/photree/config.toml`)

The first file found is used. You can also pass `--config <path>` to any command to use a specific file.

### Config file format

```toml
[importer]
# Directory where macOS Image Capture saves imported files
# \u2019 is the Unicode right single quotation mark (') used by macOS in device names.
# A regular ASCII apostrophe (') won't match the actual directory name.
image-capture-dir = "~/Pictures/Sami Dalouche\u2019s iPhone"

[exporter.profiles.mega]
share-dir = "~/MEGAsync/to-share"
share-layout = "flat"
album-layout = "main"
link-mode = "hardlink"
```

## Gallery

Most operations (check, optimize, fix, stats, export) are available in three flavours:

- **`photree gallery <op>`** — operates on all albums within an initialized gallery
  (resolved from cwd or `--gallery-dir`). This is the recommended way to manage albums.
- **`photree album <op>`** — operates on a single album directory.
- **`photree albums <op>`** — batch variant that scans a directory (`--dir`) or accepts
  explicit album directories (`--album-dir`, repeatable). Does not require a gallery.

This document covers the `gallery` commands and the Image Capture import workflow.
See the [CLI Reference](./cli-reference.md) for the full `album` and `albums` variants.

### Initialize Gallery

Initializes gallery-level metadata in the current (or specified) directory.
Creates a `.photree/gallery.yaml` file that applies to all albums underneath.

```bash
# Initialize with default settings (hardlink)
photree gallery init

# Initialize with symlink mode
photree gallery init --link-mode symlink

# Initialize a specific directory
photree gallery init -d ~/Pictures/albums
```

The `link-mode` setting in `gallery.yaml` is used as the default for `optimize`,
`fix-ios`, and other commands that accept `--link-mode`. An explicit `--link-mode`
CLI flag always overrides the gallery default.

See [internals.md](./internals.md) for the gallery metadata format and resolution rules.

### Import Images from Image Capture

Organizes files imported by macOS Image Capture into an album directory structure.
See [internals.md](./internals.md) for the Image Capture file structure and album layout.

**Workflow:**

1. Create the album directory
2. Import all pictures using macOS Image Capture (output: `~/Pictures/<Device Name>/`)
3. Tell photree which photos to import (your "selection")
4. Run `photree album import` from the album directory

**Specifying the selection:**

The selection is just a list of filenames — photree matches them by image
number against the Image Capture directory. The file contents don't matter,
only the names. Two mechanisms are available:

- **`to-import/` directory** — export from Apple Photos into this subfolder.
  This is the most common workflow: Photos is convenient for reviewing and
  curating a selection, and the exported files provide the filename list.
- **`to-import.csv`** — a one-column file (no header) with one filename per
  row (e.g. `IMG_0410.HEIC`). Useful when the selection is generated
  programmatically (a script, AppleScript, an LLM, a phone app, etc.).

In practice you'd use one or the other. Both are supported simultaneously
(entries are merged and deduplicated), but there's rarely a reason to mix them.

See [internals.md — Selection Mechanism](./internals.md#selection-mechanism)
for the full details.

```bash
# Import image capture pictures for a single album
photree album import -a "2024-06-15 - Summer Vacation"

# Import image capture pictures for all albums under a directory
photree albums import -d ~/Pictures/albums

# Dry run to preview what would happen
photree album import -n
```

The source directory (where Image Capture saved the files) is resolved in this order:

1. `--source` / `-s` flag (explicit)
2. `importer.image-capture-dir` from the config file
3. Default: `~/Pictures/iPhone`

### Import Albums into Gallery

Imports an existing album directory into the gallery's `albums/YYYY/` structure.
Automatically generates a missing album ID, refreshes stale JPEGs, optimizes
links, and runs integrity checks.

```bash
# Import a single album into the gallery (resolved from cwd)
photree gallery import -a "2024-06-15 - Summer Vacation"

# Import into a specific gallery
photree gallery import -a "2024-06-15 - Summer Vacation" -g ~/Pictures/gallery

# Batch import multiple albums
photree gallery import-all -d ~/Pictures/incoming-albums
photree gallery import-all -a album1 -a album2 -g ~/Pictures/gallery

# Dry run
photree gallery import -a "2024-06-15 - Summer Vacation" -n
```

The gallery directory is resolved in this order:
1. `--gallery-dir` / `-g` flag (explicit)
2. Walk up from cwd looking for `.photree/gallery.yaml`

The command refuses to import if the target path already exists in the gallery.

### Check Albums

Validates all albums in the gallery (structure, integrity, naming conventions, EXIF dates).

```bash
# Check all gallery albums (resolved from cwd)
photree gallery check

# Check a specific gallery
photree gallery check -d ~/Pictures/gallery

# Disable checksum verification for faster checks
photree gallery check --no-checksum

# Treat warnings as errors
photree gallery check -W
```

### Optimize Albums

Reduces disk usage by replacing file copies with links for all iOS albums in the gallery.

```bash
# Optimize all gallery albums (uses gallery link-mode default)
photree gallery optimize

# Optimize with symlinks
photree gallery optimize --link-mode symlink

# Skip integrity checks before optimizing
photree gallery optimize --no-check

# Dry run
photree gallery optimize -n
```

### Export Albums

Exports all gallery albums to a shared directory (cloud sync folders, external volumes).

```bash
# Export using a named profile
photree gallery export -p mega

# Export with explicit flags
photree gallery export --share-dir ~/MEGAsync/to-share --album-layout main-jpg

# Dry run
photree gallery export -p mega -n
```

**Album layouts:**
- `main-jpg` (default): exports `main-jpg/` and `main-vid/` (most compatible formats)
- `main`: exports `main-img/`, `main-jpg/`, `main-vid/`
- `all`: exports archival directories (orig/edit) and main-jpg, recreates main dirs with links

**Share directory layouts:**
- `flat`: albums placed directly under the share directory
- `albums`: albums organized by year (`2024/2024-06-15 - Summer Vacation/`)

The share directory must contain a `.photree-share` sentinel file to prevent accidental exports.

See [CLI Reference](./cli-reference.md) for full option details.
