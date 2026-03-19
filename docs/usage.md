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
album-layout = "main-jpg-only"
link-mode = "hardlink"

[exporter.profiles.rocketnano2tb-albums]
share-dir = "/Volumes/rocketnano2tb/photos/albums"
share-layout = "albums"
album-layout = "full"
link-mode = "symlink"
```

## Import

### `photree import image-capture`

Organizes files imported by macOS Image Capture into an album directory structure.
See [internals.md](./internals.md) for the Image Capture file structure and album layout.

**Workflow:**

1. Create the album directory with a `to-import/` subfolder
2. Import all pictures using macOS Image Capture (output: `~/Pictures/<Device Name>/`)
3. Import all pictures using Apple Photos, curate your selection, then export to `to-import/`
4. Run `photree import image-capture` from the album directory

```bash
# Import a single album
photree import image-capture -a "2024-06-15 - Summer Vacation"

# Import all albums under a directory
photree import image-capture-all -d ~/Pictures/albums

# Dry run to preview what would happen
photree import image-capture -n
```

The source directory (where Image Capture saved the files) is resolved in this order:

1. `--source` / `-s` flag (explicit)
2. `importer.image-capture-dir` from the config file
3. Default: `~/Pictures/iPhone`

## Check

### `photree album check`

Validates album directory structure and file integrity.

```bash
# Check a single album
photree album check -a "2024-06-15 - Summer Vacation"

# Check all albums under a directory
photree album check-all -d ~/Pictures/albums

# Disable checksum verification for faster checks
photree album check --no-checksum
```

Checks include:
- `main-img/` and `main-vid/` consistency with orig/edit sources
- `main-jpg/` has a JPEG counterpart for every main-img file
- Sidecar (AAE) completeness and orphan detection
- Miscategorized files and duplicate image numbers
- Actionable troubleshooting suggestions when issues are found

## Optimize

### `photree album optimize`

Reduces disk usage by replacing file copies in `main-img/` and `main-vid/` with links.

```bash
# Optimize a single album (hardlinks by default)
photree album optimize -a "2024-06-15 - Summer Vacation"

# Use symlinks instead
photree album optimize --link-mode symlink

# Optimize all albums
photree album optimize-all -d ~/Pictures/albums
```

Runs integrity checks first and refuses to optimize if errors are found (disable with `--no-check`).

## Fix

### `photree album fix-ios`

Targeted fixes for iOS album issues. Each fix is an explicit flag — at least one must be specified.
All fixes support `--dry-run` (`-n`) to preview changes.

```bash
# Rebuild main directories from sources
photree album fix-ios --refresh-combined -n

# Propagate deletions from main-jpg to upstream dirs
photree album fix-ios --rm-upstream -n

# Remove orphan files
photree album fix-ios --rm-orphan --rm-orphan-sidecar -n

# Fix miscategorized files (move to correct directory)
photree album fix-ios --mv-miscategorized -n

# Apply to all albums
photree album fix-ios-all -d ~/Pictures/albums --rm-orphan -n
```

## Export

### `photree export album`

Exports albums to shared directories (cloud sync folders, external volumes).

```bash
# Export using a named profile
photree export album -a "2024-06-15 - Summer Vacation" -p mega

# Export with explicit flags
photree export album -a "2024-06-15 - Summer Vacation" \
  --share-dir ~/MEGAsync/to-share \
  --album-layout main-jpg-only

# Batch export all albums
photree export album-all -d ~/Pictures/albums -p mega
```

**Album share layouts:**
- `main-only` (default): exports `main-img/`, `main-jpg/`, `main-vid/`
- `main-jpg-only`: exports `main-jpg/` and `main-vid/` only (most compatible)
- `full-managed`: exports everything, recreates main dirs with links
- `full`: full-managed plus any unmanaged files

**Share directory layouts:**
- `flat`: albums placed directly under the share directory
- `albums`: albums organized by year (`2024/2024-06-15 - Summer Vacation/`)

The share directory must contain a `.photree-share` sentinel file to prevent accidental exports.

See [CLI Reference](./cli-reference.md) for full option details.
