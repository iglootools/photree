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

## Album On-Disk Layout

### Album Detection

A directory is recognized as a photree album when it contains:
1. A `.photree/` directory (album marker), **and**
2. At least one contributor (iOS or plain)

The `.photree/` directory stores album metadata such as the original directory
name backup (`title.bkp`).

### Contributors

An album can have multiple **contributors** — named sources of photos. Each
contributor is either **iOS** (imported via Image Capture) or **plain** (photos
from other sources like other people's cameras).

**iOS contributor** (`ios-{name}/`):
- Detected by: `ios-{name}/` directory containing `orig-img/` or `orig-vid/`
- Has archival directories (originals, edits, sidecars)
- Has browsable directories (best version, JPEG conversion)
- Integrity checks, optimization, and iOS-specific fixes apply

**Plain contributor** (`{name}-img/` or `{name}-vid/`):
- Detected by: `{name}-img/` or `{name}-vid/` directory without a corresponding `ios-{name}/`
- Has browsable directories only (no archival originals)
- No filename naming requirements (no `IMG_` prefix convention)
- Files are matched across directories by stem (base name without extension)
- JPEG conversion applies, but iOS-specific checks and fixes do not
- Browsable directories are the source of truth — never rebuilt

The default contributor is named `main`.

### Directory Structure

```
<Album Title>/
  .photree/               album metadata
    title.bkp             original directory name backup
  to-import/              user selection files (workflow input)

  # iOS contributor "main"
  ios-main/               archival files
    orig-img/             originals + AAE sidecars
    edit-img/             edited versions (IMG_E*) + sidecars (IMG_O*)
    orig-vid/             original videos
    edit-vid/             edited videos
  main-img/               best version: edit if available, else orig
  main-jpg/               JPEG for sharing/web/compatibility
  main-vid/               best version video

  # iOS contributor "bruno" (additional contributor)
  ios-bruno/              archival files from bruno
    orig-img/
    edit-img/
    orig-vid/
    edit-vid/
  bruno-img/              best version from bruno
  bruno-jpg/              JPEG from bruno
  bruno-vid/              best version video from bruno

  # Plain contributor "nelu" (non-iOS, browsable only)
  nelu-img/               images from nelu
  nelu-vid/               videos from nelu
  nelu-jpg/               JPEG versions of nelu's images
```

### Browsable Directories

For each contributor, the `{name}-img/`, `{name}-vid/`, and `{name}-jpg/`
directories at the top level are the browsable/shareable versions:

- **`{name}-img/`**: For iOS contributors, built from the best available source
  (edited if present, otherwise original). For plain contributors, this is the
  source of truth.
- **`{name}-vid/`**: Same logic as `{name}-img/` but for videos.
- **`{name}-jpg/`**: JPEG versions for sharing/web. Generated from `{name}-img/`
  via HEIC/HEIF/DNG→JPEG conversion (sips). JPG/PNG files are copied as-is.

## EXIF Metadata

### Usage

photree reads EXIF timestamps (`DateTimeOriginal` for photos, `CreateDate` for
videos) to validate that media files match the album's date-based name. This is
a read-only, optional check — EXIF mismatches produce warnings, not errors.

During album and gallery checks, photree reads all media files from each
album's browsable directories (`{name}-jpg/`, `{name}-vid/`) and compares
their EXIF timestamps against the album date with a 1-day tolerance.

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
