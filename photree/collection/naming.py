"""Collection naming convention parsing and validation.

Target format::

    [DATE - ] Title

Where:
- DATE is optional: ``YYYY``, ``YYYY-MM``, ``YYYY-MM-DD``, or a range with ``--``
- Title is required free text (must not contain `` - ``)

This module performs **no** filesystem mutations.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..album.store.protocol import ALBUM_DATE_RE


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParsedCollectionName:
    """Parsed collection name components."""

    date: str | None
    title: str


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

# Year extraction from the date component (start year for ranges)
_YEAR_RE = re.compile(r"^(\d{4})")


def parse_collection_name(name: str) -> ParsedCollectionName:
    """Parse a collection folder name into components.

    Unlike album names, the date prefix is optional. A name without a
    recognized date prefix is treated as a dateless collection.
    """
    dm = ALBUM_DATE_RE.match(name)
    if dm is not None:
        collection_date = dm.group(1)
        title = name[dm.end() :].strip()
        return ParsedCollectionName(date=collection_date, title=title)
    else:
        return ParsedCollectionName(date=None, title=name)


def reconstruct_collection_name(parsed: ParsedCollectionName) -> str:
    """Build the canonical collection name from parsed components."""
    if parsed.date is not None:
        return f"{parsed.date} - {parsed.title}"
    return parsed.title


def parse_collection_year(name: str) -> str | None:
    """Extract the start year from a collection name, or ``None`` for dateless.

    Used for placing collections in ``collections/YYYY/`` directories.
    """
    parsed = parse_collection_name(name)
    if parsed.date is None:
        return None
    m = _YEAR_RE.match(parsed.date)
    return m.group(1) if m else None
