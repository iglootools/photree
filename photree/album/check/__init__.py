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
from .ios import IosAlbumFullIntegrityResult, check_ios_album_integrity
from .jpeg import AlbumJpegIntegrityResult, check_album_jpeg_integrity
from .std import StdAlbumFullIntegrityResult, check_std_album_integrity
from .system import (
    check_exiftool_available as check_exiftool_available,
    check_sips_available,
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
class AlbumPreflightResult:
    """Structured result of all album preflight checks."""

    sips_available: bool
    exiftool_available: bool
    media_source_summary: AlbumMediaSourceSummary
    dir_check: AlbumDirCheck
    album_id_check: AlbumIdCheck | None = None
    ios_integrity: IosAlbumFullIntegrityResult | None = None
    std_integrity: StdAlbumFullIntegrityResult | None = None
    jpeg_check: AlbumJpegIntegrityResult | None = None
    naming: AlbumNamingResult | None = None

    @property
    def success(self) -> bool:
        return (
            self.sips_available
            and self.dir_check.success
            and (self.album_id_check is None or self.album_id_check.has_id)
            and (self.ios_integrity is None or self.ios_integrity.success)
            and (self.std_integrity is None or self.std_integrity.success)
            and (self.jpeg_check is None or self.jpeg_check.success)
            and (self.naming is None or self.naming.success)
        )

    @property
    def has_warnings(self) -> bool:
        return self.has_sidecar_warnings or self.has_exif_warnings

    @property
    def has_sidecar_warnings(self) -> bool:
        return self.ios_integrity is not None and self.ios_integrity.has_warnings

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
                    ["ios integrity errors"]
                    if self.ios_integrity is not None and not self.ios_integrity.success
                    else []
                ),
                *(
                    ["std integrity errors"]
                    if self.std_integrity is not None and not self.std_integrity.success
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


def run_album_check(
    album_dir: Path,
    *,
    sips_available: bool,
    exiftool: ExifToolHelper | None,
    checksum: bool = True,
    check_naming_flag: bool = True,
    on_file_checked: Callable[[str, bool], None] | None = None,
) -> AlbumPreflightResult:
    """Run album-specific checks (dir structure, integrity, naming).

    Accepts ``sips_available`` and ``exiftool`` as parameters so
    system checks can be done once for batch operations.
    """
    media_sources = discover_media_sources(album_dir)
    summary = AlbumMediaSourceSummary(media_sources=tuple(media_sources))

    # Album ID check
    metadata = load_album_metadata(album_dir)
    album_id_check = AlbumIdCheck(
        has_id=metadata is not None,
        album_id=metadata.id if metadata is not None else None,
    )

    dir_check = check_album_dir_structure(album_dir)

    ios_integrity = (
        check_ios_album_integrity(
            album_dir, checksum=checksum, on_file_checked=on_file_checked
        )
        if summary.has_ios
        else None
    )

    std_integrity = (
        check_std_album_integrity(
            album_dir, checksum=checksum, on_file_checked=on_file_checked
        )
        if summary.has_std
        else None
    )

    # JPEG check runs for ALL media sources (iOS + std)
    jpeg_check = check_album_jpeg_integrity(album_dir) if media_sources else None

    naming = None
    if check_naming_flag:
        issues = check_album_naming(album_dir.name)
        parsed = parse_album_name(album_dir.name)
        exif_check = None
        if exiftool is not None and parsed is not None:
            exif_check = check_exif_date_match(
                album_dir, parsed.date, exiftool=exiftool, part=parsed.part
            )
        naming = AlbumNamingResult(
            parsed=parsed,
            issues=issues,
            exif_check=exif_check,
        )

    return AlbumPreflightResult(
        sips_available=sips_available,
        exiftool_available=exiftool is not None,
        media_source_summary=summary,
        dir_check=dir_check,
        album_id_check=album_id_check,
        ios_integrity=ios_integrity,
        std_integrity=std_integrity,
        jpeg_check=jpeg_check,
        naming=naming,
    )


def run_album_preflight(
    album_dir: Path,
    *,
    checksum: bool = True,
    check_naming_flag: bool = True,
    check_exif_date_match: bool = True,
    on_file_checked: Callable[[str, bool], None] | None = None,
) -> AlbumPreflightResult:
    """Run all album preflight checks including system checks."""
    exiftool = try_start_exiftool() if check_exif_date_match else None
    try:
        return run_album_check(
            album_dir,
            sips_available=check_sips_available(),
            exiftool=exiftool,
            checksum=checksum,
            check_naming_flag=check_naming_flag,
            on_file_checked=on_file_checked,
        )
    finally:
        if exiftool is not None:
            exiftool.__exit__(None, None, None)


def discover_archive_albums(base_dir: Path) -> list[Path]:
    """Recursively discover albums with archive directories under *base_dir*.

    Finds albums that have iOS (``ios-*/``) or std (``std-*/``) archive
    directories, which are the album types that support archive-based
    operations (optimize, fix-ios, etc.).

    Since all current media source types (iOS and std) have archive
    directories, this is equivalent to :func:`discover_albums`.
    """
    return discover_albums(base_dir)


# Backward compat alias
discover_ios_albums = discover_archive_albums
