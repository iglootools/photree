# Domain Concepts

This document defines the concepts photree works with: what they are, how they
relate, and the rules that govern them. It is the shared vocabulary for users
and implementors alike.

It covers the *what*. For the on-disk layout, metadata file formats, and the
algorithms behind refresh, import, and face clustering, see
[internals.md](./internals.md). For step-by-step workflows, see
[usage.md](./usage.md).

## Overview

```
Gallery
├── Albums ─────────────── one event, day, or period
│   └── Media sources ──── one per person / device (ios-main, std-nelu, ...)
│       └── Media items ── images and videos, each with variants
│                          (original, edited, sidecars, browsable, JPEG)
└── Collections ────────── group albums, media items, and other collections
```

- A **gallery** is the root of a photo library. It holds albums and collections.
- An **album** is the unit of organization: a directory of photos and videos
  from one event, day, or period, named after its date and title.
- An album is fed by one or more **media sources**, each holding the archive
  of one person's or one device's photos.
- A media source contains **media items** (images and videos), each of which
  may exist in several **variants**.
- A **collection** groups albums, media items, and other collections without
  moving or copying them.

Everything is a plain directory. There is no database: photree's state lives in
directory names and small YAML files under `.photree/`.

## Gallery

A gallery is a directory marked by `.photree/gallery.yaml`, with two managed
subtrees:

- `albums/YYYY/<album-name>/` — albums, grouped by the year of their date.
- `collections/YYYY/<collection-name>/` — dated collections, by start year;
  dateless collections live directly under `collections/`.

Content placed elsewhere in the gallery is not managed by photree. Gallery-wide
settings (default link mode, face detection) live in `gallery.yaml`.

Albums can also live outside a gallery: the `album` and `albums` commands work
on any album directory. **Importing into the gallery** (`gallery import`) is
what places an album under `albums/YYYY/` and makes it eligible for collections,
the browsable tree, and face clustering.

Most operations come in three scopes:

| Scope | Operates on |
|-------|-------------|
| `album <op>` | a single album directory |
| `albums <op>` | a set of album directories (scanned or listed), no gallery needed |
| `gallery <op>` | every album and collection in a gallery |

## Album

An album is a directory containing `.photree/album.yaml` and at least one media
source. Its identity comes from two places:

- Its **name**, which encodes its date, title, and optional series, location,
  and tags (see [Album Naming](#album-naming)).
- Its **ID**, a UUID assigned at `album import` / `album init` and preserved
  across renames and re-imports (see [Identifiers](#identifiers)).

### Album Naming

```
DATE - [PART - ] [Series - ] Title [@ Location] [tags]
```

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
Splits one day into several albums. Only valid for single-day dates
(`YYYY-MM-DD`); ranges and lower precisions must not have a part number.

**Series** (optional) — free text grouping related albums (e.g. the days of a
trip). Contiguous albums sharing a series form an
[implicit collection](#lifecycle). Must not contain ` - `.

**Title** (required) — free text, must not contain ` - `.

**Location** (optional) — free text after `@`. May contain commas
(e.g. `Banff NP, AB, CA`).

**Tags** (optional) — `[kebab-case-slug, ...]` at the end. Only `private` is
currently allowed.

Constraints:

- The date must be a real calendar date (`2024-02-30` is rejected), and a
  range must not end before it starts.
- 255 bytes maximum for the full directory name.
- ` - ` (space-dash-space) is the field separator and must not appear inside
  Title or Series (a hyphenated word without surrounding spaces is fine).
- `@` is reserved for the location separator.
- Spacing must be canonical.

Examples:

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

The album's **date** is the single source of truth for when it happened:
photree derives organization from names, not from EXIF. EXIF timestamps are
only used to *verify* that the media matches the name (see
[EXIF Date Matching](#exif-date-matching)).

### Date Collisions

Two non-private single-day albums on the same date must be told apart by part
numbers. Two albums named `2024-07-14 - Hiking` and `2024-07-14 - Dinner` are a
**date collision**; `2024-07-14 - 01 - Hiking` and `2024-07-14 - 02 - Dinner`
are not. Collisions are detected across the whole gallery (and across an import
batch) and block `gallery refresh` and `gallery import`.

### Private Albums

An album tagged `[private]` holds content that must not be mixed with public
content. Privacy affects where the album is rendered (`browsable/private/`) and
which collections may contain it (see
[Private Tag Virality](#private-tag-virality)).

When an album set uses part numbering:

- Private part numbering is independent from public albums.
- When numbered, a private part corresponds to the matching public part
  (`01 [private]` is the private counterpart of public `01`).
- Gaps in private part numbers are expected — only parts with private content
  get a private album.
- A private album may be unnumbered even when public albums are numbered
  (catch-all private content for the day).

Private albums are exempt from date collision detection.

## Media Source

A media source is a named archive of photos and videos within an album — the
contribution of one person or one device. An album usually has a single source
named `main`; a shared trip might add `bruno` (another iPhone) and `nelu` (a
friend's camera).

There are two kinds:

| | iOS source | std source |
|---|---|---|
| Archive directory | `ios-<name>/` | `std-<name>/` |
| Origin | macOS Image Capture export of an iPhone | any other camera, shared files |
| Media item key | **image number** (`0410` from `IMG_0410.HEIC`) | **filename stem** (`DSC_1234` from `DSC_1234.JPG`) |
| Filename rules | `IMG_` / `IMG_E` / `IMG_O` conventions | none |
| AAE sidecars, Live Photos | yes | no |
| iOS-specific checks and fixes | yes | no |
| JPEG conversion | yes | yes |

Every media source is backed by its archive directory. Browsable directories
without a backing archive are not a media source. A media source name is unique
within an album: `ios-bruno/` and `std-bruno/` would share `bruno-img/` and
`media-ids/bruno.yaml`, so their coexistence is an error.

### Archive, Browsable, and Derived

Each media source has three tiers:

- **Archive** (`ios-<name>/`, `std-<name>/`) — the source of truth. Holds every
  original, every edit, and every sidecar, split into `orig-img/`, `edit-img/`,
  `orig-vid/`, `edit-vid/`. Nothing here is ever generated.
- **Browsable** (`<name>-img/`, `<name>-vid/`) — the *best variant* of each
  item: the edit if one exists, otherwise the original. Built from the archive,
  usually as hardlinks so it costs no extra space.
- **Derived** (`<name>-jpg/`) — JPEG versions of `<name>-img/` for sharing and
  compatibility (HEIC/DNG converted, JPEG/PNG copied as-is).

Browsable and derived directories can always be rebuilt from the archive
(`album refresh`). This is what makes the `archive` export layout a complete
backup.

Deleting a file from a browsable directory is how you curate; `album fix
--rm-upstream` propagates that deletion back to the archive. A browsable
directory that is missing (or a JPEG directory holding none of its expected
files) is not read as a deletion signal, and a run that would remove every item
of an archive is refused unless `--force` is given.

## Media Item

A media item is a single photo or video, identified within its media source by
its **key** (image number for iOS, filename stem for std). One item has one key
and one ID, regardless of how many files represent it.

- **Image** — HEIC, DNG, JPEG, PNG. A Live Photo is an image (its companion
  video travels with it).
- **Video** — a standalone video. MOV for iOS; AVI, MOV, MP4, WMV for std.

### Variants

An item may exist as several files:

| Variant | Description |
|---------|-------------|
| Original | the file as captured |
| Edited | the result of edits applied on the device (crop, filters, ...) |
| Sidecar | Apple Adjustments and Edits (`.AAE`) describing the edits |
| Browsable | the best of original/edited, in `<name>-img/` or `<name>-vid/` |
| JPEG | the browsable image converted to JPEG, in `<name>-jpg/` |

When the same key exists in several image formats, the higher quality wins:
DNG > HEIC > HEIF > JPG/PNG.

### iOS Variants (Image Capture)

macOS Image Capture exports iOS media with the following conventions, which
photree preserves in iOS archives.

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

**Live Photos** (image + companion video):
- `IMG_0410.HEIC` — the image component
- `IMG_0410.MOV` — the companion video (~2-3 second clip)
- `IMG_0410.AAE` — sidecar for the image
- `IMG_E0410.HEIC` (optional, only if edits) — edited image
- `IMG_O0410.AAE` (optional, only if edits) — edited image sidecar
- `IMG_E0410.MOV` (optional, only if edits) — edited companion video
- A Live Photo is detected when Image Capture contains both an image
  and a video with the same number (e.g., IMG_0410.HEIC + IMG_0410.MOV).
- During import, selecting either the image or the video automatically
  imports both. Both files are stored together in `orig-img/` as a unit,
  and the companion video appears in `<name>-img/` (not `<name>-vid/`).
- Only applies to iOS media sources.

Supported formats:

- **Images**: `.dng`, `.heic`, `.heif`, `.jpeg`, `.jpg`, `.png`
  (iOS: `.dng`, `.heic`, `.jpeg`, `.jpg`, `.png`)
- **Videos**: `.avi`, `.mov`, `.mp4`, `.wmv` (iOS: `.mov`)
- **Sidecars** (iOS only): `.aae`

## Importing

Media reaches photree in two steps.

**1. Into an album** (`album import`). The album carries one **staging entry**
per media source to fill, named `to-import-{ios,std}-<media-source>`:

- **iOS staging** is a **selection** — a list of filenames, not the files
  themselves. photree matches each name by image number against the Image
  Capture directory and copies every variant of the matching items into
  `ios-<name>/`. The selection is either a `to-import-ios-<name>/` directory
  (typically an export from Apple Photos, used only for its filenames) or a
  `to-import-ios-<name>.csv` file, or both. Because only names matter, the
  selection can come from anywhere: Photos, a script, a phone, an LLM.
- **std staging** holds the actual files, in `orig/` and optionally `edit/`.
  They are copied into `std-<name>/`, split by extension.

Staging entries are consumed on success. See
[internals.md — Import Staging Directories](./internals.md#import-staging-directories).

**2. Into the gallery** (`gallery import`). The finished album is copied to
`albums/YYYY/<album-name>/`. The album ID is what tells photree an album is
*already imported* — even under a new name. Re-importing (`--reimport`) replaces
the media while preserving the album's identity and its media IDs. See
[internals.md — Gallery Import Behavior](./internals.md#gallery-import-behavior).

## Collection

A collection groups albums, media items, and other collections — a "Canada Trip"
spanning several album days, or a curated "Best of 2024" selection. Members are
referenced by ID, never copied.

### Collection Naming

```
[DATE - ] Title [@ Location] [tags]
```

The date prefix is optional (unlike albums where it is required). Some
collections are atemporal and have no date. The date format follows the
same spec as albums: `YYYY`, `YYYY-MM`, `YYYY-MM-DD`, or ranges with `--`.
Location and tags follow the same rules as albums: `@` separates the
location, `[private]` is the only currently allowed tag.

A collection is classified along three independent axes: **members**,
**lifecycle**, and **strategy**.

### Members

How membership is decided:

- **`manual`** — members are listed explicitly via `collection import`.
  Can contain all member types (albums, collections, images, videos).
- **`smart`** — members are computed by `gallery refresh`.
  Smart collections only group albums and sub-collections — never images or
  videos — and `collection import` is not allowed on them.

### Lifecycle

Who owns the collection's existence:

- **`explicit`** — created and deleted by the user (via `collection init`,
  `collection import`). Not affected by album title changes.
- **`implicit`** — derived from album [series](#album-naming). Created,
  renamed, and deleted automatically by `gallery refresh`. Only **contiguous**
  albums with the same series form a single collection; if the same series
  is interrupted by other albums, each contiguous run produces a separate
  collection (disambiguated by date range in the collection name).
  Private albums never join implicit collections.

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

### Strategy

The rule that selects members:

- **`import`** — members added manually via `collection import`. Default
  for manual collections.
- **`date-range`** — all albums and collections whose date range is **fully
  contained** in the collection's date range (mere overlap is not enough).
  Default for smart explicit collections.
- **`album-series`** — the albums of one contiguous album series. Used by
  implicit collections.
- **`chapter`** — like `date-range`, but chapter collections must not overlap
  in date range with any other chapter collection in the gallery (regardless
  of which `collections/YYYY/` directory it lives in). Ranges include both
  ends, so two chapters sharing a single day overlap; consecutive chapters
  end and start on adjacent days. Chapters partition a
  life into periods (e.g. "2019--2022 - Living in Montreal").

### Valid Combinations

| members | lifecycle | strategy | Description |
|---------|-----------|----------|-------------|
| manual | explicit | import | User-managed via `collection import` |
| smart | explicit | date-range | Auto-populated by date range containment |
| smart | explicit | chapter | Auto-populated by date range, no overlap with other chapters |
| smart | implicit | album-series | Auto-populated from contiguous album series |

Other combinations are rejected at `collection init`, `collection metadata
set`, and `collection check`.

### Private Tag Virality

The `[private]` tag is viral: private content can only live inside
private collections.

- **Non-private collections** cannot contain private members (private
  albums, private sub-collections, or media from private albums).
- **Non-private smart collections** exclude private members during
  `gallery refresh` member materialization.
- **Private smart collections** only include private members — non-private
  albums/collections in the date range are excluded during
  `gallery refresh`.
- **Private manual collections** may contain non-private members (the
  private tag protects the collection, not its contents).

These rules are enforced by `collection check` (validation) and by
`gallery refresh` (materialization for smart collections).

## Identifiers

Albums, collections, images, and videos each have a stable identity that
survives renames. Every identifiable object has two forms of the same ID:

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

Media IDs are attached to media item **keys**, so they are stable only as long
as keys are: a re-export that renumbers iOS files rotates the IDs and breaks
collection references to those items.

## Browsable Tree

`gallery refresh` generates a `browsable/` directory at the gallery root: a
navigable view of the whole gallery made of relative symlinks. It splits content
into `public/` and `private/`, renders albums by year, and renders collections
by year, as all-time (dateless), or by chapter — with each collection's members
nested inside it. It is entirely derived and recreated on every refresh. See
[internals.md — Browsable Directory](./internals.md#browsable-directory).

## Faces

photree detects faces in each album (**face detection**) and groups them by
identity across the gallery (**face clustering**). A **cluster** is a set of
faces believed to belong to the same person; it has a stable UUID that survives
re-clustering. Detection data is a per-album cache; clusters are gallery-level.
Both can be disabled per gallery (`faces-enabled`). See
[internals.md — Face Detection and Clustering Pipeline](./internals.md#face-detection-and-clustering-pipeline).

## Validation

### Light and Full Checks

- **Light check** — names only: naming convention and date collisions. Fast,
  and used as a gate before anything that reorganizes the gallery
  (`gallery refresh`, `gallery import`, `album import`).
- **Full check** — the light check plus structure, metadata, integrity
  (checksums, browsable/archive consistency, JPEG completeness, duplicates),
  EXIF date matching, and cache state. Run by the `check` commands.

See [internals.md — Album Validation Levels](./internals.md#album-validation-levels).

### EXIF Date Matching

The full check compares each file's EXIF capture timestamp against the album
date. Mismatches are warnings, not errors:

- **Single day**: files must fall on the album date or the next day (timezone
  and midnight tolerance), and at least one must fall on the album date itself
  (relaxed for part > 01).
- **Ranges and lower precisions**: files must fall within the range, inclusive.

See [internals.md — EXIF Metadata](./internals.md#exif-metadata).

## Linking and Exporting

### Link Mode

Wherever photree materializes a file that already exists elsewhere (browsable
directories, exports), it uses a **link mode**:

- **`hardlink`** (default) — no extra disk space; survives moving the source.
- **`symlink`** — no extra disk space; works across volumes.
- **`copy`** — independent files, for destinations that support neither.

The gallery sets the default (`gallery.yaml`); `--link-mode` overrides it.

### Share Directory and Export Profiles

**Exporting** copies albums to a **share directory** — a cloud sync folder or
an external volume — marked by a `.photree-share` sentinel file so a mistyped
path can never receive an export. An export is shaped by two layouts:

- **Album layout** — what of each album is exported: `browsable-jpg` (JPEGs
  and videos), `browsable`, `all` (archive, album metadata, and rebuilt
  browsable dirs), or
  `archive` (archive and metadata only, a compact backup).
- **Share layout** — how albums are arranged: `flat`, `albums` (by year), or
  `by-month`.

An **export profile** is a named combination of share directory, layouts, and
link mode in the config file. See [usage.md — Export Albums](./usage.md#export-albums).

## Glossary

| Term | Definition |
|------|------------|
| Album | Directory of media for one event, day, or period; named `DATE - Title` |
| Archive | `ios-<name>/` or `std-<name>/`: originals, edits, and sidecars; the source of truth |
| Browsable | `<name>-img/`, `<name>-vid/`: best variant of each item, rebuilt from the archive |
| Browsable tree | `browsable/` at the gallery root: symlinked view of albums and collections |
| Chapter | Smart collection strategy; date-range collections that must not overlap |
| Collection | Group of albums, media items, and collections, referenced by ID |
| Date collision | Two non-private single-day albums on one date without part numbers |
| Derived | `<name>-jpg/` and `.photree/cache/`: regenerable data |
| External ID | `<type>_<base58>` form of an ID, shown and accepted by the CLI |
| Gallery | Root directory holding `albums/` and `collections/` |
| Image number | Digits of an iOS filename (`0410` in `IMG_E0410.HEIC`); the key of iOS items |
| Implicit collection | Collection derived automatically from a contiguous album series |
| Key | Identifier of a media item within its source (image number or filename stem) |
| Live Photo | iOS image plus a companion video sharing its image number |
| Media source | Named archive of one person's or device's media within an album |
| Part | Two-digit number splitting one day into several albums |
| Private | `[private]` tag; isolates content into private albums and collections |
| Selection | List of filenames used to pick iOS items from Image Capture |
| Series | Album name component grouping contiguous albums into an implicit collection |
| Share directory | Export destination, marked by a `.photree-share` sentinel |
| Sidecar | `.AAE` file describing iOS edits |
| Smart collection | Collection whose members are computed by `gallery refresh` |
| Staging entry | `to-import-{ios,std}-<name>` input to `album import` |
| Variant | One file representation of a media item (original, edited, browsable, JPEG) |
