# Features

## Import from macOS Image Capture

Import photos and videos from an iOS device via macOS Image Capture into an organized album directory.

- Supports HEIC, ProRAW (DNG), JPEG, PNG images and MOV videos (including ProRes)
- Preserves all iOS variants: originals, edits (IMG_E\*), and AAE sidecars (Apple Adjustments and Edits)
- Matches selection files to Image Capture originals by numeric ID
- Builds browsable `main-img/` and `main-vid/` directories (edit if available, else original)
- Converts images to JPEG via macOS `sips` for `main-jpg/` (sharing/web-compatible)
- Deduplicates format variants with quality priority: DNG > HEIC > JPG/PNG
- Batch import across multiple albums (`image-capture-all`)
- Dry-run mode for all operations

## Album Integrity Checks

Validate that album directories are consistent and well-formed.

- Verifies `main-img/` and `main-vid/` match expected content from `orig/` and `edit/` sources
- Checks `main-jpg/` has a JPEG counterpart for every file in `main-img/`
- Detects missing, extra, and wrong-source files
- File comparison via size and optional SHA-256 checksum
- Hardlink/symlink-aware: skips checksum when link integrity is verified
- Sidecar validation: detects orphan and missing AAE files
- Detects miscategorized files (edits in orig dirs or vice versa)
- Detects duplicate image numbers within the same prefix category
- Batch checking across multiple albums (`check-all`)
- Troubleshooting suggestions with actionable fix commands

## Album Optimization

Reduce disk usage by replacing file copies with links.

- Rebuilds `main-img/` and `main-vid/` as hardlinks (default), symlinks, or copies
- Does not touch `main-jpg/` (JPEG conversions cannot be linked)
- Runs integrity checks before optimizing (unless `--no-check`)
- Batch optimization across multiple albums (`optimize-all`)

## Album Fixes

Repair and maintain iOS album consistency with targeted fix commands.

- **`--refresh-combined`**: Rebuild all main directories from orig/edit sources
- **`--refresh-jpeg`**: Re-convert `main-jpg/` from `main-img/`
- **`--rm-upstream`**: Propagate deletions from browsable dirs to upstream dirs (useful after curating photos in `main-jpg/`)
- **`--rm-orphan`**: Remove edited and main files with no corresponding original
- **`--rm-orphan-sidecar`**: Remove AAE sidecar files with no matching media file
- **`--prefer-higher-quality-when-dups`**: Remove lower-quality duplicates (DNG > HEIC > JPG/PNG)
- **`--rm-miscategorized`** / **`--rm-miscategorized-safe`** / **`--mv-miscategorized`**: Fix files in the wrong directory
- All fixes support dry-run mode and batch operation (`fix-ios-all`)

## Export to Shared Directories

Export albums to external volumes or cloud sync folders.

- **Profiles**: Named export configurations in TOML config (share directory, layout, link mode)
- **Album share layouts**:
  - `main-only`: Export `main-img/`, `main-jpg/`, `main-vid/` (stripped `main-` prefix)
  - `main-jpg-only`: Export `main-jpg/` and `main-vid/` only (most compatible formats)
  - `full-managed`: Export orig/edit/main-jpg, recreate main-img and main-vid with links
  - `full`: Full-managed plus any unmanaged files
- **Share directory layouts**:
  - `flat`: Albums exported directly under share directory
  - `albums`: Albums organized by year (`<YYYY>/<album-name>`), parsed from album name (`YYYY-MM-DD - Title`)
- Sentinel file (`.photree-share`) required to prevent accidental exports to wrong directories
- Validation: `albums` share layout requires `album-layout=full`
- Batch export across multiple albums (`album-all`)

## Configuration

TOML-based configuration with platform-aware search paths.

- Search order: `$XDG_CONFIG_HOME` > platform user config > platform site config
- Importer config: Image Capture source directory
- Exporter profiles: multiple named profiles with share-dir, share-layout, album-layout, link-mode
- CLI flags override profile values; profiles override defaults

## Supported Formats

| Format | Type | Notes |
|--------|------|-------|
| HEIC | Image | Native iPhone format (High Efficiency) |
| DNG | Image | Apple ProRAW |
| JPEG/JPG | Image | Most Compatible mode, front camera, ProRAW edits |
| PNG | Image | Screenshots |
| MOV | Video | Standard and ProRes codec |
| AAE | Sidecar | Apple Adjustments and Edits |
