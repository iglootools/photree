"""Album naming convention parsing and validation.

Target format::

    DATE - [PART - ] [Series - ] Title [tags]

Where:
- DATE is ``YYYY-MM-DD`` or ``YYYY-MM-DD--YYYY-MM-DD``
- PART is a zero-padded two-digit number (``01``, ``02``, …)
- Tags are ``[tag]`` at the end; only ``[private]`` is currently allowed
- Parenthesised content (e.g. ``(Day 2)``, ``(bis)``) is ordinary title text

This module performs **no** filesystem mutations.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum
from pathlib import Path

from exiftool import ExifToolHelper  # type: ignore[import-untyped]

from .exif import read_exif_timestamps_by_file
from .exif_cache.store import load_exif_cache
from .store.media_sources import (
    ios_find_files_by_number,
    ios_img_number,
    std_find_files_by_stem,
)
from .store.media_sources_discovery import (
    discover_browsable_media_files,
    discover_media_sources,
)
from .store.protocol import ALBUM_DATE_RE, MediaSource

# ---------------------------------------------------------------------------
# Regexes
# ---------------------------------------------------------------------------

# Matches "[tag1, tag2]" at the end of a name
_TAGS_RE = re.compile(r"\s*\[([^\]]+)\]\s*$")

# Prefix-style part number: "XX - rest"
_PREFIX_PART_RE = re.compile(r"^(\d{2}) - (.+)$")

# Single-day date: exactly YYYY-MM-DD (no range, no lower precision)
_DAY_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Kebab-case slug validation for tags
_KEBAB_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

# A bare two-digit segment: the part number in "Series - XX - Title"
_PART_SEGMENT_RE = re.compile(r"^\d{2}$")

# Date-like prefixes that predate the accepted forms (day ranges, enumerated
# days, old-style dash-separated ranges). Matched only to give a better error
# than "unparseable".
_LEGACY_DATE_RE = re.compile(
    r"^("
    r"\d{4}-\d{2}-\d{2}-\d{4}-\d{2}-\d{2}"  # YYYY-MM-DD-YYYY-MM-DD (old range)
    r"|\d{4}-\d{2}-\d{2}-\d{2}-\d{2}"  # YYYY-MM-DD-MM-DD
    r"|\d{4}-\d{2}-\d{2}-\d{2}"  # YYYY-MM-DD-DD
    r"|\d{4}-\d{2}-\d{2}(?:,\d{2})+"  # YYYY-MM-DD,DD (enumerated)
    r") *- *"
)

# Valid tags (whitelist)
VALID_TAGS = frozenset({"private"})


def _is_day_precision(date_str: str) -> bool:
    """Return True when *date_str* is a single day (YYYY-MM-DD)."""
    return _DAY_DATE_RE.match(date_str) is not None


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParsedAlbumName:
    """Parsed album name components."""

    date: str
    part: str | None
    private: bool
    series: str | None
    title: str
    location: str | None


class NamingIssueCode(StrEnum):
    """Kinds of naming convention violation."""

    NAME_TOO_LONG = "name-too-long"
    INVALID_DATE_FORMAT = "invalid-date-format"
    INVALID_DATE = "invalid-date"
    UNPARSEABLE = "unparseable"
    INVALID_TAG_FORMAT = "invalid-tag-format"
    INVALID_TAG = "invalid-tag"
    PART_REQUIRES_DAY_DATE = "part-requires-day-date"
    NON_CANONICAL_SPACING = "non-canonical-spacing"


@dataclass(frozen=True)
class NamingIssue:
    """A single naming convention violation."""

    code: NamingIssueCode
    message: str


class InvalidAlbumDateError(ValueError):
    """An album date matches the naming grammar but is not a real date range.

    E.g. ``2024-02-30`` or ``2024-13``, or a range ending before it starts.
    """

    def __init__(self, album_date: str) -> None:
        self.album_date = album_date
        super().__init__(f"album date {album_date!r} is not a valid date range")


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
    """Full naming validation result for a single album."""

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


@dataclass(frozen=True)
class BatchNamingResult:
    """Cross-album naming checks (date collision detection)."""

    date_collisions: tuple[tuple[str, tuple[str, ...]], ...]

    @property
    def success(self) -> bool:
        return not self.date_collisions


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def _split_tags(name: str) -> tuple[str, tuple[str, ...]]:
    """Split ``"... [a, b]"`` into the name without tags and the tag list."""
    tags_match = _TAGS_RE.search(name)
    if tags_match is None:
        return name, ()
    return (
        name[: tags_match.start()],
        tuple(t.strip() for t in tags_match.group(1).split(",")),
    )


def _split_part_prefix(remainder: str) -> tuple[str | None, str]:
    """Split ``"XX - body"`` into ``(part, body)``; ``(None, remainder)`` otherwise."""
    m = _PREFIX_PART_RE.match(remainder)
    return (m.group(1), m.group(2)) if m is not None else (None, remainder)


def _split_series(body: str, part: str | None) -> tuple[str | None, str | None, str]:
    """Split the body into ``(series, part, raw_title)``.

    With two or more `` - `` segments the first is the series; a following
    bare two-digit segment is a ``Series - XX - Title`` part number (only when
    no prefix part was found and a title follows it).
    """
    segments = [seg.strip() for seg in body.split(" - ") if seg.strip()]
    match segments:
        case []:
            return None, part, ""
        case [title]:
            return None, part, title
        case [series, maybe_part, *rest] if (
            part is None and rest and _PART_SEGMENT_RE.match(maybe_part)
        ):
            return series, maybe_part, " ".join(rest)
        case _:
            return segments[0], part, " ".join(segments[1:])


def _split_location(raw_title: str) -> tuple[str, str | None]:
    """Split ``"Title @ Location"`` into ``(title, location)``."""
    if " @ " not in raw_title:
        return raw_title, None
    title, location = raw_title.split(" @ ", 1)
    return title.strip(), location.strip()


def parse_album_name(name: str) -> ParsedAlbumName | None:
    """Parse an album folder name into components.

    Returns ``None`` if the name does not start with a valid date prefix.
    """
    without_tags, tags = _split_tags(name)
    dm = ALBUM_DATE_RE.match(without_tags)
    if dm is None:
        return None
    prefix_part, body = _split_part_prefix(without_tags[dm.end() :])
    series, part, raw_title = _split_series(body, prefix_part)
    title, location = _split_location(raw_title)
    return ParsedAlbumName(
        date=dm.group(1),
        part=part,
        private="private" in tags,
        series=series,
        title=title,
        location=location,
    )


def reconstruct_name(parsed: ParsedAlbumName) -> str:
    """Build the canonical album name from parsed components."""
    title_with_location = (
        f"{parsed.title} @ {parsed.location}"
        if parsed.location is not None
        else parsed.title
    )
    parts = [
        parsed.date,
        *([f"{int(parsed.part):02d}"] if parsed.part is not None else []),
        *([parsed.series] if parsed.series is not None else []),
        title_with_location,
    ]
    name = " - ".join(parts)
    return f"{name} [private]" if parsed.private else name


# ---------------------------------------------------------------------------
# Naming validation
# ---------------------------------------------------------------------------


# Most Linux and macOS filesystems limit directory names to 255 bytes.
MAX_NAME_BYTES = 255


def _length_issues(album_name: str) -> list[NamingIssue]:
    name_bytes = len(album_name.encode("utf-8"))
    return (
        [
            NamingIssue(
                NamingIssueCode.NAME_TOO_LONG,
                f"name is {name_bytes} bytes (max {MAX_NAME_BYTES})",
            )
        ]
        if name_bytes > MAX_NAME_BYTES
        else []
    )


def _unparseable_issue(album_name: str) -> NamingIssue:
    """Explain why a name failed to parse, recognizing legacy date formats."""
    return (
        NamingIssue(
            NamingIssueCode.INVALID_DATE_FORMAT,
            "legacy date format; use YYYY, YYYY-MM, YYYY-MM-DD, "
            "or ranges with -- (e.g. YYYY-MM-DD--YYYY-MM-DD)",
        )
        if _LEGACY_DATE_RE.match(album_name)
        else NamingIssue(
            NamingIssueCode.UNPARSEABLE, "name does not match expected format"
        )
    )


def _tag_issue(tag: str) -> NamingIssue | None:
    if not _KEBAB_SLUG_RE.match(tag):
        return NamingIssue(
            NamingIssueCode.INVALID_TAG_FORMAT,
            f'tag "{tag}" is not a valid kebab-case slug',
        )
    elif tag not in VALID_TAGS:
        allowed = ", ".join(sorted(VALID_TAGS))
        return NamingIssue(
            NamingIssueCode.INVALID_TAG,
            f'tag "{tag}" is not allowed (allowed: {allowed})',
        )
    else:
        return None


def _date_issues(parsed: ParsedAlbumName) -> list[NamingIssue]:
    """Calendar validity of the date, and part numbers on non-day dates."""
    return [
        *(
            [
                NamingIssue(
                    NamingIssueCode.INVALID_DATE,
                    f'date "{parsed.date}" is not a valid calendar date '
                    "or its range ends before it starts",
                )
            ]
            if _album_date_range(parsed.date) is None
            else []
        ),
        *(
            [
                NamingIssue(
                    NamingIssueCode.PART_REQUIRES_DAY_DATE,
                    "part number is only allowed for single-day dates "
                    f'(YYYY-MM-DD), got date "{parsed.date}"',
                )
            ]
            if parsed.part is not None and not _is_day_precision(parsed.date)
            else []
        ),
    ]


def _spacing_issues(album_name: str, parsed: ParsedAlbumName) -> list[NamingIssue]:
    """Canonical spacing: parse → reconstruct must be the identity."""
    canonical = reconstruct_name(parsed)
    return (
        [
            NamingIssue(
                NamingIssueCode.NON_CANONICAL_SPACING,
                f'name is not in canonical form (expected "{canonical}")',
            )
        ]
        if album_name != canonical
        else []
    )


def check_album_naming(album_name: str) -> tuple[NamingIssue, ...]:
    """Validate a single album name against naming conventions.

    This only inspects the name string — no filesystem access needed.
    Suitable as a pre-import check.
    """
    parsed = parse_album_name(album_name)
    if parsed is None:
        return (*_length_issues(album_name), _unparseable_issue(album_name))
    _, tags = _split_tags(album_name)
    return (
        *_length_issues(album_name),
        *(issue for tag in tags if (issue := _tag_issue(tag)) is not None),
        *_date_issues(parsed),
        *_spacing_issues(album_name, parsed),
    )


# ---------------------------------------------------------------------------
# EXIF date match
# ---------------------------------------------------------------------------


def _date_bounds(date_str: str) -> tuple[date, date] | None:
    """Return the first and last day covered by a single date string.

    ``YYYY`` → Jan 1..Dec 31, ``YYYY-MM`` → 1st..last day of month,
    ``YYYY-MM-DD`` → that day. ``None`` when it is not a real calendar date.
    """
    try:
        match [int(p) for p in date_str.split("-")]:
            case [year]:
                return date(year, 1, 1), date(year, 12, 31)
            case [year, month]:
                last_day = calendar.monthrange(year, month)[1]
                return date(year, month, 1), date(year, month, last_day)
            case [year, month, day]:
                return date(year, month, day), date(year, month, day)
            case _:
                return None
    except ValueError:
        # Non-numeric segment, or a month/day out of range (2024-13, 2024-02-30)
        return None


def _album_date_range(album_date: str) -> tuple[date, date] | None:
    """Extract the date range from an album date string.

    Handles all precisions (``YYYY``, ``YYYY-MM``, ``YYYY-MM-DD``) and
    ranges of mixed precision.  Returns ``(start, end)`` inclusive, or
    ``None`` if unparseable, not a real calendar date, or a range that ends
    before it starts.
    """
    start_str, _, end_str = album_date.partition("--")
    start_bounds = _date_bounds(start_str)
    end_bounds = _date_bounds(end_str) if end_str else start_bounds
    if start_bounds is None or end_bounds is None:
        return None
    start, end = start_bounds[0], end_bounds[1]
    return (start, end) if start <= end else None


def is_valid_album_date(album_date: str) -> bool:
    """Whether *album_date* denotes a real date range.

    Names can match the grammar yet not be real dates (``2024-02-30``, a range
    ending before it starts); :func:`_timestamp_in_album_range` raises on those.
    """
    return _album_date_range(album_date) is not None


def _timestamp_in_album_range(
    timestamp: datetime,
    album_date: str,
) -> bool:
    """Check if a timestamp falls within the album's date range.

    All cases use exclusive end:
    - Single day (``YYYY-MM-DD``): ``[album_date, album_date + 2 days)``
      — allows album date and the next day (timezone / midnight tolerance).
    - Range (``--``): ``[start, end + 1 day)``
    - Lower precision (``YYYY``, ``YYYY-MM``): ``[start, end + 1 day)``

    Raises :class:`InvalidAlbumDateError` when *album_date* is not a real date
    range: there is nothing to compare against, and answering ``True`` would
    silently pass every file.
    """
    date_range = _album_date_range(album_date)
    if date_range is None:
        raise InvalidAlbumDateError(album_date)

    start, end = date_range
    # Single day: allow album date + next day (timezone / midnight tolerance).
    # Ranges and lower precisions: strict [start, end + 1).
    tolerance_days = 2 if _is_day_precision(album_date) else 1
    return start <= timestamp.date() < end + timedelta(days=tolerance_days)


def _timestamp_matches_album_date_exactly(
    timestamp: datetime,
    album_date: str,
) -> bool:
    """Check if a timestamp's date matches the album date exactly (day precision only).

    Callers validate *album_date* first (see :func:`check_exif_date_match`).
    """
    return not _is_day_precision(album_date) or (
        timestamp.date() == date.fromisoformat(album_date)
    )


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
    from ..common.fs import file_ext
    from .store.protocol import VID_EXTENSIONS

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
        _is_day_precision(album_date)
        and not is_continuation
        and not any(
            _timestamp_matches_album_date_exactly(ts, album_date)
            for _, ts in file_timestamps
        )
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
        if not _timestamp_in_album_range(ts, album_date)
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
    if _album_date_range(album_date) is None:
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


# ---------------------------------------------------------------------------
# Batch checks
# ---------------------------------------------------------------------------


def check_batch_date_collisions(
    albums: list[tuple[str, ParsedAlbumName]],
) -> BatchNamingResult:
    """Check for date collisions across non-private albums.

    Flags groups of albums on the same single-day date whose part numbers
    do not disambiguate them: either some album lacks a part, or two
    albums share the same part value.

    *albums* is a list of ``(album_name, parsed)`` tuples.
    """
    from collections import defaultdict

    # Date ranges are excluded: parts are not valid for ranges, so
    # collisions cannot be resolved by adding a part number.
    by_date: defaultdict[str, list[ParsedAlbumName]] = defaultdict(list)
    names_by_date: defaultdict[str, list[str]] = defaultdict(list)
    for name, parsed in albums:
        if not parsed.private and _is_day_precision(parsed.date):
            by_date[parsed.date].append(parsed)
            names_by_date[parsed.date].append(name)

    collisions = tuple(
        (album_date, tuple(names_by_date[album_date]))
        for album_date, parsed_list in sorted(by_date.items())
        if len(parsed_list) > 1
        and (
            any(p.part is None for p in parsed_list)
            or len({p.part for p in parsed_list}) != len(parsed_list)
        )
    )

    return BatchNamingResult(date_collisions=collisions)
