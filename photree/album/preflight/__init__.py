"""Pre-flight checks for album operations."""

from __future__ import annotations

import shutil
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from exiftool import ExifToolHelper  # type: ignore[import-untyped]

from ...common.exif import try_start_exiftool
from ..integrity import (
    AlbumJpegIntegrityResult,
    IosAlbumFullIntegrityResult,
    check_album_jpeg_integrity,
    check_ios_album_integrity,
)
from ..naming import (
    AlbumNamingResult,
    check_album_naming,
    check_exif_date_match,
    parse_album_name,
)
from ..store.fs import (
    discover_albums,  # noqa: F401 — re-exported for backward compat
    discover_media_sources,
    load_album_metadata,
)
from ..store.protocol import MAIN_MEDIA_SOURCE, MediaSource


def check_sips_available() -> bool:
    """Check whether the macOS ``sips`` tool is on PATH."""
    return shutil.which("sips") is not None


def check_exiftool_available() -> bool:
    """Check whether ``exiftool`` is on PATH."""
    return shutil.which("exiftool") is not None


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


# Backward compat — kept for exporter and tests that still import it.
# Will be removed once all callers migrate.
class AlbumType(StrEnum):
    IOS = "ios"
    STD = "std"

    # Backward compat alias
    OTHER = "std"


def detect_album_type(album_dir: Path) -> AlbumType:
    """Detect album type. Deprecated — use discover_media_sources() instead."""
    media_sources = discover_media_sources(album_dir)
    if any(ms.is_ios for ms in media_sources):
        return AlbumType.IOS
    else:
        return AlbumType.STD


@dataclass(frozen=True)
class AlbumIdCheck:
    """Result of checking whether an album has a valid ID."""

    has_id: bool
    album_id: str | None = None


@dataclass(frozen=True)
class AlbumDirCheck:
    """Result of checking an album directory for expected subdirectories."""

    present: tuple[str, ...]
    missing: tuple[str, ...]
    optional_present: tuple[str, ...] = ()
    optional_absent: tuple[str, ...] = ()

    @property
    def success(self) -> bool:
        return len(self.missing) == 0


def _is_group_present(album_dir: Path, group: tuple[str, ...]) -> bool:
    """Check if all directories in a group are present."""
    return all((album_dir / d).is_dir() for d in group)


def _has_any(album_dir: Path, group: tuple[str, ...]) -> bool:
    """Check if any directory in a group is present."""
    return any((album_dir / d).is_dir() for d in group)


def check_album_dir_structure(album_dir: Path) -> AlbumDirCheck:
    """Check which expected album subdirectories are present in *album_dir*.

    Iterates over all media sources (iOS and std) and checks each media
    source's directory groups independently.  Results are aggregated.

    Per media source, at least one directory group must be fully present:
    - Image group: ``{archive}/orig-img``, ``{name}-img``, ``{name}-jpg``
    - Video group: ``{archive}/orig-vid``, ``{name}-vid``

    Within present groups, all directories are required.
    Directories from absent groups are reported as optional.
    Optional directories (``edit-img``, ``edit-vid``) are always informational.

    For legacy std sources whose ``std-{name}/`` archive directory does not
    yet exist on disk, archive sub-directories will naturally be reported as
    missing or optional depending on which browsable directories are present.
    """
    media_sources = discover_media_sources(album_dir)
    if not media_sources:
        # No media sources found — report missing for main media source
        return AlbumDirCheck(
            present=(),
            missing=MAIN_MEDIA_SOURCE.required_subdirs,
        )

    all_present: list[str] = []
    all_missing: list[str] = []
    all_optional_present: list[str] = []
    all_optional_absent: list[str] = []

    for ms in media_sources:
        image_present = _is_group_present(album_dir, ms.image_subdirs)
        video_present = _is_group_present(album_dir, ms.video_subdirs)

        required = [
            *(
                ms.image_subdirs
                if image_present or _has_any(album_dir, ms.image_subdirs)
                else ()
            ),
            *(
                ms.video_subdirs
                if video_present or _has_any(album_dir, ms.video_subdirs)
                else ()
            ),
        ]

        if not required:
            required = list(ms.required_subdirs)

        optional_from_groups = [
            *(
                ms.image_subdirs
                if not image_present and not _has_any(album_dir, ms.image_subdirs)
                else ()
            ),
            *(
                ms.video_subdirs
                if not video_present and not _has_any(album_dir, ms.video_subdirs)
                else ()
            ),
        ]

        all_present.extend(d for d in required if (album_dir / d).is_dir())
        all_missing.extend(d for d in required if not (album_dir / d).is_dir())
        all_optional_present.extend(
            d
            for d in (*ms.optional_subdirs, *optional_from_groups)
            if (album_dir / d).is_dir()
        )
        all_optional_absent.extend(
            d
            for d in (*ms.optional_subdirs, *optional_from_groups)
            if not (album_dir / d).is_dir()
        )

    return AlbumDirCheck(
        present=tuple(all_present),
        missing=tuple(all_missing),
        optional_present=tuple(all_optional_present),
        optional_absent=tuple(all_optional_absent),
    )


def check_album_dir(
    album_dir: Path,
    expected: tuple[str, ...] = MAIN_MEDIA_SOURCE.all_subdirs,
) -> AlbumDirCheck:
    """Check which expected subdirectories are present in *album_dir*.

    Used by import commands to check specific directories (e.g. SELECTION_DIR).
    """
    return AlbumDirCheck(
        present=tuple(d for d in expected if (album_dir / d).is_dir()),
        missing=tuple(d for d in expected if not (album_dir / d).is_dir()),
    )


@dataclass(frozen=True)
class AlbumPreflightResult:
    """Structured result of all album preflight checks."""

    sips_available: bool
    exiftool_available: bool
    media_source_summary: AlbumMediaSourceSummary
    dir_check: AlbumDirCheck
    album_id_check: AlbumIdCheck | None = None
    ios_integrity: IosAlbumFullIntegrityResult | None = None
    jpeg_check: AlbumJpegIntegrityResult | None = None
    naming: AlbumNamingResult | None = None

    # Backward compat — derived from media_source_summary
    @property
    def album_type(self) -> AlbumType:
        if self.media_source_summary.has_ios:
            return AlbumType.IOS
        else:
            return AlbumType.STD

    # Backward compat alias
    @property
    def integrity(self) -> IosAlbumFullIntegrityResult | None:
        return self.ios_integrity

    @property
    def success(self) -> bool:
        return (
            self.sips_available
            and self.dir_check.success
            and (self.album_id_check is None or self.album_id_check.has_id)
            and (self.ios_integrity is None or self.ios_integrity.success)
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
        labels: list[str] = []
        if self.has_sidecar_warnings:
            labels.append("missing sidecars")
        if self.has_exif_warnings:
            labels.append("exif date mismatch")
        return tuple(labels)

    @property
    def error_labels(self) -> tuple[str, ...]:
        labels: list[str] = []
        if not self.sips_available:
            labels.append("sips not found")
        if not self.dir_check.success:
            labels.append("missing dirs")
        if self.album_id_check is not None and not self.album_id_check.has_id:
            labels.append("missing album id")
        if self.ios_integrity is not None and not self.ios_integrity.success:
            labels.append("integrity errors")
        if self.jpeg_check is not None and not self.jpeg_check.success:
            labels.append("jpeg errors")
        if self.naming is not None and not self.naming.success:
            labels.append("naming errors")
        return tuple(labels)

    def has_fatal_warnings(self, *, fatal_sidecar: bool, fatal_exif: bool) -> bool:
        return (fatal_sidecar and self.has_sidecar_warnings) or (
            fatal_exif and self.has_exif_warnings
        )

    def fatal_warning_labels(
        self, *, fatal_sidecar: bool, fatal_exif: bool
    ) -> tuple[str, ...]:
        """Warning labels that are promoted to errors by fatal flags."""
        labels: list[str] = []
        if fatal_sidecar and self.has_sidecar_warnings:
            labels.append("missing sidecars")
        if fatal_exif and self.has_exif_warnings:
            labels.append("exif date mismatch")
        return tuple(labels)

    def non_fatal_warning_labels(
        self, *, fatal_sidecar: bool, fatal_exif: bool
    ) -> tuple[str, ...]:
        """Warning labels that remain warnings (not promoted by fatal flags)."""
        labels: list[str] = []
        if not fatal_sidecar and self.has_sidecar_warnings:
            labels.append("missing sidecars")
        if not fatal_exif and self.has_exif_warnings:
            labels.append("exif date mismatch")
        return tuple(labels)


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

    if summary.has_ios:
        ios_integrity = check_ios_album_integrity(
            album_dir,
            checksum=checksum,
            on_file_checked=on_file_checked,
        )
    else:
        ios_integrity = None

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
