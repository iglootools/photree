"""Collection naming convention parsing and validation.

Target format::

    [DATE - ] Title [@ Location] [tags]

Where:
- DATE is optional: ``YYYY``, ``YYYY-MM``, ``YYYY-MM-DD``, or a range with ``--``
- Title is required free text (must not contain `` - ``)
- Location is optional, preceded by `` @ ``
- Tags are ``[tag]`` at the end; only ``[private]`` is currently allowed

This module performs **no** filesystem mutations.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..dates import DATE_PREFIX_RE, parse_year_prefix

# ---------------------------------------------------------------------------
# Regexes
# ---------------------------------------------------------------------------

# Matches "[tag1, tag2]" at the end of a name (same as album naming)
_TAGS_RE = re.compile(r"\s*\[([^\]]+)\]\s*$")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParsedCollectionName:
    """Parsed collection name components."""

    date: str | None
    title: str
    location: str | None = None
    private: bool = False


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def parse_collection_name(name: str) -> ParsedCollectionName:
    """Parse a collection folder name into components.

    Unlike album names, the date prefix is optional. A name without a
    recognized date prefix is treated as a dateless collection.
    """
    # Step 1: extract tags from end
    remaining = name
    private = False
    tags_match = _TAGS_RE.search(remaining)
    if tags_match is not None:
        raw_tags = [t.strip() for t in tags_match.group(1).split(",")]
        private = "private" in raw_tags
        remaining = remaining[: tags_match.start()]

    # Step 2: extract date prefix (optional)
    dm = DATE_PREFIX_RE.match(remaining)
    if dm is not None:
        collection_date: str | None = dm.group(1)
        body = remaining[dm.end() :].strip()
    else:
        collection_date = None
        body = remaining

    # Step 3: extract location from " @ " separator
    location: str | None = None
    if " @ " in body:
        title, location = body.split(" @ ", 1)
        title = title.strip()
        location = location.strip()
    else:
        title = body

    return ParsedCollectionName(
        date=collection_date,
        title=title,
        location=location,
        private=private,
    )


def reconstruct_collection_name(parsed: ParsedCollectionName) -> str:
    """Build the canonical collection name from parsed components."""
    title_with_location = (
        f"{parsed.title} @ {parsed.location}"
        if parsed.location is not None
        else parsed.title
    )
    parts = [
        *([parsed.date] if parsed.date is not None else []),
        title_with_location,
    ]
    name = " - ".join(parts)
    return f"{name} [private]" if parsed.private else name


def parse_collection_year(name: str) -> str | None:
    """Extract the start year from a collection name, or ``None`` for dateless.

    Used for placing collections in ``collections/YYYY/`` directories.
    """
    parsed = parse_collection_name(name)
    # A parsed date always matches the date grammar, so it starts with a year.
    return parse_year_prefix(parsed.date) if parsed.date is not None else None
