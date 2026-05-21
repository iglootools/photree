"""Album check modules.

Orchestrates directory-structure, integrity, JPEG, naming, and system
checks for a single album.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from exiftool import ExifToolHelper  # type: ignore[import-untyped]

from ...common.exif import try_start_exiftool
from ...fsprotocol import LinkMode
from ..naming import (
    AlbumNamingResult,
    check_album_naming,
    check_exif_date_match,
    parse_album_name,
)
from ..store.album_discovery import (
    discover_albums,  # noqa: F401 — re-exported for backward compat
)
from ..store.media_sources_discovery import discover_media_sources
from ..store.metadata import load_album_metadata
from ..store.protocol import MediaSource
from .dir_structure import AlbumDirCheck, check_album_dir_structure
from .exif_cache_state import ExifCacheStateCheck, check_exif_cache_state
from .face_state import FaceStateCheck, check_face_state
from .ios import IosMediaSourceIntegrityResult, check_ios_media_source_integrity
from .jpeg import AlbumJpegIntegrityResult, check_album_jpeg_integrity
from .media_metadata import MediaMetadataCheck, check_media_metadata
from .std import StdMediaSourceIntegrityResult, check_std_media_source_integrity
from .system import (
    check_exiftool_available as check_exiftool_available,
    check_sips_available,
)
from .unexpected_dirs import UnexpectedDirsCheck, check_unexpected_dirs

# Union of per-media-source integrity results
MediaSourceIntegrityResult = (
    IosMediaSourceIntegrityResult | StdMediaSourceIntegrityResult
)


@dataclass(frozen=True)
class AlbumMediaSourceSummary:
    """Summary of media sources discovered in an album."""

    media_sources: tuple[MediaSource, ...]

    @property
    def has_ios(self) -> bool:
        return any(ms.is_ios for ms in self.media_sources)

    @property
    def has_std(self) -> bool:
        return any(ms.is_std for ms in self.media_sources)

    @property
    def ios_media_sources(self) -> tuple[MediaSource, ...]:
        return tuple(ms for ms in self.media_sources if ms.is_ios)

    @property
    def std_media_sources(self) -> tuple[MediaSource, ...]:
        return tuple(ms for ms in self.media_sources if ms.is_std)

    @property
    def description(self) -> str:
        """Human-readable summary, e.g. ``main (ios), bruno (std)``."""
        return ", ".join(
            f"{ms.name} ({ms.media_source_type})" for ms in self.media_sources
        )


@dataclass(frozen=True)
class AlbumIdCheck:
    """Result of checking whether an album has a valid ID."""

    has_id: bool
    album_id: str | None = None


@dataclass(frozen=True)
class AlbumIntegrityResult:
    """Unified integrity check result across all media sources in an album.

    Each media source gets a type-appropriate check (iOS or std).
    The album can have both iOS and std media sources simultaneously.
    """

    by_media_source: tuple[tuple[MediaSource, MediaSourceIntegrityResult], ...] = ()

    @property
    def success(self) -> bool:
        return all(result.success for _, result in self.by_media_source)

    @property
    def has_warnings(self) -> bool:
        return any(
            isinstance(result, IosMediaSourceIntegrityResult) and result.has_warnings
            for _, result in self.by_media_source
        )

    @property
    def ios_results(
        self,
    ) -> tuple[tuple[MediaSource, IosMediaSourceIntegrityResult], ...]:
        return tuple(
            (ms, result)
            for ms, result in self.by_media_source
            if isinstance(result, IosMediaSourceIntegrityResult)
        )

    @property
    def std_results(
        self,
    ) -> tuple[tuple[MediaSource, StdMediaSourceIntegrityResult], ...]:
        return tuple(
            (ms, result)
            for ms, result in self.by_media_source
            if isinstance(result, StdMediaSourceIntegrityResult)
        )


@dataclass(frozen=True)
class AlbumPreflightResult:
    """Structured result of all album preflight checks."""

    sips_available: bool
    exiftool_available: bool
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

    @property
    def success(self) -> bool:
        return (
            self.sips_available
            and self.dir_check.success
            and (self.album_id_check is None or self.album_id_check.has_id)
            and (
                self.unexpected_dirs_check is None or self.unexpected_dirs_check.success
            )
            and (self.media_metadata_check is None or self.media_metadata_check.in_sync)
            and (self.integrity is None or self.integrity.success)
            and (self.jpeg_check is None or self.jpeg_check.success)
            and (self.naming is None or self.naming.success)
            and (self.face_state_check is None or self.face_state_check.success)
            and (self.exif_cache_check is None or self.exif_cache_check.success)
        )

    @property
    def has_warnings(self) -> bool:
        return self.has_sidecar_warnings or self.has_exif_warnings

    @property
    def has_sidecar_warnings(self) -> bool:
        return self.integrity is not None and self.integrity.has_warnings

    @property
    def has_exif_warnings(self) -> bool:
        return self.naming is not None and self.naming.has_warnings

    @property
    def warning_labels(self) -> tuple[str, ...]:
        return tuple(
            [
                *(["missing sidecars"] if self.has_sidecar_warnings else []),
                *(["exif date mismatch"] if self.has_exif_warnings else []),
            ]
        )

    @property
    def error_labels(self) -> tuple[str, ...]:
        return tuple(
            [
                *(["sips not found"] if not self.sips_available else []),
                *(["missing dirs"] if not self.dir_check.success else []),
                *(
                    ["missing album id"]
                    if self.album_id_check is not None
                    and not self.album_id_check.has_id
                    else []
                ),
                *(
                    ["unexpected dirs"]
                    if self.unexpected_dirs_check is not None
                    and not self.unexpected_dirs_check.success
                    else []
                ),
                *(
                    ["media metadata stale"]
                    if self.media_metadata_check is not None
                    and not self.media_metadata_check.in_sync
                    else []
                ),
                *(
                    ["integrity errors"]
                    if self.integrity is not None and not self.integrity.success
                    else []
                ),
                *(
                    ["jpeg errors"]
                    if self.jpeg_check is not None and not self.jpeg_check.success
                    else []
                ),
                *(
                    ["naming errors"]
                    if self.naming is not None and not self.naming.success
                    else []
                ),
                *(
                    ["face state stale"]
                    if self.face_state_check is not None
                    and not self.face_state_check.success
                    else []
                ),
                *(
                    ["exif cache stale"]
                    if self.exif_cache_check is not None
                    and not self.exif_cache_check.success
                    else []
                ),
            ]
        )

    def has_fatal_warnings(self, *, fatal_sidecar: bool, fatal_exif: bool) -> bool:
        return (fatal_sidecar and self.has_sidecar_warnings) or (
            fatal_exif and self.has_exif_warnings
        )

    def fatal_warning_labels(
        self, *, fatal_sidecar: bool, fatal_exif: bool
    ) -> tuple[str, ...]:
        """Warning labels that are promoted to errors by fatal flags."""
        return tuple(
            [
                *(
                    ["missing sidecars"]
                    if fatal_sidecar and self.has_sidecar_warnings
                    else []
                ),
                *(
                    ["exif date mismatch"]
                    if fatal_exif and self.has_exif_warnings
                    else []
                ),
            ]
        )

    def non_fatal_warning_labels(
        self, *, fatal_sidecar: bool, fatal_exif: bool
    ) -> tuple[str, ...]:
        """Warning labels that remain warnings (not promoted by fatal flags)."""
        return tuple(
            [
                *(
                    ["missing sidecars"]
                    if not fatal_sidecar and self.has_sidecar_warnings
                    else []
                ),
                *(
                    ["exif date mismatch"]
                    if not fatal_exif and self.has_exif_warnings
                    else []
                ),
            ]
        )


# ---------------------------------------------------------------------------
# Integrity check orchestrator
# ---------------------------------------------------------------------------


def check_album_integrity(
    album_dir: Path,
    *,
    link_mode: LinkMode,
    checksum: bool = True,
    on_file_checked: Callable[[str, bool], None] | None = None,
    media_sources: list[MediaSource],
) -> AlbumIntegrityResult:
    """Run integrity checks for all media sources in an album.

    Dispatches to iOS or std checks based on each media source's type.
    Legacy std sources without archives are skipped.
    """
    results: list[tuple[MediaSource, MediaSourceIntegrityResult]] = []

    for ms in media_sources:
        if ms.is_ios:
            results.append(
                (
                    ms,
                    check_ios_media_source_integrity(
                        album_dir,
                        ms,
                        link_mode=link_mode,
                        checksum=checksum,
                        on_file_checked=on_file_checked,
                    ),
                )
            )
        elif ms.is_std and (album_dir / ms.archive_dir).is_dir():
            results.append(
                (
                    ms,
                    check_std_media_source_integrity(
                        album_dir,
                        ms,
                        link_mode=link_mode,
                        checksum=checksum,
                        on_file_checked=on_file_checked,
                    ),
                )
            )

    return AlbumIntegrityResult(by_media_source=tuple(results))


# ---------------------------------------------------------------------------
# Album check orchestrator
# ---------------------------------------------------------------------------


def run_album_check(
    album_dir: Path,
    *,
    sips_available: bool,
    exiftool: ExifToolHelper | None,
    link_mode: LinkMode,
    checksum: bool = True,
    check_naming_flag: bool = True,
    on_file_checked: Callable[[str, bool], None] | None = None,
) -> AlbumPreflightResult:
    """Run album-specific checks grouped by category.

    Accepts ``sips_available`` and ``exiftool`` as parameters so
    system checks can be done once for batch operations.
    """
    media_sources = discover_media_sources(album_dir)

    # Structure: album identity, directory layout, media metadata
    summary, album_id, dir_check, unexpected_dirs, media_meta = _check_structure(
        album_dir, media_sources
    )

    # Media: file integrity, JPEG completeness
    integrity, jpeg_check = _check_media(
        album_dir,
        media_sources,
        link_mode=link_mode,
        checksum=checksum,
        on_file_checked=on_file_checked,
    )

    # Naming: convention + EXIF timestamp match
    naming = _check_naming(album_dir, exiftool, check_naming_flag)

    # Cache: face state, EXIF cache state
    face_state, exif_cache_state = _check_cache(album_dir, media_sources)

    return AlbumPreflightResult(
        sips_available=sips_available,
        exiftool_available=exiftool is not None,
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


def _check_structure(
    album_dir: Path, media_sources: list[MediaSource]
) -> tuple[
    AlbumMediaSourceSummary,
    AlbumIdCheck,
    AlbumDirCheck,
    UnexpectedDirsCheck,
    MediaMetadataCheck | None,
]:
    """Structure checks: album ID, directories, media sources, media metadata."""
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
    on_file_checked: Callable[[str, bool], None] | None,
) -> tuple[AlbumIntegrityResult | None, AlbumJpegIntegrityResult | None]:
    """Media checks: file integrity + JPEG completeness."""
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
    exiftool: ExifToolHelper | None,
    check_naming_flag: bool,
) -> AlbumNamingResult | None:
    """Naming checks: convention + EXIF timestamp match."""
    if not check_naming_flag:
        return None
    issues = check_album_naming(album_dir.name)
    parsed = parse_album_name(album_dir.name)
    exif_check = (
        check_exif_date_match(
            album_dir, parsed.date, exiftool=exiftool, part=parsed.part
        )
        if exiftool is not None and parsed is not None
        else None
    )
    return AlbumNamingResult(parsed=parsed, issues=issues, exif_check=exif_check)


def _check_cache(
    album_dir: Path, media_sources: list[MediaSource]
) -> tuple[FaceStateCheck | None, ExifCacheStateCheck | None]:
    """Cache checks: face state + EXIF cache state."""
    return (
        check_face_state(album_dir, media_sources=media_sources),
        check_exif_cache_state(album_dir, media_sources=media_sources),
    )


def run_album_preflight(
    album_dir: Path,
    *,
    link_mode: LinkMode | None = None,
    checksum: bool = True,
    check_naming_flag: bool = True,
    check_exif_date_match: bool = True,
    on_file_checked: Callable[[str, bool], None] | None = None,
) -> AlbumPreflightResult:
    """Run all album preflight checks including system checks."""
    from ...fsprotocol import resolve_link_mode

    resolved_link_mode = link_mode or resolve_link_mode(None, album_dir)
    exiftool = try_start_exiftool() if check_exif_date_match else None
    try:
        return run_album_check(
            album_dir,
            sips_available=check_sips_available(),
            exiftool=exiftool,
            link_mode=resolved_link_mode,
            checksum=checksum,
            check_naming_flag=check_naming_flag,
            on_file_checked=on_file_checked,
        )
    finally:
        if exiftool is not None:
            exiftool.__exit__(None, None, None)


def discover_archive_albums(base_dir: Path) -> list[Path]:
    """Recursively discover albums with archive directories under *base_dir*."""
    return discover_albums(base_dir)


# Backward compat alias
discover_ios_albums = discover_archive_albums
