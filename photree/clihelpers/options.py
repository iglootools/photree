"""Reusable Typer option definitions shared across CLI commands."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from ..album.exporter.protocol import AlbumShareLayout, ShareDirectoryLayout
from ..fsprotocol import LinkMode

# ---------------------------------------------------------------------------
# Check options
# ---------------------------------------------------------------------------

CHECKSUM_OPTION = Annotated[
    bool,
    typer.Option(
        "--checksum/--no-checksum",
        help="Enable/disable SHA-256 checksum verification (default: enabled).",
    ),
]

FATAL_WARNINGS_OPTION = Annotated[
    bool,
    typer.Option(
        "--fatal-warnings",
        "-W",
        help="Treat all warnings as errors (implies --fatal-sidecar).",
    ),
]

FATAL_SIDECAR_OPTION = Annotated[
    bool,
    typer.Option(
        "--fatal-sidecar",
        help="Treat missing-sidecar warnings as errors.",
    ),
]

FATAL_EXIF_DATE_MATCH_OPTION = Annotated[
    bool,
    typer.Option(
        "--fatal-exif-date-match/--no-fatal-exif-date-match",
        help="Treat EXIF date mismatch warnings as errors (default: enabled).",
    ),
]

CHECK_NAMING_OPTION = Annotated[
    bool,
    typer.Option(
        "--check-naming/--no-check-naming",
        help="Enable/disable album naming convention checks (default: enabled).",
    ),
]

CHECK_DATE_PART_COLLISION_OPTION = Annotated[
    bool,
    typer.Option(
        "--check-date-part-collision/--no-check-date-part-collision",
        help="Enable/disable cross-album date collision detection (default: enabled).",
    ),
]

CHECK_EXIF_DATE_MATCH_OPTION = Annotated[
    bool,
    typer.Option(
        "--check-exif-date-match/--no-check-exif-date-match",
        help="Enable/disable EXIF timestamp vs album date validation (default: enabled).",
    ),
]

# ---------------------------------------------------------------------------
# Fix-ios options
# ---------------------------------------------------------------------------

LINK_MODE_OPTION = Annotated[
    LinkMode | None,
    typer.Option(
        "--link-mode",
        help="How to create main files: hardlink (default), symlink, or copy.",
    ),
]

LINK_MODE_REQUIRED_OPTION = Annotated[
    LinkMode,
    typer.Option(
        "--link-mode",
        help="How to create main files: hardlink, symlink, or copy.",
    ),
]

REFRESH_BROWSABLE_OPTION = Annotated[
    bool,
    typer.Option(
        "--refresh-browsable",
        help="Rebuild main-img/ and main-vid/ from orig/edit, then regenerate main-jpg/.",
    ),
]

REFRESH_JPEG_OPTION = Annotated[
    bool,
    typer.Option(
        "--refresh-jpeg",
        help="Refresh main-jpg/ from main-img/ (re-convert all HEIC→JPEG).",
    ),
]

RM_UPSTREAM_OPTION = Annotated[
    bool,
    typer.Option(
        "--rm-upstream",
        help="Propagate deletions from browsing dirs (main-jpg, main-vid) to upstream dirs.",
    ),
]

RM_ORPHAN_OPTION = Annotated[
    bool,
    typer.Option(
        "--rm-orphan",
        help="Delete edited and main files that have no corresponding orig file.",
    ),
]

PREFER_HIGHER_QUALITY_OPTION = Annotated[
    bool,
    typer.Option(
        "--prefer-higher-quality-when-dups",
        help="Delete lower-quality duplicates.",
    ),
]

RM_ORPHAN_SIDECAR_OPTION = Annotated[
    bool,
    typer.Option(
        "--rm-orphan-sidecar",
        help="Delete AAE sidecar files that have no matching media file.",
    ),
]

RM_MISCATEGORIZED_OPTION = Annotated[
    bool,
    typer.Option(
        "--rm-miscategorized",
        help="Delete files in the wrong directory.",
    ),
]

RM_MISCATEGORIZED_SAFE_OPTION = Annotated[
    bool,
    typer.Option(
        "--rm-miscategorized-safe",
        help="Delete miscategorized files only if they already exist in the correct directory.",
    ),
]

MV_MISCATEGORIZED_OPTION = Annotated[
    bool,
    typer.Option(
        "--mv-miscategorized",
        help="Move files in the wrong directory to the correct one.",
    ),
]

# ---------------------------------------------------------------------------
# Common options
# ---------------------------------------------------------------------------

DRY_RUN_OPTION = Annotated[
    bool,
    typer.Option(
        "--dry-run", "-n", help="Print what would happen without modifying files."
    ),
]

CHECK_BEFORE_OPTION = Annotated[
    bool,
    typer.Option(
        "--check/--no-check",
        help="Run integrity checks before optimizing (default: enabled).",
    ),
]

# ---------------------------------------------------------------------------
# Export options
# ---------------------------------------------------------------------------

SHARE_DIR_OPTION = Annotated[
    Optional[Path],
    typer.Option(
        "--share-dir",
        "-s",
        help="Base directory to export into (subdirectories with album names are created).",
        file_okay=False,
        resolve_path=True,
    ),
]

PROFILE_OPTION = Annotated[
    Optional[str],
    typer.Option(
        "--profile",
        "-p",
        help="Exporter profile name from config.",
    ),
]

CONFIG_OPTION = Annotated[
    Optional[str],
    typer.Option(
        "--config",
        "-c",
        help="Path to config file.",
    ),
]

SHARE_LAYOUT_OPTION = Annotated[
    Optional[ShareDirectoryLayout],
    typer.Option(
        "--share-layout",
        help="Share layout: flat (default) or albums.",
    ),
]

ALBUM_LAYOUT_OPTION = Annotated[
    Optional[AlbumShareLayout],
    typer.Option(
        "--album-layout",
        help="Export layout: main-jpg (default), main, or all.",
    ),
]

EXPORT_LINK_MODE_OPTION = Annotated[
    Optional[LinkMode],
    typer.Option(
        "--link-mode",
        help="How to create main files in all layout: hardlink (default), symlink, or copy.",
    ),
]
