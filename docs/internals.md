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

## iOS Album On-Disk Layout

After import, an iOS album has this structure:

```
<YYYY-MM-DD - Title>/
  to-import/            user selection files (workflow input)
  ios/
    orig-img/           originals + AAE sidecars
    edit-img/           edited versions (IMG_E*) + sidecars (IMG_O*)
    orig-vid/           original videos
    edit-vid/           edited videos
  main-img/             best version: edit if available, else orig (no sidecars)
  main-jpg/             JPEG for sharing/web/compatibility (no sidecars)
  main-vid/             best version video (no sidecars)
```

The `ios/` subdirectory contains archival files preserving all iOS variants.
The `main-*` directories at the top level are the browsable/shareable versions,
built from the best available source (edited if present, otherwise original).
