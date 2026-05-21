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

## Media Sources

Albums support multiple **media sources** — named sources of photos from different people or devices.

- **iOS media sources** (`ios-{name}/`): imported via Image Capture, with archival and browsable directories
- **Standard media sources** (`std-{name}/`, `{name}-img/`, `{name}-vid/`): photos from non-iOS sources (other cameras, shared files)
- The default media source is `main`; additional media sources are detected automatically
- Each media source gets its own set of browsable directories (`{name}-img/`, `{name}-vid/`, `{name}-jpg/`)
- JPEG conversion applies to all media sources; iOS-specific checks and fixes apply only to iOS media sources

## Album Naming Conventions

Enforce and validate a structured naming convention for album directories.

- Target format: `DATE - [PART - ] [Series - ] Title [@ Location] [tags]`
- Dates: `YYYY-MM-DD`, `YYYY-MM`, `YYYY`, or ranges (`YYYY-MM-DD--YYYY-MM-DD`)
- Optional part number (`01`, `02`, ...) for multi-part albums
- Optional series prefix for grouping related albums
- Optional `[private]` tag
- Optional `@ Location` suffix
- Validates canonical spacing, allowed tags, and name length
- Cross-album date collision detection (warns when unrelated albums share the same date)
- EXIF timestamp validation: checks that media file timestamps match the album date (optional, requires exiftool). Timestamps are cached in `.photree/cache/exif/` during `album refresh` to speed up subsequent checks. Use `--refresh-exif-cache` to force a cache rebuild.

## Album Integrity Checks

Validate that album directories are consistent and well-formed.

- Verifies `{name}-img/` and `{name}-vid/` match expected content from `orig/` and `edit/` sources
- Checks `{name}-jpg/` has a JPEG counterpart for every file in `{name}-img/`
- Detects missing, extra, and wrong-source files
- File comparison via size and optional SHA-256 checksum
- Hardlink/symlink-aware: skips checksum when link integrity is verified
- Sidecar validation: detects orphan and missing AAE files
- Detects miscategorized files (edits in orig dirs or vice versa)
- Detects duplicate image numbers within the same prefix category
- Troubleshooting suggestions with actionable fix commands

## Album Optimization

Reduce disk usage by replacing file copies with links.

- Rebuilds `{name}-img/` and `{name}-vid/` as hardlinks (default), symlinks, or copies
- Does not touch `{name}-jpg/` (JPEG conversions cannot be linked)
- Runs integrity checks before optimizing (unless `--no-check`)
- Dry-run mode for all operations

## Album Fixes

Repair and maintain iOS album consistency with targeted fix commands.

- **`--rm-upstream`**: Propagate deletions from browsable dirs to upstream dirs (useful after curating photos in `main-jpg/`)
- **`--rm-orphan`**: Remove edited and main files with no corresponding original
- **`--rm-orphan-sidecar`**: Remove AAE sidecar files with no matching media file
- **`--prefer-higher-quality-when-dups`**: Remove lower-quality duplicates (DNG > HEIC > JPG/PNG)
- **`--rm-miscategorized`** / **`--rm-miscategorized-safe`** / **`--mv-miscategorized`**: Fix files in the wrong directory
- All fixes support dry-run mode

## Gallery Commands

Batch operations across multiple albums under a directory.

- **`gallery list-albums`**: List all discovered albums with parsed metadata (date, title, series, location, media sources); supports text and CSV output formats
- **`gallery check`**: Check all albums (integrity, naming conventions, EXIF timestamps, cross-album date collisions)
- **`gallery fix`**: Apply fixes to all albums
- **`gallery fix-ios`**: Apply iOS-specific fixes to all iOS albums
- **`gallery rename-from-csv`**: Rename albums by diffing current vs desired CSV files (exported from `list-albums --format csv`); only title and location may be changed
- **`gallery export`**: Batch export to a shared directory
- All gallery commands accept `--dir` (scan recursively) or `--album-dir` (explicit list)

## Collections

Collections group albums, media items, and other collections for organizing
content beyond the flat album structure.

- **Manual collections** (`members: manual`): members managed explicitly via `collection import`
- **Smart collections** (`members: smart`): members auto-populated by date range during `gallery refresh`
- **Implicit collections** (`lifecycle: implicit`): auto-detected from album series (contiguous albums sharing the same series prefix). Created, renamed, and deleted automatically by `gallery refresh`.
- **Explicit collections** (`lifecycle: explicit`): created and managed by the user
- **Strategies**: `import` (manual), `date-range` (smart explicit), `album-series` (smart implicit), `chapter` (smart explicit, no date overlap with other chapters)
- **Private tag virality**: non-private collections cannot contain private members; private smart collections only include private members
- CLI commands: `collection init`, `collection show`, `collection check`, `collection import`, `collection metadata set`

## Face Detection and Clustering

Detect faces in album photos and cluster them by identity across the gallery.

- **Album-level face detection**: [InsightFace](https://github.com/deepinsight/insightface) (`buffalo_l` model) extracts face bounding boxes, landmarks, and 512-dimensional embedding vectors from each image
- **Thumbnail caching**: resized 640px JPEGs generated via `sips` and cached in `.photree/cache/faces/` for fast re-detection
- **Gallery-level clustering**: [FAISS](https://github.com/facebookresearch/faiss) `IndexFlatIP` for similarity search + agglomerative clustering (cosine distance, average linkage) groups faces by identity
- **Incremental updates**: only new/changed images are re-processed; gallery clustering runs incrementally for additions, full rebuild for removals
- **Stable cluster UUIDs**: medoid matching preserves cluster identity across full re-clusters
- **CoreML acceleration**: uses Neural Engine on M-series Macs for face detection inference
- **Parallel thumbnail generation**: `sips` conversions run in parallel via `ThreadPoolExecutor`
- **Gallery config**: `faces-enabled` (default: true) and `face-cluster-threshold` (default: 0.45) in `gallery.yaml`
- **Gallery import integration**: `gallery import` and `gallery import-all` automatically run face detection per album and gallery-wide clustering when `faces-enabled: true`
- CLI commands: `album detect-faces`, `albums detect-faces`, `gallery cluster-faces`
- Refresh flags: `--redetect-faces` (re-run detection, reuse thumbnails), `--refresh-face-thumbs` (regenerate thumbnails from originals)

## Album and Gallery Statistics

Analyze disk usage, file counts, and content breakdowns.

- **`album stats`**: Show statistics for a single album
- **`gallery stats`**: Show aggregated statistics across all albums, with per-year breakdown
- **Size columns**: On-Disk (inode-deduplicated), Size (apparent), Archive (`ios-{name}/`), Browsable (`{name}-img/`, `{name}-vid/`), Derived (`{name}-jpg/`), Cache (`.photree/cache/`); Size = Archive + Browsable + Derived + Cache
- **Content breakdown**: By media type (images, videos, sidecars), by file format (extension), and by media source
- **Media source analysis**: Per-source file counts, archive/browsable/derived sizes, unique picture and video counts
- **Year breakdown** (gallery): Albums, pictures, videos, and sizes grouped by year
- **Unique media counting**: iOS pictures deduplicated by image number (originals), std pictures by filename stem
- **Legend**: Printed at the end of output explaining each metric
- **Limitation**: Albums spanning multiple years (date ranges) are attributed to the start year only

## Export to Shared Directories

Export albums to external volumes or cloud sync folders.

- **Profiles**: Named export configurations in TOML config (share directory, layout, link mode)
- **Album share layouts**:
  - `main-jpg` (default): Export `main-jpg/` and `main-vid/` (most compatible formats)
  - `main`: Export `main-img/`, `main-jpg/`, `main-vid/`
  - `all`: Export archival directories (orig/edit) and main-jpg, recreate main-img and main-vid with links
- **Share directory layouts**:
  - `flat`: Albums exported directly under share directory
  - `albums`: Albums organized by year (`<YYYY>/<album-name>`), parsed from album name (`YYYY-MM-DD - Title`)
- Sentinel file (`.photree-share`) required to prevent accidental exports to wrong directories
- Validation: `albums` share layout requires `album-layout=all`
- Batch export via `gallery export`

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
