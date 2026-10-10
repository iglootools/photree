"""The date grammar shared by album and collection names.

A date *spec* is the ``DATE`` component of a name (see docs/domain.md, "Album
Naming")::

    YYYY | YYYY-MM | YYYY-MM-DD          single date, any precision
    <single>--<single>                  range, mixed precision allowed

Every spec denotes an inclusive ``(first day, last day)`` range: ``2024`` is
Jan 1..Dec 31, ``2024-07--2024-08-03`` is Jul 1..Aug 3. A spec can match the
grammar yet not be a real date (``2024-02-30``, ``2024-13``, a range ending
before it starts); :func:`date_range` returns ``None`` for those.

This module is pure: no filesystem access, no knowledge of albums or
collections beyond the grammar they share.
"""

from __future__ import annotations

import calendar
import re
from datetime import date, datetime, timedelta
from enum import StrEnum

# ---------------------------------------------------------------------------
# Grammar
# ---------------------------------------------------------------------------

_SINGLE_DATE = r"\d{4}(?:-\d{2}(?:-\d{2})?)?"

_DATE_SPEC = rf"{_SINGLE_DATE}(?:--{_SINGLE_DATE})?"

DATE_PREFIX_RE = re.compile(rf"^({_DATE_SPEC}) - ")
"""Matches the ``DATE - `` prefix of a name; group 1 is the date spec."""

# Single-day date: exactly YYYY-MM-DD (no range, no lower precision)
_DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# The year / month a name starts with, at any precision: "2024 - ...",
# "2024-06", "2024-06-15", "2024--2025".
_YEAR_PREFIX_RE = re.compile(r"^(\d{4})(?!\d)")
_MONTH_PREFIX_RE = re.compile(r"^(\d{4}-\d{2})(?!\d)")

DateRange = tuple[date, date]
"""An inclusive ``(first day, last day)`` range."""


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class InvalidDateError(ValueError):
    """A date spec matches the grammar but is not a real date range.

    E.g. ``2024-02-30`` or ``2024-13``, or a range ending before it starts.
    """

    def __init__(self, spec: str) -> None:
        self.spec = spec
        super().__init__(f"date {spec!r} is not a valid date range")


class DatePrefixKind(StrEnum):
    """Which date prefix a name was expected to start with."""

    YEAR = "year"
    """``YYYY`` (any date precision)."""
    MONTH = "month"
    """``YYYY-MM`` (month or day precision, or a range starting with one)."""


class DatePrefixError(ValueError):
    """A name lacks the date prefix needed to place it by year/month.

    Only album placement (gallery import, export layouts) places names by
    their date prefix, so the message speaks of an album name.
    """

    def __init__(self, name: str, kind: DatePrefixKind) -> None:
        expected = "YYYY" if kind is DatePrefixKind.YEAR else "YYYY-MM"
        super().__init__(
            f'album name "{name}" does not start with a {expected} date;'
            ' expected "DATE - <Title>" (e.g. "2024-06-15 - Summer Vacation")'
        )
        self.name = name
        self.kind = kind


# ---------------------------------------------------------------------------
# Specs and ranges
# ---------------------------------------------------------------------------


def is_day_precision(spec: str) -> bool:
    """Whether *spec* is a single day (``YYYY-MM-DD``), not a range or coarser."""
    return _DAY_RE.match(spec) is not None


def _single_date_bounds(single: str) -> DateRange | None:
    """First and last day covered by a single (non-range) date.

    ``None`` when it is not a real calendar date.
    """
    try:
        match [int(p) for p in single.split("-")]:
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


def date_range(spec: str) -> DateRange | None:
    """The inclusive ``(start, end)`` range denoted by *spec*.

    Handles all precisions and ranges of mixed precision. ``None`` if
    unparseable, not a real calendar date, or a range that ends before it
    starts.
    """
    start_str, _, end_str = spec.partition("--")
    start_bounds = _single_date_bounds(start_str)
    end_bounds = _single_date_bounds(end_str) if end_str else start_bounds
    if start_bounds is None or end_bounds is None:
        return None
    start, end = start_bounds[0], end_bounds[1]
    return (start, end) if start <= end else None


def is_valid_date(spec: str) -> bool:
    """Whether *spec* denotes a real date range (see :func:`date_range`)."""
    return date_range(spec) is not None


def range_contains(outer: DateRange, inner: DateRange) -> bool:
    """Whether *inner* lies entirely within *outer* (mere overlap is not enough)."""
    return inner[0] >= outer[0] and inner[1] <= outer[1]


def ranges_overlap(a: DateRange, b: DateRange) -> bool:
    """Whether two ranges share at least one day.

    Ranges are inclusive of both ends, so sharing a single boundary day
    (``2019-06-30`` in both) is an overlap.
    """
    return a[0] <= b[1] and b[0] <= a[1]


# ---------------------------------------------------------------------------
# Timestamps
# ---------------------------------------------------------------------------


def timestamp_in_range(timestamp: datetime, spec: str) -> bool:
    """Whether *timestamp* falls within the range denoted by *spec*.

    All cases use an exclusive end:

    - Single day (``YYYY-MM-DD``): ``[day, day + 2 days)`` — allows the day
      and the next one (timezone / midnight tolerance).
    - Range (``--``): ``[start, end + 1 day)``
    - Lower precision (``YYYY``, ``YYYY-MM``): ``[start, end + 1 day)``

    Raises :class:`InvalidDateError` when *spec* is not a real date range:
    there is nothing to compare against, and answering ``True`` would
    silently pass every timestamp.
    """
    rng = date_range(spec)
    if rng is None:
        raise InvalidDateError(spec)

    start, end = rng
    tolerance_days = 2 if is_day_precision(spec) else 1
    return start <= timestamp.date() < end + timedelta(days=tolerance_days)


def timestamp_on_day(timestamp: datetime, spec: str) -> bool:
    """Whether *timestamp* falls exactly on the day *spec* denotes.

    Always ``True`` for specs that are not day precision (there is no single
    day to match). Callers validate *spec* first.
    """
    return not is_day_precision(spec) or (timestamp.date() == date.fromisoformat(spec))


# ---------------------------------------------------------------------------
# Name prefixes
# ---------------------------------------------------------------------------


def parse_year_prefix(name: str) -> str:
    """Extract the ``YYYY`` year a name starts with.

    Any date precision works (``2024``, ``2024-06``, ``2024-06-15``, ranges):
    the year is the start year. Raises :class:`DatePrefixError` when the name
    does not start with a year.
    """
    m = _YEAR_PREFIX_RE.match(name)
    if m is None:
        raise DatePrefixError(name, DatePrefixKind.YEAR)
    else:
        return m.group(1)


def parse_month_prefix(name: str) -> str:
    """Extract the ``YYYY-MM`` month a name starts with.

    For date ranges (``YYYY-MM-DD--YYYY-MM-DD``), the start month is returned
    (the prefix is matched). Raises :class:`DatePrefixError` when the name
    does not start with at least a ``YYYY-MM`` date.
    """
    m = _MONTH_PREFIX_RE.match(name)
    if m is None:
        raise DatePrefixError(name, DatePrefixKind.MONTH)
    else:
        return m.group(1)
