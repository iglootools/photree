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

import itertools

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
from . import AlbumIndex


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


class BatchImportValidationError(ValueError):
    """Raised when batch import pre-validation fails."""


@dataclass(frozen=True)
class GalleryConflict:
    """A source album whose ID already exists in the gallery."""

    source: Path
    album_id: str
    existing: Path


@dataclass(frozen=True)
class SourceDuplicate:
    """A set of source albums sharing the same ID."""

    album_id: str
    paths: list[Path]


@dataclass(frozen=True)
class TargetConflict:
    """A source album whose target directory already exists."""

    source: Path
    target: Path


def _check_gallery_id_conflicts(
    source_metas: list[tuple[Path, AlbumMetadata]],
    index: AlbumIndex,
) -> None:
    """Raise if any source album ID already exists in the gallery."""
    conflicts = [
        GalleryConflict(source=a, album_id=meta.id, existing=index.id_to_path[meta.id])
        for a, meta in source_metas
        if meta.id in index.id_to_path
    ]
    if conflicts:
        raise BatchImportValidationError(
            f"Album ID(s) already exist in gallery: "
            f"{', '.join(c.source.name for c in conflicts)}"
        )


def _check_source_duplicate_ids(
    source_metas: list[tuple[Path, AlbumMetadata]],
) -> None:
    """Raise if multiple source albums share the same ID."""
    sorted_sources = sorted(source_metas, key=lambda t: t[1].id)
    grouped = {
        aid: [p for p, _ in group]
        for aid, group in itertools.groupby(sorted_sources, key=lambda t: t[1].id)
    }
    dups = [
        SourceDuplicate(album_id=aid, paths=paths)
        for aid, paths in grouped.items()
        if len(paths) > 1
    ]
    if dups:
        raise BatchImportValidationError(
            f"Duplicate album IDs among source albums: "
            f"{', '.join(d.album_id for d in dups)}"
        )


def _check_target_conflicts(albums: list[Path], gallery_dir: Path) -> None:
    """Raise if any target directory already exists."""
    conflicts = [
        TargetConflict(source=a, target=compute_target_dir(gallery_dir, a.name))
        for a in albums
        if compute_target_dir(gallery_dir, a.name).exists()
    ]
    if conflicts:
        raise BatchImportValidationError(
            f"Target(s) already exist: "
            f"{', '.join(c.source.name for c in conflicts)}"
        )


def validate_batch_import(
    albums: list[Path],
    index: AlbumIndex,
    gallery_dir: Path,
) -> None:
    """Pre-validate a batch import.

    Checks:
    1. Source album IDs don't conflict with existing gallery albums
    2. No duplicate IDs among source albums
    3. Target directories don't already exist

    Raises :class:`BatchImportValidationError` on failure.
    """
    source_metas = [
        (a, meta) for a in albums if (meta := load_album_metadata(a)) is not None
    ]
    _check_gallery_id_conflicts(source_metas, index)
    _check_source_duplicate_ids(source_metas)
    _check_target_conflicts(albums, gallery_dir)


def _stage_copy(
    source_dir: Path,
    target_dir: Path,
    *,
    dry_run: bool,
) -> None:
    """Stage 1: copy the album to the gallery."""
    if target_dir.exists():
        raise ValueError(
            f"Target already exists: {target_dir}\n"
            "Cannot import — an album with the same name is already in the gallery."
        )
    if not dry_run:
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(str(source_dir), str(target_dir))


def _stage_generate_id(work_dir: Path, *, dry_run: bool) -> bool:
    """Stage 2: generate a missing album ID. Returns whether one was generated."""
    if load_album_metadata(work_dir) is not None:
        return False
    if not dry_run:
        save_album_metadata(work_dir, AlbumMetadata(id=generate_album_id()))
    return True


def _stage_refresh_jpeg(
    work_dir: Path,
    *,
    dry_run: bool,
    convert_file: Callable[..., Path | None],
) -> bool:
    """Stage 3: refresh JPEGs if stale. Returns whether a refresh was needed."""
    if not _jpeg_is_stale(work_dir):
        return False
    if not dry_run:
        for ms in discover_media_sources(work_dir):
            if (work_dir / ms.img_dir).is_dir():
                album_fixes.refresh_jpeg(
                    work_dir, ms, dry_run=False, convert_file=convert_file
                )
    return True


def _stage_optimize(work_dir: Path, *, link_mode: LinkMode, dry_run: bool) -> bool:
    """Stage 4: optimize links. Returns whether the album had iOS sources."""
    ios_sources = [ms for ms in discover_media_sources(work_dir) if ms.is_ios]
    if not ios_sources:
        return False
    if not dry_run:
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
    return True


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

    _notify(on_stage_start, STAGE_COPY)
    _stage_copy(source_dir, target_dir, dry_run=dry_run)
    _notify(on_stage_end, STAGE_COPY)

    # From here, all operations happen on the target copy.
    # In dry-run mode, operate on the source (read-only checks).
    work_dir = source_dir if dry_run else target_dir

    _notify(on_stage_start, STAGE_ID)
    id_generated = _stage_generate_id(work_dir, dry_run=dry_run)
    _notify(on_stage_end, STAGE_ID)

    _notify(on_stage_start, STAGE_JPEG)
    jpeg_refreshed = _stage_refresh_jpeg(
        work_dir, dry_run=dry_run, convert_file=convert_file
    )
    _notify(on_stage_end, STAGE_JPEG)

    _notify(on_stage_start, STAGE_OPTIMIZE)
    optimized = _stage_optimize(work_dir, link_mode=link_mode, dry_run=dry_run)
    _notify(on_stage_end, STAGE_OPTIMIZE)

    return AlbumImportResult(
        album_name=album_name,
        target_dir=target_dir,
        id_generated=id_generated,
        jpeg_refreshed=jpeg_refreshed,
        optimized=optimized,
    )
