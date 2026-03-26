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

### Supported File Formats

**Images**: `.dng`, `.heic`, `.heif`, `.jpeg`, `.jpg`, `.png`

**Videos**: `.avi`, `.mov`, `.mp4`, `.wmv`

**iOS-specific subsets** (used by import, iOS fixes, integrity checks):
- Images: `.dng`, `.heic`, `.jpeg`, `.jpg`, `.png`
- Videos: `.mov`
- Sidecars: `.aae`
