"""Batch album checking: each album, then the checks across albums."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from photree.album import check as album_check, naming as album_naming
from photree.album.exif_cache.refresh import refresh_exif_cache
from photree.album.id import format_album_external_id
from photree.album.naming import BatchNamingResult
from photree.album.store.media_metadata import load_media_metadata
from photree.album.store.metadata import load_album_metadata
from photree.albums.cmd_handler import BatchFailure, failures_of, run_album_step
from photree.albums.index import find_duplicate_album_ids
from photree.albums.media_index import find_duplicate_media_ids
from photree.common.exif import ExifTagReader
from photree.common.progress import CheckedItemEnd
from photree.foundation.linking import LinkMode


@dataclass(frozen=True)
class BatchCheckResult:
    """
    Result of batch album checking.

    ``failed_albums`` includes albums whose check itself crashed (their reason
    is the error label reported through ``on_end``).
    """

    passed: int
    warned: int
    failed_albums: tuple[Path, ...] = ()
    warned_albums: tuple[Path, ...] = ()  # passed, but with warnings


@dataclass(frozen=True)
class CheckOptions:
    """Per-album check settings shared by every album of a batch."""

    sips_available: bool
    exiftool: ExifTagReader | None
    link_mode_for: Callable[[Path], LinkMode]
    checksum: bool = True
    fatal_sidecar: bool = False
    fatal_exif: bool = True
    check_naming: bool = True


@dataclass(frozen=True)
class _AlbumOutcome:
    album_dir: Path
    ok: bool
    has_warnings: bool


def _album_label(album_name: str, result: album_check.AlbumPreflightResult) -> str:
    """Include the external album ID in the label when available."""
    id_check = result.album_id_check
    return (
        f"{album_name} ({format_album_external_id(id_check.album_id)})"
        if id_check is not None and id_check.album_id is not None
        else album_name
    )


def _check_one(
    album_dir: Path,
    album_name: str,
    opts: CheckOptions,
    on_end: CheckedItemEnd | None,
) -> _AlbumOutcome:
    result = album_check.run_album_check(
        album_dir,
        sips_available=opts.sips_available,
        exiftool=opts.exiftool,
        link_mode=opts.link_mode_for(album_dir),
        checksum=opts.checksum,
        check_naming_flag=opts.check_naming,
    )
    fatal = {"fatal_sidecar": opts.fatal_sidecar, "fatal_exif": opts.fatal_exif}
    ok = result.success and not result.has_fatal_warnings(**fatal)
    err_labels = (
        () if ok else (*result.error_labels, *result.fatal_warning_labels(**fatal))
    )
    if on_end:
        on_end(
            _album_label(album_name, result),
            success=ok,
            error_labels=err_labels,
            warning_labels=result.non_fatal_warning_labels(**fatal),
        )
    return _AlbumOutcome(album_dir, ok, ok and result.has_warnings)


def _check_one_safely(
    album_dir: Path,
    album_name: str,
    opts: CheckOptions,
    on_start: Callable[[str], None] | None,
    on_end: CheckedItemEnd | None,
) -> _AlbumOutcome:
    """Check one album; an album whose check crashes is a failure, not an abort."""
    if on_start:
        on_start(album_name)
    try:
        return _check_one(album_dir, album_name, opts, on_end)
    except Exception as exc:
        if on_end:
            on_end(
                album_name,
                success=False,
                error_labels=(str(exc),),
                warning_labels=(),
            )
        return _AlbumOutcome(album_dir, ok=False, has_warnings=False)


def batch_check(
    albums: list[Path],
    *,
    sips_available: bool,
    exiftool: ExifTagReader | None = None,
    link_mode_for: Callable[[Path], LinkMode],
    checksum: bool = True,
    fatal_sidecar: bool = False,
    fatal_exif: bool = True,
    check_naming: bool = True,
    display_fn: Callable[[Path], str] = lambda p: p.name,
    on_start: Callable[[str], None] | None = None,
    on_end: CheckedItemEnd | None = None,
) -> BatchCheckResult:
    """
    Check multiple albums and return aggregated results.

    Calls ``on_start(name)`` before and
    ``on_end(name, success, error_labels, warning_labels)`` after each album.

    *link_mode_for* gives each album's link mode: the albums of a batch may
    live in different galleries. An album whose link mode cannot be resolved
    fails like one whose check crashed.

    The caller is responsible for managing the exiftool process lifecycle.
    """
    opts = CheckOptions(
        sips_available=sips_available,
        exiftool=exiftool,
        link_mode_for=link_mode_for,
        checksum=checksum,
        fatal_sidecar=fatal_sidecar,
        fatal_exif=fatal_exif,
        check_naming=check_naming,
    )
    outcomes = [
        _check_one_safely(album_dir, display_fn(album_dir), opts, on_start, on_end)
        for album_dir in albums
    ]
    return BatchCheckResult(
        passed=sum(1 for o in outcomes if o.ok),
        warned=sum(1 for o in outcomes if o.has_warnings),
        failed_albums=tuple(o.album_dir for o in outcomes if not o.ok),
        warned_albums=tuple(o.album_dir for o in outcomes if o.has_warnings),
    )


def refresh_exif_caches(
    albums: list[Path],
    exiftool: ExifTagReader | None,
) -> tuple[BatchFailure, ...]:
    """
    Refresh every album's EXIF cache before a check, returning the failures.

    A failing album is a failure of the batch, not an abort: the others are
    refreshed and checked all the same.
    """
    return failures_of(
        run_album_step(
            album_dir,
            partial(refresh_exif_cache, album_dir, exiftool=exiftool),
            name=album_dir.name,
        )
        for album_dir in albums
    )


@dataclass(frozen=True)
class CrossAlbumCheckResult:
    """
    The checks across the albums of a batch.

    *naming_result* is ``None`` when the date-collision check was not run.
    *unreadable_albums* are those whose metadata could not be read: they are
    left out of the duplicate-ID scans.
    """

    naming_result: BatchNamingResult | None
    colliding_albums: frozenset[Path]
    unreadable_albums: frozenset[Path]
    duplicate_album_ids: Mapping[str, tuple[Path, ...]]
    duplicate_media_ids: Mapping[str, tuple[Path, ...]]

    @property
    def failed_albums(self) -> frozenset[Path]:
        """Return every album that one of the cross-album checks failed."""
        return frozenset(
            {
                *self.colliding_albums,
                *self.unreadable_albums,
                *(p for paths in self.duplicate_album_ids.values() for p in paths),
                *(p for paths in self.duplicate_media_ids.values() for p in paths),
            },
        )


def _check_date_collisions(
    albums: list[Path],
) -> tuple[BatchNamingResult, frozenset[Path]]:
    naming_result = album_naming.check_batch_date_collisions(
        [
            (album.name, parsed)
            for album in albums
            if (parsed := album_naming.parse_album_name(album.name)) is not None
        ],
    )
    colliding = {name for _, names in naming_result.date_collisions for name in names}
    return naming_result, frozenset(a for a in albums if a.name in colliding)


def _has_readable_metadata(album_dir: Path) -> bool:
    """Tell whether the album's ID and media-ID files load (or are absent)."""
    try:
        load_album_metadata(album_dir)
        load_media_metadata(album_dir)
    except ValueError:
        # InvalidMetadataError: the per-album check already reported why.
        return False
    return True


def check_cross_album(
    albums: list[Path],
    *,
    check_date_collisions: bool,
) -> CrossAlbumCheckResult:
    """
    Run the checks across *albums*: date collisions, duplicate album and media IDs.

    *check_date_collisions* runs the date-collision check. An album whose
    metadata cannot be read is left out of the duplicate-ID scans and counted
    as failed, so the other albums' results are still reported.
    """
    naming_result, colliding = (
        _check_date_collisions(albums)
        if check_date_collisions
        else (None, frozenset[Path]())
    )
    unreadable = frozenset(a for a in albums if not _has_readable_metadata(a))
    readable = [a for a in albums if a not in unreadable]
    return CrossAlbumCheckResult(
        naming_result=naming_result,
        colliding_albums=colliding,
        unreadable_albums=unreadable,
        duplicate_album_ids={
            k: tuple(v) for k, v in find_duplicate_album_ids(readable).items()
        },
        duplicate_media_ids={
            k: tuple(v) for k, v in find_duplicate_media_ids(readable).items()
        },
    )


@dataclass(frozen=True)
class BatchCheckSummary:
    """The verdict of a batch check: each album counted once."""

    passed: int
    warned: int
    failed_albums: tuple[Path, ...] = ()

    @property
    def success(self) -> bool:
        """Return whether no album failed."""
        return not self.failed_albums


def compute_batch_check_summary(
    albums: list[Path],
    per_album: BatchCheckResult,
    cross_album: CrossAlbumCheckResult,
    refresh_failures: tuple[BatchFailure, ...] = (),
) -> BatchCheckSummary:
    """
    Combine the refresh, per-album and cross-album results into one verdict.

    An album can fail several ways: it is counted once, ``passed`` is whatever
    did not fail, and a failed album is never also counted as warned.
    *failed_albums* is sorted, for a stable report.
    """
    failed = frozenset(
        {
            *per_album.failed_albums,
            *cross_album.failed_albums,
            *(f.album_dir for f in refresh_failures),
        },
    )
    return BatchCheckSummary(
        passed=len(albums) - len(failed),
        warned=len(set(per_album.warned_albums) - failed),
        failed_albums=tuple(sorted(failed)),
    )
