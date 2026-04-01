"""Import existing album directories into a gallery.

Copies an album directory into the gallery's ``albums/YYYY/`` structure,
then ensures it has an ID, up-to-date JPEGs, optimized links, and passes
integrity checks.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ..album import fixes as album_fixes
from ..album import optimize as album_optimize
from ..album.integrity import check_album_jpeg_integrity, check_ios_album_integrity
from ..album.jpeg import convert_single_file
from ..fs import (
    AlbumMetadata,
    LinkMode,
    discover_media_sources,
    generate_album_id,
    load_album_metadata,
    parse_album_year,
    save_album_metadata,
)


# Import stages
STAGE_COPY = "copy"
STAGE_ID = "id"
STAGE_JPEG = "jpeg"
STAGE_OPTIMIZE = "optimize"


@dataclass(frozen=True)
class AlbumImportResult:
    """Result of importing a single album into a gallery."""

    album_name: str
    target_dir: Path
    id_generated: bool
    jpeg_refreshed: bool
    optimized: bool


def _notify(callback: Callable[[str], None] | None, stage: str) -> None:
    if callback is not None:
        callback(stage)


def compute_target_dir(gallery_dir: Path, album_name: str) -> Path:
    """Compute the target path: ``<gallery_dir>/albums/YYYY/<album_name>``."""
    year = parse_album_year(album_name)
    return gallery_dir / "albums" / year / album_name


def _jpeg_is_stale(album_dir: Path) -> bool:
    """Check if any media source has missing JPEGs."""
    result = check_album_jpeg_integrity(album_dir)
    return any(not check.success for _, check in result.by_media_source)


def import_album(
    *,
    source_dir: Path,
    gallery_dir: Path,
    link_mode: LinkMode = LinkMode.HARDLINK,
    dry_run: bool = False,
    on_stage_start: Callable[[str], None] | None = None,
    on_stage_end: Callable[[str], None] | None = None,
    convert_file: Callable[..., Path | None] = convert_single_file,
) -> AlbumImportResult:
    """Import an album directory into a gallery.

    1. Copy the album to ``<gallery_dir>/albums/YYYY/<album_name>/``
    2. Generate album ID if missing
    3. Refresh JPEGs if stale
    4. Optimize (replace copies with links)

    Raises :class:`ValueError` if the target directory already exists or
    the album name cannot be parsed.
    """
    album_name = source_dir.name
    target_dir = compute_target_dir(gallery_dir, album_name)

    if target_dir.exists():
        raise ValueError(
            f"Target already exists: {target_dir}\n"
            "Cannot import — an album with the same name is already in the gallery."
        )

    # ── Stage 1: copy ──
    _notify(on_stage_start, STAGE_COPY)
    if not dry_run:
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(str(source_dir), str(target_dir))
    _notify(on_stage_end, STAGE_COPY)

    # From here, all operations happen on the target copy.
    # In dry-run mode, operate on the source (read-only checks).
    work_dir = source_dir if dry_run else target_dir

    # ── Stage 2: generate ID ──
    _notify(on_stage_start, STAGE_ID)
    id_generated = False
    if load_album_metadata(work_dir) is None:
        id_generated = True
        if not dry_run:
            save_album_metadata(work_dir, AlbumMetadata(id=generate_album_id()))
    _notify(on_stage_end, STAGE_ID)

    # ── Stage 3: refresh JPEG ──
    _notify(on_stage_start, STAGE_JPEG)
    jpeg_refreshed = False
    if _jpeg_is_stale(work_dir):
        jpeg_refreshed = True
        if not dry_run:
            for ms in discover_media_sources(work_dir):
                if (work_dir / ms.img_dir).is_dir():
                    album_fixes.refresh_jpeg(
                        work_dir, ms, dry_run=False, convert_file=convert_file
                    )
    _notify(on_stage_end, STAGE_JPEG)

    # ── Stage 4: optimize ──
    _notify(on_stage_start, STAGE_OPTIMIZE)
    ios_sources = [ms for ms in discover_media_sources(work_dir) if ms.is_ios]
    if ios_sources and not dry_run:
        integrity = check_ios_album_integrity(work_dir, checksum=True)
        mismatched = [
            ms.name
            for ms, result in integrity.by_media_source
            if not result.combined_heic.files_match_sources
            or not result.combined_mov.files_match_sources
        ]
        if mismatched:
            raise ValueError(
                f"Pre-optimize integrity check failed for media source(s): "
                f"{', '.join(mismatched)}. "
                "Browsable files do not match their archival sources."
            )
        album_optimize.optimize_album(work_dir, link_mode=link_mode)
    _notify(on_stage_end, STAGE_OPTIMIZE)

    return AlbumImportResult(
        album_name=album_name,
        target_dir=target_dir,
        id_generated=id_generated,
        jpeg_refreshed=jpeg_refreshed,
        optimized=bool(ios_sources),
    )
