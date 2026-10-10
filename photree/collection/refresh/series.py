"""Group albums into contiguous series runs, one implicit collection each."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from ...dates import date_range
from ..naming import (
    parse_collection_name,
    reconstruct_collection_name,
)
from .scan import AlbumInfo


def _compute_date_string(dates: list[str]) -> str:
    """Compute a date string that covers all given album dates.

    Same date → that date. Different dates → min-max range.
    """
    ranges = [rng for d in dates for rng in [date_range(d)] if rng is not None]
    match dates, ranges:
        case [], _:
            return ""
        case [single], _:
            return single
        case [first, *_], []:
            return first
        case _:
            min_start = min(s for s, _ in ranges)
            max_end = max(e for _, e in ranges)
            return str(min_start) if min_start == max_end else f"{min_start}--{max_end}"


def _build_collection_name(series_title: str, album_dates: list[str]) -> str:
    """Build the canonical collection name for a series."""
    date_str = _compute_date_string(album_dates)
    raw_name = f"{date_str} - {series_title}" if date_str else series_title
    return reconstruct_collection_name(parse_collection_name(raw_name))


@dataclass(frozen=True)
class _SeriesGroup:
    """A contiguous run of albums sharing the same series."""

    series_title: str
    albums: tuple[AlbumInfo, ...]


def _group_contiguous_series(albums: Iterable[AlbumInfo]) -> list[_SeriesGroup]:
    """Group albums into contiguous runs of the same series.

    Albums are sorted by name (chronological, since names start with dates).
    A series interrupted by albums without that series (or with a different
    series) produces separate groups. The same series title appearing in
    non-contiguous positions results in multiple groups.
    """
    sorted_albums = sorted(albums, key=lambda a: a.path.name)

    groups: list[_SeriesGroup] = []
    current_series: str | None = None
    current_run: list[AlbumInfo] = []

    for album in sorted_albums:
        if album.parsed.series is not None and album.parsed.series == current_series:
            # Continue the current run
            current_run.append(album)
        else:
            # Flush previous run
            if current_series is not None and current_run:
                groups.append(
                    _SeriesGroup(series_title=current_series, albums=tuple(current_run))
                )
            # Start new run (or reset if no series)
            if album.parsed.series is not None:
                current_series = album.parsed.series
                current_run = [album]
            else:
                current_series = None
                current_run = []

    # Flush final run
    if current_series is not None and current_run:
        groups.append(
            _SeriesGroup(series_title=current_series, albums=tuple(current_run))
        )

    return groups


@dataclass(frozen=True)
class SeriesTarget:
    """What one series group's implicit collection should look like."""

    series_title: str
    collection_name: str
    album_ids: tuple[str, ...]


def series_targets(albums: tuple[AlbumInfo, ...]) -> list[SeriesTarget]:
    """One target per contiguous series run; private albums never join one."""
    return [
        SeriesTarget(
            series_title=group.series_title,
            collection_name=_build_collection_name(
                group.series_title, [a.parsed.date for a in public]
            ),
            album_ids=tuple(sorted(a.album_id for a in public)),
        )
        for group in _group_contiguous_series(albums)
        for public in [[a for a in group.albums if not a.parsed.private]]
        if public
    ]
