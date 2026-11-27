"""
Import existing album directories into a gallery.

Copies an album directory into the gallery's ``albums/YYYY/`` structure,
then ensures it has an ID, up-to-date JPEGs, optimized links, and passes
integrity checks.

Both a first import and a reimport build the new copy in a hidden sibling
directory (skipped by album discovery) and only move it into place once every
stage has succeeded. A failure therefore never leaves a half-built album at the
target name, where the next run would mistake it for an imported one.
"""

import shutil
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path

from photree.album.faces.detect import FaceAnalyzerFactory
from photree.album.faces.failures import FaceFailure
from photree.album.id import generate_album_id
from photree.album.jpeg import ConvertFile, JpegConversionFailure
from photree.album.refresh import (
    AlbumRefreshResult,
    RefreshFn,
    refresh_album_derived_data,
)
from photree.album.store.media_metadata import load_media_metadata, save_media_metadata
from photree.album.store.metadata import load_album_metadata, save_album_metadata
from photree.album.store.protocol import AlbumMetadata
from photree.common.exif import ExifTagReader
from photree.dates import parse_year_prefix
from photree.foundation.layout import ALBUMS_DIR, PHOTREE_DIR
from photree.foundation.linking import LinkMode

STAGE_COPY = "copy"
STAGE_ID = "id"
STAGE_REFRESH_DERIVED = "refresh-derived"

type JpegFailures = tuple[tuple[str, JpegConversionFailure], ...]
type FaceFailures = tuple[tuple[str, FaceFailure], ...]


class TargetExistsError(ValueError):
    """
    The gallery already has a directory at the import target.

    Carries the path as data so the CLI can render it with ``display_path``.
    """

    def __init__(self, target: Path) -> None:
        """Build the error from the import target that already exists."""
        self.target = target
        super().__init__(f"Target already exists: {target}")


@dataclass(frozen=True)
class AlbumImportResult:
    """The outcome of one album's import: where it went and what derived data failed."""

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


_BACKUP_SUFFIX = "old"


def _hidden_sibling(target_dir: Path, suffix: str) -> Path:
    """Return a dot-prefixed sibling of *target_dir*, invisible to album discovery."""
    return target_dir.parent / f".{target_dir.name}.{suffix}"


def find_reimport_backups(gallery_dir: Path) -> tuple[Path, ...]:
    """
    Return the gallery albums a reimport moved aside and never removed.

    A reimport moves the live album to a hidden ``.<name>.old`` sibling while
    it swaps the rebuilt copy in. One that is still there means the process
    died during the swap: either the album exists only as that hidden copy,
    which album discovery skips, or the copy is a stale duplicate.
    """
    albums_dir = gallery_dir / ALBUMS_DIR
    return tuple(
        sorted(
            backup
            for year_dir in (albums_dir.iterdir() if albums_dir.is_dir() else ())
            if year_dir.is_dir()
            for backup in year_dir.glob(f".*.{_BACKUP_SUFFIX}")
            if backup.is_dir()
        ),
    )


def backed_up_album_dir(backup: Path) -> Path:
    """Return where the album moved aside to *backup* lived before the swap."""
    name = backup.name.removeprefix(".").removesuffix(f".{_BACKUP_SUFFIX}")
    return backup.with_name(name)


@dataclass(frozen=True)
class ImportPipeline:
    """
    Everything the copy → ID → refresh stages need besides the paths.

    One value shared by a first import and a reimport, so a new option or seam
    is added in one place. The defaults are the real implementations; *refresh*
    and *new_id* are seams tests replace.
    """

    link_mode: LinkMode = LinkMode.HARDLINK
    max_workers: int | None = None
    convert_file: ConvertFile | None = None
    exiftool: ExifTagReader | None = None
    analyzer_factory: FaceAnalyzerFactory | None = None
    refresh: RefreshFn = refresh_album_derived_data
    new_id: Callable[[], str] = generate_album_id
    on_stage_start: Callable[[str], None] | None = None
    on_stage_end: Callable[[str], None] | None = None

    def stage(self, name: str) -> _StageScope:
        """Return a scope that notifies the start and successful end of *name*."""
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
        """
        Rebuild derived data (browsable, JPEG, media IDs, EXIF, faces).

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
        return _import_result(
            source_dir,
            target_dir,
            id_generated=id_generated,
            refreshed=refreshed,
        )

    def build(
        self,
        source_dir: Path,
        staging: Path,
        *,
        preserve_from: Path | None,
    ) -> tuple[bool, AlbumRefreshResult]:
        """
        Copy *source_dir* to *staging* and bring it to a finished state.

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
    *,
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

    pipeline: ImportPipeline
    name: str

    def __enter__(self) -> None:
        _notify(self.pipeline.on_stage_start, self.name)

    def __exit__(self, exc_type: object, *_: object) -> None:
        if exc_type is None:
            _notify(self.pipeline.on_stage_end, self.name)


@contextmanager
def _removed_on_failure(staging: Path) -> Generator[None]:
    """Delete *staging* if the block raises, then re-raise."""
    try:
        yield
    except BaseException:
        # Best-effort cleanup: a second failure here must not mask the first.
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _restore_photree(metadata_src: Path, dst: Path) -> None:
    """
    Replace ``dst/.photree`` with metadata preserved from *metadata_src*.

    Keeps only the album ID (``album.yaml``) and media-id UUIDs
    (``media-ids/``) from the existing gallery copy; the source's own
    (usually ID-less) metadata and any derived ``cache/`` are discarded so
    the refresh stage rebuilds derived data cleanly.

    An existing copy without an ``album.yaml`` is not the source's album, so
    the source's own ID and UUIDs are kept instead: dropping them would give
    the album a new ID and orphan every reference to it.
    """
    photree_dir = dst / PHOTREE_DIR
    keep_from = metadata_src if load_album_metadata(metadata_src) is not None else dst
    meta = load_album_metadata(keep_from)
    media_meta = load_media_metadata(keep_from)
    if photree_dir.exists():
        shutil.rmtree(photree_dir)
    if meta is not None:
        save_album_metadata(dst, meta)
    if media_meta is not None:
        save_media_metadata(dst, media_meta)


def swap_into_place(existing_dir: Path, staging: Path, target_dir: Path) -> None:
    """
    Replace the gallery album with the staged rebuild.

    Moves the live album aside, moves *staging* into *target_dir* (which may
    differ from *existing_dir* on a rename), then removes the old copy. Two
    renames keep the window where neither copy exists as small as possible.
    If the second rename fails, the live album is moved back before the error
    propagates, so a failed swap never loses the gallery copy.

    The aside copy sits beside *existing_dir* and is named after it, so a
    process that dies between the renames leaves a copy whose name says where
    it belongs (see :func:`find_reimport_backups`).
    """
    backup = _hidden_sibling(existing_dir, _BACKUP_SUFFIX)
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


_DEFAULT_PIPELINE = ImportPipeline()


def import_album(
    *,
    source_dir: Path,
    gallery_dir: Path,
    pipeline: ImportPipeline = _DEFAULT_PIPELINE,
    dry_run: bool = False,
) -> AlbumImportResult:
    """
    Import an album directory into a gallery.

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
    if dry_run:
        return pipeline.dry_run(source_dir, target_dir)

    staging = _hidden_sibling(target_dir, "import")
    with _removed_on_failure(staging):
        id_generated, refreshed = pipeline.build(
            source_dir,
            staging,
            preserve_from=None,
        )
        staging.rename(target_dir)
    return _import_result(
        source_dir,
        target_dir,
        id_generated=id_generated,
        refreshed=refreshed,
    )


def reimport_album(
    *,
    source_dir: Path,
    gallery_dir: Path,
    existing_dir: Path,
    pipeline: ImportPipeline = _DEFAULT_PIPELINE,
    dry_run: bool = False,
) -> AlbumImportResult:
    """
    Replace an already-imported album's media with the source's.

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
    if dry_run:
        # Nothing is generated on a reimport: the existing ID is preserved.
        return replace(pipeline.dry_run(source_dir, target_dir), id_generated=False)

    staging = _hidden_sibling(target_dir, "reimport")
    with _removed_on_failure(staging):
        id_generated, refreshed = pipeline.build(
            source_dir,
            staging,
            preserve_from=existing_dir,
        )
        swap_into_place(existing_dir, staging, target_dir)
    return _import_result(
        source_dir,
        target_dir,
        id_generated=id_generated,
        refreshed=refreshed,
    )
