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

### Private Tag Virality

The `[private]` tag is viral: private content can only live inside
private collections.

- **Non-private collections** cannot contain private members (private
  albums, private sub-collections, or media from private albums).
- **Private smart collections** only include private members — non-private
  albums/collections in the date range are excluded during
  `gallery refresh`.
- **Private manual collections** may contain non-private members (the
  private tag protects the collection, not its contents).

These rules are enforced by `collection check` and (for smart
collections) by `gallery refresh`.

### Collection Members

Determines how members are selected:

- **`smart`** — members are managed automatically by `gallery refresh`.
  Smart collections cannot contain image or video members — they only
  group albums and sub-collections. `collection import` is not allowed
  on smart collections.
- **`manual`** — members are listed explicitly via `collection import`.
  Can contain all member types (albums, collections, images, videos).

### Collection Lifecycle

- **`explicit`** — created and deleted by the user (via `collection init`,
  `collection import`). Not affected by album title changes.
- **`implicit`** — derived from album series (the series component parsed
  from album titles). Created, renamed, and deleted automatically by
  `gallery refresh`. Only **contiguous**
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

### Collection Strategy

Determines the rule for member selection:

- **`import`** — members added manually via `collection import`. Default
  for manual collections.
- **`date-range`** — members auto-populated by date range containment.
  Default for smart explicit collections.
- **`album-series`** — members auto-populated from contiguous album
  series. Used by implicit collections.
- **`chapter`** — like `date-range`, but with an additional constraint:
  chapter collections must not overlap in date range with other chapter
  collections. Enforced at both `collection check` and `gallery refresh`.

### Valid Combinations

| members | lifecycle | strategy | Description |
|---------|-----------|----------|-------------|
| manual | explicit | import | User-managed via `collection import` |
| smart | explicit | date-range | Auto-populated by date range containment |
| smart | explicit | chapter | Auto-populated by date range, no overlap with other chapters |
| smart | implicit | album-series | Auto-populated from contiguous album series |

Other combinations are rejected at `collection init`, `collection metadata
set`, and `collection check`.

### Collection Refresh

`gallery refresh` runs the following phases for collections, after the
album media refresh:

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

See [Collection Lifecycle](#collection-lifecycle) for examples.

#### Phase 3: Implicit Collection Refresh

Detects album series and creates/updates/renames/deletes implicit
collections:

1. **Group albums by contiguous series** — albums are sorted
   chronologically (by directory name). Contiguous runs sharing the same
   series form groups. Non-contiguous occurrences of the same series
   produce separate groups.

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
  - `images/` — symlinks to individual JPG files from the album's
    `{name}-jpg/` directory
  - `videos/` — symlinks to individual video files from the album's
    `{name}-vid/` directory
- **Visibility**: Albums and collections with `[private]` tag go under
  `private/`; all others under `public/`.
- **Collection buckets**: `by-year/<YYYY>` for dated collections,
  `all-time/` for dateless, `by-chapter/` for `strategy=chapter`.

### Refresh Strategy

The browsable directory is **deleted and recreated** on each
`gallery refresh`. Before deletion, a safety check validates that
the directory only contains directories and symlinks (no regular files
that could be accidentally destroyed). All symlinks are relative for
gallery portability.

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

## Album Validation Levels

photree has two levels of album validation, used in different contexts:

### Light Check (naming + cross-album)

Validates album directory names against the naming convention and detects
cross-album date collisions. No media file access — only inspects names
and album metadata. Fast, suitable as a pre-validation gate.

Includes:
- Per-album naming validation (parseability, tags, part number rules,
  canonical spacing)
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
files:
  "0410":
    mtime: 1721008370.5
    file-name: IMG_0410.jpg
    timestamp: "2024-07-14T14:32:50"
  "0411":
    mtime: 1721010622.3
    file-name: IMG_0411.jpg
    timestamp: null              # no EXIF timestamp found
```

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
face-cluster-threshold: 0.45      # cosine distance threshold (optional)
```
