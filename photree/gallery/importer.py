"""Import existing album directories into a gallery.

Copies an album directory into the gallery's ``albums/YYYY/`` structure,
then ensures it has an ID, up-to-date JPEGs, optimized links, and passes
integrity checks.

Both a first import and a reimport build the new copy in a hidden sibling
directory (skipped by album discovery) and only move it into place once every
stage has succeeded. A failure therefore never leaves a half-built album at the
target name, where the next run would mistake it for an imported one.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path

from exiftool import ExifToolHelper  # type: ignore[import-untyped]

from ..album.faces.detect import FaceAnalyzerFactory
from ..album.faces.failures import FaceFailure
from ..album.id import generate_album_id
from ..album.jpeg import ConvertFile, JpegConversionFailure
from ..album.refresh import AlbumRefreshResult, refresh_album_derived_data
from ..album.store.media_metadata import load_media_metadata, save_media_metadata
from ..album.store.metadata import load_album_metadata, save_album_metadata
from ..album.store.protocol import AlbumMetadata
from ..dates import parse_year_prefix
from ..foundation.layout import ALBUMS_DIR, PHOTREE_DIR
from ..foundation.linking import LinkMode

# Import stages
STAGE_COPY = "copy"
STAGE_ID = "id"
STAGE_REFRESH_DERIVED = "refresh-derived"

type RefreshFn = Callable[..., AlbumRefreshResult]
type JpegFailures = tuple[tuple[str, JpegConversionFailure], ...]
type FaceFailures = tuple[tuple[str, FaceFailure], ...]


class TargetExistsError(ValueError):
    """The gallery already has a directory at the import target.

    Carries the path as data so the CLI can render it with ``display_path``.
    """

    def __init__(self, target: Path) -> None:
        self.target = target
        super().__init__(f"Target already exists: {target}")


@dataclass(frozen=True)
class AlbumImportResult:
    """Result of importing a single album into a gallery."""

    album_name: str
    target_dir: Path
    id_generated: bool
    jpeg_failures: JpegFailures = ()
    face_failures: FaceFailures = ()

    @property
    def complete(self) -> bool:
        """Whether derived data was fully rebuilt (no JPEG or face failures)."""
        return not self.jpeg_failures and not self.face_failures


def _notify(callback: Callable[[str], None] | None, stage: str) -> None:
    if callback is not None:
        callback(stage)


def compute_target_dir(gallery_dir: Path, album_name: str) -> Path:
    """Compute the target path: ``<gallery_dir>/albums/YYYY/<album_name>``."""
    year = parse_year_prefix(album_name)
    return gallery_dir / ALBUMS_DIR / year / album_name


def _hidden_sibling(target_dir: Path, suffix: str) -> Path:
    """A dot-prefixed sibling of *target_dir*, invisible to album discovery."""
    return target_dir.parent / f".{target_dir.name}.{suffix}"


# ---------------------------------------------------------------------------
# Build pipeline (shared by import and reimport)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Pipeline:
    """Everything the copy → ID → refresh stages need besides the paths."""

    link_mode: LinkMode
    max_workers: int | None
    convert_file: ConvertFile | None
    exiftool: ExifToolHelper | None
    analyzer_factory: FaceAnalyzerFactory | None
    refresh: RefreshFn
    new_id: Callable[[], str]
    on_stage_start: Callable[[str], None] | None
    on_stage_end: Callable[[str], None] | None

    def stage(self, name: str) -> _StageScope:
        return _StageScope(self, name)

    def generate_id(self, work_dir: Path, *, dry_run: bool) -> bool:
        """Generate a missing album ID. Returns whether one was generated."""
        with self.stage(STAGE_ID):
            if load_album_metadata(work_dir) is not None:
                return False
            if not dry_run:
                save_album_metadata(work_dir, AlbumMetadata(id=self.new_id()))
            return True

    def refresh_derived(self, work_dir: Path, *, dry_run: bool) -> AlbumRefreshResult:
        """Rebuild derived data (browsable, JPEG, media IDs, EXIF, faces).

        Returns the refresh result, carrying the per-file JPEG conversion and
        face detection failures the refresh survived.
        """
        with self.stage(STAGE_REFRESH_DERIVED):
            return self.refresh(
                work_dir,
                link_mode=self.link_mode,
                max_workers=self.max_workers,
                convert_file=self.convert_file,
                exiftool=self.exiftool,
                analyzer_factory=self.analyzer_factory,
                dry_run=dry_run,
            )

    def dry_run(self, source_dir: Path, target_dir: Path) -> AlbumImportResult:
        """Report every stage against the source, mutating nothing."""
        with self.stage(STAGE_COPY):
            pass
        id_generated = self.generate_id(source_dir, dry_run=True)
        refreshed = self.refresh_derived(source_dir, dry_run=True)
        return _import_result(source_dir, target_dir, id_generated, refreshed)

    def build(
        self, source_dir: Path, staging: Path, *, preserve_from: Path | None
    ) -> tuple[bool, AlbumRefreshResult]:
        """Copy *source_dir* to *staging* and bring it to a finished state.

        With *preserve_from*, that album's ID and media-id UUIDs replace the
        source's own metadata before the refresh (reimport).
        """
        with self.stage(STAGE_COPY):
            if staging.exists():
                shutil.rmtree(staging)
            staging.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(str(source_dir), str(staging))
            if preserve_from is not None:
                _restore_photree(preserve_from, staging)
        id_generated = self.generate_id(staging, dry_run=False)
        return id_generated, self.refresh_derived(staging, dry_run=False)


def _import_result(
    source_dir: Path,
    target_dir: Path,
    id_generated: bool,
    refreshed: AlbumRefreshResult,
) -> AlbumImportResult:
    return AlbumImportResult(
        album_name=source_dir.name,
        target_dir=target_dir,
        id_generated=id_generated,
        jpeg_failures=refreshed.jpeg_failures,
        face_failures=refreshed.face_failures,
    )


@dataclass(frozen=True)
class _StageScope:
    """Context manager notifying stage start and (successful) end."""

    pipeline: _Pipeline
    name: str

    def __enter__(self) -> None:
        _notify(self.pipeline.on_stage_start, self.name)

    def __exit__(self, exc_type: object, *_: object) -> None:
        if exc_type is None:
            _notify(self.pipeline.on_stage_end, self.name)


@contextmanager
def _removed_on_failure(staging: Path) -> Generator[None, None, None]:
    """Delete *staging* if the block raises, then re-raise."""
    try:
        yield
    except BaseException:
        # Best-effort cleanup: a second failure here must not mask the first.
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _restore_photree(metadata_src: Path, dst: Path) -> None:
    """Replace ``dst/.photree`` with metadata preserved from *metadata_src*.

    Keeps only the album ID (``album.yaml``) and media-id UUIDs
    (``media-ids/``) from the existing gallery copy; the source's own
    (usually ID-less) metadata and any derived ``cache/`` are discarded so
    the refresh stage rebuilds derived data cleanly.
    """
    photree_dir = dst / PHOTREE_DIR
    if photree_dir.exists():
        shutil.rmtree(photree_dir)
    meta = load_album_metadata(metadata_src)
    if meta is not None:
        save_album_metadata(dst, meta)
    media_meta = load_media_metadata(metadata_src)
    if media_meta is not None:
        save_media_metadata(dst, media_meta)


def _swap_into_place(existing_dir: Path, staging: Path, target_dir: Path) -> None:
    """Replace the gallery album with the staged rebuild.

    Moves the live album aside, moves *staging* into *target_dir* (which may
    differ from *existing_dir* on a rename), then removes the old copy. Two
    renames keep the window where neither copy exists as small as possible.
    If the second rename fails, the live album is moved back before the error
    propagates, so a failed swap never loses the gallery copy.
    """
    backup = _hidden_sibling(target_dir, "old")
    if backup.exists():
        shutil.rmtree(backup)
    existing_dir.rename(backup)
    try:
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        staging.rename(target_dir)
    except BaseException:
        backup.rename(existing_dir)
        raise
    shutil.rmtree(backup)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def import_album(
    *,
    source_dir: Path,
    gallery_dir: Path,
    link_mode: LinkMode = LinkMode.HARDLINK,
    dry_run: bool = False,
    on_stage_start: Callable[[str], None] | None = None,
    on_stage_end: Callable[[str], None] | None = None,
    convert_file: ConvertFile | None = None,
    max_workers: int | None = None,
    exiftool: ExifToolHelper | None = None,
    analyzer_factory: FaceAnalyzerFactory | None = None,
    refresh: RefreshFn = refresh_album_derived_data,
    new_id: Callable[[], str] = generate_album_id,
) -> AlbumImportResult:
    """Import an album directory into a gallery.

    1. Copy the album next to ``<gallery_dir>/albums/YYYY/<album_name>/``
    2. Generate album ID if missing
    3. Refresh derived data (browsable, JPEG, media IDs, EXIF cache, faces)
    4. Move the finished copy into place

    The browsable refresh in step 3 detects that copied files use the
    wrong link mode and rebuilds them as hardlinks/symlinks.

    Raises :class:`TargetExistsError` if the target directory already exists,
    or :class:`~photree.dates.DatePrefixError` (a
    :class:`ValueError`) if the album name has no year prefix.
    """
    target_dir = compute_target_dir(gallery_dir, source_dir.name)
    if target_dir.exists():
        raise TargetExistsError(target_dir)
    pipeline = _Pipeline(
        link_mode=link_mode,
        max_workers=max_workers,
        convert_file=convert_file,
        exiftool=exiftool,
        analyzer_factory=analyzer_factory,
        refresh=refresh,
        new_id=new_id,
        on_stage_start=on_stage_start,
        on_stage_end=on_stage_end,
    )
    if dry_run:
        return pipeline.dry_run(source_dir, target_dir)

    staging = _hidden_sibling(target_dir, "import")
    with _removed_on_failure(staging):
        id_generated, refreshed = pipeline.build(
            source_dir, staging, preserve_from=None
        )
        staging.rename(target_dir)
    return _import_result(source_dir, target_dir, id_generated, refreshed)


def reimport_album(
    *,
    source_dir: Path,
    gallery_dir: Path,
    existing_dir: Path,
    link_mode: LinkMode = LinkMode.HARDLINK,
    dry_run: bool = False,
    on_stage_start: Callable[[str], None] | None = None,
    on_stage_end: Callable[[str], None] | None = None,
    convert_file: ConvertFile | None = None,
    max_workers: int | None = None,
    exiftool: ExifToolHelper | None = None,
    analyzer_factory: FaceAnalyzerFactory | None = None,
    refresh: RefreshFn = refresh_album_derived_data,
    new_id: Callable[[], str] = generate_album_id,
) -> AlbumImportResult:
    """Replace an already-imported album's media with the source's.

    Preserves the existing gallery copy's ``.photree/`` metadata (album ID +
    media-id UUIDs), rebuilds derived data from the new media, and swaps the
    result into place. *existing_dir* is the album's current gallery location,
    which may differ from the recomputed target on a rename. The original copy
    is left untouched if any step fails.

    Raises :class:`TargetExistsError` when a rename would land on a directory
    that is already taken, or :class:`~photree.dates.DatePrefixError`
    (a :class:`ValueError`) if the album name has no year prefix.
    """
    target_dir = compute_target_dir(gallery_dir, source_dir.name)
    if target_dir != existing_dir and target_dir.exists():
        raise TargetExistsError(target_dir)
    pipeline = _Pipeline(
        link_mode=link_mode,
        max_workers=max_workers,
        convert_file=convert_file,
        exiftool=exiftool,
        analyzer_factory=analyzer_factory,
        refresh=refresh,
        new_id=new_id,
        on_stage_start=on_stage_start,
        on_stage_end=on_stage_end,
    )
    if dry_run:
        # Nothing is generated on a reimport: the existing ID is preserved.
        return replace(pipeline.dry_run(source_dir, target_dir), id_generated=False)

    staging = _hidden_sibling(target_dir, "reimport")
    with _removed_on_failure(staging):
        id_generated, refreshed = pipeline.build(
            source_dir, staging, preserve_from=existing_dir
        )
        _swap_into_place(existing_dir, staging, target_dir)
    return _import_result(source_dir, target_dir, id_generated, refreshed)
