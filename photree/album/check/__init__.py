"""Album checks: run every structure, integrity, naming and cache check."""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from photree.album.check.dir_structure import AlbumDirCheck, check_album_dir_structure
from photree.album.check.exif_cache_state import (
    ExifCacheStateCheck,
    check_exif_cache_state,
)
from photree.album.check.exif_date import AlbumNamingResult, check_exif_date_match
from photree.album.check.face_state import FaceStateCheck, check_face_state
from photree.album.check.ios import (
    IosMediaSourceIntegrityResult,
    check_ios_media_source_integrity,
)
from photree.album.check.jpeg import (
    AlbumJpegIntegrityResult,
    check_album_jpeg_integrity,
)
from photree.album.check.media_metadata import MediaMetadataCheck, check_media_metadata
from photree.album.check.std import (
    StdMediaSourceIntegrityResult,
    check_std_media_source_integrity,
)
from photree.album.check.unexpected_dirs import (
    UnexpectedDirsCheck,
    check_unexpected_dirs,
)
from photree.album.naming import check_album_naming, parse_album_name
from photree.album.store.album_discovery import discover_albums
from photree.album.store.media_source import MediaSource, MediaSourceType
from photree.album.store.media_sources_discovery import (
    discover_media_sources,
    find_media_source_conflicts,
)
from photree.album.store.metadata import load_album_metadata
from photree.common.exif import ExifTagReader
from photree.common.progress import FileEnd
from photree.foundation.linking import LinkMode

MediaSourceIntegrityResult = (
    IosMediaSourceIntegrityResult | StdMediaSourceIntegrityResult
)


class AlbumCheckFailureKind(StrEnum):
    """A check an album failed; the output layer renders its label."""

    MEDIA_SOURCE_CONFLICT = "media-source-conflict"
    MISSING_DIRS = "missing-dirs"
    MISSING_ALBUM_ID = "missing-album-id"
    UNEXPECTED_DIRS = "unexpected-dirs"
    STALE_MEDIA_METADATA = "stale-media-metadata"
    INTEGRITY = "integrity"
    JPEG = "jpeg"
    NAMING = "naming"
    STALE_FACE_STATE = "stale-face-state"
    STALE_EXIF_CACHE = "stale-exif-cache"


class AlbumCheckWarningKind(StrEnum):
    """A warning an album check raised, which a fatal flag can promote to a failure."""

    MISSING_SIDECARS = "missing-sidecars"
    EXIF_DATE_MISMATCH = "exif-date-mismatch"


@dataclass(frozen=True)
class AlbumMediaSourceSummary:
    """The media sources discovered in an album."""

    media_sources: tuple[MediaSource, ...]

    @property
    def has_ios(self) -> bool:
        """Return whether any of the album's media sources is an iOS one."""
        return any(ms.is_ios for ms in self.media_sources)

    @property
    def description(self) -> str:
        """Human-readable summary, e.g. ``main (ios), bruno (std)``."""
        return ", ".join(
            f"{ms.name} ({ms.media_source_type})" for ms in self.media_sources
        )


@dataclass(frozen=True)
class AlbumIdCheck:
    """Whether the album has an ID in ``.photree/album.yaml``, and which."""

    has_id: bool
    album_id: str | None = None


@dataclass(frozen=True)
class AlbumIntegrityResult:
    """
    Each media source gets a type-appropriate check (iOS or std).

    The album can have both iOS and std media sources simultaneously.
    """

    by_media_source: tuple[tuple[MediaSource, MediaSourceIntegrityResult], ...] = ()

    @property
    def success(self) -> bool:
        """Return whether every media source passed its integrity check."""
        return all(result.success for _, result in self.by_media_source)

    @property
    def has_warnings(self) -> bool:
        """Return whether any iOS media source has warnings (missing sidecars)."""
        return any(
            isinstance(result, IosMediaSourceIntegrityResult) and result.has_warnings
            for _, result in self.by_media_source
        )

    @property
    def ios_results(
        self,
    ) -> tuple[tuple[MediaSource, IosMediaSourceIntegrityResult], ...]:
        """Return the integrity results of the iOS media sources only."""
        return tuple(
            (ms, result)
            for ms, result in self.by_media_source
            if isinstance(result, IosMediaSourceIntegrityResult)
        )

    @property
    def std_results(
        self,
    ) -> tuple[tuple[MediaSource, StdMediaSourceIntegrityResult], ...]:
        """Return the integrity results of the std media sources only."""
        return tuple(
            (ms, result)
            for ms, result in self.by_media_source
            if isinstance(result, StdMediaSourceIntegrityResult)
        )


@dataclass(frozen=True)
class AlbumPreflightResult:
    """
    The results of every check run on one album.

    A check left at ``None`` was not run.
    """

    media_source_summary: AlbumMediaSourceSummary
    dir_check: AlbumDirCheck
    album_id_check: AlbumIdCheck | None = None
    unexpected_dirs_check: UnexpectedDirsCheck | None = None
    media_metadata_check: MediaMetadataCheck | None = None
    integrity: AlbumIntegrityResult | None = None
    jpeg_check: AlbumJpegIntegrityResult | None = None
    naming: AlbumNamingResult | None = None
    face_state_check: FaceStateCheck | None = None
    exif_cache_check: ExifCacheStateCheck | None = None
    media_source_conflicts: tuple[str, ...] = ()
    """Names backed by both ``ios-<name>/`` and ``std-<name>/``.

    When non-empty, the media-source-based checks (structure, integrity,
    JPEG, caches, EXIF) were skipped: their results would be meaningless.
    """

    @property
    def _checks(self) -> tuple[tuple[AlbumCheckFailureKind, bool], ...]:
        """
        Return each check as a (kind, failed) pair.

        The single list both :attr:`success` and :attr:`failures` read, so a
        check cannot fail the album without being reported, or the reverse. A
        check that did not run (``None``) has not failed.
        """
        return (
            (
                AlbumCheckFailureKind.MEDIA_SOURCE_CONFLICT,
                bool(self.media_source_conflicts),
            ),
            (AlbumCheckFailureKind.MISSING_DIRS, not self.dir_check.success),
            (
                AlbumCheckFailureKind.MISSING_ALBUM_ID,
                self.album_id_check is not None and not self.album_id_check.has_id,
            ),
            (
                AlbumCheckFailureKind.UNEXPECTED_DIRS,
                self.unexpected_dirs_check is not None
                and not self.unexpected_dirs_check.success,
            ),
            (
                AlbumCheckFailureKind.STALE_MEDIA_METADATA,
                self.media_metadata_check is not None
                and not self.media_metadata_check.in_sync,
            ),
            (
                AlbumCheckFailureKind.INTEGRITY,
                self.integrity is not None and not self.integrity.success,
            ),
            (
                AlbumCheckFailureKind.JPEG,
                self.jpeg_check is not None and not self.jpeg_check.success,
            ),
            (
                AlbumCheckFailureKind.NAMING,
                self.naming is not None and not self.naming.success,
            ),
            (
                AlbumCheckFailureKind.STALE_FACE_STATE,
                self.face_state_check is not None and not self.face_state_check.success,
            ),
            (
                AlbumCheckFailureKind.STALE_EXIF_CACHE,
                self.exif_cache_check is not None and not self.exif_cache_check.success,
            ),
        )

    @property
    def failures(self) -> tuple[AlbumCheckFailureKind, ...]:
        """Return the checks the album failed, in report order."""
        return tuple(kind for kind, failed in self._checks if failed)

    @property
    def success(self) -> bool:
        """
        Return whether the album passed every check that ran.

        Warnings (missing sidecars, EXIF date mismatches) do not count; see
        :meth:`has_fatal_warnings`.
        """
        return not self.failures

    @property
    def has_warnings(self) -> bool:
        """Return whether the album has sidecar or EXIF date warnings."""
        return self.has_sidecar_warnings or self.has_exif_warnings

    @property
    def has_sidecar_warnings(self) -> bool:
        """Return whether any iOS media source is missing AAE sidecars."""
        return self.integrity is not None and self.integrity.has_warnings

    @property
    def has_exif_warnings(self) -> bool:
        """Return whether some files' EXIF dates do not match the album date."""
        return self.naming is not None and self.naming.has_warnings

    @property
    def warnings(self) -> tuple[AlbumCheckWarningKind, ...]:
        """Return the warnings the album's checks raised."""
        return tuple(
            kind
            for kind, present in (
                (AlbumCheckWarningKind.MISSING_SIDECARS, self.has_sidecar_warnings),
                (AlbumCheckWarningKind.EXIF_DATE_MISMATCH, self.has_exif_warnings),
            )
            if present
        )

    def fatal_warnings(
        self,
        *,
        fatal_sidecar: bool,
        fatal_exif: bool,
    ) -> tuple[AlbumCheckWarningKind, ...]:
        """Return the warnings the fatal flags promote to failures."""
        return tuple(
            kind
            for kind in self.warnings
            if _is_fatal(kind, fatal_sidecar=fatal_sidecar, fatal_exif=fatal_exif)
        )

    def non_fatal_warnings(
        self,
        *,
        fatal_sidecar: bool,
        fatal_exif: bool,
    ) -> tuple[AlbumCheckWarningKind, ...]:
        """Return the warnings that stay warnings under the fatal flags."""
        return tuple(
            kind
            for kind in self.warnings
            if not _is_fatal(kind, fatal_sidecar=fatal_sidecar, fatal_exif=fatal_exif)
        )

    def has_fatal_warnings(self, *, fatal_sidecar: bool, fatal_exif: bool) -> bool:
        """Return whether a warning the fatal flags promote to an error is present."""
        return bool(
            self.fatal_warnings(fatal_sidecar=fatal_sidecar, fatal_exif=fatal_exif),
        )


def _is_fatal(
    kind: AlbumCheckWarningKind,
    *,
    fatal_sidecar: bool,
    fatal_exif: bool,
) -> bool:
    match kind:
        case AlbumCheckWarningKind.MISSING_SIDECARS:
            return fatal_sidecar
        case AlbumCheckWarningKind.EXIF_DATE_MISMATCH:
            return fatal_exif


def check_album_integrity(
    album_dir: Path,
    *,
    link_mode: LinkMode,
    checksum: bool = True,
    on_file_checked: FileEnd | None = None,
    media_sources: list[MediaSource],
) -> AlbumIntegrityResult:
    """
    Check each media source's archive against its browsable directories.

    Each media source gets the iOS or std check that fits its type.
    """
    return AlbumIntegrityResult(
        by_media_source=tuple(
            (
                ms,
                _check_media_source_integrity(
                    album_dir,
                    ms,
                    link_mode=link_mode,
                    checksum=checksum,
                    on_file_checked=on_file_checked,
                ),
            )
            for ms in media_sources
        ),
    )


def _check_media_source_integrity(
    album_dir: Path,
    ms: MediaSource,
    *,
    link_mode: LinkMode,
    checksum: bool,
    on_file_checked: FileEnd | None,
) -> MediaSourceIntegrityResult:
    match ms.media_source_type:
        case MediaSourceType.IOS:
            return check_ios_media_source_integrity(
                album_dir,
                ms,
                link_mode=link_mode,
                checksum=checksum,
                on_file_checked=on_file_checked,
            )
        case MediaSourceType.STD:
            return check_std_media_source_integrity(
                album_dir,
                ms,
                link_mode=link_mode,
                checksum=checksum,
                on_file_checked=on_file_checked,
            )


def run_album_check(
    album_dir: Path,
    *,
    exiftool: ExifTagReader | None,
    link_mode: LinkMode,
    checksum: bool = True,
    check_naming_flag: bool = True,
    on_file_checked: FileEnd | None = None,
) -> AlbumPreflightResult:
    """
    Run every check on one album.

    Takes the *exiftool* session as a parameter so a batch starts it once;
    ``None`` skips the EXIF date match. The caller gates on the system
    dependencies the check needs before running it.

    An iOS/std media source name clash is reported as a failed check (see
    :attr:`AlbumPreflightResult.media_source_conflicts`) rather than raised,
    so a batch check carries on to the next album.
    """
    conflicts = find_media_source_conflicts(album_dir)
    if conflicts:
        return _conflicted_album_result(
            album_dir,
            conflicts,
            check_naming_flag=check_naming_flag,
        )
    media_sources = discover_media_sources(album_dir)

    summary, album_id, dir_check, unexpected_dirs, media_meta = _check_structure(
        album_dir,
        media_sources,
    )

    integrity, jpeg_check = _check_media(
        album_dir,
        media_sources,
        link_mode=link_mode,
        checksum=checksum,
        on_file_checked=on_file_checked,
    )

    naming = _check_naming(album_dir, exiftool, check_naming_flag=check_naming_flag)

    face_state, exif_cache_state = _check_cache(album_dir, media_sources)

    return AlbumPreflightResult(
        media_source_summary=summary,
        dir_check=dir_check,
        album_id_check=album_id,
        unexpected_dirs_check=unexpected_dirs,
        media_metadata_check=media_meta,
        integrity=integrity,
        jpeg_check=jpeg_check,
        naming=naming,
        face_state_check=face_state,
        exif_cache_check=exif_cache_state,
    )


def _conflicted_album_result(
    album_dir: Path,
    conflicts: tuple[str, ...],
    *,
    check_naming_flag: bool,
) -> AlbumPreflightResult:
    """
    Return the result for an album whose media sources cannot be resolved.

    Only the checks that do not depend on media sources run: album ID and
    naming (without the EXIF date match, which reads per-source caches).
    """
    metadata = load_album_metadata(album_dir)
    return AlbumPreflightResult(
        media_source_summary=AlbumMediaSourceSummary(media_sources=()),
        dir_check=AlbumDirCheck(present=(), missing=()),
        album_id_check=AlbumIdCheck(
            has_id=metadata is not None,
            album_id=metadata.id if metadata is not None else None,
        ),
        naming=_check_naming(album_dir, None, check_naming_flag=check_naming_flag),
        media_source_conflicts=conflicts,
    )


def _check_structure(
    album_dir: Path,
    media_sources: list[MediaSource],
) -> tuple[
    AlbumMediaSourceSummary,
    AlbumIdCheck,
    AlbumDirCheck,
    UnexpectedDirsCheck,
    MediaMetadataCheck | None,
]:
    summary = AlbumMediaSourceSummary(media_sources=tuple(media_sources))
    metadata = load_album_metadata(album_dir)
    album_id = AlbumIdCheck(
        has_id=metadata is not None,
        album_id=metadata.id if metadata is not None else None,
    )
    dir_check = check_album_dir_structure(album_dir, media_sources=media_sources)
    unexpected_dirs = check_unexpected_dirs(album_dir, media_sources=media_sources)
    media_meta = (
        check_media_metadata(album_dir, media_sources=media_sources)
        if media_sources
        else None
    )
    return (summary, album_id, dir_check, unexpected_dirs, media_meta)


def _check_media(
    album_dir: Path,
    media_sources: list[MediaSource],
    *,
    link_mode: LinkMode,
    checksum: bool,
    on_file_checked: FileEnd | None,
) -> tuple[AlbumIntegrityResult | None, AlbumJpegIntegrityResult | None]:
    integrity = (
        check_album_integrity(
            album_dir,
            link_mode=link_mode,
            checksum=checksum,
            on_file_checked=on_file_checked,
            media_sources=media_sources,
        )
        if media_sources
        else None
    )
    jpeg_check = (
        check_album_jpeg_integrity(album_dir, media_sources=media_sources)
        if media_sources
        else None
    )
    return (integrity, jpeg_check)


def _check_naming(
    album_dir: Path,
    exiftool: ExifTagReader | None,
    *,
    check_naming_flag: bool,
) -> AlbumNamingResult | None:
    if not check_naming_flag:
        return None
    else:
        parsed = parse_album_name(album_dir.name)
        exif_check = (
            check_exif_date_match(
                album_dir,
                parsed.date,
                exiftool=exiftool,
                part=parsed.part,
            )
            if exiftool is not None and parsed is not None
            else None
        )
        return AlbumNamingResult(
            parsed=parsed,
            issues=check_album_naming(album_dir.name),
            exif_check=exif_check,
        )


def _check_cache(
    album_dir: Path,
    media_sources: list[MediaSource],
) -> tuple[FaceStateCheck | None, ExifCacheStateCheck | None]:
    return (
        check_face_state(album_dir, media_sources=media_sources),
        check_exif_cache_state(album_dir, media_sources=media_sources),
    )


def discover_archive_albums(base_dir: Path) -> list[Path]:
    """Return the albums under *base_dir* (see :func:`discover_albums`)."""
    return discover_albums(base_dir)
