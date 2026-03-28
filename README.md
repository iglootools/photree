# photree

![Stable Version](https://img.shields.io/pypi/v/photree?label=stable)
![Pre-release Version](https://img.shields.io/github/v/release/iglootools/photree?label=pre-release&include_prereleases&sort=semver)
![Python Versions](https://img.shields.io/pypi/pyversions/photree)
![Download Stats](https://img.shields.io/pypi/dm/photree)
![GitHub Stars](https://img.shields.io/github/stars/iglootools/photree)
![License](https://img.shields.io/github/license/iglootools/photree)
![CI Status](https://github.com/iglootools/photree/actions/workflows/test.yml/badge.svg?branch=main)

A CLI tool to import, organize, verify, and export iOS photo albums as plain directories — preserving originals, edits, and sidecars without any proprietary database.

[![asciicast](https://asciinema.org/a/vyxPzsMxPtuBoXWQ.svg)](https://asciinema.org/a/vyxPzsMxPtuBoXWQ)

## Main Use Cases

- **Import iOS photos** into organized album directories, preserving originals, edits, and AAE sidecars from macOS Image Capture
- **Browse and curate** using the `main-img/`, `main-jpg/`, and `main-vid/` directories — the best version of each photo/video, ready to view
- **Share albums** by exporting JPEG-compatible versions to cloud sync folders (MEGAsync, Syncthing, etc.) or external drives
- **Back up to external volumes** with full album structure (originals + edits + sidecars) using symlinks or hardlinks to save disk space
- **Verify album integrity** with checksums and structural validation, with actionable fix suggestions

## Non-Goals

- **Not a photo viewer or editor.** photree organizes files on disk — use your favorite viewer (Finder, feh, etc.) to browse `main-img/` or `main-jpg/`.
- **Not a photo management database.** There is no catalog, index, or metadata database. Albums are plain directories, readable by any tool.
- **Not a cloud service.** photree exports to directories — pair it with your own sync tool (MEGAsync, Syncthing, rsync, etc.).
- **Not cross-platform for import.** The import pipeline requires macOS (`sips` for HEIC-to-JPEG conversion). Exported albums are portable.

## Known Limitations

- **macOS required for import.** The `sips` tool (included with macOS) is used for HEIC/DNG-to-JPEG conversion. Import is not supported on Linux. Exported albums work everywhere.
- **iOS-only import source.** The import pipeline is built around macOS Image Capture conventions (IMG_\* naming, AAE sidecars, IMG_E\* edits). Other camera sources are not currently supported.
- **No EXIF-based organization.** Album names and dates are derived from directory names (YYYY-MM-DD convention), not from EXIF metadata.

## Philosophy

- **Plain directories, no lock-in.** Albums are standard filesystem directories. No database, no proprietary format. You can always `ls`, `cp`, `rsync`, or browse with any tool.
- **Preserve everything, organize intelligently.** Originals, edits, and sidecars are archived under `ios/`. The `main-*` directories provide a clean, browsable view without losing source material.
- **Explicit over magic.** Every operation has a dry-run mode. Destructive fixes require explicit flags. The tool tells you what it would do before doing it.
- **Composable with existing tools.** photree handles album structure — pair it with rsync for backups, MEGAsync for cloud sync, or any viewer for browsing.

## Related Projects

- [Apple Photos](https://www.apple.com/macos/photos/) — Apple's built-in photo manager. Great for editing, but uses a proprietary database. photree is for people who want plain directories.
- [Immich](https://immich.app/) / [PhotoPrism](https://www.photoprism.app/) — Self-hosted photo management with a web UI. A good complement if you want a browsable gallery on top of your photree albums.
- [immich-go](https://github.com/simulot/immich-go) — CLI tool to bulk-upload photos to Immich. Can be used to upload photree albums.
- [rsync](https://rsync.samba.org/) / [Syncthing](https://syncthing.net/) / [MEGAsync](https://mega.io/) — File sync tools. photree exports to directories that these tools can sync.
- [ExifTool](https://exiftool.org/) — Metadata extraction and editing. Useful alongside photree for EXIF-based workflows.

## Installation

See [docs/installation.md](https://github.com/iglootools/photree/blob/main/docs/installation.md).

## Usage

See [docs/usage.md](https://github.com/iglootools/photree/blob/main/docs/usage.md).

## Development

See [docs/setup-development-environment.md](https://github.com/iglootools/photree/blob/main/docs/setup-development-environment.md).


## Contribute

Practical information:
- [docs/setup-development-environment.md](https://github.com/iglootools/photree/blob/main/docs/setup-development-environment.md) — development setup
- [docs/building-and-testing.md](https://github.com/iglootools/photree/blob/main/docs/building-and-testing.md) — running tests and checks
- [docs/releasing-and-publishing.md](https://github.com/iglootools/photree/blob/main/docs/releasing-and-publishing.md) — releases and PyPI publishing
- [docs/guidelines.md](https://github.com/iglootools/photree/blob/main/docs/guidelines.md) — project-specific guidelines
- [common-guidelines](https://github.com/iglootools/common-guidelines) — shared coding guidelines

Conceptual information:
- [docs/internals.md](https://github.com/iglootools/photree/blob/main/docs/internals.md) — runtime behavior, design decisions, and external commands
- [docs/architecture.md](https://github.com/iglootools/photree/blob/main/docs/architecture.md) — module dependency graph