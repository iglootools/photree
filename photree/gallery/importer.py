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
from typing import TYPE_CHECKING

from exiftool import ExifToolHelper  # type: ignore[import-untyped]

from ..album.store.metadata import load_album_metadata, save_album_metadata
from ..album.store.media_metadata import load_media_metadata, save_media_metadata
from ..album.id import generate_album_id
from ..album.store.protocol import AlbumMetadata, parse_album_year
from ..fsprotocol import ALBUMS_DIR, PHOTREE_DIR, LinkMode

if TYPE_CHECKING:
    from ..album.faces.detect import FaceAnalyzerFactory


# Import stages
STAGE_COPY = "copy"
STAGE_ID = "id"
STAGE_REFRESH_DERIVED = "refresh-derived"


@dataclass(frozen=True)
class AlbumImportResult:
    """Result of importing a single album into a gallery."""

    album_name: str
    target_dir: Path
    id_generated: bool


def _notify(callback: Callable[[str], None] | None, stage: str) -> None:
    if callback is not None:
        callback(stage)


def compute_target_dir(gallery_dir: Path, album_name: str) -> Path:
    """Compute the target path: ``<gallery_dir>/albums/YYYY/<album_name>``."""
    year = parse_album_year(album_name)
    return gallery_dir / ALBUMS_DIR / year / album_name


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


def _refresh_derived(
    work_dir: Path,
    *,
    link_mode: LinkMode,
    max_workers: int | None,
    convert_file: Callable[..., Path | None] | None,
    exiftool: ExifToolHelper | None,
    analyzer_factory: FaceAnalyzerFactory | None,
    dry_run: bool,
    on_stage_start: Callable[[str], None] | None = None,
    on_stage_end: Callable[[str], None] | None = None,
) -> None:
    """Stage 3: rebuild derived data (browsable, JPEG, media IDs, EXIF, faces)."""
    from ..album.refresh import refresh_album_derived_data

    _notify(on_stage_start, STAGE_REFRESH_DERIVED)
    refresh_album_derived_data(
        work_dir,
        link_mode=link_mode,
        max_workers=max_workers,
        convert_file=convert_file,
        exiftool=exiftool,
        analyzer_factory=analyzer_factory,
        dry_run=dry_run,
    )
    _notify(on_stage_end, STAGE_REFRESH_DERIVED)


def import_album(
    *,
    source_dir: Path,
    gallery_dir: Path,
    link_mode: LinkMode = LinkMode.HARDLINK,
    dry_run: bool = False,
    on_stage_start: Callable[[str], None] | None = None,
    on_stage_end: Callable[[str], None] | None = None,
    convert_file: Callable[..., Path | None] | None = None,
    max_workers: int | None = None,
    exiftool: ExifToolHelper | None = None,
    analyzer_factory: FaceAnalyzerFactory | None = None,
) -> AlbumImportResult:
    """Import an album directory into a gallery.

    1. Copy the album to ``<gallery_dir>/albums/YYYY/<album_name>/``
    2. Generate album ID if missing
    3. Refresh derived data (browsable, JPEG, media IDs, EXIF cache, faces)

    The browsable refresh in step 3 detects that copied files use the
    wrong link mode and rebuilds them as hardlinks/symlinks.

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

    _refresh_derived(
        work_dir,
        link_mode=link_mode,
        max_workers=max_workers,
        convert_file=convert_file,
        exiftool=exiftool,
        analyzer_factory=analyzer_factory,
        dry_run=dry_run,
        on_stage_start=on_stage_start,
        on_stage_end=on_stage_end,
    )

    return AlbumImportResult(
        album_name=album_name,
        target_dir=target_dir,
        id_generated=id_generated,
    )


def _restore_photree(metadata_src: Path, dst: Path) -> None:
    """Replace ``dst/.photree`` with metadata preserved from *metadata_src*.

    Keeps only the album ID (``album.yaml``) and media-id UUIDs
    (``media-ids/``) from the existing gallery copy; the source's own
    (usually ID-less) metadata and any derived ``cache/`` are discarded so
    the refresh stage rebuilds derived data cleanly.
    """
    shutil.rmtree(dst / PHOTREE_DIR, ignore_errors=True)
    meta = load_album_metadata(metadata_src)
    if meta is not None:
        save_album_metadata(dst, meta)
    media_meta = load_media_metadata(metadata_src)
    if media_meta is not None:
        save_media_metadata(dst, media_meta)


def _swap_into_place(existing_dir: Path, staging: Path, target_dir: Path) -> None:
    """Atomically replace the gallery album with the staged rebuild.

    Moves the live album aside, moves *staging* into *target_dir* (which may
    differ from *existing_dir* on a rename), then removes the old copy. Two
    renames keep the window where neither copy exists as small as possible.
    """
    backup = target_dir.parent / f".{target_dir.name}.old"
    if backup.exists():
        shutil.rmtree(backup)
    existing_dir.rename(backup)
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    staging.rename(target_dir)
    shutil.rmtree(backup)


def reimport_album(
    *,
    source_dir: Path,
    gallery_dir: Path,
    existing_dir: Path,
    link_mode: LinkMode = LinkMode.HARDLINK,
    dry_run: bool = False,
    on_stage_start: Callable[[str], None] | None = None,
    on_stage_end: Callable[[str], None] | None = None,
    convert_file: Callable[..., Path | None] | None = None,
    max_workers: int | None = None,
    exiftool: ExifToolHelper | None = None,
    analyzer_factory: FaceAnalyzerFactory | None = None,
) -> AlbumImportResult:
    """Replace an already-imported album's media with the source's.

    Preserves the existing gallery copy's ``.photree/`` metadata (album ID +
    media-id UUIDs), rebuilds derived data from the new media, and swaps the
    result into place atomically. *existing_dir* is the album's current
    gallery location, which may differ from the recomputed target on a
    rename. The original copy is left untouched if any step before the swap
    fails.

    Raises :class:`ValueError` if the album name cannot be parsed.
    """
    album_name = source_dir.name
    target_dir = compute_target_dir(gallery_dir, album_name)

    if dry_run:
        # Read-only: report stages against the source, mutate nothing.
        _notify(on_stage_start, STAGE_COPY)
        _notify(on_stage_end, STAGE_COPY)
        _notify(on_stage_start, STAGE_ID)
        _notify(on_stage_end, STAGE_ID)
        _refresh_derived(
            source_dir,
            link_mode=link_mode,
            max_workers=max_workers,
            convert_file=convert_file,
            exiftool=exiftool,
            analyzer_factory=analyzer_factory,
            dry_run=True,
            on_stage_start=on_stage_start,
            on_stage_end=on_stage_end,
        )
        return AlbumImportResult(
            album_name=album_name, target_dir=target_dir, id_generated=False
        )

    staging = target_dir.parent / f".{album_name}.reimport"
    try:
        _notify(on_stage_start, STAGE_COPY)
        if staging.exists():
            shutil.rmtree(staging)
        staging.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(str(source_dir), str(staging))
        _restore_photree(existing_dir, staging)
        _notify(on_stage_end, STAGE_COPY)

        _notify(on_stage_start, STAGE_ID)
        id_generated = _stage_generate_id(staging, dry_run=False)
        _notify(on_stage_end, STAGE_ID)

        _refresh_derived(
            staging,
            link_mode=link_mode,
            max_workers=max_workers,
            convert_file=convert_file,
            exiftool=exiftool,
            analyzer_factory=analyzer_factory,
            dry_run=False,
            on_stage_start=on_stage_start,
            on_stage_end=on_stage_end,
        )
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    _swap_into_place(existing_dir, staging, target_dir)

    return AlbumImportResult(
        album_name=album_name,
        target_dir=target_dir,
        id_generated=id_generated,
    )
