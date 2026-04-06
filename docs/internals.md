# Internals

This document describes the internal structures and conventions that photree uses under the hood.
It is useful for understanding how files are organized on disk, how iOS Image Capture exports work,
and how photree maps those conventions into its album layout.

## Image Capture File Structure

macOS Image Capture exports files from iOS devices in the following structure:

**HEIC photos** (Camera Capture set to "High Efficiency"):
- `IMG_0410.HEIC` — original file with depth of field metadata, etc
- `IMG_0410.AAE` — Apple Adjustments and Edits sidecar (background defocus, filters, etc). Generally provided, but not guaranteed (e.g. no edits applied, older iOS versions).
- `IMG_E0410.HEIC` (optional, only if edits) — edited file that lacks the depth of field metadata
- `IMG_O0410.AAE` (optional, only if edits) — sidecar for the edited file

**JPEG photos** (Camera Capture set to "Most Compatible"):
- `IMG_0410.JPG` — original file (same structure as HEIC, just a different format)
- `IMG_0410.AAE` — sidecar
- `IMG_E0410.JPG` (optional, only if edits) — edited file
- `IMG_O0410.AAE` (optional, only if edits) — sidecar for the edited file
- Even with "High Efficiency", some files may be JPEG (suspected: front camera selfies).

**ProRAW photos** (Apple DNG, Photo Capture set to Apple "ProRAW"):
- `IMG_0235.DNG` — original ProRAW file (~30 MB)
- `IMG_0235.AAE` — sidecar
- `IMG_E0235.JPG` (optional, only if edits) — edited file (note: JPG, not DNG)
- `IMG_O0235.AAE` (optional, only if edits) — sidecar for the edited file

**Videos** (standard and ProRes):
- `IMG_0115.MOV` — original video file
- `IMG_E0115.MOV` (optional, only if edits) — the edited video file
- `IMG_O0115.MOV` (optional, only if edits) — sidecar for the edited video file
- ProRes videos use the same `.MOV` container but are much larger (~663 MB vs ~45 MB).

## Album Naming Conventions

Album directory names follow a structured format that encodes date, optional
part number, optional series, title, optional location, and optional tags.

### Format

```
DATE - [PART - ] [Series - ] Title [@ Location] [tags]
```

### Fields

**DATE** (required) — one of the following precisions, or a range of any two:

| Precision | Example |
|-----------|---------|
| Year | `2024` |
| Month | `2024-07` |
| Day | `2024-07-14` |
| Year range | `2024--2025` |
| Month range | `2024-07--2024-08` |
| Day range | `2024-07-14--2024-07-16` |
| Mixed-precision range | `2024-07--2024-08-03` or `2024--2024-07` |

Any start–end combination of precisions is valid (e.g. `YYYY-MM--YYYY-MM-DD`
or `YYYY--YYYY-MM`).

**PART** (optional) — zero-padded two-digit number: `01`, `02`, ...
Only valid for single-day dates (`YYYY-MM-DD`). Albums with date ranges
or lower precisions (`YYYY`, `YYYY-MM`) must not have a part number.

**Series** (optional) — free text, must not contain ` - ` (the three-character
separator with surrounding spaces).

**Title** (required) — free text, must not contain ` - `.

**Location** (optional) — free text after `@`. May contain commas
(e.g. `Banff NP, AB, CA`).

**Tags** (optional) — `[kebab-case-slug, ...]` at the end. Only `private` is
currently allowed.

### Constraints

- 255 bytes maximum for the full directory name.
- ` - ` (space-dash-space) is reserved as the field separator and must not
  appear inside Title or Series (it is fine as part of a hyphenated word
  without surrounding spaces).
- `@` is reserved for the location separator.
- All fields except DATE and Title are optional.
- PART is only allowed when DATE is a single day (`YYYY-MM-DD`). Date ranges
  and lower precisions (`YYYY`, `YYYY-MM`) do not support part numbers.
- Tags are valid with any combination of fields.

### Examples

```
2024-07-14 - Hiking the Rockies
2024-07-14 - 01 - Hiking the Rockies
2024-07-14 - 01 - Canada Trip - Hiking the Rockies
2024-07-14 - Hiking the Rockies @ Banff NP, AB, CA
2024-07-14 - 01 - Canada Trip - Hiking the Rockies @ Banff NP, AB, CA
2024-07--2024-08 - Summer Road Trip
2024 - Family Photos
2024-07-14 - Hiking the Rockies [private]
2024-07-14 - 01 - Canada Trip - Hiking the Rockies @ Banff NP, AB, CA [private]
```

### Private Albums

Private albums are tagged with `[private]` like any other tag. Additional
rules apply when an album set uses part numbering:

- Part numbering is independent from public albums.
- When numbered, part numbers correspond to the matching public part
  (e.g. `01 [private]` is the private counterpart of public `01`).
- Gaps in private part numbers are expected — only parts with private content
  get a private album.
- Private albums may be unnumbered even when public albums are numbered
  (catch-all private content for the day).

## ID Convention

All identifiable objects in photree use a dual-ID system:

- **Internal ID** — a UUID v7 string stored in YAML files (e.g.
  `0192d4e1-7c3f-7b4a-8c5e-f6a7b8c9d0e1`). Used for storage,
  deduplication, and programmatic comparison. Time-ordered by creation.
- **External ID** — a user-friendly format: `{type_prefix}_{base58(uuid_bytes)}`
  (e.g. `album_3K8vJxNm2cYpR7qWz5FhG`). Used for CLI display and user input.

Base58 encoding uses the Bitcoin alphabet
(`123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz`). A 16-byte
UUID encodes to ~22 characters, making the full external ID ~28 characters.

| Object     | Type prefix  | Example external ID |
|------------|--------------|---------------------|
| Album      | `album`      | `album_3K8vJxNm2cYpR7qWz5FhG` |
| Collection | `collection` | `collection_6N1yMAPq5fBsU0tZC8IkJ` |
| Image      | `image`      | `image_4L9wKyOo3dZqS8rXA6GiH` |
| Video      | `video`      | `video_5M0xLzPp4eArT9sYB7HjI` |

## Gallery Directory Layout

A gallery is a directory containing `.photree/gallery.yaml` and an `albums/`
subdirectory where imported albums are organized by year:

```
<Gallery Root>/
  .photree/
    gallery.yaml            gallery-wide settings (link-mode)
  albums/
    2023/
      2023-12-25 - Christmas/
    2024/
      2024-07-14 - Hiking the Rockies/
      2024-07-14 - 01 - Canada Trip - Hiking the Rockies/
  collections/
    2024/
      2024-07-14--2024-07-16 - Canada Trip/
    Best of All Time/
```

A gallery has two top-level directories with a fixed structure:

- **`albums/`** — albums organized by year (`albums/YYYY/<album-name>/`).
  YYYY is extracted from the album name's date prefix.
- **`collections/`** — collections organized by year
  (`collections/YYYY/<collection-name>/`), or directly under `collections/`
  for dateless collections. YYYY uses the start year for date ranges.

Gallery commands (`gallery check`, `gallery refresh`, `gallery show`, etc.)
discover albums exclusively in `albums/` and collections exclusively in
`collections/`. Content placed outside these directories is not managed by
photree.

The `gallery import` and `gallery import-all` commands automate album
placement into `albums/YYYY/`.

### Gallery Resolution

Commands that need a gallery directory resolve it in this order:

1. Explicit `--gallery-dir` CLI option
2. Walk up from the current working directory looking for
   `.photree/gallery.yaml` — the directory containing it is the gallery root

If no gallery metadata is found, the command exits with an error suggesting
`photree gallery init`.

## Album On-Disk Layout

### Album Detection

A directory is recognized as a photree album when it contains:
1. A `.photree/album.yaml` file (album metadata), **and**
2. At least one media source (iOS or std)

The `.photree/` directory stores album metadata and configuration.

### Media Sources

An album can have multiple **media sources** — named sources of photos. Each
media source is either **iOS** (imported via Image Capture) or **std** (standard
-- photos from other sources like other people's cameras).

Both iOS and std media sources share the same two-tier structure:

- **Archive directories** (`ios-{name}/` or `std-{name}/`) store the original
  and edited variants in a fixed internal layout (`orig-img/`, `edit-img/`,
  `orig-vid/`, `edit-vid/`).
- **Browsable directories** (`{name}-img/`, `{name}-vid/`, `{name}-jpg/`)
  are the derived, shareable versions built from the archive.

**iOS media source** (`ios-{name}/`):
- Detected by: `ios-{name}/` directory containing `orig-img/` or `orig-vid/`
- Archive holds originals, edits, and AAE sidecars
- Files are matched across directories by **image number** (digits extracted
  from the `IMG_NNNN` filename)
- Integrity checks, optimization, and iOS-specific fixes apply

**Std media source** (`std-{name}/`):
- Detected by: `std-{name}/` directory containing `orig-img/` or `orig-vid/`
- Archive structure is identical to iOS (`orig-img/`, `edit-img/`, `orig-vid/`,
  `edit-vid/`)
- No filename naming requirements (no `IMG_` prefix convention)
- Files are matched across directories by **filename stem** (base name without
  extension)
- JPEG conversion applies, but iOS-specific checks and fixes do not

**Legacy std media source** (backward compatibility):
- Detected by: `{name}-img/` or `{name}-vid/` directory without a corresponding
  `ios-{name}/` or `std-{name}/` directory
- Has browsable directories only (no archive)
- Browsable directories are the source of truth -- never rebuilt
- Treated as a std media source in all other respects (stem-based matching,
  JPEG conversion, no iOS-specific logic)

The default media source is named `main`.

### Directory Structure

```
<Album Title>/
  .photree/               album metadata directory
    album.yaml            album metadata (id)
    media.yaml            media ID mappings (image/video UUIDs)
    title.bkp             original directory name backup
  to-import/              selection files exported from Photos (workflow input)
  to-import.csv           alternative selection list (one filename per row)

  # iOS media source "main"
  ios-main/               archive (iOS)
    orig-img/             originals + AAE sidecars
    edit-img/             edited variants (IMG_E*) + sidecars (IMG_O*)
    orig-vid/             original videos
    edit-vid/             edited videos
  main-img/               browsable: best variant (edit if available, else orig)
  main-jpg/               browsable: JPEG for sharing/web/compatibility
  main-vid/               browsable: best variant video

  # iOS media source "bruno" (additional iOS source)
  ios-bruno/              archive (iOS) from bruno
    orig-img/
    edit-img/
    orig-vid/
    edit-vid/
  bruno-img/              browsable: best variant from bruno
  bruno-jpg/              browsable: JPEG from bruno
  bruno-vid/              browsable: best variant video from bruno

  # Std media source "nelu" (non-iOS, with archive)
  std-nelu/               archive (std) from nelu
    orig-img/             originals
    edit-img/             edited variants
    orig-vid/             original videos
    edit-vid/             edited videos
  nelu-img/               browsable: best variant from nelu
  nelu-jpg/               browsable: JPEG from nelu
  nelu-vid/               browsable: best variant video from nelu

  # Legacy std media source "dana" (no archive, browsable only)
  dana-img/               browsable: images from dana (source of truth)
  dana-vid/               browsable: videos from dana (source of truth)
  dana-jpg/               browsable: JPEG versions of dana's images
```

### Browsable Directories

For each media source, the `{name}-img/`, `{name}-vid/`, and `{name}-jpg/`
directories at the top level are the browsable/shareable versions:

- **`{name}-img/`**: For iOS and std media sources with archives, built from
  the best available variant (edited if present, otherwise original). For
  legacy std media sources (no archive), this is the source of truth.
- **`{name}-vid/`**: Same logic as `{name}-img/` but for videos.
- **`{name}-jpg/`**: JPEG versions for sharing/web. Generated from `{name}-img/`
  via HEIC/HEIF/DNG→JPEG conversion (sips). JPG/PNG files are copied as-is.

## Selection Mechanism

The selection tells photree which photos to import from Image Capture.
Conceptually, a selection is a **list of filenames** — the actual file
contents are irrelevant. Only the filenames matter because matching against
Image Capture files is done by image number (digits extracted from the
filename, e.g. `0410` from `IMG_0410.HEIC`).

Two sources are supported:

- **`to-import/` directory** — files exported from Apple Photos. The files
  themselves are not used; only their names serve as the selection list.
- **`to-import.csv`** — a one-column CSV file (no header) where each row is
  a filename (e.g. `IMG_0410.HEIC`).

When both sources exist, their entries are merged (union). If the same image
number appears in both sources, it is deduplicated silently. After a
successful import, processed files are deleted from `to-import/` and
`to-import.csv` is deleted if all its entries were processed.

This design decouples the selection from any specific tool. Exporting from
Apple Photos into `to-import/` is the most common workflow, but the
selection can equally be generated from a phone, a custom CLI, an LLM,
AppleScript, or any other workflow that can produce a list of filenames.

## Collections

Collections group albums, media items, and other collections. They enable
organizing content beyond the flat album structure — e.g., a "Canada Trip"
series spanning multiple album days, or a curated "Best of 2024" selection.

### Collection Naming Convention

```
[DATE - ] Title [@ Location] [tags]
```

The date prefix is optional (unlike albums where it is required). Some
collections are atemporal and have no date. The date format follows the
same spec as albums: `YYYY`, `YYYY-MM`, `YYYY-MM-DD`, or ranges with `--`.
Location and tags follow the same rules as albums: `@` separates the
location, `[private]` is the only currently allowed tag.

### Collection Kind

- **`smart`** — members are auto-populated by `gallery refresh` based on
  the collection's date range. Albums and sub-collections whose dates fall
  within the range are materialized in `collection.yaml`.
- **`manual`** — members are listed explicitly. Added via `collection import`
  or managed by `gallery refresh` for implicit collections.

### Collection Lifecycle

- **`explicit`** — created and deleted by the user (via `collection init`,
  `collection import`). Not affected by album title changes.
- **`implicit`** — derived from album series (the series component parsed
  from album titles). Created, renamed, and deleted automatically by
  `gallery refresh`. Implicit collections are always `kind: manual` —
  they contain exactly the albums sharing that series. Only **contiguous**
  albums with the same series form a single collection; if the same series
  is interrupted by other albums, each contiguous run produces a separate
  collection (disambiguated by date range in the collection name).

A collection can be converted between lifecycles using
`collection metadata set --lifecycle <lifecycle>`. On the next
`gallery refresh`, album titles are synced with the new lifecycle:

- **Implicit → explicit**: The explicit collection now owns the grouping,
  so the series component in album names is redundant. `gallery refresh`
  strips the series from album names (e.g.
  `2024-07-14 - 01 - Canada Trip - Hiking` becomes
  `2024-07-14 - 01 - Hiking`).
- **Explicit → implicit**: The collection title is added as a series
  component to the contained albums' names (e.g.
  `2024-07-14 - 01 - Hiking` becomes
  `2024-07-14 - 01 - Canada Trip - Hiking`).

### Collection Directory Layout

```
<Collection Title>/
  .photree/
    collection.yaml         collection metadata
  to-import/                selection files (for collection import)
  to-import.csv             alternative selection list
```

Collections are placed in `collections/YYYY/` within the gallery, using the
start year of the date (or directly in `collections/` for dateless
collections).

## Metadata Files

### Album Metadata (`.photree/album.yaml`)

Each album has a `.photree/album.yaml` file with the following fields:

```yaml
id: 0192d4e1-7c3f-7b4a-8c5e-f6a7b8c9d0e1
```

| Field | Type   | Description |
|-------|--------|-------------|
| `id`  | string | UUID v7 identifying the album. Generated at import time. |

The album ID is generated automatically during import. For existing albums
without an ID, use `photree album fix --id` or `photree gallery fix --id`
to generate missing IDs.

### Media Metadata (`.photree/media.yaml`)

Each album can have a `.photree/media.yaml` file that assigns stable UUIDs
to individual images and videos. Each media item is identified by its **key**
(image number for iOS sources, filename stem for std sources) — one ID per
key regardless of file variants (original, edited, browsable, JPEG).

```yaml
media-sources:
  main:
    images:
      0192d4e1-7c3f-7b4a-8c5e-f6a7b8c9d0e1: "0410"
      0192d4e1-7c3f-7b4a-8c5e-f6a7b8c9d0e2: "0411"
    videos:
      0192d4e1-7c3f-7b4a-8c5e-f6a7b8c9d0e3: "0115"
  bruno:
    images:
      0192d4e1-7c3f-7b4a-8c5e-f6a7b8c9d0e4: DSC_1234
    videos: {}
```

| Field            | Type                     | Description |
|------------------|--------------------------|-------------|
| `media-sources`  | map[string, object]      | Media source name → image/video ID mappings. |
| `images`         | map[string, string]      | UUID v7 → key (image number for iOS, stem for std). |
| `videos`         | map[string, string]      | UUID v7 → key (image number for iOS, stem for std). |

Media metadata is stored separately from `album.yaml` to keep album loading
fast. Use `photree album refresh` (or `photree albums refresh` /
`photree gallery refresh`) to generate and update media IDs. The `check`
commands verify that `media.yaml` is in sync with the directory structure.

Media IDs are derived from archive directories (`orig-img/`, `orig-vid/`).

### Collection Metadata (`.photree/collection.yaml`)

Each collection has a `.photree/collection.yaml` file:

```yaml
id: 0192d4e1-7c3f-7b4a-8c5e-f6a7b8c9d0e1
kind: manual
lifecycle: implicit
albums:
- 0192d4e1-7c3f-7b4a-8c5e-f6a7b8c9d0e2
- 0192d4e1-7c3f-7b4a-8c5e-f6a7b8c9d0e3
collections: []
images: []
videos: []
```

| Field         | Type           | Description |
|---------------|----------------|-------------|
| `id`          | string         | UUID v7 identifying the collection. |
| `kind`        | string         | `smart` or `manual`. |
| `lifecycle`   | string         | `implicit` or `explicit`. |
| `albums`      | list\[string\] | Album internal UUIDs. |
| `collections` | list\[string\] | Collection internal UUIDs. |
| `images`      | list\[string\] | Image internal UUIDs. |
| `videos`      | list\[string\] | Video internal UUIDs. |

### Gallery Metadata (`.photree/gallery.yaml`)

Gallery-wide configuration is stored in a `.photree/gallery.yaml` file
placed in a parent directory above the albums. photree resolves the
gallery metadata by walking up the directory hierarchy from the album
(or batch base directory), using the first `.photree/gallery.yaml` found.

```yaml
link-mode: hardlink
```

| Field       | Type   | Default    | Description |
|-------------|--------|------------|-------------|
| `link-mode` | string | `hardlink` | Default link mode for optimize and other link-mode operations. Values: `hardlink`, `symlink`, `copy`. |

The `--link-mode` CLI argument overrides the gallery-level setting.
If no gallery.yaml is found and no CLI argument is given, the default
is `hardlink`.

### Editing Metadata

The `.photree/` directory and its YAML files are managed by photree and
should not be edited directly. Use the provided CLI commands instead:

- **Gallery settings**: `photree gallery metadata set --link-mode <value>`
- **Album ID**: Generated automatically at import time; use
  `photree album fix --id` or `photree gallery fix --id` to generate
  missing IDs.
- **Media IDs**: Use `photree album refresh` (or `photree albums refresh` /
  `photree gallery refresh`) to generate and update media IDs.

Direct edits may be silently overwritten or cause unexpected behavior.

## EXIF Metadata

### Usage

photree reads EXIF timestamps to validate that media files match the album's
date-based name. This is a read-only, optional check — EXIF mismatches
produce warnings, not errors.

Tags are checked in priority order (first match wins):

1. `CreationDate` — QuickTime tag with timezone info. Preferred for videos,
   especially edited iOS videos (`IMG_E*.MOV`) where `CreateDate` reflects
   the edit render date (UTC), not the original capture date.
2. `DateTimeOriginal` — standard EXIF tag for photos (HEIC, JPEG, DNG).
   Not present in QuickTime containers.
3. `CreateDate` — fallback for videos without `CreationDate`, or photos
   without `DateTimeOriginal`.

For photos, `CreationDate` is simply absent (QuickTime-only tag), so the
priority naturally falls through to `DateTimeOriginal`.

During album and gallery checks, photree reads all media files from each
album's browsable directories (`{name}-jpg/`, `{name}-vid/`) and compares
their EXIF timestamps against the album date. All ranges use an exclusive
end boundary:

- **Single-day albums** (`YYYY-MM-DD`): each file must fall in
  `[album_date, album_date + 2 days)` — the next day is allowed for
  timezone/midnight tolerance. Additionally, at least one file must match
  the album date exactly (relaxed for part > 01, since continuation
  albums may have all files from the next day).
- **Date ranges** (`YYYY-MM-DD--YYYY-MM-DD`): each file must fall in
  `[start, end + 1 day)` — strict, no extra tolerance.
- **Lower precisions** (`YYYY`, `YYYY-MM`): each file must fall in
  `[start, end + 1 day)` — e.g. `2024` means Jan 1 inclusive to
  Jan 1 of the next year exclusive.

### Why exiftool / PyExifTool

photree uses [exiftool](https://exiftool.org/) via the
[PyExifTool](https://pypi.org/project/PyExifTool/) Python wrapper. PyExifTool
maintains a single persistent exiftool process using the `-stay_open` protocol,
which avoids spawning a new subprocess for each album during gallery-wide
operations.

**Why not Pillow + pillow_heif:**

- **No video support.** Pillow is an image library and cannot read metadata from
  video files (MOV, MP4, etc.). photree reads `CreateDate` from videos, so a
  second library (e.g. pymediainfo, ffprobe) would be needed, adding more
  complexity than exiftool alone.
- **No performance advantage.** For the small number of files sampled per album,
  Pillow's per-file Python overhead is comparable to (or slower than) exiftool's
  batch mode. exiftool reads only metadata headers without decoding pixel data,
  and its batch/persistent-process modes amortize startup cost across many files.
- **Narrower format coverage.** exiftool handles HEIC, DNG, JPEG, PNG, MOV, MP4,
  and dozens of other formats uniformly. Pillow requires format-specific plugins
  (pillow_heif for HEIC) and still cannot match exiftool's breadth.

**Why not other Python EXIF libraries** (exifread, plum, etc.):

- Most pure-Python EXIF readers only support JPEG and TIFF-based formats. None
  cover both images and videos in a single library the way exiftool does.

### Supported File Formats

**Images**: `.dng`, `.heic`, `.heif`, `.jpeg`, `.jpg`, `.png`

**Videos**: `.avi`, `.mov`, `.mp4`, `.wmv`

**iOS-specific subsets** (used by import, iOS fixes, integrity checks):
- Images: `.dng`, `.heic`, `.jpeg`, `.jpg`, `.png`
- Videos: `.mov`
- Sidecars: `.aae`
