"""EXIF date matching: do an album's media timestamps match its name date?

Part of the full album check (see docs/domain.md, "EXIF Date Matching").
Mismatches are warnings, not errors. Timestamps come from the EXIF cache when
it is current, otherwise from exiftool.

The date arithmetic itself lives in :mod:`photree.dates`; this module applies
it to an album's files and resolves the upstream (archive) files an EXIF fix
would have to touch.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from exiftool import ExifToolHelper  # type: ignore[import-untyped]

from ..common.fs import file_ext
from ..dates import (
    is_day_precision,
    is_valid_date,
    timestamp_in_range,
    timestamp_on_day,
)
from .exif import read_exif_timestamps_by_file
from .exif_cache.store import load_exif_cache
from .formats import VID_EXTENSIONS
from .naming import NamingIssue, ParsedAlbumName
from .store.file_matching import ios_find_files_by_number, std_find_files_by_stem
from .store.media_source import MediaSource, ios_img_number
from .store.media_sources_discovery import (
    discover_browsable_media_files,
    discover_media_sources,
)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExifMismatch:
    """A single file whose EXIF timestamp falls outside the album date range."""

    file_name: str
    timestamp: str
    upstream_files: tuple[str, ...] = ()
    is_ios: bool = False


@dataclass(frozen=True)
class ExifTimestampCheck:
    """Result of validating EXIF timestamps against album date."""

    album_date: str
    total_files: int
    mismatches: tuple[ExifMismatch, ...]
    no_exact_album_date_match: bool = False

    @property
    def matches(self) -> bool:
        return not self.mismatches and not self.no_exact_album_date_match


@dataclass(frozen=True)
class AlbumNamingResult:
    """Full naming validation result for a single album.

    Combines the name check (:func:`~.naming.check_album_naming`) with the
    EXIF date match, which is why it lives here rather than in the pure
    name-grammar module.
    """

    parsed: ParsedAlbumName | None
    issues: tuple[NamingIssue, ...]
    exif_check: ExifTimestampCheck | None

    @property
    def success(self) -> bool:
        # EXIF mismatch is a warning, not a failure
        return self.parsed is not None and not self.issues

    @property
    def has_warnings(self) -> bool:
        return self.exif_check is not None and not self.exif_check.matches


# ---------------------------------------------------------------------------
# EXIF date match
# ---------------------------------------------------------------------------


def _upstream_dirs(ms: MediaSource, *, is_video: bool) -> tuple[str, ...]:
    """Directories holding the files an EXIF fix must touch for one item."""
    match (ms.is_ios, is_video):
        case (True, True):
            return (ms.orig_vid_dir, ms.edit_vid_dir)
        case (True, False):
            return (ms.orig_img_dir, ms.edit_img_dir)
        case (False, True):
            return (ms.vid_dir,)
        case (False, False):
            # Include both img (source of truth) and jpg (derived) so the
            # exiftool fix command updates all files in one go.
            return (ms.img_dir, ms.jpg_dir)


def _resolve_upstream_files(
    album_dir: Path,
    file_path: Path,
    media_sources: list[MediaSource],
) -> tuple[tuple[str, ...], bool]:
    """Find upstream source files for a browsable file.

    Returns ``(upstream_relative_paths, is_ios)``.
    """
    dir_part = str(file_path.relative_to(album_dir).parent)
    filename = file_path.name

    # Find the media source that owns this directory
    ms = next(
        (m for m in media_sources if dir_part in (m.jpg_dir, m.vid_dir, m.img_dir)),
        None,
    )
    if ms is None:
        return ((), False)

    def find(directory: Path) -> list[str]:
        return (
            ios_find_files_by_number({ios_img_number(filename)}, directory)
            if ms.is_ios
            else std_find_files_by_stem({Path(filename).stem}, directory)
        )

    dirs = _upstream_dirs(ms, is_video=file_ext(filename) in VID_EXTENSIONS)
    upstream = tuple(
        f"{d}/{uf}"
        for d in dirs
        if (album_dir / d).is_dir()
        for uf in find(album_dir / d)
    )
    return (upstream, ms.is_ios)


def _no_exact_album_date_match(
    file_timestamps: list[tuple[Path, datetime]], album_date: str, part: str | None
) -> bool:
    """For single-day albums, at least one file must match the album date exactly.

    Relaxed for part > 01 (continuation albums where all files may spill into
    the next day).
    """
    is_continuation = part is not None and part > "01"
    return (
        is_day_precision(album_date)
        and not is_continuation
        and not any(timestamp_on_day(ts, album_date) for _, ts in file_timestamps)
    )


def _exif_mismatches(
    album_dir: Path, file_timestamps: list[tuple[Path, datetime]], album_date: str
) -> tuple[ExifMismatch, ...]:
    media_sources = discover_media_sources(album_dir)
    return tuple(
        ExifMismatch(
            file_name=str(f.relative_to(album_dir)),
            timestamp=ts.isoformat(),
            upstream_files=upstream,
            is_ios=is_ios,
        )
        for f, ts in file_timestamps
        if not timestamp_in_range(ts, album_date)
        for upstream, is_ios in [_resolve_upstream_files(album_dir, f, media_sources)]
    )


def check_exif_date_match(
    album_dir: Path,
    album_date: str,
    *,
    exiftool: ExifToolHelper | None = None,
    part: str | None = None,
) -> ExifTimestampCheck | None:
    """Check EXIF timestamps of all media files against the album date.

    Reads from the EXIF cache when available and fresh. Falls back to
    exiftool when the cache is missing or stale.

    Returns ``None`` if no media files found or no timestamps could be read,
    and when *album_date* is not a real date: the naming check reports that
    as an ``invalid-date`` error, and there is no range to compare against.
    """
    if not is_valid_date(album_date):
        return None

    file_timestamps = _read_timestamps_from_cache_or_exiftool(
        album_dir, exiftool=exiftool
    )
    if not file_timestamps:
        return None

    return ExifTimestampCheck(
        album_date=album_date,
        total_files=len(file_timestamps),
        mismatches=_exif_mismatches(album_dir, file_timestamps, album_date),
        no_exact_album_date_match=_no_exact_album_date_match(
            file_timestamps, album_date, part
        ),
    )


# ---------------------------------------------------------------------------
# EXIF cache integration
# ---------------------------------------------------------------------------


def _read_timestamps_from_cache_or_exiftool(
    album_dir: Path,
    *,
    exiftool: ExifToolHelper | None,
) -> list[tuple[Path, datetime]]:
    """Read timestamps from EXIF cache if fresh, else fall back to exiftool."""
    cached = _try_read_from_cache(album_dir)
    if cached is not None:
        return cached

    files = discover_browsable_media_files(album_dir)
    if not files:
        return []
    return read_exif_timestamps_by_file(files, exiftool=exiftool)


def _try_read_from_cache(album_dir: Path) -> list[tuple[Path, datetime]] | None:
    """Try to read all timestamps from the EXIF cache.

    Returns ``None`` if any media source has no cache file, or one written in
    an older layout (see ``exif_cache.protocol.EXIF_CACHE_VERSION``). An empty
    cache file (written for sources with no browsable files) is valid.

    Trusts cached entries without per-file mtime verification — the
    cache is validated at write time during ``album refresh``. Use
    ``--refresh-exif-cache`` on check commands to force a re-read.
    """
    media_sources = discover_media_sources(album_dir)
    if not media_sources:
        return None

    caches = [load_exif_cache(album_dir, ms.name) for ms in media_sources]
    current = [cache for cache in caches if cache is not None and cache.is_current]
    if len(current) != len(caches):
        return None

    # Current-layout entries store the album-relative path, so videos resolve
    # to {name}-vid/ rather than being reported under {name}-jpg/.
    # Timestamps are normalised to naive wall-clock time, matching
    # common.exif.parse_timestamp: a cache written with an offset must compare
    # like a fresh exiftool read, and mixing aware/naive values would raise.
    return [
        (
            album_dir / entry.file_name,
            datetime.fromisoformat(entry.timestamp).replace(tzinfo=None),
        )
        for cache in current
        for entry in cache.files.values()
        if entry.timestamp is not None
    ]
