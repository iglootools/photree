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

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from ..fsprotocol import ALBUM_DATE_RE
from exiftool import ExifToolHelper  # type: ignore[import-untyped]

from .exif import discover_media_files, read_exif_timestamps_by_file

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


@dataclass(frozen=True)
class NamingIssue:
    """A single naming convention violation."""

    code: str
    message: str


@dataclass(frozen=True)
class ExifMismatch:
    """A single file whose EXIF timestamp falls outside the album date range."""

    file_name: str
    timestamp: str


@dataclass(frozen=True)
class ExifTimestampCheck:
    """Result of validating EXIF timestamps against album date."""

    album_date: str
    total_files: int
    mismatches: tuple[ExifMismatch, ...]

    @property
    def matches(self) -> bool:
        return not self.mismatches


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


def parse_album_name(name: str) -> ParsedAlbumName | None:
    """Parse an album folder name into components.

    Returns ``None`` if the name does not start with a valid date prefix.
    """
    # Step 1: extract tags from end
    remaining = name
    private = False
    tags_match = _TAGS_RE.search(remaining)
    if tags_match is not None:
        raw_tags = [t.strip() for t in tags_match.group(1).split(",")]
        private = "private" in raw_tags
        remaining = remaining[: tags_match.start()]

    # Step 2: extract date prefix
    dm = ALBUM_DATE_RE.match(remaining)
    if dm is None:
        return None
    album_date = dm.group(1)
    remainder = remaining[dm.end() :]

    # Step 3: detect prefix-style part number (XX - ...)
    part = None
    m = _PREFIX_PART_RE.match(remainder)
    if m is not None:
        part = m.group(1)
        body = m.group(2)
    else:
        body = remainder

    # Step 4: split body on " - " to identify series vs title
    segments = [s.strip() for s in body.split(" - ") if s.strip()]

    series = None
    if len(segments) >= 2:
        series = segments[0]
        rest_segments = segments[1:]

        # Check if first rest segment is a part number (Series - XX - Title)
        if (
            part is None
            and len(rest_segments) >= 2
            and re.match(r"^\d{2}$", rest_segments[0])
        ):
            part = rest_segments[0]
            rest_segments = rest_segments[1:]

        raw_title = " ".join(rest_segments)
    else:
        raw_title = segments[0] if segments else ""

    # Step 5: extract location from " @ " separator
    location = None
    if " @ " in raw_title:
        title, location = raw_title.split(" @ ", 1)
        title = title.strip()
        location = location.strip()
    else:
        title = raw_title

    return ParsedAlbumName(
        date=album_date,
        part=part,
        private=private,
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


def check_album_naming(album_name: str) -> tuple[NamingIssue, ...]:
    """Validate a single album name against naming conventions.

    This only inspects the name string — no filesystem access needed.
    Suitable as a pre-import check.
    """
    issues: list[NamingIssue] = []

    # Check byte length (UTF-8) for filesystem compatibility
    name_bytes = len(album_name.encode("utf-8"))
    if name_bytes > MAX_NAME_BYTES:
        issues.append(
            NamingIssue(
                "name-too-long",
                f"name is {name_bytes} bytes (max {MAX_NAME_BYTES})",
            )
        )

    # Check if name can be parsed at all
    parsed = parse_album_name(album_name)
    if parsed is None:
        # Try to determine if it's a legacy date format
        # These are date-like prefixes that don't match the accepted forms
        # (day ranges, enumerated days, old-style dash-separated ranges)
        legacy_date_re = re.compile(
            r"^("
            r"\d{4}-\d{2}-\d{2}-\d{4}-\d{2}-\d{2}"  # YYYY-MM-DD-YYYY-MM-DD (old range)
            r"|\d{4}-\d{2}-\d{2}-\d{2}-\d{2}"  # YYYY-MM-DD-MM-DD
            r"|\d{4}-\d{2}-\d{2}-\d{2}"  # YYYY-MM-DD-DD
            r"|\d{4}-\d{2}-\d{2}(?:,\d{2})+"  # YYYY-MM-DD,DD (enumerated)
            r") *- *"
        )
        if legacy_date_re.match(album_name):
            issues.append(
                NamingIssue(
                    "invalid-date-format",
                    "legacy date format; use YYYY, YYYY-MM, YYYY-MM-DD, "
                    "or ranges with -- (e.g. YYYY-MM-DD--YYYY-MM-DD)",
                )
            )
        else:
            issues.append(
                NamingIssue("unparseable", "name does not match expected format")
            )
        return tuple(issues)

    # Validate tags
    tags_match = _TAGS_RE.search(album_name)
    if tags_match is not None:
        raw_tags = [t.strip() for t in tags_match.group(1).split(",")]
        for tag in raw_tags:
            if not _KEBAB_SLUG_RE.match(tag):
                issues.append(
                    NamingIssue(
                        "invalid-tag-format",
                        f'tag "{tag}" is not a valid kebab-case slug',
                    )
                )
            elif tag not in VALID_TAGS:
                issues.append(
                    NamingIssue(
                        "invalid-tag",
                        f'tag "{tag}" is not allowed (allowed: {", ".join(sorted(VALID_TAGS))})',
                    )
                )

    # Part numbers are only valid for single-day dates (YYYY-MM-DD)
    if parsed.part is not None and not _is_day_precision(parsed.date):
        issues.append(
            NamingIssue(
                "part-requires-day-date",
                f"part number is only allowed for single-day dates (YYYY-MM-DD)"
                f', got date "{parsed.date}"',
            )
        )

    # Check canonical spacing: parse → reconstruct should be identity
    canonical = reconstruct_name(parsed)
    if album_name != canonical:
        issues.append(
            NamingIssue(
                "non-canonical-spacing",
                f'name is not in canonical form (expected "{canonical}")',
            )
        )

    return tuple(issues)


# ---------------------------------------------------------------------------
# EXIF date match
# ---------------------------------------------------------------------------


def _date_start(date_str: str) -> date | None:
    """Return the first day covered by a date string.

    ``YYYY`` → Jan 1, ``YYYY-MM`` → 1st of month, ``YYYY-MM-DD`` → that day.
    """
    parts = date_str.split("-")
    match len(parts):
        case 1:
            try:
                return date(int(parts[0]), 1, 1)
            except ValueError:
                return None
        case 2:
            try:
                return date(int(parts[0]), int(parts[1]), 1)
            except ValueError:
                return None
        case 3:
            try:
                return date.fromisoformat(date_str)
            except ValueError:
                return None
        case _:
            return None


def _date_end(date_str: str) -> date | None:
    """Return the last day covered by a date string.

    ``YYYY`` → Dec 31, ``YYYY-MM`` → last day of month, ``YYYY-MM-DD`` → that day.
    """
    import calendar

    parts = date_str.split("-")
    match len(parts):
        case 1:
            try:
                return date(int(parts[0]), 12, 31)
            except ValueError:
                return None
        case 2:
            try:
                year, month = int(parts[0]), int(parts[1])
                last_day = calendar.monthrange(year, month)[1]
                return date(year, month, last_day)
            except ValueError:
                return None
        case 3:
            try:
                return date.fromisoformat(date_str)
            except ValueError:
                return None
        case _:
            return None


def _album_date_range(album_date: str) -> tuple[date, date] | None:
    """Extract the date range from an album date string.

    Handles all precisions (``YYYY``, ``YYYY-MM``, ``YYYY-MM-DD``) and
    ranges of mixed precision.  Returns ``(start, end)`` inclusive, or
    ``None`` if unparseable.
    """
    if "--" in album_date:
        parts = album_date.split("--")
        start = _date_start(parts[0])
        end = _date_end(parts[1])
        if start is not None and end is not None:
            return (start, end)
        return None
    else:
        start = _date_start(album_date)
        end = _date_end(album_date)
        if start is not None and end is not None:
            return (start, end)
        return None


def _timestamp_matches_album_date(
    timestamp: datetime,
    album_date: str,
    *,
    tolerance_days: int = 1,
) -> bool:
    """Check if a timestamp falls within tolerance of the album date(s)."""
    date_range = _album_date_range(album_date)
    if date_range is None:
        return True  # can't validate, assume ok

    start, end = date_range
    ts_date = timestamp.date()
    tolerance = timedelta(days=tolerance_days)
    return (start - tolerance) <= ts_date <= (end + tolerance)


def check_exif_date_match(
    album_dir: Path,
    album_date: str,
    *,
    exiftool: ExifToolHelper | None = None,
    tolerance_days: int = 1,
) -> ExifTimestampCheck | None:
    """Check EXIF timestamps of all media files against the album date.

    Returns ``None`` if no media files found or no timestamps could be read.
    When *exiftool* is provided, the persistent process is reused.
    """
    files = discover_media_files(album_dir)
    if not files:
        return None

    timestamps = read_exif_timestamps(files, exiftool=exiftool)
    if not timestamps:
        return None

    matches = all(
        _timestamp_matches_album_date(ts, album_date, tolerance_days=tolerance_days)
        for ts in timestamps
    )

    return ExifTimestampCheck(
        album_date=album_date,
        sampled_files=tuple(f.name for f in files),
        timestamps=tuple(ts.isoformat() for ts in timestamps),
        matches=matches,
    )


# ---------------------------------------------------------------------------
# Batch checks
# ---------------------------------------------------------------------------


def check_batch_date_collisions(
    albums: list[tuple[str, ParsedAlbumName]],
) -> BatchNamingResult:
    """Check for date collisions across non-private albums without part numbers.

    *albums* is a list of ``(album_name, parsed)`` tuples.
    """
    from collections import defaultdict

    by_date: defaultdict[str, list[str]] = defaultdict(list)
    for name, parsed in albums:
        if not parsed.private:
            by_date[parsed.date].append(name)

    collisions = tuple(
        (album_date, tuple(names))
        for album_date, names in sorted(by_date.items())
        if len(names) > 1
        and any(
            parsed.part is None
            for name, parsed in albums
            if not parsed.private and parsed.date == album_date
        )
    )

    return BatchNamingResult(date_collisions=collisions)
