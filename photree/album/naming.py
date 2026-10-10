"""Album naming convention parsing and validation.

Target format::

    DATE - [PART - ] [Series - ] Title [tags]

Where:
- DATE is a date spec (``YYYY``, ``YYYY-MM``, ``YYYY-MM-DD``, or a ``--``
  range of mixed precision); its grammar lives in :mod:`photree.dates`
- PART is a zero-padded two-digit number (``01``, ``02``, …)
- Tags are ``[tag]`` at the end; only ``[private]`` is currently allowed
- Parenthesised content (e.g. ``(Day 2)``, ``(bis)``) is ordinary title text

This module only inspects name strings: no filesystem access. EXIF date
matching lives in :mod:`.exif_date_check`.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum

from ..dates import DATE_PREFIX_RE, is_day_precision, is_valid_date

# ---------------------------------------------------------------------------
# Regexes
# ---------------------------------------------------------------------------

# Matches "[tag1, tag2]" at the end of a name
_TAGS_RE = re.compile(r"\s*\[([^\]]+)\]\s*$")

# Prefix-style part number: "XX - rest"
_PREFIX_PART_RE = re.compile(r"^(\d{2}) - (.+)$")

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
    dm = DATE_PREFIX_RE.match(without_tags)
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
            if not is_valid_date(parsed.date)
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
            if parsed.part is not None and not is_day_precision(parsed.date)
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
    # Date ranges are excluded: parts are not valid for ranges, so
    # collisions cannot be resolved by adding a part number.
    by_date: defaultdict[str, list[ParsedAlbumName]] = defaultdict(list)
    names_by_date: defaultdict[str, list[str]] = defaultdict(list)
    for name, parsed in albums:
        if not parsed.private and is_day_precision(parsed.date):
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
