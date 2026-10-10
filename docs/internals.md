# Internals

This document describes how photree implements its domain: the on-disk layout,
metadata file formats, and the algorithms behind import, refresh, validation,
and face clustering.

For the concepts themselves — galleries, albums, media sources, media items,
collections, naming conventions, identifiers — see [domain.md](./domain.md).

## Gallery Directory Layout

A gallery is a directory containing `.photree/gallery.yaml` and an `albums/`
subdirectory where imported albums are organized by year:

```
<Gallery Root>/
  .photree/
    gallery.yaml            gallery-wide settings
    faces/                  gallery-level face clustering data
      face-index.faiss      serialized FAISS index
      face-manifest.yaml    maps index rows to face references
      clusters.yaml         cluster UUIDs + member face indices
      album-checksums.yaml  tracks ingested album face data
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

### Gallery Import Behavior

`gallery import` (single) and `gallery import-all` (batch) share one
classification + validation pass, then copy each album to
`albums/YYYY/<album-name>/`, generate a missing ID, and refresh derived data.

A first import is built in a hidden sibling (`albums/YYYY/.<album-name>.import`)
and renamed into place only once the copy and the derived-data refresh have
succeeded; on any failure the staging directory is removed. A half-built album
is therefore never left under its real name, where the next run would mistake it
for an already-imported one.

**Validation gate (all-or-nothing).** Before any filesystem mutation, every
source album is validated: name (`check_album_naming`), cross-album date
collisions across the batch **and** the existing gallery
(`check_batch_date_collisions`), and the presence of at least one media
source (`has_media_sources`). Duplicate IDs within the batch are also
rejected. If any album fails, the command reports all problems and imports
nothing.

**"Already imported" detection (hybrid).** Albums created by `album import`
or `album init` already carry an ID in `.photree/album.yaml`, and gallery
import preserves it on the copy — so the source and its gallery copy share
the same ID. Detection matches on:

1. **ID** — the source carries an ID already present in the gallery. This is
   the normal path, and it also handles a renamed source: the gallery album
   under its old name is matched and, on reimport, moved to the new name.
2. **Target name** — fallback for an ID-less source (e.g. an album assembled
   by hand without `album import`/`album init`): the target directory
   `albums/YYYY/<name>/` already exists.

**Default vs `--reimport`.** Without `--reimport`, already-imported albums are
**skipped** with a warning; a run whose only non-imports are skips exits 0.
With `--reimport`, the album's media is replaced:

1. The existing gallery copy's `.photree/album.yaml` (ID) and
   `.photree/media-ids/` (UUIDs) are preserved; `.photree/cache/` is dropped.
2. The source media is staged into a hidden sibling directory, the preserved
   metadata is restored over it, and derived data is rebuilt (browsable,
   JPEG, EXIF cache, faces). Media IDs reconcile: surviving keys keep their
   UUID, removed keys are pruned, new keys get fresh UUIDs.
3. The staged copy is swapped into place with two renames (old aside → new
   in place → delete old). If any step before the swap fails, the staging
   directory is removed and the live copy is left untouched.

`--reimport` on a not-yet-imported album is a normal import.

**Placement.** The target year is the start year of the album date at any
precision, so `2024 - Family` and `2024-07 - Summer` land in `albums/2024/`.

**Derived-data failures fail the album.** If JPEG conversion or face detection
fails for any image during the post-copy refresh, the album is imported but
reported as failed, and the command exits 1 (as do `album import`,
`albums import` and `albums refresh`).

**Clobber guard.** If the target name exists but is occupied by a *different*
album (the source carries an ID differing from the existing copy's), the
import is refused even with `--reimport`. This also applies when the source
was matched by ID and renamed: the gallery copy is moved to the new name only
if no other album holds it. An ID-less source cannot be distinguished, so
`--reimport` proceeds in that case.

**Swap rollback.** If the final rename of the reimport swap fails, the old copy
is moved back from its aside name and the staging directory is removed, so the
album never disappears from the gallery.

**Caveat.** UUID preservation holds only when source keys (iOS image numbers,
std filename stems) are stable; a re-export that renumbers files rotates the
UUIDs and breaks collection references to those media items.

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

See [domain.md — Media Source](./domain.md#media-source) for what a media
source is and how iOS and std sources differ. A media source is detected by its
archive directory — `ios-{name}/` or `std-{name}/` — containing `orig-img/` or
`orig-vid/`. Browsable directories without a backing archive are not media
sources.

### Directory Structure

```
<Album Title>/
  .photree/               album metadata directory
    album.yaml            album metadata (id)
    media-ids/            per-source media ID mappings (image/video UUIDs)
      main.yaml
      bruno.yaml
    cache/                derived data (safely deletable, rebuilt by refresh)
      exif/               cached EXIF timestamps per media source
        main.yaml
        bruno.yaml
      faces/              face detection data per media source
        main.npz          embeddings, bboxes, landmarks, scores
        main.yaml         processing state (mtimes, model version)
        main-thumbs/      resized 640px JPEGs for face detection
        bruno.npz
        bruno.yaml
        bruno-thumbs/
  to-import-ios-main/     iOS selection list for source "main" (workflow input)
  to-import-ios-main.csv  alternative iOS selection list (one filename per row)
  to-import-std-nelu/     std import staging for source "nelu"
    orig/                 originals to import into std-nelu/orig-{img,vid}
    edit/                 edited variants to import into std-nelu/edit-{img,vid}

  # iOS media source "main"
  ios-main/               archive (iOS)
    orig-img/             originals + AAE sidecars + Live Photo companion videos
    edit-img/             edited variants (IMG_E*) + sidecars (IMG_O*)
    orig-vid/             original standalone videos
    edit-vid/             edited standalone videos
  main-img/               browsable: best variant images + Live Photo videos
  main-jpg/               browsable: JPEG for sharing/web/compatibility
  main-vid/               browsable: best variant standalone video

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
```

### Browsable Directories

For each media source, the `{name}-img/`, `{name}-vid/`, and `{name}-jpg/`
directories at the top level are the browsable/shareable versions:

- **`{name}-img/`**: For iOS and std media sources, built from the best
  available variant (edited if present, otherwise original). For iOS
  sources, Live Photo companion videos (`.MOV` files with matching image
  keys) are also included alongside their images.
- **`{name}-vid/`**: Same logic as `{name}-img/` but for standalone videos
  only. Live Photo companion videos live in `{name}-img/` instead.
- **`{name}-jpg/`**: JPEG versions for sharing/web. Generated from `{name}-img/`
  via HEIC/HEIF/DNG→JPEG conversion (sips). JPG/PNG files are copied as-is.
  Live Photo companion videos are excluded (not convertible to JPEG).

## Import Staging Directories

An album is fed by one or more per-media-source staging entries, named
`to-import-{ios,std}-<media-source>`. `album import` / `albums import`
discover every staging entry in the album, validate them all, import each into
its target media source, then refresh derived data once. Validation includes
the archive collision checks (an incoming iOS image number or std stem that
already exists in the target archive), so a collision in any entry refuses the
whole import before anything is copied. A single album can
carry several (e.g. `to-import-ios-main/` plus `to-import-std-nelu/`).

### iOS staging (`to-import-ios-<name>/`, `to-import-ios-<name>.csv`)

For iOS sources the staging entry is a **selection** — a list of filenames
that photree matches, by image number, against a macOS Image Capture source
directory. The actual file contents are irrelevant; only the filenames matter
(the image number is the digits extracted from the filename, e.g. `0410` from
`IMG_0410.HEIC`). Two forms are supported and may be combined:

- **`to-import-ios-<name>/` directory** — files exported from Apple Photos.
  The files themselves are not used; only their names serve as the selection.
- **`to-import-ios-<name>.csv`** — a one-column CSV file (no header) where
  each row is a filename (e.g. `IMG_0410.HEIC`).

When both forms exist, their entries are merged (union), deduplicated by image
number. After a successful import, cleanup also works by image number: every
directory entry and CSV row whose number was imported is removed — including
the second half of a Live Photo export (`IMG_0410.HEIC` + `IMG_0410.MOV`). A CSV
is deleted once all its numbers are processed, and otherwise rewritten with only
its remaining rows. This
decouples the selection from any specific tool: exporting from Apple Photos is
the most common workflow, but the list can equally come from a phone, a custom
CLI, an LLM, AppleScript, or anything that produces filenames.

### Std staging (`to-import-std-<name>/`)

For std (non-iOS) sources there is no selection list and no Image Capture
source — the files themselves are imported. The staging directory contains
`orig/` and (optionally) `edit/` subfolders; their files are copied into the
std archive (`std-<name>/orig-{img,vid}` and `edit-{img,vid}`), split by
extension. Files are matched across `orig`/`edit` by filename stem. On a
successful import the whole `to-import-std-<name>/` directory is consumed
(removed). Duplicate stems within a folder are rejected; an `edit/` file with
no matching `orig/` stem is allowed (it is imported but, as with existing std
sources, omitted from the browsable directory).

## Collections

See [domain.md — Collection](./domain.md#collection) for collection naming,
the members/lifecycle/strategy axes, their valid combinations, and private tag
virality.

### Collection Refresh

`gallery refresh` runs the following phases for collections, after the
album media refresh. They are implemented in `photree/collection/refresh/`
(one module per phase, orchestrated by `refresh_collections`):

#### Phase 1: Scan and Validate Albums

Parses all album names (light check) and detects cross-album date
collisions. If any album name is unparseable or date collisions are
found, the refresh aborts before modifying anything.

#### Phase 2: Album Title Sync

Syncs album directory names with collection lifecycle state. This runs
before implicit collection detection so that phase 3 sees the updated
album names.

- **Album has series + explicit collection with that title exists** →
  strip the series from the album name. The explicit collection owns
  the grouping, so the series is redundant.
- **Album has no series + implicit collection contains it** → add the
  collection title as series to the album name.

See [domain.md — Lifecycle](./domain.md#lifecycle) for examples.

All renames are planned and checked before any is applied: a target name that
already exists, or two albums renaming to the same name, is reported as an
error and nothing is renamed. The planned renames are applied to the in-memory
album list (in both normal and dry-run mode), so phase 3 sees the post-sync
names without re-reading the disk and a dry run predicts the real run.

#### Phase 3: Implicit Collection Refresh

Detects album series and creates/updates/renames/deletes implicit
collections:

1. **Group albums by contiguous series** — albums are sorted
   chronologically (by directory name). Contiguous runs sharing the same
   series form groups. Non-contiguous occurrences of the same series
   produce separate groups. **Private albums are excluded** from implicit
   collections (implicit collection names are built from the series title
   without `[private]` tags, so they are always non-private). If all
   albums in a series are private, no implicit collection is created.

2. **Match each group to an existing implicit collection** — a three-tier
   strategy preserves the collection ID across changes:
   - **Exact name match**: the collection name (including date range) is
     unchanged — fast path.
   - **Title + member overlap**: the date range changed (albums added or
     removed) but the series title is the same and the collection shares
     at least one album with the group. The collection is renamed to
     reflect the new date range and its members are updated.
   - **Exact member match**: the series title changed but the album
     members are identical — treated as a rename.

3. **Create new** — groups with no matching collection get a new implicit
   collection in `collections/YYYY/`.

   Each existing collection is claimed by at most one group. Two runs of the
   same series that would produce the same collection name (e.g. same date,
   parts 01/02/03 with series A, B, A) are reported as a naming conflict and
   nothing is written.

4. **Delete orphaned** — implicit collections whose series no longer
   appears in any album are removed.

**Limitation**: changing the series title and adding/removing albums at the
same time (before a refresh) causes the old collection to be deleted and a
new one created — the collection ID is not preserved. Each tier handles one
kind of change: title+overlap handles member changes, exact-member handles
title changes, but neither covers both simultaneously. To preserve the ID,
apply changes incrementally: rename the series in one refresh, then
add/remove albums in a subsequent refresh.

#### Phase 4: Smart Collection Refresh

Materializes members for `members: smart` collections based on strict
date range containment:

- For each smart collection with a date, finds all albums and
  sub-collections whose date ranges are **fully contained** within the
  collection's range. Mere overlap is not sufficient — the member's
  entire date range must fall within the collection's boundaries.
- Private smart collections only include private members; non-private
  smart collections exclude private members.
- Writes the matched IDs into `collection.yaml`, replacing the previous
  album and collection member lists.
- Smart collections do not support image or video members — these fields
  are cleared on each refresh.

### Collection Directory Layout

```
<Collection Title>/
  .photree/
    collection.yaml         collection metadata
  to-import/                selection files (for collection import)
  to-import.csv             alternative selection list
```

## Browsable Directory

`gallery refresh` generates a `browsable/` directory at the gallery root
with relative symlinks that organize content for easy navigation.

### Structure

```
browsable/
  public/
    albums/
      by-year/<YYYY>/<album-name>/
        main-jpg -> (relative symlink to album's main-jpg)
        main-vid -> (relative symlink to album's main-vid)
    collections/
      by-year/<YYYY>/<collection-name>/
        albums/<album rendering>
        collections/<sub-collection rendering (recursive)>
        images/<symlinks to individual JPG files>
        videos/<symlinks to individual video files>
      all-time/<dateless-collection-name>/...
      by-chapter/<chapter-collection-name>/...
  private/
    (same structure as public/)
```

### Rendering Rules

- **Albums**: Each album gets a directory with symlinks to its `{name}-jpg`
  and `{name}-vid` browsable dirs (main-img excluded — JPGs preferred for
  browsability). One symlink per media source.
- **Collections** (recursive):
  - `albums/` — album members rendered as above
  - `collections/` — sub-collection members rendered recursively
  - `images/` — symlinks to individual JPG files, prefixed with
    album name and media source to prevent collisions
    (e.g. `2024-07-14 - Hiking - main - IMG_0001.jpg`)
  - `videos/` — symlinks to individual video files, same naming
- **Visibility**: Albums and collections with `[private]` tag go under
  `private/`; all others under `public/`.
- **Collection buckets**: `by-year/<YYYY>` for dated collections,
  `all-time/` for dateless, `by-chapter/` for `strategy=chapter`.

### Refresh Strategy

The browsable directory is **deleted and recreated** on each
`gallery refresh`. Before deletion, a safety check validates that
the directory only contains directories and symlinks (no regular files
that could be accidentally destroyed). Albums or collections whose metadata
cannot be read, or whose name does not parse, abort the step before anything is
deleted. Collection members whose ID no longer resolves are rendered without
that member and reported as warnings. All symlinks are relative for gallery
portability.

Collection `images/` and `videos/` entries are matched with the media source's
own key rule (image number for iOS, filename stem for std), so a std source
whose files happen to start with `IMG_` is linked correctly.

### Cycle Detection

During recursive collection rendering, visited collection IDs are
tracked. If a collection references another that has already been
rendered in the current path, a cycle is detected and the refresh
reports an error.

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

### Media Metadata (`.photree/media-ids/`)

Each media source has a YAML file under ``.photree/media-ids/`` that assigns
stable UUIDs to individual images and videos. Each media item is identified
by its **key** (image number for iOS sources, filename stem for std sources)
— one ID per key regardless of file variants (original, edited, browsable,
JPEG).

```yaml
# .photree/media-ids/main.yaml
images:
  0192d4e1-7c3f-7b4a-8c5e-f6a7b8c9d0e1: "0410"
  0192d4e1-7c3f-7b4a-8c5e-f6a7b8c9d0e2: "0411"
videos:
  0192d4e1-7c3f-7b4a-8c5e-f6a7b8c9d0e3: "0115"
```

| Field    | Type                | Description |
|----------|---------------------|-------------|
| `images` | map[string, string] | UUID v7 → key (image number for iOS, stem for std). |
| `videos` | map[string, string] | UUID v7 → key (image number for iOS, stem for std). |

Media metadata is stored separately from `album.yaml` to keep album loading
fast. Use `photree album refresh` (or `photree albums refresh` /
`photree gallery refresh`) to generate and update media IDs. The `check`
commands verify that `media-ids` is in sync with the directory structure.

Media IDs are derived from archive directories (`orig-img/`, `orig-vid/`).

### Collection Metadata (`.photree/collection.yaml`)

Each collection has a `.photree/collection.yaml` file:

```yaml
id: 0192d4e1-7c3f-7b4a-8c5e-f6a7b8c9d0e1
members: smart
lifecycle: implicit
strategy: album-series
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
| `members`     | string         | `smart` or `manual`. |
| `lifecycle`   | string         | `implicit` or `explicit`. |
| `strategy`    | string         | `import`, `date-range`, `album-series`, or `chapter`. |
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
faces-enabled: true
face-cluster-threshold: 0.45
```

| Field                    | Type           | Default    | Description |
|--------------------------|----------------|------------|-------------|
| `link-mode`              | string         | `hardlink` | Default link mode for refresh and other link-mode operations. Values: `hardlink`, `symlink`, `copy`. |
| `faces-enabled`          | bool           | `true`     | Enable face detection and clustering during gallery refresh. |
| `face-cluster-threshold` | float or null  | `null`     | Cosine distance threshold for face clustering (0.0–1.0, validated; 0.0 is valid). When null, defaults to 0.45 at runtime. Lower = stricter (fewer merges). |

The `--link-mode` CLI argument overrides the gallery-level setting.
If no gallery.yaml is found and no CLI argument is given, the default
is `hardlink`.

### Editing Metadata

The `.photree/` directory and its YAML files are managed by photree and
should not be edited directly. Use the provided CLI commands instead:

- **Gallery settings**: `photree gallery metadata set --link-mode <value>`,
  `--faces-enabled`, `--face-cluster-threshold`
- **Album ID**: Generated automatically at import time; use
  `photree album fix --id` or `photree gallery fix --id` to generate
  missing IDs.
- **Media IDs**: Use `photree album refresh` (or `photree albums refresh` /
  `photree gallery refresh`) to generate and update media IDs.

Direct edits may be silently overwritten or cause unexpected behavior.

### Absent vs Corrupt Metadata

Every `.photree/*.yaml` reader (`foundation.metadata_io.load_yaml_mapping` /
`validate_metadata`) distinguishes two cases:

- **Absent** — the file does not exist. Commands that create metadata
  (`album init`, `fix --id`, refresh of media IDs) may write it.
- **Present but unusable** — empty, truncated, not a YAML mapping, or failing
  validation. This raises `InvalidMetadataError` and the command stops,
  printing the file and the reason. photree never regenerates such a file:
  a fresh `album.yaml`, `media-ids/*.yaml`, `collection.yaml` or
  `clusters.yaml` would carry fresh IDs and silently orphan every reference to
  the old ones.

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

Timestamps are **naive wall-clock** values. `DateTimeOriginal` carries no
offset; when a tag does (`CreationDate` on videos), the offset is parsed and
then dropped, so photos and videos compare on the same basis.

`album fix-exif` writes through exiftool and stops on the first failure: the
files and exiftool's diagnostics are printed and the command exits 1. Files
written before the failure keep their new value.

During album and gallery checks, photree reads all media files from each
album's browsable directories (`{name}-jpg/`, `{name}-vid/`) and compares
their EXIF timestamps against the album date (`album/exif_date_check.py`,
on top of the date arithmetic in `dates.py`). All ranges use an exclusive
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

See [domain.md — iOS Variants](./domain.md#ios-variants-image-capture).

## System Dependencies

photree shells out to two external binaries:

| Binary | Used for |
|---|---|
| `sips` | HEIC/DNG-to-JPEG conversion, face detection thumbnails |
| `exiftool` | reading and writing EXIF timestamps |

`photree/common/sysdeps.py` owns the list, each entry's purpose, and its
install hint. `photree/common/sysdeps_output.py` renders statuses and install
instructions, and `photree/clihelpers/sysdeps.py` turns both into the CLI gate.

### Fail-fast gate

Commands that need a binary call `require_system_deps` **before** any
filesystem mutation. A missing binary is a property of the machine, not of the
album being processed, so retrying per album can only reproduce the same
failure N times — worse, it does so after some albums have already been
written. The gate prints a check line per dependency, then install
instructions for whatever is missing, and exits 1 having modified nothing.

| Command | Requires |
|---|---|
| `album import`, `albums import` | `sips` + `exiftool` (`sips` dropped by `--skip-heic-to-jpeg`) |
| `gallery import`, `gallery import-all` | `sips` + `exiftool` |
| `album refresh`, `albums refresh`, `gallery refresh` | `sips` + `exiftool` |
| `collection import`, `collections import` | `exiftool` |
| `album detect-faces`, `albums detect-faces` | `sips` |
| `album check`, `albums check`, `gallery check` | `sips` (`CHECK_DEPS`); `albums check --refresh-exif-cache` also `exiftool` |
| `gallery cluster-faces` | `sips`; also `exiftool` with `--redetect` / `--refresh-thumbs` |
| `album fix-exif` | `exiftool` |
| `check system` | reports both, exits 1 if any is missing |

For `album import` / `albums import` the gate is folded into the existing
import preflight block, so all preflight failures are reported together.

The `check` commands are deliberately **not** gated on `exiftool`: EXIF
validation is optional there and degrades to a "checks skipped" line. They are
still gated on `sips`, which the browsable/JPEG consistency checks need.

### Defense in depth

`common.exif.get_metadata` raises `MissingSystemDependencyError` when asked to
start its own exiftool process on a machine that has none — otherwise
PyExifTool surfaces a bare `FileNotFoundError` that reads like a missing media
file. The CLI entry point catches that error and prints the same install
instructions, so a code path not fronted by the gate still fails legibly
instead of with a traceback.

## Album Validation Levels

photree has two levels of album validation, used in different contexts:

### Light Check (naming + cross-album)

Validates album directory names against the naming convention and detects
cross-album date collisions. No media file access — only inspects names
and album metadata. Fast, suitable as a pre-validation gate.

Includes:
- Per-album naming validation (parseability, valid calendar dates and
  ranges, tags, part number rules, canonical spacing)
- Cross-album date collision detection (multiple non-private single-day
  albums on the same date without part numbers)

Used by:
- `gallery refresh` — ensures all album names are parsable and
  collision-free before modifying any collections
- `gallery import` / `gallery import-all` — validates naming before
  importing an album into the gallery
- `album import` — validates naming before importing Image Capture files

### Full Check

Includes the light check plus filesystem and media validation:
- Directory structure (required/optional subdirectories)
- Album ID and media metadata presence and sync
- Per-media-source integrity (checksum verification, browsable/archive
  consistency, JPEG completeness, duplicate detection)
- EXIF timestamp validation (requires exiftool, reads media files)
- EXIF cache state (cache file presence per media source, if cache exists)
- Face detection state (model version, .npz/.yaml sync, if face data exists)
- Cross-album checks (date collisions, duplicate IDs)

Used by:
- `album check` / `albums check` / `gallery check`
- Post-import checks after `gallery import`

The full check accepts flags to disable expensive operations:
`--no-checksum` skips file checksums, `--no-check-exif-date-match`
skips EXIF timestamp reading.

## EXIF Timestamp Cache

photree caches EXIF timestamps to speed up album checks. Without the
cache, every `album check` reads EXIF metadata from all browsable files
via exiftool. With the cache, checks only need `stat()` calls to verify
mtimes — no exiftool process needed.

### Storage Layout

```
<Album>/
  .photree/
    cache/
      exif/
        main.yaml        # cached timestamps for media source "main"
        bruno.yaml        # cached timestamps for media source "bruno"
```

### Cache Schema

```yaml
version: 2
files:
  main-jpg/IMG_0410:
    mtime: 1721008370.5
    file-name: main-jpg/IMG_0410.jpg
    timestamp: "2024-07-14T14:32:50"
  main-vid/IMG_0115:
    mtime: 1721010622.3
    file-name: main-vid/IMG_0115.MOV
    timestamp: null              # no EXIF timestamp found
```

Entries are keyed by `{browsable-dir}/{stem}` and store the album-relative
path, so an image and a video sharing a stem (`clip.jpg`, `clip.mp4`) do not
collide, and mismatches point at the right directory. A cache without the
current `version` is treated as absent and rebuilt on the next refresh.

### Cache Lifecycle

- **Populated during** `album refresh` / `albums refresh` / `gallery refresh`
- **Consumed during** `album check` / `albums check` / `gallery check`
- **Falls back** to exiftool when cache is missing or stale
- **Refreshable** via `album check --refresh-exif-cache`

### Change Detection

A file needs EXIF re-reading when:
- Its key is not in the cache (new file)
- Its mtime differs from cached mtime (file changed)

Stale keys (files removed from disk) are pruned on refresh. The
`cache/exif` directory is purely derived data and can be safely deleted.

## Face Detection and Clustering Pipeline

photree includes a face detection and clustering pipeline built on
[InsightFace](https://github.com/deepinsight/insightface) (detection +
recognition) and [FAISS](https://github.com/facebookresearch/faiss)
(similarity search + clustering).

### Overview

The pipeline has two levels:

1. **Album-level**: Face detection runs per-album during `album refresh`,
   extracting face bounding boxes, landmarks, and 512-dimensional
   embedding vectors for each detected face.
2. **Gallery-level**: Face clustering runs during `gallery refresh`,
   collecting all album embeddings and grouping faces by identity using
   agglomerative clustering.

### InsightFace Pipeline (per image)

The `buffalo_l` model bundles two neural networks:

1. **RetinaFace** — detects face regions, producing bounding boxes,
   detection scores, and 5-point landmarks (eyes, nose, mouth corners).
2. **ArcFace** — produces a 512-dimensional L2-normalized embedding
   vector that encodes facial identity. Similar people produce similar
   vectors across photos, lighting, and expressions.

InsightFace internally resizes images to 640x640 for detection. On
M-series Macs, the `CoreMLExecutionProvider` leverages the Neural Engine
for acceleration.

### Album-Level Storage

```
<Album>/
  .photree/
    cache/
      faces/
        main.npz           # face data (embeddings, bboxes, landmarks, scores)
        main.yaml           # processing state (mtimes, model version)
        main-thumbs/        # resized 640px JPEGs for face detection
          0410.jpg
          0411.jpg
        bruno.npz
        bruno.yaml
        bruno-thumbs/
```

Per media source: one `.npz` (binary face data) + one `.yaml` (state) +
one `-thumbs/` directory (resized JPEGs).

#### .npz Schema

| Array         | Shape        | Dtype    | Description |
|--------------|-------------|----------|-------------|
| `keys`       | `(N,)`      | str      | Media key per face |
| `face_indices`| `(N,)`     | int32    | 0-based face index within image |
| `det_scores` | `(N,)`      | float32  | Detection confidence |
| `bboxes`     | `(N, 4)`    | float32  | Bounding boxes [x1, y1, x2, y2] |
| `landmarks`  | `(N, 5, 2)` | float32  | 5-point landmarks |
| `embeddings` | `(N, 512)`  | float32  | ArcFace embeddings |

#### Processing State (.yaml)

```yaml
model-name: buffalo_l
model-version: "1.0"
processed-keys:
  "0410":
    mtime: 1712345678.123
    file-name: IMG_0410.HEIC
    face-count: 2
    orig-width: 4032
    orig-height: 3024
    thumb-width: 640
    thumb-height: 480
```

#### Thumbnail Generation

Since OpenCV cannot read HEIC/DNG natively, photree generates resized
JPEG thumbnails (640px max dimension) from originals via macOS `sips`.
These are cached in `-thumbs/` directories and reused for re-detection
(e.g., model upgrades), making re-analysis fast (~100ms per image).

Thumbnail generation runs in parallel via `ThreadPoolExecutor`, and
InsightFace inference uses `CoreMLExecutionProvider` on M-series Macs
to overlap CPU-bound `sips` work with Neural Engine inference.

#### Change Detection

An image needs re-processing when:
- Not yet in `processed-keys` (new image)
- File modification time differs from stored `mtime`
- Model name/version changed (only re-detection, thumbnails reused)

### Gallery-Level Storage

```
<Gallery>/
  .photree/
    faces/
      face-index.faiss        # serialized FAISS IndexFlatIP
      face-manifest.yaml      # maps index rows to face references
      clusters.yaml           # cluster UUIDs + member face indices
      album-checksums.yaml    # tracks ingested album face data
```

#### Clustering Algorithm

Agglomerative clustering with cosine distance and average linkage:

```python
AgglomerativeClustering(
    n_clusters=None,
    metric="cosine",
    linkage="average",
    distance_threshold=0.45,  # configurable via gallery.yaml
)
```

For N > 10,000 faces, a sparse k-NN connectivity matrix (via FAISS)
limits memory from O(N^2) to O(N*k).

#### FAISS Index

Uses `IndexFlatIP` (exact inner-product search). For L2-normalized
InsightFace embeddings, inner product = cosine similarity. At personal
library scale (<50k faces), exact search is instant (~1ms).

#### Incremental Updates

- **Adding photos**: New faces are assigned to nearest existing cluster
  (or create singleton clusters). Cluster UUIDs are naturally stable.
- **Removing photos**: Full rebuild of FAISS index + full re-cluster
  with medoid-based UUID matching to preserve cluster identity.
- **Threshold change**: Triggers full re-cluster (reuses existing
  FAISS index).

#### Cluster UUID Stability

Each cluster receives a UUID v7 at creation. On full re-cluster,
medoid matching preserves UUIDs: for each old/new cluster, the medoid
(face nearest to centroid) is compared. If the old and new medoids are
similar, the UUID is preserved.

### CLI Commands

| Command | Scope | Description |
|---------|-------|-------------|
| `album refresh` | Single album | Includes face detection |
| `albums refresh` | Batch | Shared FaceAnalysis instance |
| `gallery refresh` | Gallery | Detection + clustering (gated by `faces-enabled`) |
| `album detect-faces` | Single album | Standalone face detection |
| `albums detect-faces` | Batch | Standalone batch face detection |
| `gallery cluster-faces` | Gallery | Standalone detection + clustering |

#### Force-Rebuild Flags

| Context | Flag | Effect |
|---------|------|--------|
| `refresh` commands | `--redetect-faces` | Re-detect all (reuse thumbnails) |
| `refresh` commands | `--refresh-face-thumbs` | Refresh thumbnails + re-detect |
| Standalone commands | `--redetect` | Re-detect all (reuse thumbnails) |
| Standalone commands | `--refresh-thumbs` | Refresh thumbnails + re-detect |
| `gallery cluster-faces` | `--threshold N` | Override clustering threshold |

### Gallery Configuration

```yaml
# .photree/gallery.yaml
link-mode: hardlink
faces-enabled: true                # enable face pipeline (default: true)
face-cluster-threshold: 0.45      # cosine distance threshold (optional, defaults to 0.45)
```
